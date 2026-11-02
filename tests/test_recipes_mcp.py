"""End-to-end tests for the recipe MCP tools via fastmcp's in-memory Client.

The server is built with create_server(enable_db=False): recipe tools are
always registered, and enable_db=False avoids touching the SQLite state dir.
Tests are sync and drive the async client with asyncio.run (no async tests
elsewhere in the repo).

recipes.json is built once from the REAL committed canada.ca fixture pages
(tests/fixtures/pages) via the production builder + CachedFetcher — no stubs,
no mocks, zero network. Real slugs used:
- ``apple-sandwiches``: single ingredient group, meal__snack tag.
- ``baked-fish-chips``: two named ingredient groups.
- ``colourful-quinoa-salad``: title ("Quinoa salad") differs from the slug,
  carries collection__vegetarian.
"""

import asyncio

import pytest
from fastmcp import Client
from pages_fixture import fixture_recipe_cache_dir

from foodguide.recipes.builder import build_recipes_json
from foodguide.recipes.fetch import CachedFetcher
from foodguide.server import create_server

SLUGS = ["apple-sandwiches", "baked-fish-chips", "colourful-quinoa-salad"]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """recipes.json built once from the real fixture pages; one server over it.

    FOODGUIDE_DATA_DIR is set with a module-scoped MonkeyPatch context (it
    must outlive every test in the module); the production recipe API
    singleton reads the env at call time, so no attribute patching is needed.
    """
    tmp_path = tmp_path_factory.mktemp("recipes_mcp")
    build_recipes_json(
        tmp_path / "recipes.json",
        fetcher=CachedFetcher(fixture_recipe_cache_dir(tmp_path), delay=0.0),
        only=SLUGS,
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
        yield create_server(enable_db=False)


def call_tool(server, name, arguments):
    """call_tool via an in-memory Client; returns the unwrapped .data payload."""

    async def _run():
        async with Client(server) as client:
            result = await client.call_tool(name, arguments)
            assert not result.is_error, f"{name} returned an error result: {result}"
            return result.data

    return asyncio.run(_run())


def test_search_by_text(server):
    payload = call_tool(server, "search_recipes", {"search_text": "quinoa"})
    assert "error" not in payload
    assert payload["count"] == 1
    assert [r["slug"] for r in payload["recipes"]] == ["colourful-quinoa-salad"]


def test_search_by_meal_filter(server):
    payload = call_tool(
        server, "search_recipes", {"search_text": "", "meals": ["Snack"]}
    )
    assert "error" not in payload
    assert payload["count"] == 1
    for recipe in payload["recipes"]:
        assert "meal__snack" in recipe["tags"]
    assert payload["recipes"][0]["slug"] == "apple-sandwiches"
    assert "meal__snack" in payload["filters_applied"]


def test_search_ignores_retired_filters(server):
    payload = call_tool(
        server, "search_recipes", {"search_text": "", "fruits": ["apple"]}
    )
    assert "error" not in payload
    assert payload["filters_ignored"] == ["apple"]
    assert payload["count"] == 3


def test_get_recipe_by_slug_and_url(server):
    by_slug = call_tool(server, "get_recipe", {"url_or_slug": "baked-fish-chips"})
    assert "error" not in by_slug
    assert by_slug["title"] == "Baked fish and chips"
    assert by_slug["ingredients"]
    assert by_slug["directions"]

    by_url = call_tool(
        server,
        "get_recipe",
        {
            "url_or_slug": (
                "https://www.canada.ca/en/health-canada/services/food-guide"
                "/eating-support/kitchen/recipes/baked-fish-chips.html"
            )
        },
    )
    assert "error" not in by_url
    assert by_url == by_slug


def test_get_recipe_payload_is_the_real_recipe(server):
    payload = call_tool(server, "get_recipe", {"url_or_slug": "apple-sandwiches"})
    assert "error" not in payload
    assert payload["title"] == "Apple sandwiches"
    assert payload["prep_time"] == "10 min" and payload["cook_time"] == "0 min"
    assert payload["ingredients"][1] == "85 mL (⅓ cup) 0% plain Greek yogurt"
    assert "meal__snack" in payload["tags"]


def test_get_recipe_unknown_slug(server):
    payload = call_tool(server, "get_recipe", {"url_or_slug": "no-such-recipe"})
    assert "error" in payload


def test_list_filters(server):
    payload = call_tool(server, "list_filters", {})
    assert "error" not in payload
    # The real canada.ca index ships six collection and three meal filters.
    assert set(payload["collection"]) == {
        "collection__10_ingredients_less",
        "collection__30_minutes_less",
        "collection__freezer_friendly",
        "collection__kid_friendly",
        "collection__no_cook",
        "collection__vegetarian",
    }
    assert payload["collection"]["collection__vegetarian"] == "Vegetarian"
    assert payload["meal"] == {
        "meal__breakfast": "Breakfast",
        "meal__lunch_dinner": "Lunch/dinner",
        "meal__snack": "Snack",
    }


def test_missing_data_returns_build_hint(tmp_path, monkeypatch):
    # The production recipe API singleton reads FOODGUIDE_DATA_DIR at call
    # time, so pointing it at an empty dir is enough — no patching.
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path / "empty"))
    server = create_server(enable_db=False)
    payload = call_tool(server, "search_recipes", {"search_text": ""})
    assert "error" in payload
    assert "foodguide data build recipes" in payload["error"]
