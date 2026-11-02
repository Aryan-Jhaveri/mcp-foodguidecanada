"""Tests for LocalRecipeSource over a recipes.json built from the REAL committed
canada.ca fixture pages (tests/fixtures/pages), via the production CachedFetcher.

Zero network: the build reads the committed pages from a cache dir laid out the
way production ``CachedFetcher`` expects (see ``pages_fixture.fixture_recipe_cache_dir``),
so these tests run even in sandboxes that block all loopback TCP connections.

Real slugs used (chosen for parser variety):
- ``apple-sandwiches``: one ingredient group, tips, many tags (incl. meal__snack).
- ``baked-fish-chips``: TWO named ingredient groups ("Oven Fries:", "Almond Crusted Fish:").
- ``colourful-quinoa-salad``: title differs from the slug ("Quinoa salad"),
  only two tags, one of which (collection__vegetarian) the others lack.
"""

from pathlib import Path

import pytest
from pages_fixture import fixture_recipe_cache_dir

from foodguide.recipes.builder import build_recipes_json
from foodguide.recipes.fetch import CachedFetcher, recipe_url
from foodguide.recipes.source import LocalRecipeSource, recipes_data_path

#: The fixture recipe pages exercised by these tests.
SLUGS = ["apple-sandwiches", "baked-fish-chips", "colourful-quinoa-salad"]

#: sha256 of the index text as the production fetcher delivers it to the
#: builder. The committed fixture page has CRLF line endings; CachedFetcher
#: reads it with read_text(), which normalizes them to LF before hashing.
INDEX_SHA256 = "2d6152eba8105ca759f0c689fa021b9bc86cfc73037b864bf2b214a03f07c56e"


def _build(tmp_path, name="recipes.json") -> Path:
    """Build a real recipes.json from the committed pages via the production
    builder + CachedFetcher (offline: every page is a cache hit)."""
    out_path = tmp_path / name
    build_recipes_json(
        out_path,
        fetcher=CachedFetcher(fixture_recipe_cache_dir(tmp_path), delay=0.0),
        only=SLUGS,
    )
    return out_path


def _titles(results):
    return [r["title"] for r in results]


