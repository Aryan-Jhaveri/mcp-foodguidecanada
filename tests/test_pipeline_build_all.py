"""Tests for `data build all` (foodguide.pipeline.build_all), fully offline.

DRI/EER/recipe pages are served from tests/fixtures by monkeypatching
``HttpFetcher.fetch`` (DRI/EER) and ``PoliteFetcher.fetch`` (recipes); the CNF
zip comes from the deterministic mini-zip fixture. One test spins a localhost
http.server to exercise the CKAN lookup + zip download helpers.
"""

from __future__ import annotations

import functools
import hashlib
import http.server
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cnf_fixture import make_mini_zip

import foodguide.pipeline.build_all as build_all_module
from foodguide.builders.dri_eer import (
    DRI_URL,
    EER_URL,
    HttpFetcher,
    _provenance,
    _write_payload,
    parse_dri_page,
    parse_eer_page,
)
from foodguide.cnf import builder as cnf_builder
from foodguide.pipeline.build_all import (
    BuildAllError,
    build_all,
    download_cnf_zip,
    find_cnf_zip_url,
    normalize_skip,
)
from foodguide.pipeline.manifest import changed_datasets
from foodguide.recipes.fetch import INDEX_URL, PoliteFetcher, recipe_url

FIXTURES = Path(__file__).parent / "fixtures"

DATASET_NAMES = {
    "cnf.sqlite",
    "cnf.sqlite.gz",
    "recipes.json",
    "dri_macronutrients.json",
    "eer_equations.json",
}

_RECIPE_FIXTURES = {
    "test-berry-crisp": "two-groups.html",
    "test-fruit-salad": "fruit-salad.html",
    "test-oat-bowl": "no-tips.html",
}


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _recipe_map() -> dict[str, str]:
    mapping = {INDEX_URL: _fixture("recipes_html/index.html")}
    for slug, filename in _RECIPE_FIXTURES.items():
        mapping[recipe_url(slug)] = _fixture(f"recipes_html/{filename}")
    return mapping


def _recipe_fetcher(monkeypatch):
    """Point PoliteFetcher.fetch at the recipes_html fixtures."""
    mapping = _recipe_map()
    monkeypatch.setattr(PoliteFetcher, "fetch", lambda self, url: mapping[url])


def _dri_eer_fetcher(monkeypatch):
    """Point HttpFetcher.fetch at the dri_eer fixtures (kept offline even if a
    builder ignores the substituted builder functions)."""
    mapping = {
        DRI_URL: _fixture("dri_eer/dri_minimal.html"),
        EER_URL: _fixture("dri_eer/eer_minimal.html"),
    }
    monkeypatch.setattr(HttpFetcher, "fetch", lambda self, url: mapping[url])


def _fixture_dri_eer_builders(monkeypatch):
    """Replace build_all's build_dri/build_eer with fixture-backed versions.

    The real builders run the full-page validator (22 DRI rows, every EER
    band), which the minimal hand-written fixtures cannot satisfy; these
    substitutes parse the fixture with the real parser and write through the
    real payload writer, so only validation is skipped (same trick as
    tests/test_dri_eer_cli.py).
    """
    from bs4 import BeautifulSoup

    def build_dri(out_path, fetcher=None):
        html = _fixture("dri_eer/dri_minimal.html")
        payload = parse_dri_page(html)
        payload["_provenance"] = _provenance(DRI_URL, html, BeautifulSoup(html, "html.parser"))
        return _write_payload(Path(out_path), payload)

    def build_eer(out_path, fetcher=None):
        html = _fixture("dri_eer/eer_minimal.html")
        payload = parse_eer_page(html)
        payload["_provenance"] = _provenance(EER_URL, html, BeautifulSoup(html, "html.parser"))
        return _write_payload(Path(out_path), payload)

    monkeypatch.setattr(build_all_module, "build_dri", build_dri)
    monkeypatch.setattr(build_all_module, "build_eer", build_eer)


def _no_network(monkeypatch):
    """Make every network fetch serve local fixtures."""
    _recipe_fetcher(monkeypatch)
    _dri_eer_fetcher(monkeypatch)
    _fixture_dri_eer_builders(monkeypatch)


def _load_manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))


def _temp_build_dirs(parent: Path) -> list[str]:
    return [p.name for p in parent.iterdir() if p.name.startswith(".foodguide-build-")]


# ----------------------------------------------------------------- end to end


