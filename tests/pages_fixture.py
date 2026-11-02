"""Real localhost http.server fixture for the saved canada.ca pages.

No mocks: this module starts a real ``http.server.ThreadingHTTPServer`` in a
background thread and serves the REAL committed fixture pages from
``tests/fixtures/pages/`` at the SAME URL paths the live canada.ca site uses,
so production code (builders/CLI honuring ``FOODGUIDE_SOURCE_BASE_URL``) can be
exercised end-to-end against a real HTTP round trip.

Importable as ``pages_fixture`` from tests, same pattern as ``cnf_fixture``.

Some CI sandboxes block ALL local TCP connects, so ``loopback_available()``
probes first and the ``pages_server`` pytest fixture (tests/conftest.py) skips
cleanly when that is the case. GitHub runners and dev machines work.

Self-check without the network (staging/tree layout only)::

    uv run python tests/pages_fixture.py
"""

from __future__ import annotations

import http.server
import re
import shutil
import socket
import tempfile
import threading
from functools import partial
from pathlib import Path

# --------------------------------------------------------------------------- #
# Canonical fixture mapping: URL paths <-> committed files
# --------------------------------------------------------------------------- #

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pages"

#: URL paths exactly as they exist on live canada.ca.
URL_PATHS: dict[str, str] = {
    "dri": (
        "/en/health-canada/services/food-nutrition/healthy-eating/"
        "dietary-reference-intakes/tables/reference-values-macronutrients.html"
    ),
    "eer": (
        "/en/health-canada/services/food-nutrition/healthy-eating/"
        "dietary-reference-intakes/tables/"
        "equations-estimate-energy-requirement.html"
    ),
    "index": "/en/health-canada/services/food-guide/eating-support/kitchen/recipes.html",
    "recipe:<slug>": (
        "/en/health-canada/services/food-guide/eating-support/kitchen/"
        "recipes/<slug>.html"
    ),
}

#: canonical key -> file name inside FIXTURE_DIR (recipes live in recipes/).
_FILES: dict[str, str] = {
    "dri": "dri_macronutrients.html",
    "eer": "eer_equations.html",
    "index": "recipes_index.html",
}


def url_path_for_key(key: str) -> str:
    """Canonical key ("dri", "eer", "index", "recipe:<slug>") -> URL path."""
    if key in ("dri", "eer", "index"):
        return URL_PATHS[key]
    if key.startswith("recipe:"):
        return URL_PATHS["recipe:<slug>"].replace("<slug>", key.split(":", 1)[1])
    raise KeyError(f"unknown pages_fixture key: {key!r} (want dri/eer/index/recipe:<slug>)")


def fixture_file_for_key(key: str) -> Path:
    """Canonical key -> the committed pristine fixture file."""
    if key.startswith("recipe:"):
        return FIXTURE_DIR / "recipes" / f"{key.split(':', 1)[1]}.html"
    return FIXTURE_DIR / _FILES[key]


def canonical_keys() -> list[str]:
    """All canonical keys: dri, eer, index and one recipe:<slug> per fixture."""
    recipes = sorted((FIXTURE_DIR / "recipes").glob("*.html"))
    return ["dri", "eer", "index"] + [f"recipe:{page.stem}" for page in recipes]


def pristine(dest: Path) -> None:
    """Stage the pristine fixture tree into *dest* at the canonical URL paths.

    Files land mirrored to the live canada.ca layout, e.g. *dest* +
    "/en/health-canada/services/food-guide/eating-support/kitchen/recipes.html".
    """
    dest.mkdir(parents=True, exist_ok=True)
    for key in canonical_keys():
        target = dest / url_path_for_key(key).lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture_file_for_key(key), target)


# --------------------------------------------------------------------------- #
# The real HTTP server
# --------------------------------------------------------------------------- #


