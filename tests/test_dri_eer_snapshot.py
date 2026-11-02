"""Live snapshot tests: bundled DRI/EER snapshots vs the real canada.ca pages.

These tests fetch the LIVE pages with the default fetcher (real network, slow):
parse them with parse_dri_page/parse_eer_page, strip the non-deterministic
fields from both sides, and compare against the bundled snapshots field by
field. On any difference the assertion message lists a readable path-by-path
diff. An independent arithmetic check (published adult equations hardcoded
here) catches a wrong snapshot AND a wrong parser at the same time.

Skip with FOODGUIDE_SKIP_LIVE_TESTS=1 (e.g. in offline CI); by default they run.
"""

import json
import os
from pathlib import Path

import pytest

from foodguide.builders.dri_eer import (
    DRI_URL,
    EER_URL,
    calculate_eer,
    fetch_page,
    parse_dri_page,
    parse_eer_page,
)

pytestmark = pytest.mark.live

FIXTURES = Path(__file__).parent / "fixtures" / "dri_eer"
skip_live = pytest.mark.skipif(
    os.environ.get("FOODGUIDE_SKIP_LIVE_TESTS") == "1",
    reason="FOODGUIDE_SKIP_LIVE_TESTS=1 (live snapshot tests skipped)",
)

# Published adult EER equations (kcal/day), Health Canada DRI tables 2005,
# as printed on the live page. Used to compute expected values independently
# of the bundled snapshot / parser pipeline.
_ADULT_EQUATIONS = {
    "male": {
        "inactive": (753.07, 10.83, 6.50, 14.10),
        "low_active": (581.47, 10.83, 8.30, 14.94),
        "active": (1004.82, 10.83, 6.52, 15.91),
        "very_active": (-517.88, 10.83, 15.61, 19.11),
    },
    "female": {
        "inactive": (584.90, 7.01, 5.72, 11.71),
        "low_active": (575.77, 7.01, 6.60, 12.14),
        "active": (710.25, 7.01, 6.54, 12.34),
        "very_active": (511.83, 9.07, 12.56, 12.56),
    },
}


def _load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _strip_dri(payload: dict) -> dict:
    """Drop non-deterministic fields from a DRI payload (either side)."""
    payload = json.loads(json.dumps(payload))
    payload.pop("last_updated", None)
    payload.pop("_provenance", None)
    data_quality = payload.get("data_quality")
    if isinstance(data_quality, dict):
        data_quality.pop("parsing_timestamp", None)
    return payload


def _strip_eer(payload: dict) -> dict:
    payload = json.loads(json.dumps(payload))
    payload.pop("_provenance", None)
    payload.pop("_metadata", None)
    return payload


def _diff_lines(bundled, scraped, path: str = "$") -> list[str]:
    """Readable path-by-path diff lines ('path: bundled -> scraped')."""
    lines: list[str] = []
    if isinstance(bundled, dict) and isinstance(scraped, dict):
        for key in sorted(set(bundled) | set(scraped)):
            child = f"{path}.{key}"
            if key not in bundled:
                lines.append(f"{child}: <missing in bundled snapshot> -> {scraped[key]!r}")
            elif key not in scraped:
                lines.append(f"{child}: {bundled[key]!r} -> <missing in scraped page>")
            else:
                lines.extend(_diff_lines(bundled[key], scraped[key], child))
    elif isinstance(bundled, list) and isinstance(scraped, list):
        if len(bundled) != len(scraped):
            lines.append(f"{path}: list of {len(bundled)} items -> list of {len(scraped)} items")
        for index, (b, s) in enumerate(zip(bundled, scraped)):
            lines.extend(_diff_lines(b, s, f"{path}[{index}]"))
    elif bundled != scraped:
        lines.append(f"{path}: {bundled!r} -> {scraped!r}")
    return lines


def assert_equal_deep(bundled, scraped, label: str) -> None:
    diff = _diff_lines(bundled, scraped)
    assert not diff, (
        f"bundled {label} snapshot differs from the live-scraped page:\n"
        + "\n".join(diff)
    )


def _eer_from_equations(data: dict, sex: str, age: int, weight: float, height: float, pal: str):
    return calculate_eer(data.get("equations", data), sex, age, weight, height, pal)["eer_kcal"]


@pytest.mark.skipif(
    os.environ.get("FOODGUIDE_SKIP_LIVE_TESTS") == "1",
    reason="FOODGUIDE_SKIP_LIVE_TESTS=1 (live snapshot tests skipped)",
)
def test_live_dri_page_matches_snapshot():
    html = fetch_page(DRI_URL)
    scraped = _strip_dri(parse_dri_page(html))
    bundled = _strip_dri(_load_json("dri_macronutrients.json"))
    assert_equal_deep(bundled, scraped, "dri_macronutrients")


@pytest.mark.skipif(
    os.environ.get("FOODGUIDE_SKIP_LIVE_TESTS") == "1",
    reason="FOODGUIDE_SKIP_LIVE_TESTS=1 (live snapshot tests skipped)",
)
def test_live_eer_page_matches_snapshot():
    html = fetch_page(EER_URL)
    scraped = _strip_eer(parse_eer_page(html))
    bundled = _strip_eer(_load_json("eer_equations.json"))
    assert_equal_deep(bundled, scraped, "eer_equations")


@pytest.mark.skipif(
    os.environ.get("FOODGUIDE_SKIP_LIVE_TESTS") == "1",
    reason="FOODGUIDE_SKIP_LIVE_TESTS=1 (live snapshot tests skipped)",
)
def test_live_adult_eer_arithmetic():
    """calculate_eer on the live-parsed data must reproduce the published math.

    For each case the expected value is computed here from the hardcoded
    published constants (EER = intercept - c_age*age + c_height*height
    + c_weight*weight) and cross-checked against calculate_eer fed with the
    freshly scraped adult coefficients. A mismatch means either the snapshot
    is wrong or the parser misread the page.
    """
    html = fetch_page(EER_URL)
    live = parse_eer_page(html)

    cases = [
        # (sex, pal, age, weight_kg, height_cm)
        ("male", "active", 30, 70, 175),  # 1004.82 - 10.83*30 + 6.52*175 + 15.91*70
        ("female", "low_active", 30, 60, 165),  # 575.77 - 7.01*30 + 6.60*165 + 12.14*60
        ("male", "inactive", 45, 75, 172),  # 753.07 - 10.83*45 + 6.50*172 + 14.10*75
    ]
    for sex, pal, age, weight, height in cases:
        intercept, c_age, c_height, c_weight = _ADULT_EQUATIONS[sex][pal]
        expected = round(
            intercept - c_age * age + c_height * height + c_weight * weight, 1
        )
        actual = _eer_from_equations(live, sex, age, weight, height, pal)
        assert actual == expected, (
            f"EER({sex}, {pal}, age={age}, {weight} kg, {height} cm): published "
            f"constants give {expected} but calculate_eer on the live-parsed "
            f"page gives {actual}"
        )
        # The bundled snapshot must agree with the live-parsed result too.
        snapshot = _load_json("eer_equations.json")
        assert _eer_from_equations(snapshot, sex, age, weight, height, pal) == actual, (
            f"bundled snapshot disagrees with the live page for {sex}/{pal}"
        )
