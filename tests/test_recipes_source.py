"""Tests for LocalRecipeSource over a recipes.json built from the HTML fixtures."""

from pathlib import Path

import pytest

from foodguide.recipes.builder import build_recipes_json
from foodguide.recipes.fetch import INDEX_URL, recipe_url
from foodguide.recipes.source import LocalRecipeSource, recipes_data_path

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_html"


class StubFetcher:
    """Serves fixture pages instead of the network."""

    def __init__(self, mapping):
        self.mapping = mapping

    def fetch(self, url: str) -> str:
        return self.mapping[url]


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _stub_fetcher() -> StubFetcher:
    return StubFetcher(
        {
            INDEX_URL: _fixture("index.html"),
            recipe_url("test-berry-crisp"): _fixture("two-groups.html"),
            recipe_url("test-fruit-salad"): _fixture("fruit-salad.html"),
            recipe_url("test-oat-bowl"): _fixture("no-tips.html"),
        }
    )


def _build(tmp_path, name="recipes.json"):
    out_path = tmp_path / name
    build_recipes_json(out_path, fetcher=_stub_fetcher())
    return out_path


def _titles(results):
    return [r["title"] for r in results]


def test_search_empty_matches_all_sorted_by_title(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    results = source.search("")
    assert _titles(results) == ["Test berry crisp", "Test fruit salad", "Test oat bowl"]
    for row in results:
        assert set(row) == {"title", "url", "slug", "tags"}
        assert row["url"] == recipe_url(row["slug"])


def test_search_text_matches_title_intro_ingredients_directions(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert _titles(source.search("berry")) == ["Test berry crisp"]
    assert _titles(source.search("YOGURT")) == ["Test berry crisp"]  # intro, case-insensitive
    assert _titles(source.search("margarine")) == ["Test berry crisp"]  # ingredient
    assert _titles(source.search("chill until serving")) == ["Test fruit salad"]  # direction
    assert source.search("no-such-thing-xyz") == []


def test_search_tags_and_semantics(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert _titles(source.search(tags=["collection__vegetarian", "meal__snack"])) == [
        "Test berry crisp"
    ]
    # breakfast and snack never co-occur in the fixture index.
    assert source.search(tags=["meal__breakfast", "meal__snack"]) == []


def test_search_tag_by_label_or_raw_value(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    by_raw = source.search(tags=["meal__snack"])
    by_label = source.search(tags=["Snack"])
    by_label_lower = source.search(tags=["snack"])
    assert _titles(by_raw) == _titles(by_label) == _titles(by_label_lower) == [
        "Test berry crisp"
    ]
    assert _titles(source.search(tags=["vegetarian"])) == ["Test berry crisp"]
    # A label with no matching filter simply matches nothing.
    assert source.search(tags=["30 Minutes Less"]) == []
    assert source.search(tags=["not-a-real-tag"]) == []


def test_search_limit_after_sorting(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert _titles(source.search(limit=2)) == ["Test berry crisp", "Test fruit salad"]
    # None and <=0 mean no limit.
    assert len(source.search(limit=None)) == 3
    assert len(source.search(limit=0)) == 3
    assert len(source.search(limit=-1)) == 3


def test_get_recipe_by_slug_and_url_identical_with_flat_ingredients(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    by_slug = source.get_recipe("test-berry-crisp")
    by_url = source.get_recipe(
        "https://www.canada.ca/en/health-canada/services/food-guide/eating-support"
        "/kitchen/recipes/test-berry-crisp.html"
    )
    by_old_url = source.get_recipe("https://food-guide.canada.ca/en/recipes/test-berry-crisp/")
    assert by_slug == by_url == by_old_url

    assert by_slug["title"] == "Test berry crisp"
    assert by_slug["prep_time"] == "15 min"
    assert by_slug["cook_time"] == "50 min"
    assert by_slug["servings"] == "6"
    # Flattened across both groups, in order.
    assert by_slug["ingredients"] == [
        "4 apples, cored and chopped",
        "500 mL (2 cups) frozen blueberries",
        "45 mL (3 tbsp) packed brown sugar",
        "125 mL (½ cup) large flake oats",
        "30 mL (2 tbsp) soft margarine, melted",
    ]
    assert [g["group"] for g in by_slug["ingredient_groups"]] == [None, "Topping:"]
    assert by_slug["directions"][0] == "Preheat the oven to 180 °C (350 °F)."
    assert by_slug["tips"] == ["Little chefs can stir the topping ingredients together."]
    assert by_slug["tags"] == ["collection__vegetarian", "meal__snack"]
    assert by_slug["source"] == "Health Canada's Food Guide"
    assert by_slug["attribution"] == (
        "Recipe sourced from Health Canada's Food Guide kitchen (canada.ca)"
    )
    assert "page_sha256" not in by_slug


def test_get_recipe_unknown_returns_none(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert source.get_recipe("no-such-recipe") is None
    assert source.get_recipe("https://food-guide.canada.ca/en/recipes/no-such-recipe/") is None


def test_list_filters_sorted(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert source.list_filters() == {
        "collection__vegetarian": "Vegetarian",
        "meal__breakfast": "Breakfast",
        "meal__snack": "Snack",
    }


def test_status_built_and_missing(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    status = source.status()
    assert status["built"] is True
    assert status["path"] == str(path)
    assert status["size_bytes"] == path.stat().st_size
    assert status["recipe_count"] == 3
    assert status["filter_count"] == 3
    assert status["fetched_at"]
    assert len(status["index_sha256"]) == 64

    missing = LocalRecipeSource(tmp_path / "nope.json")
    assert missing.status() == {"built": False}


def test_missing_file_raises_with_build_hint(tmp_path):
    source = LocalRecipeSource(tmp_path / "missing.json")
    with pytest.raises(RuntimeError) as excinfo:
        source.data
    assert str(excinfo.value) == (
        f"Recipes data not found at {tmp_path / 'missing.json'}. "
        "Build it with `foodguide data build recipes`."
    )


def test_recipes_data_path_follows_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    assert recipes_data_path() == tmp_path / "recipes.json"
    # A source without an explicit path reads that same location lazily.
    source = LocalRecipeSource()
    assert source.path == tmp_path / "recipes.json"
    _build(tmp_path)
    assert len(source.search("")) == 3
