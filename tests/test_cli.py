"""Tests for the foodguide typer CLI (offline, via typer.testing.CliRunner)."""

import json

from typer.testing import CliRunner

from foodguide.cli import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"})


def test_help_shows_all_command_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("cnf", "dri", "eer", "recipes", "data", "version"):
        assert name in result.stdout


def test_version_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_data_status_json() -> None:
    result = runner.invoke(app, ["data", "status", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "cnf_db" in payload
    files = payload["files"]
    assert len(files) >= 2
    for info in files:
        assert "size_bytes" in info


def test_data_status_csv_header() -> None:
    result = runner.invoke(app, ["data", "status", "--format", "csv"])
    assert result.exit_code == 0
    assert result.stdout.startswith("file,size_bytes,provenance")


def test_dri_tables_offline_default_output() -> None:
    result = runner.invoke(app, ["dri", "tables"])
    assert result.exit_code == 0
    assert "Males" in result.stdout
    assert "protein" in result.stdout


def test_dri_table_alias_matches_tables() -> None:
    tables = runner.invoke(app, ["dri", "tables", "--age-range", "19-30 y", "--format", "json"])
    alias = runner.invoke(app, ["dri", "table", "--age-range", "19-30 y", "--format", "json"])
    assert tables.exit_code == 0
    assert alias.exit_code == 0
    assert json.loads(tables.stdout) == json.loads(alias.stdout)


def test_recipes_help_exits_0_and_lists_examples() -> None:
    result = runner.invoke(app, ["recipes", "--help"])
    assert result.exit_code == 0
    assert "foodguide recipes search lentil" in result.stdout
    assert "foodguide recipes search --tag collection__vegetarian --limit 5" in result.stdout


def test_recipes_search_missing_data_exits_1(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["recipes", "search", "no-such-thing-xyz"])
    assert result.exit_code == 1
    assert "Recipes data not found" in result.output
    assert "foodguide data build recipes" in result.output


def test_unknown_command_exits_2() -> None:
    result = runner.invoke(app, ["definitely-not-a-command"])
    assert result.exit_code == 2
