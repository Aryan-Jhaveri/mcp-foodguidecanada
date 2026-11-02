"""CLI tests for the recipes app and the recipes sections of the data app.

All recipe data comes from the REAL committed canada.ca fixture pages
(tests/fixtures/pages) via the production ``CachedFetcher`` — no stubs, no
mocks. The offline tests build recipes.json from the fixture cache dir (zero
network, works in sandboxes without loopback TCP); the two build tests
exercise the real CLI build path, one over a real local http.server
(``pages_server``) and one purely from the on-disk cache.
"""

import hashlib
import json
from pathlib import Path

import pytest
from pages_fixture import FIXTURE_DIR, fixture_recipe_cache_dir
from typer.testing import CliRunner

from foodguide.cli import app
from foodguide.recipes.source import recipes_data_path

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"})

#: The fixture recipe pages exercised by the offline CLI tests.
SLUGS = ["apple-sandwiches", "baked-fish-chips", "colourful-quinoa-salad"]

#: Every committed recipe page: a full fixture-set build (CLI --only).
ALL_FIXTURE_SLUGS = sorted(p.stem for p in (FIXTURE_DIR / "recipes").glob("*.html"))

FIXTURE_INDEX = Path(__file__).parent / "fixtures" / "pages" / "recipes_index.html"
#: sha256 of the raw committed index page (what an HTTP fetch delivers, byte
#: for byte — unlike CachedFetcher, which normalizes CRLF to LF on read).
INDEX_SHA256_HTTP = hashlib.sha256(FIXTURE_INDEX.read_bytes()).hexdigest()
#: sha256 of the index text as CachedFetcher delivers it: it reads the cache
#: file with read_text(), which normalizes the fixture's CRLF endings to LF.
INDEX_SHA256_CACHED = hashlib.sha256(FIXTURE_INDEX.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _build(tmp_path: Path) -> Path:
    """Build a real recipes.json from the committed pages via the production
    builder + CachedFetcher (offline: every page is a cache hit)."""
    from foodguide.recipes.builder import build_recipes_json
    from foodguide.recipes.fetch import CachedFetcher

    out_path = tmp_path / "recipes.json"
    build_recipes_json(
        out_path,
        fetcher=CachedFetcher(fixture_recipe_cache_dir(tmp_path), delay=0.0),
        only=SLUGS,
    )
    return out_path


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """A FOODGUIDE_DATA_DIR containing a recipes.json built from the real pages."""
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    _build(tmp_path)
    return tmp_path


def test_search_table(data_dir):
    result = runner.invoke(app, ["recipes", "search"])
    assert result.exit_code == 0
    for title in ("Apple sandwiches", "Baked fish and chips", "Quinoa salad"):
        assert title in result.stdout


def test_search_json(data_dir):
    result = runner.invoke(app, ["recipes", "search", "--format", "json"])
    assert result.exit_code == 0
    results = json.loads(result.stdout)
    assert [r["slug"] for r in results] == [
        "apple-sandwiches",
        "baked-fish-chips",
        "colourful-quinoa-salad",
    ]
    assert set(results[0]) == {"title", "url", "slug", "tags"}


def test_search_csv(data_dir):
    result = runner.invoke(app, ["recipes", "search", "--format", "csv"])
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "title,slug,tags"
    assert "apple-sandwiches" in lines[1]
    assert "collection__10_ingredients_less" in lines[1]


def test_search_tag_and_limit(data_dir):
    result = runner.invoke(app, ["recipes", "search", "--tag", "meal__snack", "--format", "json"])
    assert result.exit_code == 0
    assert [r["slug"] for r in json.loads(result.stdout)] == ["apple-sandwiches"]

    result = runner.invoke(
        app, ["recipes", "search", "--tag", "Snack", "--format", "json"]
    )
    assert result.exit_code == 0
    assert [r["slug"] for r in json.loads(result.stdout)] == ["apple-sandwiches"]

    result = runner.invoke(app, ["recipes", "search", "--limit", "1", "--format", "json"])
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)) == 1


def test_search_no_match(data_dir):
    result = runner.invoke(app, ["recipes", "search", "no-such-thing-xyz"])
    assert result.exit_code == 0
    assert "No recipes match." in result.stdout


def test_show_by_slug_table(data_dir):
    result = runner.invoke(app, ["recipes", "show", "baked-fish-chips"])
    assert result.exit_code == 0
    out = result.stdout
    assert "Title: Baked fish and chips" in out
    assert "URL: " in out and "baked-fish-chips.html" in out
    assert "collection__freezer_friendly" in out
    assert "Prep time: 20 min" in out and "Cook time: 45 min" in out and "Servings: 4" in out
    assert "Ingredients:" in out
    assert "1 sweet potato, cut into strips" in out
    assert "Oven Fries:" in out
    assert "125 mL (½ cup) whole almonds" in out
    assert (
        "Directions:" in out
        and "1. Preheat the oven to 220 °C (425 °F) and line 2 baking sheets with "
        "parchment paper. Set aside." in out
    )
    assert "Tips:" in out and "Shop around for the best deal" in out


def test_show_by_url_json(data_dir):
    result = runner.invoke(
        app,
        [
            "recipes", "show",
            "https://www.canada.ca/en/health-canada/services/food-guide/eating-support"
            "/kitchen/recipes/apple-sandwiches.html",
            "--format", "json",
        ],
    )
    assert result.exit_code == 0
    recipe = json.loads(result.stdout)
    assert recipe["slug"] == "apple-sandwiches"
    assert recipe["ingredients"] == [
        "60 (¼ cup) natural almond or peanut butter or non-nut alternative",
        "85 mL (⅓ cup) 0% plain Greek yogurt",
        "Sprinkle of cinnamon",
        "2 apples, cored and thinly sliced horizontally",
        "Optional toppings: sliced almonds, dried fruit, unsweetened shredded coconut, seeds",
    ]
    assert "page_sha256" not in recipe


