"""Builders for the DRI macronutrient and EER equation data files.

Scrapes the two Health Canada DRI pages and produces JSON payloads that match
the bundled snapshots in ``src/foodguide/data/`` (plus a top-level
``_provenance`` object):

- ``dri_macronutrients.json`` from the reference-values-for-macronutrients page
- ``eer_equations.json`` from the equations-to-estimate-energy-requirement page

The HTTP rules match ``foodguide.recipes.fetch``: canada.ca stalls generic
Mozilla/5.0 user agents, so requests use the build-tool user agent, an
``Accept: */*`` header, a 30 second timeout, and 4 attempts with exponential
backoff on network errors and 5xx responses.

Development/testing override: set ``FOODGUIDE_SOURCE_BASE_URL`` to fetch both
pages from another base (e.g. a local http.server fixture serving copies of
the Health Canada pages). It is read at call time, never at import time; the
``DRI_URL``/``EER_URL`` constants remain the canonical live URLs and the
default behaviour is unchanged when the variable is unset.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import requests
from bs4 import BeautifulSoup

from foodguide.api.dri import MacronutrientScraper
from foodguide.config import DEFAULT_SOURCE_BASE_URL, source_base_url

USER_AGENT = "foodguide-data-build/0.1 (+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada)"
DRI_PATH = (
    "/en/health-canada/services/food-nutrition/healthy-eating/"
    "dietary-reference-intakes/tables/reference-values-macronutrients.html"
)
EER_PATH = (
    "/en/health-canada/services/food-nutrition/healthy-eating/"
    "dietary-reference-intakes/tables/equations-estimate-energy-requirement.html"
)
# Canonical live defaults; the fetch functions below apply source_base_url()
# (FOODGUIDE_SOURCE_BASE_URL, read at call time) on top of these paths.
DRI_URL = DEFAULT_SOURCE_BASE_URL + DRI_PATH
EER_URL = DEFAULT_SOURCE_BASE_URL + EER_PATH


def dri_url() -> str:
    """DRI macronutrients page URL, honouring FOODGUIDE_SOURCE_BASE_URL at call time."""
    return source_base_url() + DRI_PATH


def eer_url() -> str:
    """EER equations page URL, honouring FOODGUIDE_SOURCE_BASE_URL at call time."""
    return source_base_url() + EER_PATH

_REQUEST_TIMEOUT = 30
_MAX_ATTEMPTS = 4
_RETRY_BACKOFF_SECONDS = (1, 2, 4, 8)

_PAL_KEYS = ("inactive", "low_active", "active", "very_active")

# Curated wording carried over from the bundled snapshot. These strings are
# editorial (not verbatim page text), so the builders reproduce them exactly.
_GENERAL_NOTE = (
    "These equations provide an estimate of energy requirement (EER). Relative body weight "
    "(that is, loss, stable, gain) is the preferred indicator of energy adequacy."
)
_PAL_DEFINITIONS_DESCRIPTION = "Physical Activity Level (PAL) category ranges by age group"
_ADULT_ACTIVITY_EXAMPLES = {
    "inactive": "30 min walking + 90 min light to moderate activity",
    "low_active": "60 to 80 min of walking at 5-7 km/h",
    "active": "30-50 min walking + 45 min moderate cycling + 40 min doubles tennis",
    "very_active": "45 min moderate cycling + 25 min jogging at 10 km/h + 60 min doubles tennis",
}
_PAL_DESCRIPTIONS = {
    "inactive": {
        "description": "Sedentary lifestyle",
        "examples": [
            "Typical daily living activities only",
            "Sitting most of the day",
            "Little to no structured exercise",
        ],
    },
    "low_active": {
        "description": "Low active lifestyle",
        "examples": [
            "Daily living activities plus 30-60 minutes of moderate activity",
            "Walking 2.5-5 km per day",
            "Light exercise 3-4 times per week",
        ],
    },
    "active": {
        "description": "Active lifestyle",
        "examples": [
            "Daily living activities plus 60+ minutes of moderate activity",
            "Walking 7.5-10 km per day",
            "Regular structured exercise 4-5 times per week",
        ],
    },
    "very_active": {
        "description": "Very active lifestyle",
        "examples": [
            "Daily living activities plus 60+ minutes of moderate to vigorous activity",
            "Walking 12.5+ km per day",
            "Intensive training or physical work",
        ],
    },
}
_SECTION_META = {
    "infant_toddler": {
        "description": "Infants and toddlers 0-3 years. No activity level differentiation.",
        "age_range": "0 to <3 years",
    },
    "child_adolescent": {
        "description": (
            "Children and adolescents 3-18 years. Activity level dependent with "
            "age-specific growth constants."
        ),
        "age_range": "3 to <19 years",
    },
    "adult": {
        "description": "Adults 19 years and older. No growth constant.",
        "age_range": "19+ years",
    },
    "pregnancy": {
        "description": (
            "Pregnancy equations for 2nd and 3rd trimester. For 1st trimester, "
            "use non-pregnant female equations."
        ),
        "age_range": "All ages",
        "note": "Use non-pregnant female equations for first trimester",
    },
    "lactation": {
        "description": (
            "Breastfeeding equations. Uses non-pregnant female base equations plus "
            "milk energy constants."
        ),
        "age_range": "All ages",
        "note": "Base equation uses adolescent female coefficients for age <19, adult female "
                "coefficients for age 19+",
    },
}
_LACTATION_BASE_DESCRIPTIONS = {
    "age_under_19": "Uses adolescent female (3-18y) coefficients",
    "age_19_plus": "Uses adult female coefficients",
}
_MILK_BREAKDOWNS = {
    "0_to_6_months_postpartum": "540 (milk energy output) - 140 (weight loss allowance)",
    "7_to_12_months_postpartum": "380 (milk energy output, no weight loss allowance)",
}


class BuildError(Exception):
    """A Health Canada page is missing an expected table, equation or section."""


class Fetcher(Protocol):
    """Protocol: an object with a ``.fetch(url) -> str`` method (see recipes/builder.py)."""

    def fetch(self, url: str) -> str: ...


class HttpFetcher:
    """Default fetcher: build user agent, Accept: */*, 30s timeout, retry with backoff."""

    def fetch(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = requests.get(
                    url,
                    headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                    timeout=_REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                response.encoding = "utf-8"
                return response.text
            except requests.RequestException as error:
                last_error = error
                status = getattr(getattr(error, "response", None), "status_code", None)
                if status is not None and status < 500:
                    break  # client errors do not get better by retrying
                if attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(_RETRY_BACKOFF_SECONDS[attempt])
        raise BuildError(f"Failed to fetch {url} after {_MAX_ATTEMPTS} attempts: {last_error}")


def fetch_page(url: str) -> str:
    """Fetch a page with the default requests-based fetcher."""
    return HttpFetcher().fetch(url)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _page_date_modified(soup: BeautifulSoup) -> str | None:
    element = soup.find("gcds-date-modified")
    if element is None:
        return None
    text = element.get_text(strip=True)
    return text or None


def _page_content_sha256(soup: BeautifulSoup) -> str:
    """sha256 of the page content with script/style elements stripped.

    canada.ca injects an Akamai boomerang monitoring <script> with per-request
    IDs and timestamps, so hashing the raw bytes would change on every fetch.
    Stripping script/style makes the fingerprint stable for a given page
    version while still catching any real content change.
    """
    content = BeautifulSoup(str(soup), "html.parser")
    for element in content.find_all(["script", "style"]):
        element.decompose()
    return hashlib.sha256(str(content).encode("utf-8")).hexdigest()


def _provenance(url: str, html: str, soup: BeautifulSoup) -> dict[str, Any]:
    return {
        "source_url": url,
        "page_sha256": _page_content_sha256(soup),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "page_date_modified": _page_date_modified(soup),
    }


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes to a temp file in the same directory, then os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _dump_bytes(payload: dict[str, Any]) -> bytes:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def _write_payload(out_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    data = _dump_bytes(payload)
    _atomic_write(Path(out_path), data)
    provenance = payload["_provenance"]
    return {
        "path": str(out_path),
        "size_bytes": len(data),
        "page_sha256": provenance["page_sha256"],
        "page_date_modified": provenance["page_date_modified"],
        "fetched_at": provenance["fetched_at"],
    }


def _clean_text(text: str) -> str:
    """Normalize NBSP and all whitespace runs to single ASCII spaces."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


# ---------------------------------------------------------------------------
# DRI macronutrients
# ---------------------------------------------------------------------------


def parse_dri_page(html: str) -> dict[str, Any]:
    """Parse the DRI macronutrient page into the bundled DRI schema (timestamps = now)."""
    soup = BeautifulSoup(html, "html.parser")
    scraper = MacronutrientScraper()
    reference_values = scraper._parse_main_reference_table(soup)
    result = {
        "status": "success",
        "source": "Health Canada DRI Tables",
        "url": dri_url(),
        "last_updated": datetime.now().isoformat(),
        "reference_values": reference_values,
        "additional_recommendations": scraper._parse_additional_recommendations(soup),
        "amino_acid_patterns": scraper._parse_amino_acid_patterns(soup),
        "amdrs": scraper._parse_amdrs(soup),
        "footnotes": scraper._parse_footnotes(soup),
        "data_quality": {
            "parsing_timestamp": datetime.now().isoformat(),
            "total_age_groups_parsed": len(reference_values),
            "total_nutrients_parsed": sum(
                len(age_group.get("nutrients", {})) for age_group in reference_values
            ),
            "parsing_warnings": [],
        },
    }
    # data_quality matches the bundled snapshot's schema exactly (4 keys); the
    # scraper's richer validation metrics stay internal to fetch_macronutrient_data.
    return result


_DRI_CATEGORY_ORDER = [
    ("Infants", 2),
    ("Children", 2),
    ("Males", 6),
    ("Females", 6),
    ("Pregnancy", 3),
    ("Lactation", 3),
]


def _validate_dri(payload: dict[str, Any]) -> None:
    reference_values = payload.get("reference_values")
    if not reference_values:
        raise BuildError("DRI page: missing table 'reference_values'")
    if len(reference_values) != 22:
        raise BuildError(
            f"DRI page: table 'reference_values' has {len(reference_values)} rows, expected 22"
        )
    expected_categories: list[str] = []
    for category, count in _DRI_CATEGORY_ORDER:
        expected_categories.extend([category] * count)
    actual_categories = [row.get("category") for row in reference_values]
    if actual_categories != expected_categories:
        raise BuildError(
            "DRI page: table 'reference_values' categories do not match expected "
            f"{expected_categories}: got {actual_categories}"
        )
    for section in ("amino_acid_patterns", "amdrs", "footnotes"):
        if not payload.get(section):
            raise BuildError(f"DRI page: missing table '{section}'")
    # The bundled snapshot (and the live page) carries an empty
    # additional_recommendations dict; require the key but not contents.
    if "additional_recommendations" not in payload:
        raise BuildError("DRI page: missing table 'additional_recommendations'")
    for section in ("amino_acid_patterns", "amdrs", "footnotes", "additional_recommendations"):
        if "parsing_error" in payload.get(section, {}):
            raise BuildError(f"DRI page: table '{section}' failed to parse")


def build_dri(out_path: Path, fetcher: Fetcher | None = None) -> dict[str, Any]:
    """Fetch, parse, validate and atomically write the DRI macronutrient data file."""
    fetcher = fetcher if fetcher is not None else HttpFetcher()
    url = dri_url()
    html = fetcher.fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    payload = parse_dri_page(html)
    _validate_dri(payload)
    payload["_provenance"] = _provenance(url, html, soup)
    return _write_payload(out_path, payload)


# ---------------------------------------------------------------------------
# EER equations
# ---------------------------------------------------------------------------


def _normalize_equation_text(text: str) -> str:
    """Normalize an equation string: NBSP/whitespace, times sign, dashes, commas."""
    text = text.replace("\xa0", " ")
    text = text.replace("×", "*")
    for dash in ("–", "−", "—"):
        text = text.replace(dash, "-")
    text = text.replace(",", "")  # thousands separators
    return re.sub(r"\s+", " ", text).strip()


_VAR_KEYS = {
    "age": "age",
    "height": "height_cm",
    "weight": "weight_kg",
    "gestation": "gestation_weeks",
}

_TERM_RE = re.compile(
    r"(?P<sign>[+-])\s*"
    r"(?:\(\s*(?P<num>[\d.]+)\s*\*\s*(?P<var>age|height|weight|gestation)"
    r"(?:\s*\[[^\]]*\])?\s*\)"
    r"|(?P<const>[\d.]+)(?!\s*\*))"
)


class _Equation:
    """A parsed EER equation: intercept, signed variable terms and bare constants."""

    def __init__(self, intercept_str: str, terms: list[tuple[str, str, str]], constants: list[float],
                 coefficients: dict[str, float]) -> None:
        self.intercept_str = intercept_str
        self.terms = terms  # (sign, number token as written, variable key)
        self.constants = constants
        self.coefficients = coefficients


def _parse_equation(raw_text: str, label: str) -> _Equation:
    text = _normalize_equation_text(raw_text)
    match = re.match(r"EER\s*=\s*(-?[\d.]+)", text)
    if not match:
        raise BuildError(f"EER page: unparseable equation in {label}: {raw_text!r}")
    remainder = text[match.end():]
    terms: list[tuple[str, str, str]] = []
    constants: list[float] = []
    coefficients: dict[str, float] = {"intercept": float(match.group(1))}
    position = 0
    for token in _TERM_RE.finditer(remainder):
        between = remainder[position:token.start()]
        if between.strip():
            raise BuildError(f"EER page: unexpected text {between!r} in equation {label}")
        position = token.end()
        sign = token.group("sign")
        if token.group("var"):
            var_key = _VAR_KEYS[token.group("var")]
            if var_key in coefficients:
                raise BuildError(f"EER page: duplicate '{var_key}' term in equation {label}")
            value = float(token.group("num"))
            if sign == "-":
                value = -value
            coefficients[var_key] = value
            terms.append((sign, token.group("num"), var_key))
        else:
            value = float(token.group("const"))
            constants.append(-value if sign == "-" else value)
    if remainder[position:].strip():
        raise BuildError(f"EER page: unexpected text {remainder[position:]!r} in equation {label}")
    return _Equation(match.group(1), terms, constants, coefficients)


def _formula(equation: _Equation, style: str, suffix: str | None = None) -> str:
    """Render a formula string in the bundled style.

    style "outside": signs stay in front of the parentheses
        (e.g. " - (1.00 * age)"); style "inside": signs move inside
        (e.g. " + (-22.25 * age)").
    """
    parts = [f"EER = {equation.intercept_str}"]
    for sign, num, var_key in equation.terms:
        if style == "outside":
            parts.append(f" {'-' if sign == '-' else '+'} ({num} * {var_key})")
        else:
            signed = f"-{num}" if sign == "-" else num
            parts.append(f" + ({signed} * {var_key})")
    if suffix:
        parts.append(f" + {suffix}")
    return "".join(parts)


def _section_parts(soup: BeautifulSoup, section_id: str) -> list[Any]:
    heading = soup.find("h2", id=section_id)
    if heading is None:
        raise BuildError(f"EER page: missing section '{section_id}'")
    parts = []
    for sibling in heading.find_next_siblings():
        if sibling.name == "h2":
            break
        parts.append(sibling)
    return parts


def _section_details(soup: BeautifulSoup, section_id: str) -> list[Any]:
    details = [part for part in _section_parts(soup, section_id) if part.name == "details"]
    if not details:
        raise BuildError(f"EER page: section {section_id} has no equation details blocks")
    return details


def _details_equations(
    details, label: str, initial_sex: str | None = None
) -> list[tuple[str | None, str | None, str]]:
    """Walk an element's paragraphs; return (sex, pal, equation text) triples."""
    entries: list[tuple[str | None, str | None, str]] = []
    sex: str | None = initial_sex
    pal: str | None = None
    for paragraph in details.find_all("p"):
        text = _clean_text(paragraph.get_text(" ", strip=True))
        if not text:
            continue
        if text in ("Males", "Females"):
            sex = "male" if text == "Males" else "female"
            continue
        if text.startswith("PA CAT"):
            pal_key = text[len("PA CAT"):].strip().lower().replace(" ", "_")
            if pal_key not in _PAL_KEYS:
                raise BuildError(f"EER page: unknown PA CAT '{text}' in {label}")
            pal = pal_key
            continue
        if "EER =" in text:
            entries.append((sex, pal, text))
    return entries


def _single_equation(entries, label: str, sex: str | None, pal: str | None) -> _Equation:
    found = [text for entry_sex, entry_pal, text in entries if entry_sex == sex and entry_pal == pal]
    if len(found) != 1:
        raise BuildError(f"EER page: missing equation for {label} (sex={sex}, pal={pal})")
    return _parse_equation(found[0], f"{label} (sex={sex}, pal={pal})")


_INFANT_BANDS = [
    (re.compile(r"0\s*to\s*<\s*3\s*months", re.I), "0_to_3_months"),
    (re.compile(r"3\s*to\s*<\s*6\s*months", re.I), "3_to_6_months"),
    (re.compile(r"6\s*to\s*<\s*12\s*months", re.I), "6_to_12_months"),
    (re.compile(r"1\s*year\s*to\s*<\s*3\s*years", re.I), "1_to_3_years"),
]

_CHILD_BANDS = [
    (re.compile(r"3\s*years?\s*to\s*<\s*4\s*years", re.I), "3_to_4_years"),
    (re.compile(r"4\s*years?\s*to\s*<\s*9\s*years", re.I), "4_to_9_years"),
    (re.compile(r"9\s*years?\s*to\s*<\s*14\s*years", re.I), "9_to_14_years"),
    (re.compile(r"14\s*years?\s*to\s*<\s*19\s*years", re.I), "14_to_19_years"),
]

_BMI_ROWS = [
    ("underweight", re.compile(r"underweight", re.I)),
    ("normal_weight", re.compile(r"normal\s+weight", re.I)),
    ("overweight", re.compile(r"overweight", re.I)),
    ("obese", re.compile(r"obese", re.I)),
]

_LACTATION_AGE_GROUPS = [
    ("age_under_19", re.compile(r"less\s+than\s+19", re.I)),
    ("age_19_plus", re.compile(r"19\s+years\s+and\s+older", re.I)),
]


def _band_key(summary_text: str, bands: list[tuple[re.Pattern[str], str]], section_id: str) -> str:
    text = _clean_text(summary_text)
    for pattern, key in bands:
        if pattern.search(text):
            return key
    raise BuildError(f"EER page: section {section_id}: unexpected details summary {text!r}")


def _parse_growth_section(
    soup: BeautifulSoup, section_id: str, bands: list[tuple[re.Pattern[str], str]]
) -> dict[str, dict[tuple[str | None, str | None], _Equation]]:
    """Parse a2/a3-style sections: details per age band with Males/Females equations.

    Returns {band_key: {(sex, pal): _Equation}}; ``pal`` is None for sections
    without PA CAT paragraphs (a2) and a PAL key for a3.
    """
    parsed: dict[str, dict[tuple[str | None, str | None], _Equation]] = {}
    for details in _section_details(soup, section_id):
        summary = details.find("summary")
        if summary is None:
            raise BuildError(f"EER page: section {section_id}: details block without summary")
        band = _band_key(summary.get_text(), bands, section_id)
        if band in parsed:
            raise BuildError(f"EER page: section {section_id}: duplicate age band '{band}'")
        entries = _details_equations(details, f"section {section_id} band {band}")
        grouped: dict[tuple[str | None, str | None], _Equation] = {}
        for sex, pal, text in entries:
            if sex not in ("male", "female"):
                raise BuildError(
                    f"EER page: section {section_id} band {band}: equation without "
                    f"Males/Females header: {text!r}"
                )
            if pal is not None and pal not in _PAL_KEYS:
                raise BuildError(
                    f"EER page: section {section_id} band {band}: unknown PA CAT {pal!r}"
                )
            key = (sex, pal)
            if key in grouped:
                raise BuildError(
                    f"EER page: section {section_id} band {band}: duplicate equation for "
                    f"sex={sex}, pal={pal}"
                )
            grouped[key] = _parse_equation(
                text, f"section {section_id} band {band} (sex={sex}, pal={pal})"
            )
        parsed[band] = grouped
    if len(parsed) != len(bands):
        raise BuildError(
            f"EER page: section {section_id}: expected {len(bands)} age bands, got {len(parsed)}"
        )
    return parsed


def _coefficients_agree(equations: list[_Equation], label: str) -> None:
    first = equations[0].coefficients
    for other in equations[1:]:
        if other.coefficients != first:
            raise BuildError(f"EER page: coefficients disagree across bands in {label}")


def _band_equations(
    bands: dict[str, dict[tuple[str | None, str | None], _Equation]],
    ordered: list[str],
    sex: str,
    pal: str | None,
    section_id: str,
) -> list[_Equation]:
    equations = []
    for band in ordered:
        equation = bands[band].get((sex, pal))
        if equation is None:
            raise BuildError(
                f"EER page: section {section_id}: missing equation for band {band}, "
                f"sex={sex}, pal={pal}"
            )
        equations.append(equation)
    return equations


def _growth_constants(equations: list[_Equation], label: str) -> list[float]:
    constants = [equation.constants for equation in equations]
    if any(len(values) != 1 for values in constants):
        raise BuildError(
            f"EER page: {label}: expected exactly one growth constant per band, got {constants}"
        )
    return [values[0] for values in constants]


def _parse_infant_toddler(soup: BeautifulSoup) -> dict[str, Any]:
    bands = _parse_growth_section(soup, "a2", _INFANT_BANDS)
    ordered = [band for _, band in _INFANT_BANDS]
    section: dict[str, Any] = {
        "description": _SECTION_META["infant_toddler"]["description"],
        "age_range": _SECTION_META["infant_toddler"]["age_range"],
    }
    for sex in ("male", "female"):
        equations = _band_equations(bands, ordered, sex, None, "a2")
        _coefficients_agree(equations, f"infant_toddler/{sex}")
        constants = _growth_constants(equations, f"infant_toddler/{sex}")
        section[sex] = {
            "formula": _formula(equations[0], "outside", "growth_constant"),
            "coefficients": dict(equations[0].coefficients),
            "growth_constants": {band: int(value) for band, value in zip(ordered, constants)},
        }
    return section


def _parse_child_adolescent(soup: BeautifulSoup) -> dict[str, Any]:
    bands = _parse_growth_section(soup, "a3", _CHILD_BANDS)
    ordered = [band for _, band in _CHILD_BANDS]
    # Formula sign style: the bundled snapshot renders male coefficients with the
    # sign outside the parentheses and female coefficients with the sign inside.
    styles = {"male": "outside", "female": "inside"}
    section: dict[str, Any] = {
        "description": _SECTION_META["child_adolescent"]["description"],
        "age_range": _SECTION_META["child_adolescent"]["age_range"],
    }
    for sex in ("male", "female"):
        sex_data: dict[str, Any] = {}
        for pal in _PAL_KEYS:
            equations = _band_equations(bands, ordered, sex, pal, "a3")
            _coefficients_agree(equations, f"child_adolescent/{sex}/{pal}")
            sex_data[pal] = {
                "formula": _formula(equations[0], styles[sex], "growth_constant"),
                "coefficients": dict(equations[0].coefficients),
            }
        constants = _growth_constants(
            _band_equations(bands, ordered, sex, _PAL_KEYS[0], "a3"),
            f"child_adolescent/{sex}",
        )
        sex_data["growth_constants"] = {
            band: int(value) for band, value in zip(ordered, constants)
        }
        section[sex] = sex_data
    return section


def _parse_adult(soup: BeautifulSoup) -> dict[str, Any]:
    section: dict[str, Any] = {
        "description": _SECTION_META["adult"]["description"],
        "age_range": _SECTION_META["adult"]["age_range"],
    }
    for details in _section_details(soup, "a4"):
        summary = details.find("summary")
        summary_text = _clean_text(summary.get_text()) if summary else ""
        sex = {"Males": "male", "Females": "female"}.get(summary_text, summary_text.lower())
        if sex not in ("male", "female"):
            raise BuildError(f"EER page: section a4: unexpected details summary {summary!r}")
        if sex in section:
            raise BuildError(f"EER page: section a4: duplicate details for '{sex}'")
        entries = _details_equations(details, f"section a4 ({sex})", initial_sex=sex)
        pal_data: dict[str, Any] = {}
        for pal in _PAL_KEYS:
            equation = _single_equation(entries, f"section a4 ({sex})", sex, pal)
            if equation.constants:
                raise BuildError(
                    f"EER page: adult/{sex}/{pal}: unexpected constant {equation.constants}"
                )
            pal_data[pal] = {
                "formula": _formula(equation, "inside"),
                "coefficients": dict(equation.coefficients),
            }
        section[sex] = pal_data
    if set(section) - {"description", "age_range"} != {"male", "female"}:
        raise BuildError("EER page: section a4: expected Males and Females details blocks")
    return section


def _parse_bmi_range(summary_text: str, bmi_key: str) -> str:
    match = re.search(r"\(([^)]*)\)", summary_text)
    if not match:
        raise BuildError(f"EER page: section a5: no BMI range in summary for '{bmi_key}'")
    range_text = _clean_text(match.group(1))
    range_text = re.sub(r"\s*kg/m\s*2\s*$", "", range_text)
    range_text = range_text.replace("≥", ">=").replace("–", " - ").replace("−", " - ")
    return _clean_text(range_text)


def _parse_pregnancy(soup: BeautifulSoup) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    for details in _section_details(soup, "a5"):
        summary = details.find("summary")
        if summary is None:
            raise BuildError("EER page: section a5: details block without summary")
        summary_text = _clean_text(summary.get_text())
        bmi_key = next((key for key, pattern in _BMI_ROWS if pattern.search(summary_text)), None)
        if bmi_key is None:
            raise BuildError(
                f"EER page: section a5: unexpected details summary {summary_text!r}"
            )
        if bmi_key in rows:
            raise BuildError(f"EER page: section a5: duplicate BMI row '{bmi_key}'")
        entries = _details_equations(details, f"section a5 row {bmi_key}")
        pal_equations: dict[str, _Equation] = {}
        for pal in _PAL_KEYS:
            pal_equations[pal] = _single_equation(entries, f"section a5 row {bmi_key}", None, pal)
        depositions = {pal: eq.constants for pal, eq in pal_equations.items()}
        first = depositions[_PAL_KEYS[0]]
        if len(first) != 1 or any(deps != first for deps in depositions.values()):
            raise BuildError(
                f"EER page: pregnancy/{bmi_key}: energy deposition constants disagree "
                f"across PA CATs: {depositions}"
            )
        rows[bmi_key] = {
            "equations": pal_equations,
            "deposition": first[0],
            "bmi_range": _parse_bmi_range(summary_text, bmi_key),
        }
    if set(rows) != {key for key, _ in _BMI_ROWS}:
        raise BuildError(
            f"EER page: section a5: expected BMI rows {[key for key, _ in _BMI_ROWS]}, "
            f"got {sorted(rows)}"
        )
    ordered_pals = list(_PAL_KEYS)
    equations_by_pal: dict[str, Any] = {}
    for pal in ordered_pals:
        equations = [rows[key]["equations"][pal] for key, _ in _BMI_ROWS]
        _coefficients_agree(equations, f"pregnancy/{pal}")
        if "gestation_weeks" not in equations[0].coefficients:
            raise BuildError(
                f"EER page: pregnancy/{pal}: missing gestation_weeks coefficient"
            )
        equations_by_pal[pal] = {
            "formula": _formula(equations[0], "inside", "energy_deposition"),
            "coefficients": dict(equations[0].coefficients),
        }
    return {
        "description": _SECTION_META["pregnancy"]["description"],
        "age_range": _SECTION_META["pregnancy"]["age_range"],
        "note": _SECTION_META["pregnancy"]["note"],
        "equations_by_pal": equations_by_pal,
        "energy_deposition_by_bmi": {
            key: {
                "bmi_range": rows[key]["bmi_range"],
                "kcal_per_day": int(rows[key]["deposition"]),
            }
            for key, _ in _BMI_ROWS
        },
    }


def _parse_lactation(soup: BeautifulSoup) -> dict[str, Any]:
    sections = {"a6": "0_to_6_months_postpartum", "a7": "7_to_12_months_postpartum"}
    constants: dict[str, list[float]] = {}
    base_equations: dict[str, dict[str, Any]] = {}
    for section_id, period_key in sections.items():
        period: dict[str, dict[str, _Equation]] = {}
        for details in _section_details(soup, section_id):
            summary = details.find("summary")
            if summary is None:
                raise BuildError(f"EER page: section {section_id}: details block without summary")
            summary_text = _clean_text(summary.get_text())
            age_key = next(
                (key for key, pattern in _LACTATION_AGE_GROUPS if pattern.search(summary_text)),
                None,
            )
            if age_key is None:
                raise BuildError(
                    f"EER page: section {section_id}: unexpected details summary {summary_text!r}"
                )
            if age_key in period:
                raise BuildError(f"EER page: section {section_id}: duplicate age group '{age_key}'")
            entries = _details_equations(details, f"section {section_id} group {age_key}")
            period[age_key] = {
                pal: _single_equation(entries, f"section {section_id} ({age_key})", None, pal)
                for pal in _PAL_KEYS
            }
        if set(period) != {key for key, _ in _LACTATION_AGE_GROUPS}:
            raise BuildError(
                f"EER page: section {section_id}: expected age groups "
                f"{[key for key, _ in _LACTATION_AGE_GROUPS]}, got {sorted(period)}"
            )
        # Verify the trailing milk-energy constants match the expected breakdown.
        first_group = next(iter(period.values()))
        trailing = {pal: eq.constants for pal, eq in first_group.items()}
        reference = trailing[_PAL_KEYS[0]]
        if any(constants_ != reference for constants_ in trailing.values()):
            raise BuildError(
                f"EER page: lactation {period_key}: trailing constants disagree "
                f"across PA CATs: {trailing}"
            )
        if period_key == "0_to_6_months_postpartum":
            expected = [540.0, -140.0]
        else:
            expected = [380.0]
        if reference != expected:
            raise BuildError(
                f"EER page: lactation {period_key}: expected trailing constants {expected}, "
                f"got {reference}"
            )
        constants[period_key] = reference
        for age_key, pal_equations in period.items():
            group = base_equations.setdefault(age_key, {"description": None})
            for pal, equation in pal_equations.items():
                group[pal] = {"coefficients": dict(equation.coefficients)}
    for age_key, description in _LACTATION_BASE_DESCRIPTIONS.items():
        base_equations[age_key]["description"] = description
    milk_constants = {}
    for period_key, values in constants.items():
        milk_constants[period_key] = {
            "total_addition_kcal": int(sum(values)),
            "breakdown": _MILK_BREAKDOWNS[period_key],
        }
    return {
        "description": _SECTION_META["lactation"]["description"],
        "age_range": _SECTION_META["lactation"]["age_range"],
        "note": _SECTION_META["lactation"]["note"],
        "milk_energy_constants": milk_constants,
        "base_equations": base_equations,
    }


_BUNDLED_PAL_AGE_GROUPS = {
    "3_to_9_years": {
        "inactive": {"min": 1.00, "max": 1.31},
        "low_active": {"min": 1.31, "max": 1.44},
        "active": {"min": 1.44, "max": 1.59},
        "very_active": {"min": 1.59, "max": 2.50},
    },
    "9_to_14_years": {
        "inactive": {"min": 1.00, "max": 1.44},
        "low_active": {"min": 1.44, "max": 1.59},
        "active": {"min": 1.59, "max": 1.77},
        "very_active": {"min": 1.77, "max": 2.50},
    },
    "14_to_19_years": {
        "inactive": {"min": 1.00, "max": 1.56},
        "low_active": {"min": 1.56, "max": 1.73},
        "active": {"min": 1.73, "max": 1.92},
        "very_active": {"min": 1.92, "max": 2.50},
    },
    "19_years_and_older": {
        "inactive": {"min": 1.00, "max": 1.53},
        "low_active": {"min": 1.53, "max": 1.68},
        "active": {"min": 1.68, "max": 1.85},
        "very_active": {"min": 1.85, "max": 2.50},
    },
}

_PAL_AGE_GROUP_ROWS = [
    (re.compile(r"(\d+)\s*to\s*<\s*(\d+)\s*years"), "{a}_to_{b}_years"),
    (None, "19_years_and_older"),  # "19 years and older" row, matched below
]


def _parse_pal_definitions(soup: BeautifulSoup) -> dict[str, Any]:
    heading = soup.find("h2", id="a1")
    if heading is None:
        raise BuildError("EER page: missing section 'a1' (PA CAT definitions)")
    table = heading.find_next("table")
    if table is None:
        raise BuildError("EER page: section a1: PAL definitions table not found")
    age_groups: dict[str, dict[str, dict[str, float]]] = {}
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue
        first = _clean_text(cells[0].get_text(" ", strip=True))
        band_match = re.match(r"(\d+)\s*to\s*<\s*(\d+)\s*years$", first)
        if band_match:
            key = f"{band_match.group(1)}_to_{band_match.group(2)}_years"
        elif first == "19 years and older":
            key = "19_years_and_older"
        else:
            continue  # header row or the daily-activities example row
        if key in age_groups:
            raise BuildError(f"EER page: section a1: duplicate PAL row '{key}'")
        values: dict[str, dict[str, float]] = {}
        for cell, pal in zip(cells[1:5], _PAL_KEYS):
            cell_text = _clean_text(cell.get_text(" ", strip=True))
            range_match = re.search(r"([\d.]+)\s*≤\s*PAL\s*<\s*([\d.]+)", cell_text)
            if not range_match:
                raise BuildError(
                    f"EER page: section a1: unparseable PAL range {cell_text!r} for {key}/{pal}"
                )
            values[pal] = {"min": float(range_match.group(1)), "max": float(range_match.group(2))}
        age_groups[key] = values
    expected_keys = set(_BUNDLED_PAL_AGE_GROUPS)
    if set(age_groups) != expected_keys:
        raise BuildError(
            f"EER page: section a1: expected PAL age groups {sorted(expected_keys)}, "
            f"got {sorted(age_groups)}"
        )
    if age_groups != _BUNDLED_PAL_AGE_GROUPS:
        raise BuildError(
            "EER page: section a1: parsed PAL age groups differ from the bundled "
            f"pal_category_definitions: {age_groups}"
        )
    return {
        "description": _PAL_DEFINITIONS_DESCRIPTION,
        "age_groups": age_groups,
        "adult_activity_examples": dict(_ADULT_ACTIVITY_EXAMPLES),
    }


def _validate_eer(equations: dict[str, Any]) -> None:
    expected_sections = {"infant_toddler", "child_adolescent", "adult", "pregnancy", "lactation"}
    missing = expected_sections - set(equations)
    if missing:
        raise BuildError(f"EER page: missing equation section(s) {sorted(missing)}")

    def coefficients_complete(coeffs: Any, label: str, keys: tuple[str, ...]) -> None:
        if not isinstance(coeffs, dict) or set(coeffs) != set(keys):
            raise BuildError(f"EER page: {label} coefficients incomplete: {coeffs}")

    base_keys = ("intercept", "age", "height_cm", "weight_kg")
    for sex in ("male", "female"):
        infant = equations["infant_toddler"].get(sex)
        if not infant or not infant.get("coefficients") or not infant.get("growth_constants"):
            raise BuildError(f"EER page: infant_toddler/{sex} coefficients incomplete")
        coefficients_complete(infant["coefficients"], f"infant_toddler/{sex}", base_keys)
        if set(infant["growth_constants"]) != {
            "0_to_3_months", "3_to_6_months", "6_to_12_months", "1_to_3_years"
        }:
            raise BuildError(f"EER page: infant_toddler/{sex} growth constants incomplete")
        child = equations["child_adolescent"].get(sex)
        if not child:
            raise BuildError(f"EER page: child_adolescent/{sex} coefficients incomplete")
        for pal in _PAL_KEYS:
            coefficients_complete(
                child.get(pal, {}).get("coefficients"),
                f"child_adolescent/{sex}/{pal}", base_keys,
            )
        if set(child.get("growth_constants", {})) != {
            "3_to_4_years", "4_to_9_years", "9_to_14_years", "14_to_19_years"
        }:
            raise BuildError(f"EER page: child_adolescent/{sex} growth constants incomplete")
        for pal in _PAL_KEYS:
            coefficients_complete(
                equations["adult"].get(sex, {}).get(pal, {}).get("coefficients"),
                f"adult/{sex}/{pal}", base_keys,
            )
    pregnancy = equations["pregnancy"]
    for pal in _PAL_KEYS:
        coefficients_complete(
            pregnancy.get("equations_by_pal", {}).get(pal, {}).get("coefficients"),
            f"pregnancy/{pal}", base_keys + ("gestation_weeks",),
        )
    if set(pregnancy.get("energy_deposition_by_bmi", {})) != {
        "underweight", "normal_weight", "overweight", "obese"
    }:
        raise BuildError("EER page: pregnancy energy deposition by BMI incomplete")
    lactation = equations["lactation"]
    if set(lactation.get("milk_energy_constants", {})) != {
        "0_to_6_months_postpartum", "7_to_12_months_postpartum"
    }:
        raise BuildError("EER page: lactation milk energy constants incomplete")
    for age_key in ("age_under_19", "age_19_plus"):
        group = lactation.get("base_equations", {}).get(age_key, {})
        for pal in _PAL_KEYS:
            coefficients_complete(
                group.get(pal, {}).get("coefficients"),
                f"lactation/{age_key}/{pal}", base_keys,
            )


def parse_eer_page(html: str) -> dict[str, Any]:
    """Parse the EER equations page into the bundled EER schema (without _metadata)."""
    soup = BeautifulSoup(html, "html.parser")
    equations = {
        "infant_toddler": _parse_infant_toddler(soup),
        "child_adolescent": _parse_child_adolescent(soup),
        "adult": _parse_adult(soup),
        "pregnancy": _parse_pregnancy(soup),
        "lactation": _parse_lactation(soup),
    }
    _validate_eer(equations)
    return {
        "general_note": _GENERAL_NOTE,
        "pal_category_definitions": _parse_pal_definitions(soup),
        "pal_descriptions": json.loads(json.dumps(_PAL_DESCRIPTIONS)),
        "equations": equations,
    }


def build_eer(out_path: Path, fetcher: Fetcher | None = None) -> dict[str, Any]:
    """Fetch, parse, validate and atomically write the EER equations data file."""
    fetcher = fetcher if fetcher is not None else HttpFetcher()
    url = eer_url()
    html = fetcher.fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    payload = parse_eer_page(html)
    payload["_provenance"] = _provenance(url, html, soup)
    return _write_payload(out_path, payload)


# ---------------------------------------------------------------------------
# EER calculation
# ---------------------------------------------------------------------------

_SEX_ALIASES = {"m": "male", "male": "male", "f": "female", "female": "female"}


def _normalize_sex(sex: str) -> str:
    key = str(sex).strip().lower()
    if key not in _SEX_ALIASES:
        raise ValueError(f"Unknown sex {sex!r}; use 'male' or 'female'")
    return _SEX_ALIASES[key]


def _normalize_pal(pal: str) -> str:
    key = re.sub(r"[\s_-]+", "_", str(pal).strip().lower())
    if key not in _PAL_KEYS:
        raise ValueError(
            f"Unknown PAL category {pal!r}; use one of {', '.join(_PAL_KEYS)}"
        )
    return key


def calculate_eer(
    data: dict[str, Any],
    sex: str,
    age_years: float,
    weight_kg: float,
    height_cm: float,
    pal: str,
) -> dict[str, Any]:
    """Calculate an EER from parsed/bundled EER equations data.

    ``data`` may be the full bundled payload (with an ``equations`` key) or a bare
    ``equations`` mapping. Pregnancy and lactation are out of scope here; see the
    ``pregnancy``/``lactation`` equation sections for those.
    """
    sex = _normalize_sex(sex)
    pal_key = _normalize_pal(pal)
    age_years = float(age_years)
    weight_kg = float(weight_kg)
    height_cm = float(height_cm)
    equations = data.get("equations", data)

    growth_constant: float | None = None
    growth_band: str | None = None
    if age_years < 3:
        section = "infant_toddler"
        months = age_years * 12
        if months < 3:
            growth_band = "0_to_3_months"
        elif months < 6:
            growth_band = "3_to_6_months"
        elif months < 12:
            growth_band = "6_to_12_months"
        else:
            growth_band = "1_to_3_years"
        entry = equations.get(section, {}).get(sex)
        if entry:
            growth_constant = entry.get("growth_constants", {}).get(growth_band)
            formula = entry.get("formula", "")
            coefficients = entry.get("coefficients")
    elif age_years < 19:
        section = "child_adolescent"
        if age_years < 4:
            growth_band = "3_to_4_years"
        elif age_years < 9:
            growth_band = "4_to_9_years"
        elif age_years < 14:
            growth_band = "9_to_14_years"
        else:
            growth_band = "14_to_19_years"
        sex_data = equations.get(section, {}).get(sex)
        entry = (sex_data or {}).get(pal_key)
        if sex_data:
            growth_constant = sex_data.get("growth_constants", {}).get(growth_band)
        formula = (entry or {}).get("formula", "")
        coefficients = (entry or {}).get("coefficients")
    else:
        section = "adult"
        entry = equations.get(section, {}).get(sex, {}).get(pal_key)
        formula = (entry or {}).get("formula", "")
        coefficients = (entry or {}).get("coefficients")

    if not coefficients:
        raise ValueError(
            f"EER data: missing {section}/{sex}"
            + (f"/{pal_key}" if section != "infant_toddler" else "")
            + " coefficients"
        )
    if growth_band is not None and growth_constant is None:
        raise ValueError(
            f"EER data: missing growth constant {section}/{sex}/{growth_band}"
        )

    age_contribution = coefficients["age"] * age_years
    height_contribution = coefficients["height_cm"] * height_cm
    weight_contribution = coefficients["weight_kg"] * weight_kg
    value = coefficients["intercept"] + age_contribution + height_contribution + weight_contribution
    if growth_constant is not None:
        value += growth_constant
    components = {
        "intercept": coefficients["intercept"],
        "age": age_contribution,
        "height_cm": height_contribution,
        "weight_kg": weight_contribution,
    }
    if growth_constant is not None:
        components["growth_constant"] = growth_constant
    return {
        "eer_kcal": round(value, 1),
        "formula": formula,
        "section": section,
        "pal": pal_key,
        "growth_constant": growth_constant,
        "components": components,
    }
