"""Golden tests for the recipes builder, in two parts.

The golden key lives at tests/fixtures/golden_recipes.json (override the path with
the FOODGUIDE_TEST_GOLDEN_RECIPES env var — that escape hatch exists purely so a
broken-copy sanity check can be run against a deliberately wrong key; production
runs should never set it).

Part 1 (NOT marked live, runs everywhere, no network): a build over the REAL
committed fixture pages (tests/fixtures/pages) via the production CachedFetcher,
restricted to the 8 golden slugs with ``only=``. The committed index is the real
canada.ca index, so the built document reports index_recipe_count == 141 while
exactly the 8 golden recipes are built.

Part 2 (marked ``live``): the full 141-page crawl. If
/nonexistent/foodguide-test-data/recipes_cache holds the crawled pages
(index.html + one file per slug) the build runs entirely from cache; otherwise
the test falls back to a live PoliteFetcher crawl and skips with a clear message
if the network fetch itself fails. Override the cache dir with
FOODGUIDE_TEST_RECIPE_CACHE.

page_sha256 is informational only: canada.ca serves a dynamic analytics script,
so page_sha256 differs between fetches even for identical content — and the
golden key hashes raw pages while the parser hashes pages with script/style
blocks stripped. Mismatches are reported (warnings.warn) but do NOT fail the
test — only the content fields (title, ingredients, directions, times,
servings) do.
"""

import json
import os
import warnings
from pathlib import Path

import pytest
from pages_fixture import fixture_recipe_cache_dir

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


def _golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _golden_slugs() -> list[str]:
    return [recipe["slug"] for recipe in _golden()["recipes"]]


def _check_golden_recipes(document: dict, recipes_json_path: Path, golden: dict) -> list[str]:
    """Assert every golden recipe's content against the built document.

    Returns the slugs whose page_sha256 differs (reported, not failed).
    """
    source = LocalRecipeSource(recipes_json_path)

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
    return sha_mismatches


def _built_recipe(document, slug):
    for recipe in document["recipes"]:
        if recipe["slug"] == slug:
            return recipe
    raise AssertionError(f"built recipes.json has no recipe with slug {slug!r}")


def _report_sha_mismatches(sha_mismatches: list[str], total: int) -> None:
    if sha_mismatches:
        message = (
            f"page_sha256 mismatch for {len(sha_mismatches)}/{total} "
            f"golden recipes: {', '.join(sha_mismatches)}. {SHA_NOTE}."
        )
        warnings.warn(message, stacklevel=1)
        print(f"\n[GOLDEN] {message}")


# --------------------------------------------------------------------------- #
# Part 1: fixture-based golden test (no network, runs everywhere)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def fixture_built(tmp_path_factory, golden):
    """recipes.json built from the committed fixture pages for the golden slugs."""
    tmp_path = tmp_path_factory.mktemp("recipes_golden_fixture")
    out_path = tmp_path / "recipes.json"
    build_recipes_json(
        out_path,
        fetcher=CachedFetcher(fixture_recipe_cache_dir(tmp_path), delay=0.0),
        only=_golden_slugs(),
    )
    document = json.loads(out_path.read_text(encoding="utf-8"))
    return out_path, document


@pytest.fixture(scope="module")
def golden():
    return _golden()


def test_golden_fixture_document_shape(fixture_built, golden):
    """The fixture build crawls the REAL index (141 links) but builds 8 recipes."""
    _, document = fixture_built
    assert document["source"]["index_recipe_count"] == golden["source"]["recipe_count"]
    assert document["source"]["recipe_count"] == len(golden["recipes"]) == 8


def test_golden_fixture_recipes_content(fixture_built, golden):
    out_path, document = fixture_built
    sha_mismatches = _check_golden_recipes(document, out_path, golden)
    _report_sha_mismatches(sha_mismatches, len(golden["recipes"]))


# --------------------------------------------------------------------------- #
# Part 2: full-crawl golden test (marked live)
# --------------------------------------------------------------------------- #


@pytest.mark.live
def test_golden_full_crawl(tmp_path, golden):
    """A full 141-page build must reproduce the golden key's content.

    Runs from the crawled page cache when present, else crawls canada.ca live
    (skipping with a clear message if the network fetch fails).
    """
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

    out_path = tmp_path / "recipes.json"
    build_recipes_json(out_path, fetcher=fetcher)
    document = json.loads(out_path.read_text(encoding="utf-8"))

    expected_count = golden["source"]["recipe_count"]
    actual_count = document["source"]["recipe_count"]
    assert actual_count == expected_count, (
        f"built recipes.json has {actual_count} recipes but the golden key expects "
        f"{expected_count} — the canada.ca index page changed"
    )

    sha_mismatches = _check_golden_recipes(document, out_path, golden)
    _report_sha_mismatches(sha_mismatches, len(golden["recipes"]))
