"""Tests for the recipes crawler/parser (fixtures + one real-page integration test)."""

import hashlib
import os
from pathlib import Path

import pytest

from foodguide.recipes.parser import parse_index, parse_recipe

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_html"
REAL_CACHE = Path(
    os.environ.get("FOODGUIDE_TEST_RECIPE_CACHE")
    or "/srv/agent/work/foodguide-tasks/data/recipes_cache"
)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_index_fixture():
    parsed = parse_index(_read("index.html"))

    assert parsed["slugs"] == ["test-berry-crisp", "test-fruit-salad", "test-oat-bowl"]
    assert parsed["tags"] == {
        "test-berry-crisp": ["collection__vegetarian", "meal__snack"],
        "test-oat-bowl": ["meal__breakfast"],
        "test-fruit-salad": ["collection__30_minutes_less", "collection__no_cook"],
    }
    assert parsed["filters"] == {
        "collection__vegetarian": "Vegetarian",
        "meal__breakfast": "Breakfast",
        "meal__snack": "Snack",
    }


def test_parse_recipe_two_groups():
    html_text = _read("two-groups.html")
    recipe = parse_recipe(
        html_text,
        "test-berry-crisp",
        "https://www.canada.ca/en/health-canada/services/food-guide/eating-support"
        "/kitchen/recipes/test-berry-crisp.html",
        ["collection__vegetarian", "meal__snack"],
    )

    assert recipe["slug"] == "test-berry-crisp"
    assert recipe["title"] == "Test berry crisp"
    assert recipe["intro"] == (
        "This irresistible test recipe showcases berries. Enjoy it warm with a "
        "dollop of yogurt — it serves a ½ dozen."
    )
    assert recipe["prep_time"] == "15 min"
    assert recipe["cook_time"] == "50 min"
    assert recipe["servings"] == "6"
    assert len(recipe["ingredient_groups"]) == 2
    assert [group["group"] for group in recipe["ingredient_groups"]] == [None, "Topping:"]
    assert [item for group in recipe["ingredient_groups"] for item in group["items"]] == [
        "4 apples, cored and chopped",
        "500 mL (2 cups) frozen blueberries",
        "45 mL (3 tbsp) packed brown sugar",
        "125 mL (½ cup) large flake oats",
        "30 mL (2 tbsp) soft margarine, melted",
    ]
    assert recipe["directions"] == [
        "Preheat the oven to 180 °C (350 °F).",
        "In a large bowl, combine apples and blueberries; sprinkle topping over top.",
    ]
    assert recipe["tips"] == ["Little chefs can stir the topping ingredients together."]
    assert recipe["tags"] == ["collection__vegetarian", "meal__snack"]
    assert recipe["page_sha256"] == hashlib.sha256(html_text.encode("utf-8")).hexdigest()
    assert list(recipe.keys()) == [
        "slug",
        "url",
        "title",
        "intro",
        "prep_time",
        "cook_time",
        "servings",
        "ingredient_groups",
        "directions",
        "tips",
        "tags",
        "page_sha256",
    ]


def test_parse_recipe_no_tips():
    recipe = parse_recipe(_read("no-tips.html"), "test-oat-bowl", "https://example.com/x.html", [])

    assert recipe["title"] == "Test oat bowl"
    assert len(recipe["ingredient_groups"]) == 1
    assert recipe["ingredient_groups"][0]["group"] is None
    assert recipe["ingredient_groups"][0]["items"] == [
        "250 mL (1 cup) rolled oats",
        "250 mL (1 cup) milk",
        "1 apple, diced",
    ]
    assert recipe["servings"] == "2"
    assert recipe["cook_time"] is None
    assert recipe["tips"] == []


def test_parse_recipe_missing_directions_raises():
    with pytest.raises(ValueError, match="test-broken"):
        parse_recipe(_read("broken.html"), "test-broken", "https://example.com/broken.html", [])


@pytest.mark.skipif(
    not (REAL_CACHE / "apple-berry-crisp.html").exists(),
    reason="real cached recipe page not available",
)
def test_parse_real_apple_berry_crisp():
    html_text = (REAL_CACHE / "apple-berry-crisp.html").read_text(encoding="utf-8")
    recipe = parse_recipe(
        html_text,
        "apple-berry-crisp",
        "https://www.canada.ca/en/health-canada/services/food-guide/eating-support"
        "/kitchen/recipes/apple-berry-crisp.html",
        ["collection__kid_friendly", "collection__vegetarian", "meal__snack"],
    )

    assert recipe["title"] == "Apple berry crisp"
    assert recipe["prep_time"] == "15 min"
    assert recipe["cook_time"] == "50 min"
    assert recipe["servings"] == "8"
    assert recipe["ingredient_groups"][0]["items"][0] == "4 apples, cored and chopped"
