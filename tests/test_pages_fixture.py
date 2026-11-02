"""Tests for the real localhost pages server fixture (no mocks anywhere)."""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest
from pages_fixture import (
    FIXTURE_DIR,
    URL_PATHS,
    fixture_file_for_key,
    fixture_recipe_cache_dir,
    loopback_available,
    strip_ingredients_heading,
    truncate_html,
)

# This sandbox blocks ALL local TCP connects; the tests must skip cleanly
# there (GitHub runners and dev machines work).
pytestmark = pytest.mark.skipif(
    not loopback_available(),
    reason="loopback TCP connections unavailable in this sandbox",
)


def _fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.status == 200
        assert response.headers["Content-Type"].startswith("text/html")
        return response.read()


def test_server_serves_canonical_pages_bytes_identical_to_fixtures(pages_server):
    """Every canonical path serves the exact committed fixture bytes."""
    cases = {
        "dri": FIXTURE_DIR / "dri_macronutrients.html",
        "eer": FIXTURE_DIR / "eer_equations.html",
        "index": FIXTURE_DIR / "recipes_index.html",
        "recipe:apple-sandwiches": FIXTURE_DIR / "recipes" / "apple-sandwiches.html",
    }
    for key, fixture_path in cases.items():
        assert URL_PATHS.get(key) or key.startswith("recipe:")
        served = _fetch_bytes(pages_server.url(key))
        assert served == fixture_path.read_bytes(), key
        assert pages_server.url(key).startswith(pages_server.base_url)


def test_fail_forces_status_on_dri_path(pages_server):
    pages_server.fail("dri", 500)
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _fetch_bytes(pages_server.url("dri"))
    assert excinfo.value.code == 500
    # The forced failure is pre-filesystem: unfail restores the real page.
    pages_server.unfail("dri")
    assert _fetch_bytes(pages_server.url("dri")) == (FIXTURE_DIR / "dri_macronutrients.html").read_bytes()


def test_stage_none_override_makes_path_404(pages_server):
    pages_server.stage({"index": None})
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _fetch_bytes(pages_server.url("index"))
    assert excinfo.value.code == 404
    # Other pages are untouched; recipe:<slug> keys work as override keys too.
    assert _fetch_bytes(pages_server.url("recipe:kale-chickpea-curry")) == (
        FIXTURE_DIR / "recipes" / "kale-chickpea-curry.html"
    ).read_bytes()


def test_strip_ingredients_heading_keeps_list():
    """On the real apple-sandwiches page: heading gone, <li> items kept."""
    html = fixture_file_for_key("recipe:apple-sandwiches").read_text(encoding="utf-8")
    assert "Ingredients</h2>" in html
    out = strip_ingredients_heading(html)
    assert "Ingredients</h2>" not in out
    assert "<li" in out
    assert len(truncate_html(out, 200)) == 200


def test_fixture_recipe_cache_dir_layout(tmp_path):
    """The flat CachedFetcher cache dir: index.html + <slug>.html files."""
    cache_dir = fixture_recipe_cache_dir(tmp_path)
    assert (cache_dir / "index.html").is_file()
    assert (cache_dir / "index.html").read_bytes() == (FIXTURE_DIR / "recipes_index.html").read_bytes()
    slugs = {p.name for p in cache_dir.glob("*.html")} - {"index.html"}
    assert slugs == {p.name for p in (FIXTURE_DIR / "recipes").glob("*.html")}
    assert "apple-sandwiches.html" in slugs
