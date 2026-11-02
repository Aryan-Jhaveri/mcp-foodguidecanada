"""End-to-end tests for the recipe MCP tools via fastmcp's in-memory Client.

The server is built with create_server(enable_db=False): recipe tools are
always registered, and enable_db=False avoids touching the SQLite state dir.
Tests are sync and drive the async client with asyncio.run (no async tests
elsewhere in the repo).
"""

import asyncio
import os
from pathlib import Path

import pytest
from fastmcp import Client

from foodguide.api import recipe as recipe_api
from foodguide.recipes.builder import build_recipes_json
from foodguide.recipes.fetch import INDEX_URL, recipe_url
from foodguide.recipes.source import LocalRecipeSource
from foodguide.server import create_server

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_html"


class StubFetcher:
    """Serves fixture pages instead of the network."""

    def __init__(self, mapping):
        self.mapping = mapping

    def fetch(self, url: str) -> str:
        return self.mapping[url]


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def server(tmp_path_factory, request):
    """recipes.json built once from the HTML fixtures; one server over it."""
    tmp_path = tmp_path_factory.mktemp("recipes_mcp")
    build_recipes_json(
        tmp_path / "recipes.json",
        fetcher=StubFetcher(
            {
                INDEX_URL: _fixture("index.html"),
                recipe_url("test-berry-crisp"): _fixture("two-groups.html"),
                recipe_url("test-fruit-salad"): _fixture("fruit-salad.html"),
                recipe_url("test-oat-bowl"): _fixture("no-tips.html"),
            }
        ),
    )
    os.environ["FOODGUIDE_DATA_DIR"] = str(tmp_path)
    request.addfinalizer(lambda: os.environ.pop("FOODGUIDE_DATA_DIR", None))
    # A fresh source for this module's server (api.recipe caches one globally).
    previous = recipe_api._source
    recipe_api._source = LocalRecipeSource(tmp_path / "recipes.json")
    request.addfinalizer(lambda: setattr(recipe_api, "_source", previous))
    return create_server(enable_db=False)


def call_tool(server, name, arguments):
    """call_tool via an in-memory Client; returns the unwrapped .data payload."""

    async def _run():
        async with Client(server) as client:
            result = await client.call_tool(name, arguments)
            assert not result.is_error, f"{name} returned an error result: {result}"
            return result.data

    return asyncio.run(_run())


def test_search_by_text(server):
    payload = call_tool(server, "search_recipes", {"search_text": "berry"})
    assert "error" not in payload
    assert payload["count"] >= 1
    assert len(payload["recipes"]) >= 1
    assert any(r["slug"] == "test-berry-crisp" for r in payload["recipes"])


def test_search_by_meal_filter(server):
    payload = call_tool(
        server, "search_recipes", {"search_text": "", "meals": ["Snack"]}
    )
    assert "error" not in payload
    assert payload["count"] >= 1
    for recipe in payload["recipes"]:
        assert "meal__snack" in recipe["tags"]
    assert "meal__snack" in payload["filters_applied"]


def test_search_ignores_retired_filters(server):
    payload = call_tool(
        server, "search_recipes", {"search_text": "", "fruits": ["apple"]}
    )
    assert "error" not in payload
    assert payload["filters_ignored"] == ["apple"]
    assert payload["count"] >= 1


def test_get_recipe_by_slug_and_url(server):
    by_slug = call_tool(server, "get_recipe", {"url_or_slug": "test-berry-crisp"})
    assert "error" not in by_slug
    assert by_slug["ingredients"]
    assert by_slug["directions"]

    by_url = call_tool(
        server,
        "get_recipe",
        {
            "url_or_slug": (
                "https://www.canada.ca/en/health-canada/services/food-guide"
                "/eating-support/kitchen/recipes/test-berry-crisp.html"
            )
        },
    )
    assert "error" not in by_url
    assert by_url == by_slug


def test_get_recipe_unknown_slug(server):
    payload = call_tool(server, "get_recipe", {"url_or_slug": "no-such-recipe"})
    assert "error" in payload


def test_list_filters(server):
    payload = call_tool(server, "list_filters", {})
    assert "error" not in payload
    assert set(payload["collection"].values()) and set(payload["meal"].values())
    assert all(isinstance(label, str) and label for label in payload["collection"].values())
    assert all(isinstance(label, str) and label for label in payload["meal"].values())


def test_missing_data_returns_build_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr(recipe_api, "_source", LocalRecipeSource())
    server = create_server(enable_db=False)
    payload = call_tool(server, "search_recipes", {"search_text": ""})
    assert "error" in payload
    assert "foodguide data build recipes" in payload["error"]
