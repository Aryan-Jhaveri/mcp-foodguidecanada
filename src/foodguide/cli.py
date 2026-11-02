"""foodguide command line interface (typer-based).

Entry point: ``foodguide = "foodguide.cli:main"``.

Exit codes: 0 = ok, 1 = error, 2 = usage (typer/click default).
All logs go to stderr; data output goes to stdout.
"""

import contextlib
import csv
import json
import os
import re
import sqlite3
import sys
from enum import Enum
from importlib import metadata
from importlib.resources import files
from pathlib import Path

import requests
import typer

from foodguide.builders.dri_eer import BuildError, build_dri, build_eer, calculate_eer
from foodguide.cnf import db as cnf_db
from foodguide.cnf.builder import DEFAULT_DATASET_ID, DEFAULT_ZIP_URL, build_cnf_db
from foodguide.data_manager import get_dri_data_manager, get_eer_data_manager
from foodguide.pipeline import build_all as pipeline_build_all
from foodguide.pipeline import install as pipeline_install
from foodguide.pipeline.manifest import (
    ManifestError,
    changed_datasets,
    load_manifest,
    write_manifest,
)
from foodguide.recipes.builder import build_recipes_json
from foodguide.recipes.source import LocalRecipeSource, recipes_data_path

# ---------------------------------------------------------------- helpers


class OutputFormat(str, Enum):
    """Formats supported by the global --format option."""

    table = "table"
    csv = "csv"
    json = "json"


def _log(message: str) -> None:
    """Write a log line to stderr (never stdout)."""
    typer.echo(message, err=True)


def _package_version() -> str:
    try:
        return metadata.version("foodguide")
    except Exception:
        return "0.1.0"


def _provenance(payload: object) -> str | None:
    """Return the data provenance from a bundled JSON payload, if any."""
    if not isinstance(payload, dict):
        return None
    md = payload.get("_metadata")
    if isinstance(md, dict) and md.get("source"):
        return str(md["source"])
    if payload.get("source"):
        return str(payload["source"])
    return None


# ---------------------------------------------------------------- app


app = typer.Typer(
    name="foodguide",
    help=(
        "Canada's Food Guide data tools: nutrient lookups (CNF), Dietary "
        "Reference Intakes (DRI), energy requirements (EER), and local data "
        "management."
    ),
    epilog=(
        "Examples:\n"
        "  foodguide cnf search lentils\n"
        "  foodguide cnf nutrients 3393 --measure \"1 cup\"\n"
        "  foodguide dri tables --age-range \"19-30 y\"\n"
        "  foodguide eer calc --sex male --age 30 --weight-kg 70 --height-cm 175\n"
        "  foodguide data status"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)


@app.callback()
def _callback(
    ctx: typer.Context,
    format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Output format for data on stdout",
    ),
) -> None:
    """Global options for the foodguide CLI."""
    ctx.obj = {"format": format}


# ---------------------------------------------------------------- cnf

def _check_lang(lang: str) -> None:
    """Validate the --lang option."""
    if lang not in ("en", "fr"):
        _log(f"invalid --lang {lang!r}; use 'en' or 'fr'")
        raise typer.Exit(code=1)


def _open_cnf_db() -> sqlite3.Connection:
    """Open the CNF database, or exit 1 with build guidance if it is missing."""
    try:
        return cnf_db.open_cnf_db()
    except FileNotFoundError:
        db_path = cnf_db.get_cnf_db_path()
        _log(f"CNF database not found at {db_path}; build it with: foodguide data build cnf --zip <path>")
        raise typer.Exit(code=1) from None


def _get_food_or_exit(conn: sqlite3.Connection, code: int) -> dict:
    """Fetch one food, or exit 1 if the code is unknown."""
    food = cnf_db.get_food(conn, code)
    if food is None:
        _log(f"unknown food code {code}")
        raise typer.Exit(code=1)
    return food


def _normalize_measure_text(text: str | None) -> str:
    """Lowercase with stripped edges and collapsed internal whitespace runs."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def _food_label(key: str) -> str:
    """Human-readable label for a food dict key."""
    return _FOOD_FIELD_LABELS.get(key, key.replace("_", " ").capitalize())


_FOOD_FIELD_LABELS = {
    "food_code": "Food code",
    "name_en": "Name (English)",
    "name_fr": "Name (French)",
    "alternate_name_en": "Alternate name (English)",
    "alternate_name_fr": "Alternate name (French)",
    "group_code": "Food group code",
    "group_name_en": "Food group (English)",
    "group_name_fr": "Food group (French)",
    "source_code": "Source code",
    "source_name_en": "Source (English)",
    "source_name_fr": "Source (French)",
    "usda_ndb_code": "USDA NDB code",
    "scientific_name": "Scientific name",
    "last_updated_date": "Last updated",
}


cnf_app = typer.Typer(
    name="cnf",
    help=(
        "Query the Canadian Nutrient File (CNF) 2026 from a local SQLite "
        "database built with `foodguide data build cnf`. Amounts are per "
        "100 g unless a household measure is given."
    ),
    epilog=(
        "Examples:\n"
        "  foodguide cnf search lentils --limit 5\n"
        "  foodguide cnf search lentilles --lang fr\n"
        "  foodguide cnf food 3393\n"
        "  foodguide cnf nutrients 3393 --measure \"1 cup\"\n"
        "  foodguide cnf nutrients 3393 --nutrient PROT --nutrient KCAL\n"
        "  foodguide cnf measures 3393 --format csv"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(cnf_app, help="Canadian Nutrient File query tools (CNF SQLite database, built by HOM-76)")


@cnf_app.command("search")
def cnf_search(
    ctx: typer.Context,
    term: str = typer.Argument(..., help="Food name or name fragment to search for."),
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum number of results."),
    lang: str = typer.Option("en", "--lang", help="Which names to search: en or fr."),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Search CNF foods by name (results always include both languages).

    Example:
      foodguide cnf search lentils --limit 5
    """
    fmt = format if format is not None else ctx.obj["format"]
    _check_lang(lang)
    with contextlib.closing(_open_cnf_db()) as conn:
        results = cnf_db.search_foods(conn, term, lang=lang, limit=limit)
    if not results:
        _log("no foods match")

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(results, indent=2))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["food_code", "name_en", "name_fr"])
        for row in results:
            writer.writerow([row["food_code"], row["name_en"], row["name_fr"]])
    else:
        width = max((len(str(row["food_code"])) for row in results), default=0)
        for row in results:
            typer.echo(
                f"{row['food_code']:>{width}}  {row['name_en']}  /  {row['name_fr']}"
            )
    raise typer.Exit(code=0)


