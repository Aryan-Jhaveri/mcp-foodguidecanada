"""Shared pytest fixtures for the foodguide test suite (kept small)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pages_fixture import PagesServer, loopback_available


@pytest.fixture()
def pages_server(tmp_path: Path):
    """A real http.server serving the committed canada.ca fixture pages.

    Tests point production code at it with::

        monkeypatch.setenv("FOODGUIDE_SOURCE_BASE_URL", pages_server.base_url)

    Skips cleanly in sandboxes that block all local TCP connects.
    """
    if not loopback_available():
        pytest.skip("loopback TCP connections unavailable in this sandbox")
    server = PagesServer(serve_dir=tmp_path / "www")
    try:
        server.stage()
        yield server
    finally:
        server.close()
