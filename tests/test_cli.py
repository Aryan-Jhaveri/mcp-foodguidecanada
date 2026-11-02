"""Tests for the foodguide typer CLI (offline, via typer.testing.CliRunner)."""

import json

from typer.testing import CliRunner

from foodguide.cli import app

runner = CliRunner()


def test_help_shows_all_command_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("cnf", "dri", "eer", "recipe", "data", "version"):
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


def test_dri_tables_stub_exits_1() -> None:
    result = runner.invoke(app, ["dri", "tables"])
    assert result.exit_code == 1


def test_recipe_search_stub_exits_1() -> None:
    result = runner.invoke(app, ["recipe", "search", "x"])
    assert result.exit_code == 1


def test_unknown_command_exits_2() -> None:
    result = runner.invoke(app, ["definitely-not-a-command"])
    assert result.exit_code == 2
