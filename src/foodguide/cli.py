"""foodguide command line interface (typer-based).

Entry point: ``foodguide = "foodguide.cli:main"``.

Exit codes: 0 = ok, 1 = error, 2 = usage (typer/click default).
All logs go to stderr; data output goes to stdout.
"""

import csv
import json
import sys
from enum import Enum
from importlib import metadata
from importlib.resources import files
from pathlib import Path

import typer

from foodguide import config

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
    epilog="Example:\n  foodguide data status\n  foodguide version",
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

cnf_app = typer.Typer(
    name="cnf",
    help=(
        "Query the Canadian Nutrient File (CNF). Backed by a local CNF "
        "SQLite database that is built by HOM-76; the database is not "
        "present yet, so these commands are stubs until then."
    ),
    epilog="Example:\n  foodguide cnf search milk",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
app.add_typer(cnf_app, help="Canadian Nutrient File query tools (CNF SQLite database, built by HOM-76)")


@cnf_app.command("search")
def cnf_search(
    term: str = typer.Argument(..., help="Food name or name fragment to search for."),
) -> None:
    """Search CNF foods by name.

    Example:
      foodguide cnf search milk
    """
    _stub("HOM-76")


@cnf_app.command("get")
def cnf_get(
    food_id: int = typer.Argument(..., help="CNF FoodID of the food to fetch."),
) -> None:
    """Show the full nutrient profile for one CNF food.

    Example:
      foodguide cnf get 586
    """
    _stub("HOM-76")


@cnf_app.command("nutrients")
def cnf_nutrients(
    food_id: int = typer.Argument(..., help="CNF FoodID of the food to summarize."),
) -> None:
    """Show core macronutrients (protein, fat, carbohydrate, energy) for one CNF food.

    Example:
      foodguide cnf nutrients 586
    """
    _stub("HOM-76")


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


def _cnf_db_info() -> dict:
    """Describe the local CNF SQLite database (built by HOM-76)."""
    db_path = Path(config.DB_FILE)
    if db_path.exists():
        return {
            "built": True,
            "path": str(db_path),
            "size_bytes": db_path.stat().st_size,
        }
    return {"built": False}


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
        "CNF SQLite database built by HOM-76."
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
        else:
            writer.writerow(["cnf_db", "", "not built (HOM-76 will build it)"])
        raise typer.Exit(code=0)

    # table (default)
    width = max(len(info["file"]) for info in files_info)
    typer.echo(f"{'file':<{width}}  {'size_bytes':>10}  provenance")
    for info in files_info:
        prov = info["provenance"] or "-"
        typer.echo(f"{info['file']:<{width}}  {info['size_bytes']:>10}  {prov}")
    if cnf["built"]:
        typer.echo(f"CNF database: {cnf['path']} ({cnf['size_bytes']} bytes)")
    else:
        typer.echo("CNF database: not built (HOM-76 will build it)")
    raise typer.Exit(code=0)


@data_app.command("build")
def data_build() -> None:
    """Build the local CNF SQLite database from Health Canada data.

    Example:
      foodguide data build
    """
    _stub("HOM-76")


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
