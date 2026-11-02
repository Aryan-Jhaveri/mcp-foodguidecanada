"""CLI tests for the CNF commands and data build/status (offline, mini fixture)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cnf_fixture import make_mini_zip
from typer.testing import CliRunner

from foodguide.cli import app
from foodguide.cnf.builder import build_cnf_db

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"})


@pytest.fixture()
def cnf_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mini CNF zip built into tmp_path, with FOODGUIDE_DATA_DIR pointed there."""
    zip_path = make_mini_zip(tmp_path / "mini_cnf.zip")
    build_cnf_db(zip_path, tmp_path / "cnf.sqlite")
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FOODGUIDE_CNF_ZIP", raising=False)
    return tmp_path


# --- search ----------------------------------------------------------------


def test_search_json_en_and_fr(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "search", "lentils", "--lang", "en", "--format", "json"])
    assert result.exit_code == 0
    hits = json.loads(result.stdout)
    assert {h["food_code"] for h in hits} == {100, 102}
    assert all(h["name_en"] and h["name_fr"] for h in hits)

    result = runner.invoke(app, ["cnf", "search", "lentilles", "--lang", "fr", "--format", "json"])
    assert result.exit_code == 0
    hits = json.loads(result.stdout)
    assert {h["food_code"] for h in hits} == {100, 102}


def test_search_limit_truncates(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "search", "lentils", "--limit", "1", "--format", "json"])
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)) == 1


def test_search_no_match_exits_0(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "search", "zzqq", "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []
    assert "no foods match" in result.stderr


# --- food ------------------------------------------------------------------


def test_food_json(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "food", "100", "--format", "json"])
    assert result.exit_code == 0
    food = json.loads(result.stdout)
    assert food["group_name_en"] == "Vegetables and vegetable products"
    assert food["name_fr"] == "Lentilles rouges, cuites"
    assert food["food_code"] == 100


def test_food_unknown_code_exits_1(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "food", "999"])
    assert result.exit_code == 1
    assert "999" in result.stderr


# --- nutrients -------------------------------------------------------------


def test_nutrients_per_100g_json(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "nutrients", "100", "--per", "100g", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["basis"] == {"type": "100g"}
    assert len(payload["nutrients"]) == 3
    prot = next(n for n in payload["nutrients"] if n["symbol"] == "PROT")
    assert prot["amount"] == 9.02
    assert prot["amount_text"] == "9.020000000"


def test_nutrients_filter_by_symbol_case_insensitive(cnf_env: Path) -> None:
    result = runner.invoke(
        app, ["cnf", "nutrients", "100", "--nutrient", "prot", "--nutrient", "KCAL", "--format", "json"]
    )
    assert result.exit_code == 0
    nutrients = json.loads(result.stdout)["nutrients"]
    assert {n["symbol"] for n in nutrients} == {"PROT", "KCAL"}


def test_nutrients_unknown_symbol_empty_exit_0(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "nutrients", "100", "--nutrient", "NOPE", "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["nutrients"] == []
    assert "NOPE" in result.stderr


def test_nutrients_measure_scaling(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "nutrients", "100", "--measure", "1 cup", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["basis"]["type"] == "measure"
    assert payload["basis"]["measure_code"] == 2
    assert payload["basis"]["description"] == "1 cup"
    assert payload["basis"]["grams"] == 198.0
    prot = next(n for n in payload["nutrients"] if n["symbol"] == "PROT")
    assert prot["amount"] == pytest.approx(9.02 * 198 / 100)
    assert prot["amount_text"] is None


def test_nutrients_measure_french_match(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "nutrients", "100", "--measure", "1 tasse", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["basis"]["grams"] == 198.0
    assert payload["basis"]["description"] == "1 tasse"


def test_nutrients_measure_not_available(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "nutrients", "100", "--measure", "1 quart"])
    assert result.exit_code == 1
    assert "not available" in result.stderr


def test_nutrients_per_and_measure_mutually_exclusive(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "nutrients", "100", "--measure", "1 cup", "--per", "100g"])
    assert result.exit_code == 1


def test_nutrients_unknown_food_code(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "nutrients", "999"])
    assert result.exit_code == 1
    assert "999" in result.stderr


def test_nutrients_invalid_per(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "nutrients", "100", "--per", "liters"])
    assert result.exit_code == 1
    assert "100g" in result.stderr


# --- measures ----------------------------------------------------------------


def test_measures_json(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "measures", "100", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    measures = payload["measures"]
    assert [m["measure_code"] for m in measures] == [1, 2, 3]
    assert [m["grams"] for m in measures] == [100.0, 198.0, 13.5]
    assert payload["name_en"] == "Red lentils, cooked"


def test_measures_csv_single_row(cnf_env: Path) -> None:
    result = runner.invoke(app, ["cnf", "measures", "101", "--format", "csv"])
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "measure_code,description_en,description_fr,grams"
    assert len(lines) == 2
    assert lines[1].startswith("2,")


# --- data build cnf + data status --------------------------------------------


def test_data_build_cnf_and_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    zip_path = make_mini_zip(tmp_path / "mini_cnf.zip")
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FOODGUIDE_CNF_ZIP", raising=False)

    out = tmp_path / "out.sqlite"
    result = runner.invoke(
        app,
        ["data", "build", "cnf", "--zip", str(zip_path), "--out", str(out), "--no-fetch-metadata"],
    )
    assert result.exit_code == 0
    assert "content_hash" in result.stdout

    # A second build into the default location so `data status` sees it.
    result = runner.invoke(app, ["data", "build", "cnf", "--zip", str(zip_path), "--no-fetch-metadata"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["data", "status", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    cnf = payload["cnf_db"]
    assert cnf["built"] is True
    assert cnf["size_bytes"] == (tmp_path / "cnf.sqlite").stat().st_size
    provenance = cnf["provenance"]
    assert provenance["content_hash"] in result.stdout
    assert provenance["metadata_modified"] == "unknown"


def test_missing_db_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty-data"
    empty.mkdir()
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(empty))
    result = runner.invoke(app, ["cnf", "search", "x"])
    assert result.exit_code == 1
    assert "not found" in result.stderr
    assert "build" in result.stderr


def test_build_without_zip_fails_with_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "data"
    empty.mkdir()
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(empty))
    monkeypatch.delenv("FOODGUIDE_CNF_ZIP", raising=False)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["data", "build", "cnf", "--no-fetch-metadata"])
    assert result.exit_code == 1
    assert "--zip" in result.stderr
    assert "NOT downloaded" in result.stderr