def test_show_by_old_food_guide_url(data_dir):
    result = runner.invoke(
        app,
        ["recipes", "show", "https://food-guide.canada.ca/en/recipes/colourful-quinoa-salad/", "--format", "json"],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["slug"] == "colourful-quinoa-salad"


def test_show_unknown_exits_1(data_dir):
    result = runner.invoke(app, ["recipes", "show", "no-such-recipe"])
    assert result.exit_code == 1
    assert "not found in local data" in result.output
    assert "foodguide data build recipes" in result.output


def test_show_csv(data_dir):
    result = runner.invoke(app, ["recipes", "show", "baked-fish-chips", "--format", "csv"])
    assert result.exit_code == 0
    assert result.stdout.startswith("key,value")
    assert "title,Baked fish and chips" in result.stdout


def test_filters_formats(data_dir):
    table = runner.invoke(app, ["recipes", "filters"])
    assert table.exit_code == 0
    assert "collection__vegetarian" in table.stdout
    assert "Vegetarian" in table.stdout
    assert table.stdout.index("collection__vegetarian") < table.stdout.index("meal__breakfast")

    csv_result = runner.invoke(app, ["recipes", "filters", "--format", "csv"])
    assert csv_result.exit_code == 0
    lines = csv_result.stdout.strip().splitlines()
    assert lines[0] == "tag,label"
    assert "collection__vegetarian,Vegetarian" in lines

    json_result = runner.invoke(app, ["recipes", "filters", "--format", "json"])
    assert json_result.exit_code == 0
    # The exact nine filters from the real canada.ca index page.
    assert json.loads(json_result.stdout) == {
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


def test_data_status_shows_recipes_section(data_dir):
    table = runner.invoke(app, ["data", "status"])
    assert table.exit_code == 0
    assert "Recipes data:" in table.stdout
    assert f"{data_dir / 'recipes.json'}" in table.stdout
    assert "fetched_at:" in table.stdout
    assert "index_sha256:" in table.stdout

    json_result = runner.invoke(app, ["data", "status", "--format", "json"])
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["recipes"]["built"] is True
    assert payload["recipes"]["recipe_count"] == 3
    assert payload["recipes"]["filter_count"] == 9
    assert payload["recipes"]["index_sha256"]

    csv_result = runner.invoke(app, ["data", "status", "--format", "csv"])
    assert csv_result.exit_code == 0
    assert "recipes_json," in csv_result.stdout
    assert "recipes_provenance,fetched_at," in csv_result.stdout


def test_data_status_recipes_not_built(tmp_path, monkeypatch):
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    table = runner.invoke(app, ["data", "status"])
    assert table.exit_code == 0
    assert "Recipes data: not built (run: foodguide data build recipes)" in table.stdout


def test_data_build_recipes_via_local_server(tmp_path, monkeypatch, pages_server):
    """The real CLI build against a real local http.server serving the pages.

    Exercises the production PoliteFetcher over real HTTP round trips (the
    default fetcher path, i.e. no FOODGUIDE_RECIPES_CACHE_DIR) with
    FOODGUIDE_SOURCE_BASE_URL pointed at the fixture server. Skips in
    sandboxes without loopback TCP.
    """
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FOODGUIDE_SOURCE_BASE_URL", pages_server.base_url)
    out_path = tmp_path / "built" / "r.json"

    # The real index lists 141 recipes but only 12 pages are committed as
    # fixtures; --only keeps the crawl inside the fixture set (development
    # option, also used by `data build all`'s recipes_only parameter).
    result = runner.invoke(
        app,
        ["data", "build", "recipes", "--out", str(out_path), "--only", ",".join(ALL_FIXTURE_SLUGS)],
    )
    assert result.exit_code == 0, result.output
    assert "recipes: 12" in result.stdout
    assert "filters: 9" in result.stdout
    assert out_path.exists()
    assert f"index_sha256: {INDEX_SHA256_HTTP}" in result.stdout
    assert "build_time:" in result.stdout

    document = json.loads(out_path.read_text(encoding="utf-8"))
    assert document["source"]["index_recipe_count"] == 141
    assert document["source"]["recipe_count"] == 12


def test_data_build_recipes_from_cache_dir(tmp_path, monkeypatch):
    """FOODGUIDE_RECIPES_CACHE_DIR makes the CLI build serve pages from disk.

    No server, no network: the cache holds the real committed pages, and
    --only keeps the build to slugs that are certainly in it.
    """
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FOODGUIDE_RECIPES_CACHE_DIR", str(fixture_recipe_cache_dir(tmp_path)))
    out_path = tmp_path / "built" / "r.json"

    result = runner.invoke(
        app,
        [
            "data", "build", "recipes",
            "--only", "apple-sandwiches,baked-fish-chips",
            "--out", str(out_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "recipes: 2" in result.stdout
    assert "filters: 9" in result.stdout
    assert f"index_sha256: {INDEX_SHA256_CACHED}" in result.stdout
    assert "build_time:" in result.stdout
    document = json.loads(out_path.read_text(encoding="utf-8"))
    assert [r["slug"] for r in document["recipes"]] == [
        "apple-sandwiches",
        "baked-fish-chips",
    ]


def test_data_build_recipes_help_mentions_cache_dir():
    result = runner.invoke(app, ["data", "build", "recipes", "--help"])
    assert result.exit_code == 0
    assert "on-disk cache" in result.stdout


def test_recipes_data_path_used_as_default_build_output(tmp_path, monkeypatch):
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    assert recipes_data_path() == tmp_path / "recipes.json"