def test_build_all_end_to_end(tmp_path, monkeypatch):
    monkeypatch.delenv("FOODGUIDE_RECIPES_CACHE_DIR", raising=False)
    _no_network(monkeypatch)
    zip_path = make_mini_zip(tmp_path / "cnf.zip")
    zip_sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    out_dir = tmp_path / "out"
    manifest = build_all(out_dir, cnf_zip=zip_path)

    for name in DATASET_NAMES | {"manifest.json"}:
        assert (out_dir / name).exists(), f"missing {name}"
    assert set(manifest["datasets"]) == DATASET_NAMES
    assert manifest["schema_version"] == 1

    cnf = manifest["datasets"]["cnf.sqlite"]
    assert cnf["content_hash"]
    assert cnf["upstream"]["zip_sha256"] == zip_sha256
    assert manifest["datasets"]["recipes.json"]["record_count"] == 3
    gz_sha256 = hashlib.sha256((out_dir / "cnf.sqlite.gz").read_bytes()).hexdigest()
    assert manifest["datasets"]["cnf.sqlite.gz"]["sha256"] == gz_sha256

    assert _temp_build_dirs(tmp_path) == []


# ------------------------------------------------------------ reproducibility


def test_rebuild_is_reproducible(tmp_path, monkeypatch):
    monkeypatch.delenv("FOODGUIDE_RECIPES_CACHE_DIR", raising=False)
    _no_network(monkeypatch)
    # build_cnf_db stamps build_time=datetime.now() into its provenance table,
    # which would make the sqlite bytes (and thus the .gz sha256) differ between
    # the two runs. Freeze its clock so the test isolates true determinism; in
    # production, changed_datasets still reports no change across rebuilds
    # because the CNF identity is the content hash, not the file sha256.
    frozen = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(cnf_builder, "datetime", _FrozenDateTime)
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    manifest1 = build_all(tmp_path / "out1", cnf_zip=zip_path)
    manifest2 = build_all(tmp_path / "out2", cnf_zip=zip_path)

    gz1 = manifest1["datasets"]["cnf.sqlite.gz"]["sha256"]
    gz2 = manifest2["datasets"]["cnf.sqlite.gz"]["sha256"]
    assert gz1 == gz2

    # The golden property: a rebuild with unchanged upstreams reports no changes.
    assert changed_datasets(manifest1, manifest2) == []


# ---------------------------------------------------------- failure atomicity


def test_failure_leaves_no_partial_build(tmp_path, monkeypatch):
    _recipe_fetcher(monkeypatch)  # cnf + recipes succeed...
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    def boom(out_path, fetcher=None):
        raise RuntimeError("DRI server exploded")

    monkeypatch.setattr(build_all_module, "build_dri", boom)

    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError):
        build_all(out_dir, cnf_zip=zip_path)

    assert not out_dir.exists()
    assert list(out_dir.glob("*")) == []
    assert _temp_build_dirs(tmp_path) == []


# ------------------------------------------------------------------- skipping


def test_skip_cnf_needs_no_zip(tmp_path, monkeypatch):
    monkeypatch.delenv("FOODGUIDE_RECIPES_CACHE_DIR", raising=False)
    _no_network(monkeypatch)

    manifest = build_all(tmp_path / "out", skip=["cnf"])

    assert set(manifest["datasets"]) == DATASET_NAMES - {"cnf.sqlite", "cnf.sqlite.gz"}
    assert _temp_build_dirs(tmp_path) == []


def test_skip_canonical_names(tmp_path, monkeypatch):
    monkeypatch.delenv("FOODGUIDE_RECIPES_CACHE_DIR", raising=False)
    _no_network(monkeypatch)
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    manifest = build_all(tmp_path / "out", cnf_zip=zip_path, skip=["recipes.json"])

    assert "recipes.json" not in manifest["datasets"]
    assert {"cnf.sqlite", "cnf.sqlite.gz", "dri_macronutrients.json", "eer_equations.json"} <= set(
        manifest["datasets"]
    )


def test_unknown_skip_name_raises():
    with pytest.raises(BuildAllError, match="unknown --skip name"):
        build_all(Path("/tmp/unused"), skip=["bogus"])


# ------------------------------------------------------------------ no zip


def test_missing_zip_raises_with_hint(tmp_path, monkeypatch):
    monkeypatch.delenv("FOODGUIDE_RECIPES_CACHE_DIR", raising=False)
    _no_network(monkeypatch)

    with pytest.raises(BuildAllError, match="--cnf-zip"):
        build_all(tmp_path / "out")

    assert not (tmp_path / "out").exists()
    assert _temp_build_dirs(tmp_path) == []


# ------------------------------------------------------------ normalize_skip


def test_normalize_skip_mapping():
    assert normalize_skip([]) == set()
    assert normalize_skip(["cnf"]) == {"cnf.sqlite"}
    assert normalize_skip(["cnf.sqlite"]) == {"cnf.sqlite"}
    assert normalize_skip(["recipes"]) == {"recipes.json"}
    assert normalize_skip(["recipes.json"]) == {"recipes.json"}
    assert normalize_skip(["dri"]) == {"dri_macronutrients.json"}
    assert normalize_skip(["eer"]) == {"eer_equations.json"}
    assert normalize_skip(["eer_equations.json"]) == {"eer_equations.json"}
    assert normalize_skip(["cnf", "recipes", "dri", "eer"]) == DATASET_NAMES - {
        "cnf.sqlite.gz"
    }