@cnf_app.command("food")
def cnf_food(
    ctx: typer.Context,
    code: int = typer.Argument(..., help="CNF food code."),
    lang: str = typer.Option("en", "--lang", help="Primary name language: en or fr."),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Show the full record for one CNF food.

    Example:
      foodguide cnf food 3393
    """
    fmt = format if format is not None else ctx.obj["format"]
    _check_lang(lang)
    with contextlib.closing(_open_cnf_db()) as conn:
        food = _get_food_or_exit(conn, code)

    primary = f"name_{lang}"
    other = f"name_{'fr' if lang == 'en' else 'en'}"

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(food, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["key", "value"])
        for key, value in food.items():
            if value is not None:
                writer.writerow([key, value])
    else:
        ordered = [primary, other] + [key for key in food if key not in (primary, other)]
        for key in ordered:
            value = food[key]
            if value is None:
                continue
            typer.echo(f"{_food_label(key)}: {value}")
    raise typer.Exit(code=0)


@cnf_app.command("nutrients")
def cnf_nutrients(
    ctx: typer.Context,
    code: int = typer.Argument(..., help="CNF food code."),
    per: str | None = typer.Option(
        None, "--per", help="Amount basis; only '100g' is supported (the default)."
    ),
    measure: str | None = typer.Option(
        None,
        "--measure",
        help='Household measure to scale to, e.g. "1 cup" (mutually exclusive with --per).',
    ),
    nutrient: list[str] | None = typer.Option(
        None, "--nutrient", help="Only show these nutrient symbols (case-insensitive); repeatable."
    ),
    lang: str = typer.Option("en", "--lang", help="Language for nutrient and food names: en or fr."),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """List nutrient amounts for one food, per 100 g or per household measure.

    Example:
      foodguide cnf nutrients 3393 --measure "1 cup" --format json
    """
    fmt = format if format is not None else ctx.obj["format"]
    _check_lang(lang)
    if per is not None and measure is not None:
        _log("--per and --measure are mutually exclusive; give only one")
        raise typer.Exit(code=1)
    if per is not None and per.lower() != "100g":
        _log(f"invalid --per value {per!r}; only '100g' is supported")
        raise typer.Exit(code=1)

    with contextlib.closing(_open_cnf_db()) as conn:
        food = _get_food_or_exit(conn, code)
        rows = cnf_db.get_nutrients(conn, code)
        measures = cnf_db.get_measures(conn, code)

    if measure is not None:
        wanted = _normalize_measure_text(measure)
        matched = None
        for m in measures:
            if wanted in (_normalize_measure_text(m["description_en"]), _normalize_measure_text(m["description_fr"])):
                matched = m
                break
        if matched is None:
            _log(f"measure {measure!r} not available for food {code} (see: foodguide cnf measures {code})")
            raise typer.Exit(code=1)
        matched_text = (
            matched["description_en"]
            if _normalize_measure_text(matched["description_en"]) == wanted
            else matched["description_fr"]
        )
        grams = float(matched["grams"])
        basis = {
            "type": "measure",
            "measure_code": matched["measure_code"],
            "description": matched_text,
            "grams": grams,
        }
    else:
        basis = {"type": "100g"}

    name_key = f"name_{lang}"
    nutrients = []
    for row in rows:
        if basis["type"] == "measure":
            amount = row["amount"] * grams / 100
            amount_text = None
        else:
            amount = row["amount"]
            amount_text = row["amount_text"]
        nutrients.append(
            {
                "code": row["code"],
                "symbol": row["symbol"],
                "name": row[name_key],
                "unit": row["unit"],
                "amount": amount,
                "amount_text": amount_text,
            }
        )

    if nutrient is not None:
        wanted_symbols = {symbol.lower() for symbol in nutrient}
        found_symbols = {n["symbol"].lower() for n in nutrients if n["symbol"]}
        missing = [s for s in nutrient if s.lower() not in found_symbols]
        if missing:
            _log("nutrient symbol(s) not found for this food: " + ", ".join(missing))
        nutrients = [n for n in nutrients if n["symbol"] and n["symbol"].lower() in wanted_symbols]

    if fmt == OutputFormat.json:
        payload = {
            "food_code": food["food_code"],
            "name_en": food["name_en"],
            "name_fr": food["name_fr"],
            "basis": basis,
            "nutrients": nutrients,
        }
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        header = ["code", "symbol", "name", "unit", "amount"]
        if basis["type"] == "100g":
            header.append("amount_text")
        writer.writerow(header)
        for n in nutrients:
            values = [n["code"], n["symbol"], n["name"], n["unit"], str(n["amount"])]
            if basis["type"] == "100g":
                values.append(n["amount_text"] or "")
            writer.writerow(values)
    else:
        if basis["type"] == "measure":
            typer.echo(f"Nutrients per {basis['description']} ({basis['grams']:g} g) — {food[name_key]}")
        else:
            typer.echo(f"Nutrients per 100 g — {food[name_key]}")
        headers = ["Code", "Symbol", "Name", "Unit", "Amount"]
        table_rows = [
            [
                str(n["code"]),
                n["symbol"] or "",
                n["name"] or "",
                n["unit"] or "",
                f"{n['amount']:g} {n['unit'] or ''}".strip(),
            ]
            for n in nutrients
        ]
        widths = [len(h) for h in headers]
        for tr in table_rows:
            widths = [max(w, len(v)) for w, v in zip(widths, tr)]
        typer.echo(f"{headers[0]:>{widths[0]}}  {headers[1]:<{widths[1]}}  {headers[2]:<{widths[2]}}  {headers[3]:<{widths[3]}}  {headers[4]}")
        for tr in table_rows:
            typer.echo(
                f"{tr[0]:>{widths[0]}}  {tr[1]:<{widths[1]}}  {tr[2]:<{widths[2]}}  {tr[3]:<{widths[3]}}  {tr[4]}"
            )
    raise typer.Exit(code=0)


@cnf_app.command("measures")
def cnf_measures(
    ctx: typer.Context,
    code: int = typer.Argument(..., help="CNF food code."),
    lang: str = typer.Option("en", "--lang", help="Primary name language: en or fr."),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """List household measures and gram conversions for one food.

    Example:
      foodguide cnf measures 3393
    """
    fmt = format if format is not None else ctx.obj["format"]
    _check_lang(lang)
    with contextlib.closing(_open_cnf_db()) as conn:
        food = _get_food_or_exit(conn, code)
        rows = cnf_db.get_measures(conn, code)
    measures = [
        {
            "measure_code": m["measure_code"],
            "description_en": m["description_en"],
            "description_fr": m["description_fr"],
            "grams": m["grams"],
            "measure_type_code": m["measure_type_code"],
        }
        for m in rows
    ]
    if not measures:
        _log(f"no measures for food {code}")

    if fmt == OutputFormat.json:
        payload = {
            "food_code": food["food_code"],
            "name_en": food["name_en"],
            "name_fr": food["name_fr"],
            "measures": measures,
        }
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["measure_code", "description_en", "description_fr", "grams"])
        for m in measures:
            writer.writerow(
                [m["measure_code"], m["description_en"], m["description_fr"], str(m["grams"])]
            )
    else:
        headers = ["Measure code", "EN", "FR", "grams"]
        table_rows = [
            [
                str(m["measure_code"]),
                m["description_en"] or "",
                m["description_fr"] or "",
                f"{m['grams']:g}",
            ]
            for m in measures
        ]
        widths = [len(h) for h in headers]
        for tr in table_rows:
            widths = [max(w, len(v)) for w, v in zip(widths, tr)]
        typer.echo("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
        for tr in table_rows:
            typer.echo("  ".join(v.ljust(w) for v, w in zip(tr, widths)))
    raise typer.Exit(code=0)


# ---------------------------------------------------------------- dri/eer helpers

_PAL_KEYS = ("inactive", "low_active", "active", "very_active")


def _cli_normalize_text(text: str) -> str:
    """Tolerant normalization: NBSP/narrow NBSP and en/em dashes become plain, lowercase, collapsed."""
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def _normalize_age_text(text: str) -> str:
    """Normalize age range text (same rules as foodguide.db.dri_tools)."""
    if not text:
        return text
    text = text.replace("\u00a0", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _flexible_age_match(target_age: str, available_age: str) -> bool:
    """Flexible age-range matching (copied from foodguide.db.dri_tools)."""
    target_norm = _normalize_age_text(target_age).lower()
    available_norm = _normalize_age_text(available_age).lower()

    if target_norm == available_norm:
        return True

    variations = [
        (re.sub(r"\s*-\s*", "-", target_norm), re.sub(r"\s*-\s*", "-", available_norm)),
        (re.sub(r"\byears?\b", "y", target_norm), re.sub(r"\byears?\b", "y", available_norm)),
        (re.sub(r"\bmonths?\b", "mo", target_norm), re.sub(r"\bmonths?\b", "mo", available_norm)),
        (re.sub(r"\s+", "", target_norm), re.sub(r"\s+", "", available_norm)),
    ]

    for target_var, available_var in variations:
        if target_var == available_var:
            return True

    return False


def _dri_age_match(target: str, available: str) -> bool:
    """Age-range match with CLI-normalized text on both sides."""
    return _flexible_age_match(_cli_normalize_text(target), _cli_normalize_text(available))


_DRI_NUTRIENT_ALIASES = {
    "protein": ("protein",),
    "carbohydrate": ("carbohydrate", "carbs"),
    "total_fat": ("total_fat", "fat"),
    "linoleic_acid": ("linoleic_acid", "linoleic"),
    "alpha_linolenic_acid": ("alpha_linolenic_acid", "ala"),
    "total_fibre": ("total_fibre", "fibre", "fiber"),
    "total_water": ("total_water", "water"),
}


def _resolve_dri_nutrient(name: str) -> str | None:
    """Map a user-supplied nutrient name (with aliases) to the canonical data key."""
    key = _cli_normalize_text(name).replace("-", "_").replace(" ", "_")
    for canonical, aliases in _DRI_NUTRIENT_ALIASES.items():
        if key in aliases:
            return canonical
    return None


_DRI_FIELD_PREFIXES = {"ear": "EAR", "rda_ai": "RDA/AI", "ai": "AI", "ul": "UL"}
_DRI_FIELD_UNITS = (
    ("g_kg_day", "g/kg/day"),
    ("litres_day", "L/day"),
    ("g_day", "g/day"),
)


def _dri_field_label(field: str) -> str:
    """Human label for a DRI value field, e.g. rda_ai_g_kg_day -> 'RDA/AI (g/kg/day)'."""
    for suffix, unit in _DRI_FIELD_UNITS:
        if field.endswith(suffix):
            prefix = field[: -len(suffix)].rstrip("_")
            prefix_label = _DRI_FIELD_PREFIXES.get(prefix, prefix.replace("_", " ").upper())
            return f"{prefix_label} ({unit})"
    return field.replace("_", " ")


def _dri_nutrient_value_pairs(nutrient: dict) -> list[tuple[str, object]]:
    """(field, value) pairs for the non-null, non-flag fields of one nutrient."""
    return [
        (field, value)
        for field, value in nutrient.items()
        if field != "is_ai" and value is not None
    ]


def _dri_render_nutrient(name: str, nutrient: dict) -> str:
    """One-line rendering of one nutrient's values, e.g. 'protein: RDA/AI (g/day) 56 (AI)'."""
    pairs = _dri_nutrient_value_pairs(nutrient)
    parts = [
        f"{_dri_field_label(field)} {value:g}"
        + (" (AI)" if nutrient.get("is_ai") else "")
        for field, value in pairs
    ]
    return f"  {name}: " + (", ".join(parts) if parts else "no values recorded")


def _dri_available_age_ranges(rows: list) -> list[str]:
    seen: list[str] = []
    for row in rows:
        age = str(row.get("age_range", ""))
        if age and age not in seen:
            seen.append(age)
    return seen


def _dri_available_categories(rows: list) -> list[str]:
    seen: list[str] = []
    for row in rows:
        cat = str(row.get("category", ""))
        if cat and cat not in seen:
            seen.append(cat)
    return seen


def _dri_lookup_nutrient_key(nutrient: dict) -> str:
    """Pick the most specific non-null value field of a nutrient for single-value display."""
    preferred = (
        "rda_ai_g_day",
        "ai_g_day",
        "rda_ai_g_kg_day",
        "ai_litres_day",
        "ear_g_day",
        "ear_g_kg_day",
        "ul_g_day",
        "ul_litres_day",
    )
    for field in preferred:
        if nutrient.get(field) is not None:
            return field
    for field, value in _dri_nutrient_value_pairs(nutrient):
        return field
    return ""


def _resolve_eer_type(value: str) -> str:
    key = _cli_normalize_text(value)
    if key not in ("adult", "child", "pregnancy", "lactation", "all"):
        _log(f"invalid --type {value!r}; use adult, child, pregnancy, lactation or all")
        raise typer.Exit(code=1)
    return key


def _resolve_eer_pal(value: str) -> str:
    key = re.sub(r"[\s_-]+", "_", _cli_normalize_text(value))
    if key not in _PAL_KEYS + ("all",):
        _log(f"invalid --pal {value!r}; use one of {', '.join(_PAL_KEYS)}, all")
        raise typer.Exit(code=1)
    return key


def _eer_formula_rows(equations: dict) -> list[tuple[str, str, str, str]]:
    """Flatten EER equation sections into (section, who, pal, formula) rows."""
    rows: list[tuple[str, str, str, str]] = []

    def coeffs_formula(coeffs: dict) -> str:
        return (
            f"EER = {coeffs.get('intercept', '?')} + ({coeffs.get('age', 0)} * age)"
            f" + ({coeffs.get('height_cm', 0)} * height_cm)"
            f" + ({coeffs.get('weight_kg', 0)} * weight_kg)"
        )

    for section_key, section in equations.items():
        if not isinstance(section, dict):
            continue
        for sex in ("male", "female"):
            entry = section.get(sex)
            if not isinstance(entry, dict):
                continue
            if "formula" in entry:
                rows.append((section_key, sex, "", str(entry["formula"])))
            for pal in _PAL_KEYS:
                sub = entry.get(pal)
                if isinstance(sub, dict) and "formula" in sub:
                    rows.append((section_key, sex, pal, str(sub["formula"])))
        by_pal = section.get("equations_by_pal")
        if isinstance(by_pal, dict):
            for pal in _PAL_KEYS:
                sub = by_pal.get(pal)
                if isinstance(sub, dict) and "formula" in sub:
                    rows.append((section_key, "", pal, str(sub["formula"])))
        base = section.get("base_equations")
        if isinstance(base, dict):
            for age_key, group in base.items():
                if not isinstance(group, dict):
                    continue
                for pal in _PAL_KEYS:
                    sub = group.get(pal)
                    if isinstance(sub, dict) and isinstance(sub.get("coefficients"), dict):
                        rows.append(
                            (section_key, f"base {age_key}", pal, coeffs_formula(sub["coefficients"]))
                        )
    return rows


# ---------------------------------------------------------------- dri

dri_app = typer.Typer(
    name="dri",
    help=(
        "Dietary Reference Intakes: reference values for macronutrients and "
        "AMDRs by age/sex group (offline: data-dir snapshot first, bundled "
        "fallback; refresh with `foodguide data build dri`)."
    ),
    epilog=(
        "Examples:\n"
        "  foodguide dri tables\n"
        "  foodguide dri tables --age-range \"19-30 y\" --format json\n"
        "  foodguide dri amdr --format csv\n"
        "  foodguide dri lookup --age-range \"19-30 y\" --nutrient protein\n"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(dri_app, help="Dietary Reference Intakes lookups")


def _run_dri_tables(
    ctx: typer.Context,
    age_range: str | None,
    category: str | None,
    format: OutputFormat | None,
) -> None:
    """Shared implementation for `dri tables` and `dri table`."""
    fmt = format if format is not None else ctx.obj["format"]
    data = get_dri_data_manager().get_dri_data()
    rows = data.get("reference_values", [])
    matching = [
        row
        for row in rows
        if (age_range is None or _dri_age_match(age_range, str(row.get("age_range", ""))))
        and (category is None or _cli_normalize_text(category) in _cli_normalize_text(str(row.get("category", ""))))
    ]
    if not matching:
        _log(
            f"no DRI rows match age_range={age_range!r} category={category!r}; "
            f"available age ranges: {', '.join(_dri_available_age_ranges(rows)) or 'none'}"
        )
        raise typer.Exit(code=1)

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(matching, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["age_range", "category", "nutrient", "field", "value", "is_ai"])
        for row in matching:
            for name, nutrient in row.get("nutrients", {}).items():
                if not isinstance(nutrient, dict):
                    continue
                pairs = _dri_nutrient_value_pairs(nutrient)
                if not pairs:
                    writer.writerow(
                        [row.get("age_range", ""), row.get("category", ""), name, "", "", bool(nutrient.get("is_ai"))]
                    )
                for field, value in pairs:
                    writer.writerow(
                        [
                            row.get("age_range", ""),
                            row.get("category", ""),
                            name,
                            field,
                            value,
                            bool(nutrient.get("is_ai")),
                        ]
                    )
    else:
        for row in matching:
            typer.echo(f"{row.get('category', '?')} \u2014 {row.get('age_range', '?')}")
            nutrients = row.get("nutrients", {})
            if not nutrients:
                typer.echo("  (no nutrient values)")
            for name, nutrient in nutrients.items():
                if isinstance(nutrient, dict):
                    typer.echo(_dri_render_nutrient(name, nutrient))
    raise typer.Exit(code=0)


@dri_app.command("tables")
@dri_app.command("table")
def dri_tables(
    ctx: typer.Context,
    age_range: str | None = typer.Option(
        None, "--age-range", help='Only rows for this age range, e.g. "19-30 y" (tolerant matching).'
    ),
    category: str | None = typer.Option(
        None,
        "--category",
        help="Only rows for this life-stage category, e.g. Infants, Males, Females, Pregnancy, Lactation (case-insensitive).",
    ),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Show DRI tables (EAR/RDA-AI/UL per macronutrient) by age/sex group.

    Example:
      foodguide dri tables --age-range "19-30 y"
    """
    _run_dri_tables(ctx, age_range, category, format)


@dri_app.command("amdr")
def dri_amdr(
    ctx: typer.Context,
    age_range: str | None = typer.Option(
        None, "--age-range", help='Only AMDR rows for this age range, e.g. "4-18 y" (tolerant matching).'
    ),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Show Acceptable Macronutrient Distribution Ranges (AMDR) by age group.

    Example:
      foodguide dri amdr
    """
    fmt = format if format is not None else ctx.obj["format"]
    data = get_dri_data_manager().get_dri_data()
    amdrs = data.get("amdrs", {})
    matching = {
        age: values
        for age, values in amdrs.items()
        if age_range is None or _dri_age_match(age_range, str(age))
    }
    if not matching:
        _log(
            f"no AMDR rows match age_range={age_range!r}; "
            f"available age ranges: {', '.join(str(k) for k in amdrs) or 'none'}"
        )
        raise typer.Exit(code=1)

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(matching, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["age_range", "nutrient", "percent_range"])
        for age, values in matching.items():
            for nutrient, percent in values.items():
                writer.writerow([age, nutrient, percent])
    else:
        for age, values in matching.items():
            typer.echo(age)
            for nutrient, percent in values.items():
                typer.echo(f"  {nutrient.replace('_', ' ')}: {percent}")
    raise typer.Exit(code=0)


@dri_app.command("lookup")
def dri_lookup(
    ctx: typer.Context,
    age_range: str = typer.Option(
        ..., "--age-range", help='Age range to look up, e.g. "19-30 y" (tolerant matching).'
    ),
    nutrient: str = typer.Option(
        ..., "--nutrient", help="Nutrient name or alias, e.g. protein, carbs, fibre, water."
    ),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Look up one macronutrient's DRI values for an age range across categories.

    Example:
      foodguide dri lookup --age-range "19-30 y" --nutrient protein
    """
    fmt = format if format is not None else ctx.obj["format"]
    canonical = _resolve_dri_nutrient(nutrient)
    data = get_dri_data_manager().get_dri_data()
    rows = data.get("reference_values", [])
    if canonical is None:
        _log(
            f"unknown nutrient {nutrient!r}; available nutrients: "
            + ", ".join(_DRI_NUTRIENT_ALIASES)
        )
        raise typer.Exit(code=1)
    matching = [row for row in rows if _dri_age_match(age_range, str(row.get("age_range", "")))]
    if not matching:
        _log(
            f"no DRI rows match age_range={age_range!r}; "
            f"available age ranges: {', '.join(_dri_available_age_ranges(rows)) or 'none'}"
        )
        raise typer.Exit(code=1)

    matches = []
    for row in matching:
        nutrient_data = row.get("nutrients", {}).get(canonical)
        if isinstance(nutrient_data, dict):
            matches.append(
                {
                    "category": row.get("category", ""),
                    "age_range": row.get("age_range", ""),
                    "nutrient": canonical,
                    "values": nutrient_data,
                }
            )
    if not matches:
        _log(f"nutrient {canonical!r} has no values for age range {age_range!r}")
        raise typer.Exit(code=1)

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(matches, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["category", "age_range", "nutrient", "field", "value", "is_ai"])
        for match in matches:
            pairs = _dri_nutrient_value_pairs(match["values"])
            if not pairs:
                writer.writerow(
                    [match["category"], match["age_range"], match["nutrient"], "", "", bool(match["values"].get("is_ai"))]
                )
            for field, value in pairs:
                writer.writerow(
                    [
                        match["category"],
                        match["age_range"],
                        match["nutrient"],
                        field,
                        value,
                        bool(match["values"].get("is_ai")),
                    ]
                )
    else:
        for match in matches:
            typer.echo(f"{match['category']} \u2014 {match['age_range']}")
            typer.echo(_dri_render_nutrient(match["nutrient"], match["values"]))
    raise typer.Exit(code=0)


# ---------------------------------------------------------------- eer

eer_app = typer.Typer(
    name="eer",
    help=(
        "Estimated Energy Requirement: Health Canada / Institute of "
        "Medicine EER equations (offline: data-dir snapshot first, bundled "
        "fallback; refresh with `foodguide data build eer`)."
    ),
    epilog=(
        "Examples:\n"
        "  foodguide eer calc --sex male --age 30 --weight-kg 70 --height-cm 175\n"
        "  foodguide eer equations --type adult --pal active --format csv\n"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(eer_app, help="Estimated Energy Requirement calculations")


@eer_app.command("calc")
def eer_calc(
    ctx: typer.Context,
    sex: str = typer.Option(..., "--sex", help="Sex: male or female (m/f accepted)."),
    age: float = typer.Option(..., "--age", help="Age in years (e.g. 30, or 1.5 for 18 months)."),
    weight_kg: float = typer.Option(..., "--weight-kg", help="Weight in kilograms."),
    height_cm: float = typer.Option(..., "--height-cm", help="Height in centimetres."),
    pal: str = typer.Option(
        "active", "--pal", help="Physical activity level: inactive, low_active, active or very_active."
    ),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Compute EER from age, sex, height, weight and physical activity level (PAL).

    Example:
      foodguide eer calc --sex male --age 30 --weight-kg 70 --height-cm 175
    """
    fmt = format if format is not None else ctx.obj["format"]
    data = get_eer_data_manager().get_eer_data()
    try:
        result = calculate_eer(data, sex, age, weight_kg, height_cm, pal)
    except ValueError as exc:
        _log(str(exc))
        raise typer.Exit(code=1) from None
    inputs = {
        "sex": sex,
        "age_years": age,
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "pal": pal,
    }

    if fmt == OutputFormat.json:
        typer.echo(json.dumps({**result, "inputs": inputs}, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["eer_kcal", "sex", "age_years", "weight_kg", "height_cm", "pal", "formula"])
        writer.writerow(
            [
                result["eer_kcal"],
                sex,
                age,
                weight_kg,
                height_cm,
                result["pal"],
                result["formula"],
            ]
        )
    else:
        typer.echo(
            f"EER ({sex}, {age:g} y, {weight_kg:.1f} kg, {height_cm:.1f} cm, {result['pal']}):"
            f" {result['eer_kcal']} kcal/day"
        )
        typer.echo(f"formula: {result['formula']}")
        if result.get("growth_constant") is not None:
            typer.echo(f"growth constant: {result['growth_constant']} kcal/day")
    raise typer.Exit(code=0)


@eer_app.command("equations")
def eer_equations(
    ctx: typer.Context,
    type: str = typer.Option(
        "all",
        "--type",
        help="Equation family: adult, child, pregnancy, lactation or all.",
    ),
    pal: str = typer.Option(
        "all",
        "--pal",
        help="Physical activity level filter: inactive, low_active, active, very_active or all.",
    ),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """List the Health Canada EER equations and their variables.

    Example:
      foodguide eer equations --type adult --pal active
    """
    fmt = format if format is not None else ctx.obj["format"]
    equation_type = _resolve_eer_type(type)
    pal_category = _resolve_eer_pal(pal)
    payload = get_eer_data_manager().get_equations(equation_type, pal_category)

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        raise typer.Exit(code=0)

    rows = _eer_formula_rows(payload.get("equations", {}))
    if not rows:
        _log(f"no EER equations match type={equation_type!r} pal={pal_category!r}")
        raise typer.Exit(code=1)

    if fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["section", "who", "pal", "formula"])
        for section, who, pal_key, formula in rows:
            writer.writerow([section, who, pal_key, formula])
        raise typer.Exit(code=0)

    sections = payload.get("equations", {})
    for section_key, section in sections.items():
        if not isinstance(section, dict):
            continue
        typer.echo(f"{section_key} ({section.get('age_range', '?')}): {section.get('description', '')}")
        if section.get("note"):
            typer.echo(f"  note: {section['note']}")
        for row_section, who, pal_key, formula in rows:
            if row_section != section_key:
                continue
            label = " ".join(part for part in (who, f"({pal_key})" if pal_key else "") if part)
            typer.echo(f"  {label}: {formula}" if label else f"  {formula}")
        for sex in ("male", "female"):
            entry = section.get(sex)
            if isinstance(entry, dict) and isinstance(entry.get("growth_constants"), dict):
                constants = ", ".join(f"{k}={v:g}" for k, v in entry["growth_constants"].items())
                typer.echo(f"  {sex} growth constants (kcal/day): {constants}")
        if isinstance(section.get("milk_energy_constants"), dict):
            constants = ", ".join(
                f"{k}={v.get('total_addition_kcal', '?'):g}"
                for k, v in section["milk_energy_constants"].items()
                if isinstance(v, dict)
            )
            typer.echo(f"  milk energy constants (kcal/day): {constants}")
    raise typer.Exit(code=0)


# ---------------------------------------------------------------- recipes

def _recipe_csv_value(value: object) -> str:
    """Render a recipe field as a single CSV cell (lists become 'a; b; c')."""
    if isinstance(value, list):
        return "; ".join(
            _recipe_csv_value(item) if isinstance(item, (list, dict)) else str(item)
            for item in value
        )
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_recipe_csv_value(val)}" for key, val in value.items())
    return "" if value is None else str(value)


def _table_line(left: str, middle: str, right: str, w1: int, w2: int) -> str:
    return f"{left:<{w1}}  {middle:<{w2}}  {right}"


recipes_app = typer.Typer(
    name="recipes",
    help=(
        "Search and read Health Canada Food Guide recipes from the offline "
        "recipes.json data file (build it with `foodguide data build recipes`)."
    ),
    epilog=(
        "Examples:\n"
        "  foodguide recipes search lentil\n"
        "  foodguide recipes search --tag collection__vegetarian --limit 5\n"
        "  foodguide recipes search \"apple\" --tag meal__breakfast --format json"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(recipes_app, help="Recipe search and lookups (offline recipes.json)")


@recipes_app.command("search")
def recipes_search(
    ctx: typer.Context,
    query: str = typer.Argument("", help="Text to look for in titles, intros, ingredients and directions."),
    tag: list[str] | None = typer.Option(
        None,
        "--tag",
        "-t",
        help=(
            "Only recipes carrying this tag; repeatable (all must match). "
            "Accepts raw tags (meal__snack) or human labels (Snack)."
        ),
    ),
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of results."),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Search Food Guide recipes by text and tags (offline recipes.json).

    Example:
      foodguide recipes search lentil
    """
    fmt = format if format is not None else ctx.obj["format"]
    source = LocalRecipeSource()
    try:
        results = source.search(
            search_text=query or "",
            tags=list(tag) if tag else None,
            limit=limit,
        )
    except RuntimeError as exc:
        _log(str(exc))
        raise typer.Exit(code=1) from None

    if not results:
        typer.echo("No recipes match.")
        raise typer.Exit(code=0)

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(results, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["title", "slug", "tags"])
        for row in results:
            writer.writerow([row["title"], row["slug"], ", ".join(row["tags"])])
    else:
        widths = [
            max(len(row[key]) for row in results)
            for key in ("title", "slug")
        ]
        for row in results:
            typer.echo(
                _table_line(
                    row["title"], row["slug"], ", ".join(row["tags"]), widths[0], widths[1]
                )
            )
    raise typer.Exit(code=0)


@recipes_app.command("show")
def recipes_show(
    ctx: typer.Context,
    slug: str = typer.Argument(..., help="Recipe slug or canada.ca recipe URL."),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Show the full record for one recipe (slug or URL accepted).

    Example:
      foodguide recipes show apple-berry-crisp
    """
    fmt = format if format is not None else ctx.obj["format"]
    source = LocalRecipeSource()
    try:
        recipe = source.get_recipe(slug)
    except RuntimeError as exc:
        _log(str(exc))
        raise typer.Exit(code=1) from None
    if recipe is None:
        _log(
            f"Recipe '{slug}' not found in local data. "
            "Run `foodguide data build recipes` to refresh."
        )
        raise typer.Exit(code=1)

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(recipe, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["key", "value"])
        for key, value in recipe.items():
            writer.writerow([key, _recipe_csv_value(value)])
    else:
        typer.echo(f"Title: {recipe['title']}")
        typer.echo(f"URL: {recipe['url']}")
        typer.echo(f"Tags: {', '.join(recipe['tags'])}")
        stats = [
            f"{label}: {recipe[key]}"
            for label, key in (
                ("Prep time", "prep_time"),
                ("Cook time", "cook_time"),
                ("Servings", "servings"),
            )
            if recipe[key]
        ]
        typer.echo(" / ".join(stats) if stats else "No timing information.")
        if recipe["intro"]:
            typer.echo(f"\n{recipe['intro']}")
        typer.echo("\nIngredients:")
        for group in recipe["ingredient_groups"]:
            if group["group"]:
                typer.echo(f"  {group['group']}")
            for item in group["items"]:
                typer.echo(f"  {item}" if not group["group"] else f"    {item}")
        typer.echo("\nDirections:")
        for i, step in enumerate(recipe["directions"], start=1):
            typer.echo(f"  {i}. {step}")
        if recipe["tips"]:
            typer.echo("\nTips:")
            for tip in recipe["tips"]:
                typer.echo(f"  - {tip}")
    raise typer.Exit(code=0)


@recipes_app.command("filters")
def recipes_filters(
    ctx: typer.Context,
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """List the recipe filter tags and their human labels.

    Example:
      foodguide recipes filters --format csv
    """
    fmt = format if format is not None else ctx.obj["format"]
    source = LocalRecipeSource()
    try:
        filters = source.list_filters()
    except RuntimeError as exc:
        _log(str(exc))
        raise typer.Exit(code=1) from None

    if fmt == OutputFormat.json:
        typer.echo(json.dumps(filters, indent=2, ensure_ascii=False))
    elif fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["tag", "label"])
        for tag, label in filters.items():
            writer.writerow([tag, label])
    else:
        width = max((len(tag) for tag in filters), default=3)
        for tag, label in filters.items():
            typer.echo(f"{tag:<{width}}  {label}")
    raise typer.Exit(code=0)


# ---------------------------------------------------------------- data

BUNDLED_DATA_FILES = ("dri_macronutrients.json", "eer_equations.json")
CNF_ZIP_FALLBACK_NAME = "cnf_fcen_all-files-data_2026.zip"
CNF_METADATA_URL = (
    f"https://open.canada.ca/data/api/3/action/package_show?id={DEFAULT_DATASET_ID}"
)


def _cnf_db_info() -> dict:
    """Describe the local CNF SQLite database, including its provenance."""
    status = cnf_db.db_status()
    if status is None:
        return {"built": False}
    return {
        "built": True,
        "path": status["path"],
        "size_bytes": status["size_bytes"],
        "provenance": status["provenance"],
    }


def _bundled_file_info() -> list[dict]:
    out = []
    for name in BUNDLED_DATA_FILES:
        res = files("foodguide.data").joinpath(name)
        raw = res.read_bytes()
        prov = _provenance(json.loads(raw))
        out.append({"file": name, "size_bytes": len(raw), "provenance": prov})
    return out


def _recipes_info() -> dict:
    """Describe the local recipes.json snapshot, including its provenance."""
    return LocalRecipeSource().status()


def _provenance_summary(provenance: object) -> str:
    """One-line provenance summary for table output ('-' when absent)."""
    if not isinstance(provenance, dict) or not provenance:
        return "-"
    parts = [str(provenance[key]) for key in ("source_url", "page_sha256", "page_date_modified", "fetched_at") if provenance.get(key)]
    return "; ".join(parts) if parts else "-"


def _dri_info() -> dict:
    """Describe the active DRI data source (data-dir file or bundled snapshot)."""
    return get_dri_data_manager().get_status()


def _eer_info() -> dict:
    """Describe the active EER data source (data-dir file or bundled snapshot)."""
    return get_eer_data_manager().get_status()


_RECIPES_PROVENANCE_KEYS = ("fetched_at", "index_sha256")


data_app = typer.Typer(
    name="data",
    help=(
        "Local data management: inspect the DRI/EER data files (data-dir "
        "snapshot first, bundled fallback — build the data-dir ones with "
        "`foodguide data build dri` / `foodguide data build eer`), the CNF "
        "SQLite database and the recipes.json recipe snapshot (built with "
        "`foodguide data build cnf` / `foodguide data build recipes`)."
    ),
    epilog=(
        "Examples:\n"
        "  foodguide data status --format json\n"
        "  foodguide data fetch --from-dir /path/to/release --dest ~/.local/state/foodguide\n"
        "  foodguide data manifest ./out\n"
        "  foodguide data changed old/manifest.json new/manifest.json"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(data_app, help="Local data management (DRI/EER snapshots, CNF database, recipes)")


@data_app.command("status")
def data_status(
    ctx: typer.Context,
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """List local data files: DRI/EER data (data-dir first, bundled fallback), CNF database, recipes.

    Example:
      foodguide data status --format json
    """
    fmt = format if format is not None else ctx.obj["format"]
    files_info = _bundled_file_info()
    cnf = _cnf_db_info()
    recipes = _recipes_info()
    dri = _dri_info()
    eer = _eer_info()
    install = pipeline_install.status(cnf_db.get_data_dir())

    if fmt == OutputFormat.json:
        typer.echo(
            json.dumps(
                {
                    "files": files_info,
                    "cnf_db": cnf,
                    "recipes": recipes,
                    "dri": dri,
                    "eer": eer,
                    "install": install,
                },
                indent=2,
            )
        )
        raise typer.Exit(code=0)

    if fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["file", "size_bytes", "provenance"])
        for info in files_info:
            writer.writerow([info["file"], info["size_bytes"], info["provenance"] or ""])
        for label, info in (("dri", dri), ("eer", eer)):
            writer.writerow([label, info.get("size_bytes") or "", f"{info.get('source')}: {info.get('path')}"])
            provenance = info.get("provenance")
            if isinstance(provenance, dict) and provenance:
                for key, value in sorted(provenance.items()):
                    writer.writerow([f"{label}_provenance", key, value])
        if cnf["built"]:
            writer.writerow(["cnf_db", cnf["size_bytes"], cnf["path"]])
            for key, value in sorted(cnf["provenance"].items()):
                writer.writerow(["cnf_provenance", key, value])
        else:
            writer.writerow(["cnf_db", "", "not built (run: foodguide data build cnf)"])
        if recipes["built"]:
            writer.writerow(["recipes_json", recipes["size_bytes"], recipes["path"]])
            for key in _RECIPES_PROVENANCE_KEYS:
                writer.writerow(["recipes_provenance", key, recipes[key]])
        else:
            writer.writerow(
                ["recipes_json", "", "not built (run: foodguide data build recipes)"]
            )
        if install.get("installed"):
            writer.writerow(
                ["install", "manifest_built_at", install["manifest"]["built_at"]]
            )
            for info in install["files"]:
                writer.writerow(["install", info["name"], info["state"]])
        raise typer.Exit(code=0)

    # table (default)
    width = max(len(info["file"]) for info in files_info)
    typer.echo(f"{'file':<{width}}  {'size_bytes':>10}  provenance")
    for info in files_info:
        prov = info["provenance"] or "-"
        typer.echo(f"{info['file']:<{width}}  {info['size_bytes']:>10}  {prov}")
    for label, info in (("DRI data", dri), ("EER data", eer)):
        source = info.get("source") or "unknown"
        path = info.get("path") or "?"
        size = info.get("size_bytes")
        size_text = f"{size} bytes" if size is not None else "size unknown"
        typer.echo(f"{label}: {path} ({size_text}, source: {source})")
        typer.echo(f"  provenance: {_provenance_summary(info.get('provenance'))}")
    if cnf["built"]:
        typer.echo(f"CNF database: {cnf['path']} ({cnf['size_bytes']} bytes)")
        for key, value in sorted(cnf["provenance"].items()):
            typer.echo(f"  {key}: {value}")
    else:
        typer.echo("CNF database: not built (run: foodguide data build cnf)")
    if recipes["built"]:
        typer.echo(f"Recipes data: {recipes['path']} ({recipes['size_bytes']} bytes)")
        for key in _RECIPES_PROVENANCE_KEYS:
            typer.echo(f"  {key}: {recipes[key]}")
    else:
        typer.echo("Recipes data: not built (run: foodguide data build recipes)")
    _echo_install_status(install)
    raise typer.Exit(code=0)


def _echo_install_status(install: dict) -> None:
    """Append the manifest install status (data-dir manifest.json) to table output."""
    if not install.get("installed"):
        typer.echo(
            "Installed release: no manifest.json in the data dir "
            "(run: foodguide data fetch --from-dir <release dir>)"
        )
        return
    md = install["manifest"]
    typer.echo(
        f"Installed release: built_at={md['built_at']} "
        f"package_version={md['package_version']} (manifest.json in the data dir)"
    )
    for info in install["files"]:
        if info["state"] == "ok":
            typer.echo(f"  {info['name']}: ok")
        else:
            typer.echo(
                f"  {info['name']}: {info['state']} "
                f"(expected sha256={info['expected_sha256']})"
            )
    if not install["all_ok"]:
        typer.echo("  some files do not match the manifest; re-run: foodguide data fetch")


# ---------------------------------------------------------------- data build


def _fetch_metadata_modified() -> str:
    """Best-effort dataset metadata_modified from open.canada.ca; 'unknown' offline."""
    try:
        response = requests.get(CNF_METADATA_URL, timeout=15)
        return str(response.json()["result"]["metadata_modified"])
    except Exception:
        return "unknown"


def _resolve_cnf_zip(zip_opt: Path | None) -> Path:
    """Find the CNF source zip; never download it."""
    candidates: list[Path] = []
    if zip_opt is not None:
        candidates.append(zip_opt)
    env_zip = os.environ.get("FOODGUIDE_CNF_ZIP")
    if env_zip:
        candidates.append(Path(env_zip).expanduser())
    candidates.append(cnf_db.get_data_dir() / CNF_ZIP_FALLBACK_NAME)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    _log(
        "no CNF zip found; pass --zip or set FOODGUIDE_CNF_ZIP; download the zip "
        f"from {DEFAULT_ZIP_URL} — the zip is NOT downloaded for you"
    )
    raise typer.Exit(code=1)


data_build_app = typer.Typer(
    name="build",
    help="Build local databases from source data.",
    epilog=(
        "Environment overrides (mainly for tests/dev):\n"
        "  FOODGUIDE_SOURCE_BASE_URL   serve Health Canada pages from another base,\n"
        "                              e.g. a local test server (build recipes/dri/eer)\n"
        "  FOODGUIDE_CKAN_PACKAGE_URL  override the CKAN package-show URL for --download-cnf\n"
        "  SOURCE_DATE_EPOCH           fixed build timestamp for reproducible builds (build cnf)\n"
        "  FOODGUIDE_CNF_ZIP           CNF zip path (build cnf)\n\n"
        "Example:\n  foodguide data build cnf --zip cnf_fcen_all-files-data_2026.zip"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
data_app.add_typer(data_build_app, help="Build local databases from source data")


@data_build_app.command("cnf")
def data_build_cnf(
    zip: Path | None = typer.Option(
        None,
        "--zip",
        help="Path to the CNF zip (otherwise FOODGUIDE_CNF_ZIP, or a file in the data dir). Never downloaded.",
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Output SQLite path (default: <data dir>/cnf.sqlite)."
    ),
    metadata_modified: str | None = typer.Option(
        None,
        "--metadata-modified",
        help="Dataset last-modified timestamp to record (fetched from open.canada.ca by default).",
    ),
    no_fetch_metadata: bool = typer.Option(
        False,
        "--no-fetch-metadata",
        help="Skip the metadata lookup and record 'unknown' (offline-safe).",
    ),
) -> None:
    """Build the local CNF SQLite database from the Health Canada CNF 2026 zip.

    The zip is never downloaded by this command. The output is always these
    human-readable summary lines; the global --format option is ignored.

    Example:
      foodguide data build cnf --zip cnf_fcen_all-files-data_2026.zip
    """
    zip_path = _resolve_cnf_zip(zip)
    out_path = out if out is not None else cnf_db.get_cnf_db_path()
    if metadata_modified is not None:
        modified = metadata_modified
    elif no_fetch_metadata:
        modified = "unknown"
    else:
        modified = _fetch_metadata_modified()
    try:
        result = build_cnf_db(zip_path, out_path, metadata_modified=modified)
    except Exception as exc:
        _log(f"CNF build failed: {exc}")
        raise typer.Exit(code=1) from None
    typer.echo(f"Built {result.out_path}")
    typer.echo(f"  foods: {result.rows['food']}")
    typer.echo(f"  nutrient_amounts: {result.rows['nutrient_amount']}")
    typer.echo(f"  measures: {result.rows['measure_name']}")
    typer.echo(f"  conversions: {result.rows['measure_weight_conversion']}")
    typer.echo(f"  size: {result.size_bytes} bytes")
    typer.echo(f"  content_hash: {result.content_hash}")
    typer.echo(f"  zip_sha256: {result.zip_sha256}")
    typer.echo(f"  build_time: {result.build_time}")


@data_build_app.command("recipes")
def data_build_recipes(
    out: Path | None = typer.Option(
        None, "--out", help="Output path (default: <data dir>/recipes.json)."
    ),
    max_recipes: int | None = typer.Option(
        None,
        "--max-recipes",
        help="Development option: crawl only the first N recipes in index order",
    ),
    only: str | None = typer.Option(
        None,
        "--only",
        help="Development option: comma-separated recipe slugs to crawl",
    ),
) -> None:
    """Crawl the canada.ca recipe pages and build the offline recipes.json.

    The output is always these human-readable summary lines; the global
    --format option is ignored.

    Example:
      foodguide data build recipes
    """
    only_slugs: list[str] | None = None
    if only is not None:
        only_slugs = [slug.strip() for slug in only.split(",") if slug.strip()]
        if not only_slugs:
            _log("--only did not contain any recipe slugs (comma-separated)")
            raise typer.Exit(code=1)
    out_path = out if out is not None else recipes_data_path()
    try:
        summary = build_recipes_json(
            out_path, only=only_slugs, max_recipes=max_recipes
        )
    except (ValueError, RuntimeError, OSError) as exc:
        _log(f"Recipes build failed: {exc}")
        raise typer.Exit(code=1) from None
    typer.echo(f"Built {summary['path']}")
    typer.echo(f"  recipes: {summary['recipe_count']}")
    typer.echo(f"  filters: {summary['filter_count']}")
    typer.echo(f"  size: {summary['size_bytes']} bytes")
    typer.echo(f"  index_sha256: {summary['index_sha256']}")
    typer.echo(f"  build_time: {summary['build_time']}")


@data_build_app.command("dri")
def data_build_dri(
    out: Path | None = typer.Option(
        None, "--out", help="Output path (default: <data dir>/dri_macronutrients.json)."
    ),
) -> None:
    """Fetch the Health Canada DRI macronutrients page and write dri_macronutrients.json.

    The output is always these human-readable summary lines; the global
    --format option is ignored. Once written to the data dir, the file takes
    priority over the bundled snapshot for all offline lookups.

    Example:
      foodguide data build dri
    """
    out_path = out if out is not None else cnf_db.get_data_dir() / "dri_macronutrients.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        summary = build_dri(out_path)
    except BuildError as exc:
        _log(f"DRI build failed: {exc}")
        raise typer.Exit(code=1) from None
    typer.echo(f"Built {summary['path']}")
    typer.echo(f"  size: {summary['size_bytes']} bytes")
    typer.echo(f"  page_sha256: {summary['page_sha256']}")
    typer.echo(f"  page_date_modified: {summary['page_date_modified']}")
    typer.echo(f"  fetched_at: {summary['fetched_at']}")


@data_build_app.command("eer")
def data_build_eer(
    out: Path | None = typer.Option(
        None, "--out", help="Output path (default: <data dir>/eer_equations.json)."
    ),
) -> None:
    """Fetch the Health Canada EER equations page and write eer_equations.json.

    The output is always these human-readable summary lines; the global
    --format option is ignored. Once written to the data dir, the file takes
    priority over the bundled snapshot for all offline lookups.

    Example:
      foodguide data build eer
    """
    out_path = out if out is not None else cnf_db.get_data_dir() / "eer_equations.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        summary = build_eer(out_path)
    except BuildError as exc:
        _log(f"EER build failed: {exc}")
        raise typer.Exit(code=1) from None
    typer.echo(f"Built {summary['path']}")
    typer.echo(f"  size: {summary['size_bytes']} bytes")
    typer.echo(f"  page_sha256: {summary['page_sha256']}")
    typer.echo(f"  page_date_modified: {summary['page_date_modified']}")
    typer.echo(f"  fetched_at: {summary['fetched_at']}")


@data_build_app.command("all")
def data_build_all(
    cnf_zip: Path | None = typer.Option(
        None,
        "--cnf-zip",
        help="Path to the CNF zip (otherwise --download-cnf is required, or --skip cnf).",
    ),
    download_cnf: bool = typer.Option(
        False,
        "--download-cnf",
        help="Find the CNF zip URL in the open.canada.ca CKAN record, download it "
        "(temporary, never published) and record its sha256.",
    ),
    out_dir: Path = typer.Option(
        ..., "--out-dir", help="Directory every dataset is built into."
    ),
    skip: list[str] = typer.Option(
        [],
        "--skip",
        help="Skip a dataset (cnf, recipes, dri, eer); repeatable.",
    ),
    max_recipes: int | None = typer.Option(
        None,
        "--max-recipes",
        help="Development option: crawl only the first N recipes in index order",
    ),
    only: str | None = typer.Option(
        None,
        "--only",
        help="Development option: comma-separated recipe slugs to crawl",
    ),
) -> None:
    """Build every dataset into one directory, then write manifest.json.

    Builds cnf.sqlite (+ cnf.sqlite.gz, gzip with mtime 0), recipes.json,
    dri_macronutrients.json and eer_equations.json into a temporary directory
    and only moves them into --out-dir when every builder succeeded — a
    failure never leaves a partial output directory. manifest.json records
    per-file sha256/size, content hashes, record counts and upstream version
    info, so `foodguide data changed` can compare two builds and `foodguide
    data fetch` can verify a release.

    Example:
      foodguide data build all --cnf-zip cnf.zip --out-dir ./out
    """
    if cnf_zip is not None and download_cnf:
        _log("--cnf-zip and --download-cnf are mutually exclusive")
        raise typer.Exit(code=2)
    only_slugs: list[str] | None = None
    if only is not None:
        only_slugs = [slug.strip() for slug in only.split(",") if slug.strip()]
        if not only_slugs:
            _log("--only did not contain any recipe slugs (comma-separated)")
            raise typer.Exit(code=1)
    metadata_modified = None
    if cnf_zip is not None and not download_cnf:
        # Best-effort: 'unknown' when the CKAN metadata lookup fails offline.
        metadata_modified = _fetch_metadata_modified()
    pipeline_build_all.run_build_all(
        out_dir,
        cnf_zip=cnf_zip,
        download_cnf=download_cnf,
        skip=list(skip),
        log=_log,
        metadata_modified=metadata_modified,
        recipes_only=only_slugs,
        max_recipes=max_recipes,
    )


# ---------------------------------------------------------------- manifest /
# ---------------------------------------------------------------- changed / fetch


def _manifest_or_exit(path: Path) -> dict:
    """Load a manifest file or exit 1 with a clear message."""
    try:
        return load_manifest(path)
    except ManifestError as exc:
        _log(f"invalid manifest {path}: {exc}")
        raise typer.Exit(code=1) from None


@data_app.command("manifest")
def data_manifest(
    ctx: typer.Context,
    directory: Path = typer.Argument(
        ..., help="Directory containing the built dataset files."
    ),
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """Write manifest.json in DIR describing its dataset files.

    Scans DIR for cnf.sqlite(.gz), recipes.json, dri_macronutrients.json and
    eer_equations.json and records per-file sha256/size, content hashes,
    record counts and upstream version info. Run automatically by
    `foodguide data build all`.

    Example:
      foodguide data manifest ./out --format json
    """
    try:
        manifest = write_manifest(directory)
    except ManifestError as exc:
        _log(f"manifest failed: {exc}")
        raise typer.Exit(code=1) from None
    fmt = format if format is not None else ctx.obj["format"]
    if fmt == OutputFormat.json:
        typer.echo(json.dumps(manifest, indent=2, sort_keys=True))
        raise typer.Exit(code=0)
    typer.echo(f"Wrote {directory / 'manifest.json'}")
    typer.echo(f"  built_at: {manifest['built_at']}")
    typer.echo(f"  package_version: {manifest['package_version']}")
    for name in sorted(manifest["datasets"]):
        entry = manifest["datasets"][name]
        typer.echo(f"  {name}: {entry['size']} bytes, sha256={entry['sha256']}")
    raise typer.Exit(code=0)


@data_app.command("changed")
def data_changed(
    old: Path = typer.Argument(..., help="Old manifest.json path."),
    new: Path = typer.Argument(..., help="New manifest.json path."),
) -> None:
    """Exit 0 and print nothing when the datasets are equivalent; else exit 10.

    Compares content identities (CNF content_hash, recipes index_sha256 +
    recipe count, DRI/EER page_sha256 + date modified), ignoring built_at,
    package_version and gzip bytes. Prints one changed dataset per line.

    Example:
      foodguide data changed data1/manifest.json data2/manifest.json
    """
    old_manifest = _manifest_or_exit(old)
    new_manifest = _manifest_or_exit(new)
    try:
        changed = changed_datasets(old_manifest, new_manifest)
    except ManifestError as exc:
        _log(f"cannot compare manifests: {exc}")
        raise typer.Exit(code=1) from None
    if not changed:
        raise typer.Exit(code=0)
    for name in changed:
        typer.echo(name)
    raise typer.Exit(code=10)


@data_app.command("fetch")
def data_fetch(
    tag: str = typer.Option(
        pipeline_install.DEFAULT_TAG, "--tag", help="Release tag to fetch."
    ),
    repo: str = typer.Option(
        pipeline_install.DEFAULT_REPO,
        "--repo",
        help="GitHub repository (owner/name) publishing the data release.",
    ),
    from_dir: Path | None = typer.Option(
        None,
        "--from-dir",
        help="Install from a local release directory instead of GitHub.",
    ),
    dest: Path | None = typer.Option(
        None,
        "--dest",
        help="Data dir to install into (default: the foodguide data dir).",
    ),
    only: list[str] = typer.Option(
        [],
        "--only",
        help="Install only these datasets (cnf, recipes, dri, eer); repeatable.",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Override the release download base URL (tests and mirrors).",
    ),
) -> None:
    """Install datasets from a data release (GitHub release or local dir).

    Plain HTTPS, no token needed: assets are downloaded from
    https://github.com/<repo>/releases/download/<tag>/<asset>. manifest.json
    is fetched first and every asset is verified against it before anything
    is written; cnf.sqlite is installed by decompressing cnf.sqlite.gz.
    Idempotent: files already matching the manifest are skipped.

    Examples:
      foodguide data fetch --tag data-latest
      foodguide data fetch --from-dir ./release --dest ./data
    """
    dest_dir = dest if dest is not None else cnf_db.get_data_dir()
    try:
        if from_dir is not None:
            installed = pipeline_install.fetch_from_dir(
                from_dir, dest_dir, only=list(only), log=_log
            )
        else:
            installed = pipeline_install.fetch_from_http(
                repo, tag, dest_dir, only=list(only), base_url=base_url, log=_log
            )
    except (pipeline_install.FetchError, ManifestError) as exc:
        _log(f"fetch failed: {exc}")
        raise typer.Exit(code=1) from None
    for record in installed:
        upstream = record.get("upstream") or {}
        upstream_text = ", ".join(f"{k}={v}" for k, v in sorted(upstream.items()))
        typer.echo(f"{record['name']}: {record['size']} bytes, sha256={record['sha256']}")
        if record.get("content_hash"):
            typer.echo(f"  content_hash: {record['content_hash']}")
        if upstream_text:
            typer.echo(f"  upstream: {upstream_text}")
        typer.echo(f"  source: {record['source']}")
    if not installed:
        typer.echo("already up to date; nothing installed")


# ---------------------------------------------------------------- version


@app.command("version")
def version() -> None:
    """Print the foodguide version.

    Example:
      foodguide version
    """
    typer.echo(f"foodguide {_package_version()}")


def main():
    app()


if __name__ == "__main__":
    main()