def test_search_empty_matches_all_sorted_by_title(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    results = source.search("")
    assert _titles(results) == ["Apple sandwiches", "Baked fish and chips", "Quinoa salad"]
    for row in results:
        assert set(row) == {"title", "url", "slug", "tags"}
        assert row["url"] == recipe_url(row["slug"])


def test_search_text_matches_title_intro_ingredients_directions(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert _titles(source.search("quinoa")) == ["Quinoa salad"]  # title
    assert _titles(source.search("AFTER-SCHOOL SNACK")) == ["Apple sandwiches"]  # intro, case-insensitive
    assert _titles(source.search("parsnips")) == ["Baked fish and chips"]  # ingredient
    assert _titles(source.search("serve with lemon wedge")) == ["Baked fish and chips"]  # direction
    assert source.search("no-such-thing-xyz") == []


def test_search_tags_and_semantics(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert _titles(source.search(tags=["collection__vegetarian", "meal__lunch_dinner"])) == [
        "Quinoa salad"
    ]
    # breakfast and snack never co-occur on the real pages either.
    assert source.search(tags=["meal__breakfast", "meal__snack"]) == []


def test_search_tag_by_label_or_raw_value(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    by_raw = source.search(tags=["meal__snack"])
    by_label = source.search(tags=["Snack"])
    by_label_lower = source.search(tags=["snack"])
    assert _titles(by_raw) == _titles(by_label) == _titles(by_label_lower) == [
        "Apple sandwiches"
    ]
    assert _titles(source.search(tags=["vegetarian"])) == ["Quinoa salad"]
    # A label with no matching filter simply matches nothing ("30 minutes or
    # less" is the REAL label; "30 Minutes Less" matches no filter).
    assert source.search(tags=["30 Minutes Less"]) == []
    assert source.search(tags=["not-a-real-tag"]) == []


def test_search_limit_after_sorting(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert _titles(source.search(limit=2)) == ["Apple sandwiches", "Baked fish and chips"]
    # None and <=0 mean no limit.
    assert len(source.search(limit=None)) == 3
    assert len(source.search(limit=0)) == 3
    assert len(source.search(limit=-1)) == 3


def test_get_recipe_by_slug_and_url_identical_with_flat_ingredients(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    by_slug = source.get_recipe("baked-fish-chips")
    by_url = source.get_recipe(
        "https://www.canada.ca/en/health-canada/services/food-guide/eating-support"
        "/kitchen/recipes/baked-fish-chips.html"
    )
    by_old_url = source.get_recipe("https://food-guide.canada.ca/en/recipes/baked-fish-chips/")
    assert by_slug == by_url == by_old_url

    assert by_slug["title"] == "Baked fish and chips"
    assert by_slug["prep_time"] == "20 min"
    assert by_slug["cook_time"] == "45 min"
    assert by_slug["servings"] == "4"
    # Flattened across both real groups, in order.
    assert by_slug["ingredients"] == [
        "1 sweet potato, cut into strips",
        "2 parsnips, cut into strips",
        "5 mL (1 tsp) vegetable oil",
        "2 mL (½ tsp) chili powder",
        "125 mL (½ cup) whole almonds",
        "180 mL (¾ cup) whole grain breadcrumbs",
        "10 mL (2 tsp) dried oregano",
        "1 egg",
        "30 mL (2 tbsp) water",
        "60 mL (¼ cup) whole wheat flour",
        "10 mL (2 tsp) paprika",
        "454 g (1 lb) tilapia fillets",
        "2 mL (½ tsp) salt (optional)",
        "2 mL (½ tsp) black pepper",
        "1 lemon, cut into wedges",
    ]
    assert [g["group"] for g in by_slug["ingredient_groups"]] == [
        "Oven Fries:",
        "Almond Crusted Fish:",
    ]
    assert by_slug["directions"][0] == (
        "Preheat the oven to 220 °C (425 °F) and line 2 baking sheets with parchment paper. Set aside."
    )
    assert by_slug["tips"][0] == (
        "Use your family’s favourite fresh or frozen fish. Shop around for the best deal!"
    )
    assert by_slug["tags"] == [
        "collection__freezer_friendly",
        "collection__kid_friendly",
        "meal__lunch_dinner",
    ]
    assert by_slug["source"] == "Health Canada's Food Guide"
    assert by_slug["attribution"] == (
        "Recipe sourced from Health Canada's Food Guide kitchen (canada.ca)"
    )
    assert "page_sha256" not in by_slug


def test_get_recipe_single_group_real_content(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    recipe = source.get_recipe("apple-sandwiches")
    assert recipe["title"] == "Apple sandwiches"
    assert recipe["prep_time"] == "10 min"
    assert recipe["cook_time"] == "0 min"
    assert recipe["servings"] == "4"
    assert [g["group"] for g in recipe["ingredient_groups"]] == [None]
    assert recipe["ingredients"][1] == "85 mL (⅓ cup) 0% plain Greek yogurt"
    assert recipe["directions"][-1].startswith("On a clean cutting board, lay apple slices")
    assert len(recipe["tips"]) == 3
    assert recipe["tags"] == [
        "collection__10_ingredients_less",
        "collection__30_minutes_less",
        "collection__kid_friendly",
        "collection__no_cook",
        "meal__snack",
    ]


def test_get_recipe_unknown_returns_none(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    assert source.get_recipe("no-such-recipe") is None
    assert source.get_recipe("https://food-guide.canada.ca/en/recipes/no-such-recipe/") is None


def test_list_filters_sorted_from_real_index(tmp_path):
    path = _build(tmp_path)
    source = LocalRecipeSource(path)
    # The REAL canada.ca index ships exactly these nine filters.
    assert source.list_filters() == {
        "collection__10_ingredients_less": "10 ingredients or less",
        "collection__30_minutes_less": "30 minutes or less",
        "collection__freezer_friendly": "Freezer-friendly",
        "collection__kid_friendly": "Kid-friendly",
        "collection__no_cook": "No-cook",
        "collection__vegetarian": "Vegetarian",
        "meal__breakfast": "Breakfast",
        "meal__lunch_dinner": "Lunch/dinner",
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
    assert status["filter_count"] == 9
    assert status["fetched_at"]
    assert status["index_sha256"] == INDEX_SHA256

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
