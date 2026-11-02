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

from foodguide.cnf import db as cnf_db
from foodguide.cnf.builder import DEFAULT_DATASET_ID, DEFAULT_ZIP_URL, build_cnf_db

# ---------------------------------------------------------------- helpers


class OutputFormat(str, Enum):
    """Formats supported by the global --format option."""

    table = "table"
    csv = "csv"
    json = "json"


def _log(message: str) -> None:
    """Write a log line to stderr (never stdout)."""
    typer.echo(message, err=True)


def _stub(ticket: str) -> None:
    """Print the standard stub message for an unimplemented command and exit 1."""
    _log(f"not implemented yet ({ticket})")
    raise typer.Exit(code=1)


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


# ---------------------------------------------------------------- dri

dri_app = typer.Typer(
    name="dri",
    help=(
        "Dietary Reference Intakes: reference values for macronutrients "
        "by age/sex group, from the bundled Health Canada DRI snapshot."
    ),
    epilog="Example:\n  foodguide dri tables",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(dri_app, help="Dietary Reference Intakes lookups")


@dri_app.command("tables")
def dri_tables() -> None:
    """Show DRI tables (RDA/AI per macronutrient) by age/sex group.

    Example:
      foodguide dri tables
    """
    _stub("HOM-77")


@dri_app.command("amdr")
def dri_amdr() -> None:
    """Show Acceptable Macronutrient Distribution Ranges (AMDR).

    Example:
      foodguide dri amdr
    """
    _stub("HOM-77")


# ---------------------------------------------------------------- eer

eer_app = typer.Typer(
    name="eer",
    help=(
        "Estimated Energy Requirement: Health Canada / Institute of "
        "Medicine EER equations from the bundled snapshot."
    ),
    epilog="Example:\n  foodguide eer calc --age 35 --sex male",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(eer_app, help="Estimated Energy Requirement calculations")


@eer_app.command("calc")
def eer_calc() -> None:
    """Compute EER from age, sex, height, weight and physical activity level (PAL).

    Example:
      foodguide eer calc --age 35 --sex male
    """
    _stub("HOM-78")


@eer_app.command("equations")
def eer_equations() -> None:
    """List the Health Canada EER equations and their variables.

    Example:
      foodguide eer equations
    """
    _stub("HOM-78")


# ---------------------------------------------------------------- recipe

recipe_app = typer.Typer(
    name="recipe",
    help=(
        "Recipe search and fetch tools. The original recipe source is "
        "unavailable (see HOM-79); these commands are stubs."
    ),
    epilog="Example:\n  foodguide recipe search chicken",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(recipe_app, help="Recipe tools (source moved; see HOM-79)")


@recipe_app.command("search")
def recipe_search(
    query: str = typer.Argument(..., help="Recipe search query."),
) -> None:
    """Search recipes by query.

    Example:
      foodguide recipe search chicken
    """
    _log("recipe source moved, see HOM-79")
    raise typer.Exit(code=1)


@recipe_app.command("fetch")
def recipe_fetch(
    url: str = typer.Argument(..., help="URL of the recipe page to fetch."),
) -> None:
    """Fetch and parse a recipe from a URL.

    Example:
      foodguide recipe fetch https://example.com/recipe
    """
    _log("recipe source moved, see HOM-79")
    raise typer.Exit(code=1)


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


data_app = typer.Typer(
    name="data",
    help=(
        "Local data management: inspect bundled DRI/EER snapshots and the "
        "CNF SQLite database (build it with `foodguide data build cnf`)."
    ),
    epilog="Example:\n  foodguide data status --format json",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(data_app, help="Local data management (bundled snapshots, CNF database)")


@data_app.command("status")
def data_status(
    ctx: typer.Context,
    format: OutputFormat | None = typer.Option(
        None, "--format", help="Output format for data on stdout"
    ),
) -> None:
    """List local data files: bundled DRI/EER snapshots and the CNF database.

    Example:
      foodguide data status --format json
    """
    fmt = format if format is not None else ctx.obj["format"]
    files_info = _bundled_file_info()
    cnf = _cnf_db_info()

    if fmt == OutputFormat.json:
        typer.echo(json.dumps({"files": files_info, "cnf_db": cnf}, indent=2))
        raise typer.Exit(code=0)

    if fmt == OutputFormat.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["file", "size_bytes", "provenance"])
        for info in files_info:
            writer.writerow([info["file"], info["size_bytes"], info["provenance"] or ""])
        if cnf["built"]:
            writer.writerow(["cnf_db", cnf["size_bytes"], cnf["path"]])
            for key, value in sorted(cnf["provenance"].items()):
                writer.writerow(["cnf_provenance", key, value])
        else:
            writer.writerow(["cnf_db", "", "not built (run: foodguide data build cnf)"])
        raise typer.Exit(code=0)

    # table (default)
    width = max(len(info["file"]) for info in files_info)
    typer.echo(f"{'file':<{width}}  {'size_bytes':>10}  provenance")
    for info in files_info:
        prov = info["provenance"] or "-"
        typer.echo(f"{info['file']:<{width}}  {info['size_bytes']:>10}  {prov}")
    if cnf["built"]:
        typer.echo(f"CNF database: {cnf['path']} ({cnf['size_bytes']} bytes)")
        for key, value in sorted(cnf["provenance"].items()):
            typer.echo(f"  {key}: {value}")
    else:
        typer.echo("CNF database: not built (run: foodguide data build cnf)")
    raise typer.Exit(code=0)


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
    epilog="Example:\n  foodguide data build cnf --zip cnf_fcen_all-files-data_2026.zip",
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