class _PagesHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the staged tree; honours per-server ``fail_paths`` first."""

    def log_message(self, *args):  # keep test output clean
        pass

    def guess_type(self, path):  # fixture pages are always HTML
        if str(path).endswith(".html"):
            return "text/html; charset=utf-8"
        return super().guess_type(path)

    def _fail_status(self) -> int | None:
        return getattr(self.server, "fail_paths", {}).get(self.path)

    def _send_failure(self, status: int) -> None:
        body = f"pages_fixture: forced HTTP {status} for {self.path}\n".encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        status = self._fail_status()
        if status is not None:
            self._send_failure(status)
            return
        super().do_GET()

    def do_HEAD(self):
        status = self._fail_status()
        if status is not None:
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        super().do_HEAD()


class PagesServer:
    """A real ThreadingHTTPServer on 127.0.0.1:0 serving the fixture pages.

    Usage::

        server = PagesServer()
        server.stage()                      # pristine fixture tree
        server.stage({"index": None})       # ...or with overrides
        server.fail("dri")                  # force 500 on the DRI path
        server.url("index")                 # http://127.0.0.1:<port>/en/...
    """

    def __init__(self, serve_dir: Path | None = None):
        self._owns_dir = serve_dir is None
        self.serve_dir = Path(serve_dir) if serve_dir is not None else Path(tempfile.mkdtemp(prefix="foodguide-pages-"))
        handler = partial(_PagesHandler, directory=str(self.serve_dir))
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        #: URL path -> HTTP status to force for that path (checked pre-filesystem).
        self._httpd.fail_paths: dict[str, int] = {}
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="pages-fixture-server")
        self._thread.start()

    # -- basics ------------------------------------------------------------ #

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def url(self, key: str) -> str:
        """Full URL for a canonical key ("dri", "eer", "index", "recipe:<slug>")."""
        return self.base_url + url_path_for_key(key)

    def _resolve(self, key_or_path: str) -> str:
        """Canonical key OR full URL path -> URL path."""
        if key_or_path.startswith("/"):
            return key_or_path
        return url_path_for_key(key_or_path)

    # -- staging ----------------------------------------------------------- #

    def stage(self, overrides: dict[str, str | bytes | Path | None] | None = None) -> None:
        """Re-copy the pristine fixture tree, then apply overrides.

        Override keys: "dri", "eer", "index", "recipe:<slug>". Values:
        str (utf-8 text), bytes, Path (copy that file), or None (delete the
        file from the tree -> 404). Staging again starts from the pristine
        tree, so overrides are not cumulative; forced failures are cleared.
        """
        pristine(self.serve_dir)
        self._httpd.fail_paths = {}
        for key, value in (overrides or {}).items():
            target = self.serve_dir / self._resolve(key).lstrip("/")
            if value is None:
                target.unlink(missing_ok=True)
            elif isinstance(value, bytes):
                target.write_bytes(value)
            elif isinstance(value, Path):
                shutil.copyfile(value, target)
            else:
                target.write_text(str(value), encoding="utf-8")

    # -- forced failures --------------------------------------------------- #

    def fail(self, key_or_path: str, code: int = 500) -> None:
        """Force *code* on a canonical key or full URL path (pre-filesystem)."""
        self._httpd.fail_paths[self._resolve(key_or_path)] = code

    def unfail(self, key_or_path: str) -> None:
        self._httpd.fail_paths.pop(self._resolve(key_or_path), None)

    # -- lifecycle --------------------------------------------------------- #

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()
        if self._owns_dir:
            shutil.rmtree(self.serve_dir, ignore_errors=True)

    def __enter__(self) -> "PagesServer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Helpers for offline failure tests
# --------------------------------------------------------------------------- #

_INGREDIENTS_HEADING_RE = re.compile(r"<h2\b[^>]*>\s*Ingredients\s*</h2\s*>", re.IGNORECASE)


def strip_ingredients_heading(html: str) -> str:
    """Remove only the ``<h2 ...>Ingredients</h2>`` heading, keep the list."""
    return _INGREDIENTS_HEADING_RE.sub("", html)


def truncate_html(html: str, n_chars: int) -> str:
    """Return ``html[:n_chars]`` (simulates a truncated/interrupted response)."""
    return html[:n_chars]


def dead_proxy_env() -> dict[str, str]:
    """Env for subprocess offline tests: everything goes to the discard port."""
    dead = "http://127.0.0.1:9"
    return {
        "HTTP_PROXY": dead,
        "HTTPS_PROXY": dead,
        "http_proxy": dead,
        "https_proxy": dead,
        "NO_PROXY": "",
        "no_proxy": "",
    }


def fixture_recipe_cache_dir(tmp_path: Path) -> Path:
    """Build the flat cache dir layout production ``CachedFetcher`` expects.

    ``index.html`` + ``<slug>.html`` copied from the committed fixtures, so
    the recipes golden test can run with zero network when loopback is
    unavailable. Returns the cache directory path.
    """
    cache_dir = tmp_path / "recipe_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE_DIR / "recipes_index.html", cache_dir / "index.html")
    for page in sorted((FIXTURE_DIR / "recipes").glob("*.html")):
        shutil.copyfile(page, cache_dir / page.name)
    return cache_dir


# --------------------------------------------------------------------------- #
# Loopback probe
# --------------------------------------------------------------------------- #


def loopback_available() -> bool:
    """Probe that a real ThreadingHTTPServer accepts a loopback TCP connect.

    Some sandboxes block ALL local TCP connects; there the network tests must
    skip cleanly (GitHub runners and dev machines work).
    """
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PagesHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            return True
    except OSError:
        return False
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    # Offline self-check: stage the pristine tree into a temp dir and print
    # where the canonical URL paths landed.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "www"
        pristine(root)
        print(f"staged fixture tree into {root}\n")
        for key in canonical_keys():
            landed = root / url_path_for_key(key).lstrip("/")
            ok = "ok" if landed.is_file() else "MISSING"
            print(f"{ok}  {url_path_for_key(key)}  <-  {landed}")