def test_normalize_skip_unknown_name_lists_valid_names():
    with pytest.raises(BuildAllError) as excinfo:
        normalize_skip(["nonsense"])
    assert "cnf.sqlite" in str(excinfo.value)
    assert "recipes.json" in str(excinfo.value)


# ------------------------------------------------- CKAN lookup + zip download


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass


def _loopback_available() -> bool:
    """Probe that loopback TCP connects work (some CI sandboxes block it)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import socket

        with socket.create_connection(("127.0.0.1", port), timeout=3):
            return True
    except OSError:
        return False
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture()
def ckan_server(tmp_path):
    """A localhost http.server serving a fake CKAN record and the zip bytes."""
    if not _loopback_available():
        pytest.skip("loopback TCP connections unavailable in this sandbox")
    www = tmp_path / "www"
    (www / "files").mkdir(parents=True)

    zip_path = make_mini_zip(www / "files" / "cnf.zip")
    zip_sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    def _record(name: str, resources: list[dict]) -> None:
        payload = {"result": {"metadata_modified": "2026-01-02T03:04:05Z", "resources": resources}}
        (www / name).write_text(json.dumps(payload), encoding="utf-8")

    handler = functools.partial(_QuietHandler, directory=str(www))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield www, f"http://127.0.0.1:{server.server_address[1]}", zip_sha256
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_find_and_download_cnf_zip(tmp_path, ckan_server, monkeypatch):
    www, base, zip_sha256 = ckan_server
    _record = json.dumps(
        {
            "result": {
                "metadata_modified": "2026-01-02T03:04:05Z",
                "resources": [
                    {"format": "CSV", "url": f"{base}/files/other.csv"},
                    {"format": "zip", "url": f"{base}/files/cnf.zip"},
                ],
            }
        }
    )
    (www / "package_show.json").write_text(_record, encoding="utf-8")
    monkeypatch.setattr(build_all_module, "CKAN_PACKAGE_URL", f"{base}/package_show.json")

    url, modified = find_cnf_zip_url()
    assert url == f"{base}/files/cnf.zip"
    assert modified == "2026-01-02T03:04:05Z"

    dest = tmp_path / "downloads"
    path = download_cnf_zip(url, dest)
    assert path == dest / "cnf.zip"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == zip_sha256
    assert not (dest / "cnf.zip.part").exists()


def test_find_cnf_zip_url_no_zip_resource(tmp_path, ckan_server, monkeypatch):
    www, base, _zip_sha256 = ckan_server
    payload = json.dumps(
        {
            "result": {
                "metadata_modified": "2026-01-02T03:04:05Z",
                "resources": [{"format": "CSV", "url": f"{base}/files/other.csv"}],
            }
        }
    )
    (www / "package_nozip.json").write_text(payload, encoding="utf-8")
    monkeypatch.setattr(build_all_module, "CKAN_PACKAGE_URL", f"{base}/package_nozip.json")

    with pytest.raises(BuildAllError, match="no ZIP resource"):
        find_cnf_zip_url()


def test_download_failure_cleans_part(tmp_path, ckan_server, monkeypatch):
    _www, base, _zip_sha256 = ckan_server

    with pytest.raises(BuildAllError, match="cannot download"):
        download_cnf_zip(f"{base}/files/missing.zip", tmp_path / "downloads")

    assert not (tmp_path / "downloads" / "cnf.zip.part").exists()
    assert not (tmp_path / "downloads" / "cnf.zip").exists()


# --------------------------------------------------------------- run_build_all


def test_run_build_all_logs_summary(tmp_path, monkeypatch):
    monkeypatch.delenv("FOODGUIDE_RECIPES_CACHE_DIR", raising=False)
    _no_network(monkeypatch)
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    lines: list[str] = []
    manifest = build_all_module.run_build_all(
        tmp_path / "out", cnf_zip=zip_path, download_cnf=False, skip=[], log=lines.append
    )

    assert manifest["schema_version"] == 1
    joined = "\n".join(lines)
    assert "content_hash=" in joined
    assert "zip_sha256=" in joined
    assert "recipe_count=3" in joined
    assert "page_sha256=" in joined
    assert f"Wrote {tmp_path / 'out'}/manifest.json" in lines[-1]


def test_run_build_all_failure_exits_1(tmp_path, monkeypatch):
    _recipe_fetcher(monkeypatch)
    zip_path = make_mini_zip(tmp_path / "cnf.zip")
    monkeypatch.setattr(
        build_all_module,
        "build_dri",
        lambda out_path, fetcher=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    lines: list[str] = []
    with pytest.raises(SystemExit) as excinfo:
        build_all_module.run_build_all(
            tmp_path / "out", cnf_zip=zip_path, download_cnf=False, skip=[], log=lines.append
        )
    assert excinfo.value.code == 1
    assert any("build all failed: boom" in line for line in lines)
    assert not (tmp_path / "out").exists()
