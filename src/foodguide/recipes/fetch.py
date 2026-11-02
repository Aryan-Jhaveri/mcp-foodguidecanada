"""Fetch canada.ca recipe pages, with polite delays and optional on-disk caching.

The URLs here are the canonical live defaults. Set ``FOODGUIDE_SOURCE_BASE_URL``
to fetch the index and recipe pages from another base (e.g. a local http.server
fixture in tests); ``index_url()`` and ``recipe_url()`` read it at call time,
never at import time, so the default behaviour is unchanged when it is unset.
``cache_name`` is path-based and works with any base URL.
"""

import time
import urllib.error
import urllib.request
from pathlib import Path

from foodguide.config import source_base_url

USER_AGENT = "foodguide-data-build/0.1 (+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada)"
INDEX_URL = "https://www.canada.ca/en/health-canada/services/food-guide/eating-support/kitchen/recipes.html"
BASE_URL = "https://www.canada.ca/en/health-canada/services/food-guide/eating-support/kitchen"


def fetch_page(url: str, timeout: float = 30.0, retries: int = 4) -> str:
    """GET a URL and return its body decoded as utf-8, retrying on network errors."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as error:
            last_error = error
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    assert last_error is not None
    raise last_error


def index_url() -> str:
    """Recipe index URL, honouring FOODGUIDE_SOURCE_BASE_URL at call time."""
    return source_base_url() + "/en/health-canada/services/food-guide/eating-support/kitchen/recipes.html"


def recipe_url(slug: str) -> str:
    """Recipe page URL for a slug, honouring FOODGUIDE_SOURCE_BASE_URL at call time."""
    return source_base_url() + f"/en/health-canada/services/food-guide/eating-support/kitchen/recipes/{slug}.html"


def cache_name(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    if path.endswith("recipes.html"):
        return "index.html"
    return path.rsplit("/", 1)[-1]


class PoliteFetcher:
    """Fetches pages directly, enforcing a minimum delay between fetches."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._last_fetch: float | None = None

    def fetch(self, url: str) -> str:
        if self._last_fetch is not None:
            elapsed = time.monotonic() - self._last_fetch
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
        text = fetch_page(url)
        self._last_fetch = time.monotonic()
        return text


class CachedFetcher:
    """Fetches through PoliteFetcher but serves repeat requests from a cache dir."""

    def __init__(self, cache_dir, delay: float = 1.0):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._polite = PoliteFetcher(delay=delay)

    def fetch(self, url: str) -> str:
        cache_path = self.cache_dir / cache_name(url)
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8")
        text = self._polite.fetch(url)
        cache_path.write_text(text, encoding="utf-8")
        return text
