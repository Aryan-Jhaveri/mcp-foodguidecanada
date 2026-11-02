"""Unit tests for LocalCNFSource — the offline CNF source behind the MCP tools."""

from __future__ import annotations

from pathlib import Path

import pytest
from cnf_fixture import make_mini_zip

from foodguide.api.cnf_api import get_cnf_api_client
from foodguide.cnf.builder import build_cnf_db
from foodguide.cnf.db import get_data_dir
from foodguide.cnf.mcp_source import LocalCNFSource


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build the mini CNF zip into a tmp data dir and point FOODGUIDE_DATA_DIR at it."""
    zip_path = make_mini_zip(tmp_path / "mini_cnf.zip")
    db_dir = tmp_path / "data"
    build_cnf_db(zip_path, db_dir / "cnf.sqlite")
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(db_dir))
    return db_dir


@pytest.fixture()
def source(data_dir: Path) -> LocalCNFSource:
    return LocalCNFSource()


def test_search_food_lentils(source: LocalCNFSource) -> None:
    results = source.search_food("lentils", max_results=10)
    codes = [r["food_code"] for r in results]
    assert codes == ["100", "102"]
    assert all(isinstance(c, str) for c in codes)
    names = {r["food_name"] for r in results}
    assert names == {"Red lentils, cooked", "Boiled lentils"}


def test_get_food(source: LocalCNFSource) -> None:
    food = source.get_food("100")
    assert food == {"food_code": "100", "food_description": "Red lentils, cooked"}
    assert source.get_food("999") is None


def test_get_nutrient_amounts(source: LocalCNFSource) -> None:
    rows = source.get_nutrient_amounts("100")
    assert len(rows) == 3
    ids = {r["nutrient_name_id"] for r in rows}
    assert ids == {203, 208, 301}
    for row in rows:
        assert isinstance(row["nutrient_value"], float)
    protein = next(r for r in rows if r["nutrient_name_id"] == 203)
    assert protein["nutrient_value"] == pytest.approx(9.02)


def test_get_serving_sizes(source: LocalCNFSource) -> None:
    servings = source.get_serving_sizes("100")
    assert len(servings) == 3
    by_name = {s["measure_name"]: s["conversion_factor_value"] for s in servings}
    assert by_name == {"100 g": 100.0, "1 cup": 198.0, "1 tbsp": 13.5}
    assert len(source.get_serving_sizes("102")) == 1
    assert source.get_serving_sizes("999") == []


def test_get_refuse_amount_always_none(source: LocalCNFSource) -> None:
    # The CNF 2026 all-files zip has no refuse-amount table, so this is always None.
    assert source.get_refuse_amount("100") is None
    assert source.get_refuse_amount("999") is None


def test_get_macronutrients(source: LocalCNFSource) -> None:
    result = source.get_macronutrients("100")
    assert result["food_code"] == "100"
    assert result["refuse"] is None
    protein = next(n for n in result["nutrients"] if n["nutrient_name_id"] == 203)
    assert protein["unit"] == "g"
    assert protein["symbol"] == "PROT"
    assert protein["value_per_100g"] == pytest.approx(9.02)
    cup = next(s for s in result["servings"] if s["measure_name"] == "1 cup")
    assert cup["amount"] == pytest.approx(1.0)
    assert cup["unit"] == "cup"
    assert cup["conversion_factor"] == pytest.approx(198.0)


def test_get_full_nutrient_profile(source: LocalCNFSource) -> None:
    result = source.get_full_nutrient_profile("100")
    assert len(result["nutrients"]) == 3
    by_id = {n["nutrient_name_id"]: n for n in result["nutrients"]}
    assert set(by_id) == {203, 208, 301}
    assert by_id[203]["name"] == "Protein"
    assert by_id[203]["unit"] == "Gram"
    assert by_id[203]["symbol"] == "PROT"
    assert by_id[301]["name"] == "Calcium"
    assert by_id[301]["symbol"] == "CA"
    assert result["refuse"] is None


def test_get_nutrient_names(source: LocalCNFSource) -> None:
    names = source.get_nutrient_names()
    assert len(names) == 3
    by_id = {n["nutrient_name_id"]: n for n in names}
    assert by_id[208]["nutrient_web_name"] == "Energy (kilocalories)"
    assert by_id[208]["nutrient_web_unit"] == "kilocalorie"
    assert by_id[208]["nutrient_web_symbol"] == "KCAL"


def test_get_all_foods_cached(source: LocalCNFSource) -> None:
    foods = source.get_all_foods()
    assert len(foods) == 3
    assert foods[0] == {"food_code": 100, "food_description": "Red lentils, cooked"}
    assert source.get_all_foods() is foods  # cached within the instance


def test_missing_db_raises_runtime_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(empty))
    assert get_data_dir() == empty
    src = LocalCNFSource()  # lazy: constructing without a db must not fail
    with pytest.raises(RuntimeError, match="data build cnf"):
        src.search_food("lentils")


def test_factory_returns_local_source(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import foodguide.api.cnf_api as cnf_api_module

    monkeypatch.setattr(cnf_api_module, "_cnf_api_instance", None)
    client = get_cnf_api_client()
    assert isinstance(client, LocalCNFSource)
    # And it actually reads the env-pointed database, not the network.
    assert client.search_food("lentils", max_results=10)[0]["food_code"] == "100"
