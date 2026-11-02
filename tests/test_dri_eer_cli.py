"""Tests for the DRI/EER CLI commands (typer CliRunner, offline fixtures).

`foodguide data build dri|eer` is exercised by monkeypatching
foodguide.builders.dri_eer.HttpFetcher.fetch to serve the minimal fixtures,
so the commands are tested end-to-end without the network.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from foodguide import data_manager
from foodguide.builders.dri_eer import (
    DRI_URL,
    EER_URL,
    BuildError,
    _provenance,
    _write_payload,
    parse_dri_page,
    parse_eer_page,
)
from foodguide.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures" / "dri_eer"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """FOODGUIDE_DATA_DIR on a tmp dir; manager singletons reset per test."""
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data_manager, "_dri_manager", None, raising=False)
    monkeypatch.setattr(data_manager, "_eer_manager", None, raising=False)
    return tmp_path


def _inject_fixture_builders(monkeypatch, html_by_url: dict):
    """Replace the CLI's imported build_dri/build_eer with fixture-backed versions.

    The real build_dri/build_eer run the full-page validator (22 DRI rows and
    every EER band present), which the minimal hand-written fixtures cannot
    satisfy; these substitutes parse the fixture with the real parser and write
    through the real payload writer, so only the validation step is skipped.
    """
    from bs4 import BeautifulSoup

    def build_dri(out_path, fetcher=None):
        html = html_by_url[DRI_URL]
        payload = parse_dri_page(html)
        payload["_provenance"] = _provenance(DRI_URL, html, BeautifulSoup(html, "html.parser"))
        return _write_payload(Path(out_path), payload)

    def build_eer(out_path, fetcher=None):
        html = html_by_url[EER_URL]
        payload = parse_eer_page(html)
        payload["_provenance"] = _provenance(EER_URL, html, BeautifulSoup(html, "html.parser"))
        return _write_payload(Path(out_path), payload)

    monkeypatch.setattr("foodguide.cli.build_dri", build_dri)
    monkeypatch.setattr("foodguide.cli.build_eer", build_eer)


# ---------------------------------------------------------------- data build


def test_data_build_dri_writes_file_and_status(data_dir, monkeypatch):
    _inject_fixture_builders(monkeypatch, {DRI_URL: _fixture("dri_minimal.html")})
    # Canonical data-dir filename: the data manager must pick this file up.
    out = data_dir / "dri_macronutrients.json"

    result = runner.invoke(app, ["data", "build", "dri", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Built" in result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert len(payload["reference_values"]) == 2
    assert payload["_provenance"]["source_url"] == DRI_URL

    status = json.loads(
        runner.invoke(app, ["data", "status", "--format", "json"]).output
    )
    assert status["dri"]["source"] == "data_dir"
    assert status["dri"]["path"] == str(out)


def test_data_build_eer_writes_file_and_status(data_dir, monkeypatch):
    _inject_fixture_builders(monkeypatch, {EER_URL: _fixture("eer_minimal.html")})
    out = data_dir / "eer_equations.json"

    result = runner.invoke(app, ["data", "build", "eer", "--out", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["equations"]["adult"]["male"]["active"]["coefficients"]["intercept"] == 1004.82
    assert payload["_provenance"]["source_url"] == EER_URL

    status = json.loads(
        runner.invoke(app, ["data", "status", "--format", "json"]).output
    )
    assert status["eer"]["source"] == "data_dir"


def test_data_build_dri_failure_exit_1_no_file(data_dir, monkeypatch):
    def build_dri(out_path, fetcher=None):
        raise BuildError("DRI page: missing table 'reference_values'")

    monkeypatch.setattr("foodguide.cli.build_dri", build_dri)
    out = data_dir / "dri_macronutrients.json"

    result = runner.invoke(app, ["data", "build", "dri", "--out", str(out)])
    assert result.exit_code == 1
    assert "DRI build failed" in result.output
    assert not out.exists()


def test_data_build_eer_failure_exit_1_no_file(data_dir, monkeypatch):
    def build_eer(out_path, fetcher=None):
        raise BuildError("EER page: missing section 'a5'")

    monkeypatch.setattr("foodguide.cli.build_eer", build_eer)
    out = data_dir / "eer_equations.json"

    result = runner.invoke(app, ["data", "build", "eer", "--out", str(out)])
    assert result.exit_code == 1
    assert "EER build failed" in result.output
    assert not out.exists()


# ---------------------------------------------------------------- dri lookups


def test_dri_tables_age_range_formats(data_dir):
    # Bundled snapshot serves the table (no data-dir file yet).
    table = runner.invoke(
        app, ["dri", "tables", "--age-range", "19-30 y", "--format", "table"]
    )
    assert table.exit_code == 0
    # The snapshot's NBSP is preserved verbatim in the rendered header.
    assert "19–30\xa0y" in table.stdout

    js = runner.invoke(
        app, ["dri", "tables", "--age-range", "19-30 y", "--format", "json"]
    )
    assert js.exit_code == 0
    rows = json.loads(js.stdout)
    assert rows
    assert all(row["age_range"] == "19–30\xa0y" for row in rows)

    csv = runner.invoke(
        app, ["dri", "tables", "--age-range", "19-30 y", "--format", "csv"]
    )
    assert csv.exit_code == 0
    assert "19–30" in csv.stdout


def test_dri_table_alias_same_output(data_dir):
    tables = runner.invoke(app, ["dri", "tables", "--age-range", "19-30 y"])
    alias = runner.invoke(app, ["dri", "table", "--age-range", "19-30 y"])
    assert tables.exit_code == alias.exit_code == 0
    assert tables.stdout == alias.stdout


def test_dri_lookup_protein(data_dir):
    table = runner.invoke(
        app, ["dri", "lookup", "--age-range", "19-30 y", "--nutrient", "protein"]
    )
    assert table.exit_code == 0
    assert "protein" in table.stdout
    assert "RDA/AI" in table.stdout

    js = runner.invoke(
        app,
        ["dri", "lookup", "--age-range", "19-30 y", "--nutrient", "protein", "--format", "json"],
    )
    assert js.exit_code == 0
    matches = json.loads(js.stdout)
    assert matches
    assert matches[0]["nutrient"] == "protein"
    assert matches[0]["values"]["rda_ai_g_day"] == 56.0
    assert matches[0]["category"] in ("Males", "Females")


def test_dri_lookup_unknown_nutrient(data_dir):
    result = runner.invoke(
        app, ["dri", "lookup", "--age-range", "19-30 y", "--nutrient", "vitamin-z"]
    )
    assert result.exit_code == 1


def test_dri_amdr_json(data_dir):
    result = runner.invoke(app, ["dri", "amdr", "--format", "json"])
    assert result.exit_code == 0
    amdrs = json.loads(result.stdout)
    assert amdrs
    first = next(iter(amdrs.values()))
    assert "carbohydrate_percent" in first
    assert "fat_percent" in first


# ---------------------------------------------------------------- eer commands


def test_eer_equations_adult_csv(data_dir):
    result = runner.invoke(
        app, ["eer", "equations", "--type", "adult", "--format", "csv"]
    )
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "section,who,pal,formula"
    assert any(line.startswith("adult,male,active,") for line in lines[1:])
    assert all(line.split(",")[0] == "adult" for line in lines[1:])


def test_eer_equations_pal_filter(data_dir):
    result = runner.invoke(
        app, ["eer", "equations", "--type", "adult", "--pal", "very_active", "--format", "csv"]
    )
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 3  # header + male + female
    assert "very_active" in lines[1]
    assert "-517.88" in lines[1]


def test_eer_calc_formats(data_dir):
    table = runner.invoke(
        app,
        ["eer", "calc", "--sex", "male", "--age", "30", "--weight-kg", "70",
         "--height-cm", "175", "--pal", "active"],
    )
    assert table.exit_code == 0
    assert "2934.6 kcal/day" in table.stdout
    assert "formula:" in table.stdout

    js = runner.invoke(
        app,
        ["eer", "calc", "--sex", "male", "--age", "30", "--weight-kg", "70",
         "--height-cm", "175", "--pal", "active", "--format", "json"],
    )
    assert js.exit_code == 0
    payload = json.loads(js.stdout)
    assert payload["eer_kcal"] == 2934.6
    assert payload["section"] == "adult"
    assert payload["inputs"]["pal"] == "active"

    csv = runner.invoke(
        app,
        ["eer", "calc", "--sex", "male", "--age", "30", "--weight-kg", "70",
         "--height-cm", "175", "--pal", "active", "--format", "csv"],
    )
    assert csv.exit_code == 0
    rows = csv.stdout.strip().splitlines()
    assert rows[0].startswith("eer_kcal,sex,age_years")
    assert rows[1].startswith("2934.6")


def test_eer_calc_bad_pal_exit_1(data_dir):
    result = runner.invoke(
        app,
        ["eer", "calc", "--sex", "male", "--age", "30", "--weight-kg", "70",
         "--height-cm", "175", "--pal", "hyperactive"],
    )
    assert result.exit_code == 1


# ---------------------------------------------------------------- data status


def test_data_status_json_has_dri_and_eer(data_dir):
    result = runner.invoke(app, ["data", "status", "--format", "json"])
    assert result.exit_code == 0
    status = json.loads(result.stdout)
    assert "dri" in status and "eer" in status
    for label in ("dri", "eer"):
        assert status[label]["source"] in ("data_dir", "bundled_snapshot")
        assert status[label]["size_bytes"]
