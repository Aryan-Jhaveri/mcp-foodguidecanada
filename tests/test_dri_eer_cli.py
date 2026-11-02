"""Tests for the DRI/EER CLI commands (typer CliRunner), with no mocks.

`foodguide data build dri|eer` is exercised against a real localhost
http.server serving the committed canada.ca fixture pages
(tests/pages_fixture.py): tests set ``FOODGUIDE_SOURCE_BASE_URL`` to the
server's base URL, so the REAL builders run — full-page validation included —
over a real HTTP round trip. Failure tests stage a truncated copy of the real
page (HTTP 200 with broken content) and assert the CLI exits 1 without
writing the output file. The lookup/calc/status commands need no server: they
read the bundled snapshot via ``FOODGUIDE_DATA_DIR``.
"""

import json

import pytest
from pages_fixture import FIXTURE_DIR as PAGES_FIXTURE_DIR
from pages_fixture import truncate_html
from typer.testing import CliRunner

from foodguide.cli import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"})


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """FOODGUIDE_DATA_DIR on a tmp dir; singletons are recreated per env change."""
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- data build


def test_data_build_dri_writes_file_and_status(data_dir, monkeypatch, pages_server):
    monkeypatch.setenv("FOODGUIDE_SOURCE_BASE_URL", pages_server.base_url)
    # Canonical data-dir filename: the data manager must pick this file up.
    out = data_dir / "dri_macronutrients.json"

    result = runner.invoke(app, ["data", "build", "dri", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Built" in result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert len(payload["reference_values"]) == 22  # full real-page validation
    assert payload["_provenance"]["source_url"] == pages_server.url("dri")

    status = json.loads(
        runner.invoke(app, ["data", "status", "--format", "json"]).output
    )
    assert status["dri"]["source"] == "data_dir"
    assert status["dri"]["path"] == str(out)


def test_data_build_eer_writes_file_and_status(data_dir, monkeypatch, pages_server):
    monkeypatch.setenv("FOODGUIDE_SOURCE_BASE_URL", pages_server.base_url)
    out = data_dir / "eer_equations.json"

    result = runner.invoke(app, ["data", "build", "eer", "--out", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["equations"]["adult"]["male"]["active"]["coefficients"]["intercept"] == 1004.82
    assert payload["_provenance"]["source_url"] == pages_server.url("eer")

    status = json.loads(
        runner.invoke(app, ["data", "status", "--format", "json"]).output
    )
    assert status["eer"]["source"] == "data_dir"


def test_data_build_dri_failure_exit_1_no_file(data_dir, monkeypatch, pages_server):
    monkeypatch.setenv("FOODGUIDE_SOURCE_BASE_URL", pages_server.base_url)
    # Truncate the REAL page mid-document: HTTP 200, but the real parser's
    # validator raises BuildError (missing table).
    dri_html = (PAGES_FIXTURE_DIR / "dri_macronutrients.html").read_text(encoding="utf-8")
    pages_server.stage({"dri": truncate_html(dri_html, 5000)})
    out = data_dir / "dri_macronutrients.json"

    result = runner.invoke(app, ["data", "build", "dri", "--out", str(out)])
    assert result.exit_code == 1
    assert "DRI build failed" in result.output
    assert "missing table" in result.output
    assert not out.exists()


def test_data_build_eer_failure_exit_1_no_file(data_dir, monkeypatch, pages_server):
    monkeypatch.setenv("FOODGUIDE_SOURCE_BASE_URL", pages_server.base_url)
    eer_html = (PAGES_FIXTURE_DIR / "eer_equations.html").read_text(encoding="utf-8")
    pages_server.stage({"eer": truncate_html(eer_html, 5000)})
    out = data_dir / "eer_equations.json"

    result = runner.invoke(app, ["data", "build", "eer", "--out", str(out)])
    assert result.exit_code == 1
    assert "EER build failed" in result.output
    assert "missing section" in result.output
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
