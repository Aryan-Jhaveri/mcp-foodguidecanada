"""Golden test: a full-cache build of all 141 recipe pages must reproduce the key.

The golden key lives at tests/fixtures/golden_recipes.json (override the path with
the FOODGUIDE_TEST_GOLDEN_RECIPES env var — that escape hatch exists purely so a
broken-copy sanity check can be run against a deliberately wrong key; production
runs should never set it).

If /nonexistent/foodguide-test-data/recipes_cache holds the crawled pages
(index.html + one file per slug) the build runs entirely from cache; otherwise
the test falls back to a live PoliteFetcher crawl and skips with a clear message
if the network fetch itself fails.

page_sha256 is informational only: canada.ca serves a dynamic analytics script,
so page_sha256 differs between fetches even for identical content. Mismatches
are reported (warnings.warn) but do NOT fail the test — only the content fields
(title, ingredients, directions, times, servings) do.
"""

import json
import os
import warnings
from pathlib import Path

import pytest

from foodguide.recipes.builder import build_recipes_json
from foodguide.recipes.fetch import CachedFetcher, PoliteFetcher
from foodguide.recipes.source import LocalRecipeSource

GOLDEN_PATH = Path(
    os.environ.get("FOODGUIDE_TEST_GOLDEN_RECIPES")
    or Path(__file__).parent / "fixtures" / "golden_recipes.json"
)
CACHE_DIR = Path(
    os.environ.get("FOODGUIDE_TEST_RECIPE_CACHE")
    or "/nonexistent/foodguide-test-data/recipes_cache"
)
SHA_NOTE = (
    "the golden key hashes raw pages while the parser hashes pages with "
    "script/style blocks stripped (canada.ca serves a dynamic analytics script); "
    "the page content itself was verified identical"
)


@pytest.fixture(scope="module")
def built_data_dir(tmp_path_factory, request):
    """Build recipes.json once for the module and point FOODGUIDE_DATA_DIR at it."""
    tmp_path = tmp_path_factory.mktemp("recipes_golden")
    if (CACHE_DIR / "index.html").exists():
        fetcher = CachedFetcher(CACHE_DIR, delay=0.0)
    else:
        try:
            PoliteFetcher().fetch(
                "https://www.canada.ca/en/health-canada/services/food-guide"
                "/eating-support/kitchen/recipes.html"
            )
        except Exception as error:  # noqa: BLE001 - any network failure skips
            pytest.skip(f"live canada.ca fetch unavailable, skipping golden build: {error}")
        fetcher = PoliteFetcher()
    build_recipes_json(tmp_path / "recipes.json", fetcher=fetcher)
    os.environ["FOODGUIDE_DATA_DIR"] = str(tmp_path)
    request.addfinalizer(lambda: os.environ.pop("FOODGUIDE_DATA_DIR", None))

    document = json.loads((tmp_path / "recipes.json").read_text(encoding="utf-8"))
    return tmp_path, document


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _built_recipe(document, slug):
    for recipe in document["recipes"]:
        if recipe["slug"] == slug:
            return recipe
    raise AssertionError(f"built recipes.json has no recipe with slug {slug!r}")


def test_golden_recipe_count(built_data_dir, golden):
    _, document = built_data_dir
    expected = golden["source"]["recipe_count"]
    actual = document["source"]["recipe_count"]
    assert actual == expected, (
        f"built recipes.json has {actual} recipes but the golden key expects "
        f"{expected} — the canada.ca index page changed"
    )


def test_golden_recipes_content(built_data_dir, golden):
    tmp_path, document = built_data_dir
    source = LocalRecipeSource(tmp_path / "recipes.json")

    sha_mismatches = []
    for expected in golden["recipes"]:
        slug = expected["slug"]
        recipe = source.get_recipe(slug)
        assert recipe is not None, f"slug {slug!r}: missing from built recipes.json"

        assert recipe["title"] == expected["title"], f"{slug}: title"
        flattened = [
            item for group in recipe["ingredient_groups"] for item in group["items"]
        ]
        assert flattened == expected["ingredients"], f"{slug}: ingredients"
        assert recipe["directions"] == expected["directions"], f"{slug}: directions"
        assert recipe["prep_time"] == expected["prep_time"], f"{slug}: prep_time"
        assert recipe["cook_time"] == expected["cook_time"], f"{slug}: cook_time"
        assert recipe["servings"] == expected["servings"], f"{slug}: servings"

        built = _built_recipe(document, slug)
        if built.get("page_sha256") != expected.get("page_sha256"):
            sha_mismatches.append(slug)

    if sha_mismatches:
        message = (
            f"page_sha256 mismatch for {len(sha_mismatches)}/{len(golden['recipes'])} "
            f"golden recipes: {', '.join(sha_mismatches)}. {SHA_NOTE}."
        )
        warnings.warn(message, stacklevel=1)
        print(f"\n[GOLDEN] {message}")
