"""Tests for `data build all` (foodguide.pipeline.build_all), with no mocks.

Every page fetch goes through a real localhost http.server serving the
committed canada.ca fixture pages (tests/pages_fixture.py): tests point the
production builders at it purely via the ``FOODGUIDE_SOURCE_BASE_URL``
environment variable, so the real builders, parsers and validators run
unchanged. The CNF zip comes from the deterministic mini-zip fixture; the
CKAN lookup/download tests spin up their own real localhost http.server for
the CKAN record and the zip bytes (addressable via
``FOODGUIDE_CKAN_PACKAGE_URL``).
"""

from __future__ import annotations

import functools
import hashlib
import http.server
import json
import threading
from pathlib import Path

import pytest
from cnf_fixture import make_mini_zip
from pages_fixture import FIXTURE_DIR as PAGES_FIXTURE_DIR
from pages_fixture import truncate_html

import foodguide.pipeline.build_all as build_all_module
from foodguide.builders.dri_eer import BuildError
from foodguide.pipeline.build_all import (
    BuildAllError,
    build_all,
    download_cnf_zip,
    find_cnf_zip_url,
    normalize_skip,
)
from foodguide.pipeline.manifest import changed_datasets

DATASET_NAMES = {
    "cnf.sqlite",
    "cnf.sqlite.gz",
    "recipes.json",
    "dri_macronutrients.json",
    "eer_equations.json",
}

#: The recipe pages committed under tests/fixtures/pages/recipes/ — exactly
#: what the fixture server can serve. The committed index still lists 141
#: slugs, so every crawl passes ``recipes_only=RECIPE_SLUGS``.
RECIPE_SLUGS = sorted(p.stem for p in (PAGES_FIXTURE_DIR / "recipes").glob("*.html"))


def _use_fixture_pages(monkeypatch, pages_server) -> None:
    """Point every builder at the real fixture pages server via env only."""
    monkeypatch.delenv("FOODGUIDE_RECIPES_CACHE_DIR", raising=False)
    monkeypatch.setenv("FOODGUIDE_SOURCE_BASE_URL", pages_server.base_url)


def _load_manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))


def _temp_build_dirs(parent: Path) -> list[str]:
    return [p.name for p in parent.iterdir() if p.name.startswith(".foodguide-build-")]


# ----------------------------------------------------------------- end to end


def test_build_all_end_to_end(tmp_path, monkeypatch, pages_server):
    _use_fixture_pages(monkeypatch, pages_server)
    assert len(RECIPE_SLUGS) == 12
    zip_path = make_mini_zip(tmp_path / "cnf.zip")
    zip_sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    out_dir = tmp_path / "out"
    manifest = build_all(out_dir, cnf_zip=zip_path, recipes_only=RECIPE_SLUGS)

    for name in DATASET_NAMES | {"manifest.json"}:
        assert (out_dir / name).exists(), f"missing {name}"
    assert set(manifest["datasets"]) == DATASET_NAMES
    assert manifest["schema_version"] == 1

    cnf = manifest["datasets"]["cnf.sqlite"]
    assert cnf["content_hash"]
    assert cnf["upstream"]["zip_sha256"] == zip_sha256
    assert manifest["datasets"]["recipes.json"]["record_count"] == 12
    recipes_doc = json.loads((out_dir / "recipes.json").read_text(encoding="utf-8"))
    assert recipes_doc["source"]["recipe_count"] == 12
    assert recipes_doc["source"]["index_recipe_count"] == 141
    assert recipes_doc["source"]["index_url"] == pages_server.url("index")
    gz_sha256 = hashlib.sha256((out_dir / "cnf.sqlite.gz").read_bytes()).hexdigest()
    assert manifest["datasets"]["cnf.sqlite.gz"]["sha256"] == gz_sha256

    assert _temp_build_dirs(tmp_path) == []


# ------------------------------------------------------------ reproducibility


def test_rebuild_is_reproducible(tmp_path, monkeypatch, pages_server):
    _use_fixture_pages(monkeypatch, pages_server)
    # build_cnf_db stamps build_time into its provenance table, which would
    # make the sqlite bytes (and thus the .gz sha256) differ between the two
    # runs. SOURCE_DATE_EPOCH is production's reproducible-build override and
    # pins that timestamp, so the test isolates true determinism. (The
    # recipes.json fetched_at still differs per run, but changed_datasets
    # compares content identities, which ignore build timestamps.)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1765000000")
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    manifest1 = build_all(tmp_path / "out1", cnf_zip=zip_path, recipes_only=RECIPE_SLUGS)
    manifest2 = build_all(tmp_path / "out2", cnf_zip=zip_path, recipes_only=RECIPE_SLUGS)

    gz1 = manifest1["datasets"]["cnf.sqlite.gz"]["sha256"]
    gz2 = manifest2["datasets"]["cnf.sqlite.gz"]["sha256"]
    assert gz1 == gz2

    # The golden property: a rebuild with unchanged upstreams reports no changes.
    assert changed_datasets(manifest1, manifest2) == []


def test_skip_rebuild_removes_stale_dataset_files(tmp_path, monkeypatch, pages_server):
    """Rebuilding with --skip into an existing dir must not leave stale datasets.

    The manifest describes the whole directory: files it no longer lists are
    removed, so the dir never ships unverified files next to a manifest.
    """
    _use_fixture_pages(monkeypatch, pages_server)
    zip_path = make_mini_zip(tmp_path / "cnf.zip")
    out_dir = tmp_path / "out"

    build_all(out_dir, cnf_zip=zip_path, recipes_only=RECIPE_SLUGS)
    assert (out_dir / "cnf.sqlite").exists()
    assert (out_dir / "cnf.sqlite.gz").exists()

    manifest = build_all(out_dir, cnf_zip=zip_path, skip=["cnf"], recipes_only=RECIPE_SLUGS)
    assert "cnf.sqlite" not in manifest["datasets"]
    assert not (out_dir / "cnf.sqlite").exists()
    assert not (out_dir / "cnf.sqlite.gz").exists()
    assert (out_dir / "recipes.json").exists()
    for name in manifest["datasets"]:
        assert (out_dir / name).exists()


# ---------------------------------------------------------- failure atomicity


def test_failure_leaves_no_partial_build(tmp_path, monkeypatch, pages_server):
    """A truncated (HTTP 200) DRI page fails the real builder; nothing publishes."""
    _use_fixture_pages(monkeypatch, pages_server)
    # CNF and recipes succeed; the DRI page is cut off mid-document so the
    # real parser/validator raises BuildError ("missing table").
    dri_html = (PAGES_FIXTURE_DIR / "dri_macronutrients.html").read_text(encoding="utf-8")
    pages_server.stage({"dri": truncate_html(dri_html, 5000)})
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    out_dir = tmp_path / "out"
    with pytest.raises(BuildError):
        build_all(out_dir, cnf_zip=zip_path, recipes_only=RECIPE_SLUGS)

    assert not out_dir.exists()
    assert list(out_dir.glob("*")) == []
    assert _temp_build_dirs(tmp_path) == []


# ------------------------------------------------------------------- skipping


def test_skip_cnf_needs_no_zip(tmp_path, monkeypatch, pages_server):
    _use_fixture_pages(monkeypatch, pages_server)

    manifest = build_all(tmp_path / "out", skip=["cnf"], recipes_only=RECIPE_SLUGS)

    assert set(manifest["datasets"]) == DATASET_NAMES - {"cnf.sqlite", "cnf.sqlite.gz"}
    assert _temp_build_dirs(tmp_path) == []


def test_skip_canonical_names(tmp_path, monkeypatch, pages_server):
    _use_fixture_pages(monkeypatch, pages_server)
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    manifest = build_all(
        tmp_path / "out", cnf_zip=zip_path, skip=["recipes.json"], recipes_only=RECIPE_SLUGS
    )

    assert "recipes.json" not in manifest["datasets"]
    assert {"cnf.sqlite", "cnf.sqlite.gz", "dri_macronutrients.json", "eer_equations.json"} <= set(
        manifest["datasets"]
    )


def test_unknown_skip_name_raises():
    with pytest.raises(BuildAllError, match="unknown --skip name"):
        build_all(Path("/tmp/unused"), skip=["bogus"])


# ------------------------------------------------------------------ no zip


def test_missing_zip_raises_with_hint(tmp_path):
    # Nothing is fetched before the missing-zip check, so no server is needed.
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


@pytest.fixture()
def ckan_server(tmp_path):
    """A localhost http.server serving a CKAN record and the zip bytes."""
    from pages_fixture import loopback_available

    if not loopback_available():
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
    monkeypatch.setenv("FOODGUIDE_CKAN_PACKAGE_URL", f"{base}/package_show.json")

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
    monkeypatch.setenv("FOODGUIDE_CKAN_PACKAGE_URL", f"{base}/package_nozip.json")

    with pytest.raises(BuildAllError, match="no ZIP resource"):
        find_cnf_zip_url()


def test_download_failure_cleans_part(tmp_path, ckan_server, monkeypatch):
    _www, base, _zip_sha256 = ckan_server

    with pytest.raises(BuildAllError, match="cannot download"):
        download_cnf_zip(f"{base}/files/missing.zip", tmp_path / "downloads")

    assert not (tmp_path / "downloads" / "cnf.zip.part").exists()
    assert not (tmp_path / "downloads" / "cnf.zip").exists()


# --------------------------------------------------------------- run_build_all


def test_run_build_all_logs_summary(tmp_path, monkeypatch, pages_server):
    _use_fixture_pages(monkeypatch, pages_server)
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    lines: list[str] = []
    manifest = build_all_module.run_build_all(
        tmp_path / "out",
        cnf_zip=zip_path,
        download_cnf=False,
        skip=[],
        recipes_only=RECIPE_SLUGS,
        log=lines.append,
    )

    assert manifest["schema_version"] == 1
    joined = "\n".join(lines)
    assert "content_hash=" in joined
    assert "zip_sha256=" in joined
    assert "recipe_count=12" in joined
    assert "page_sha256=" in joined
    assert f"Wrote {tmp_path / 'out'}/manifest.json" in lines[-1]


def test_run_build_all_failure_exits_1(tmp_path, monkeypatch, pages_server):
    _use_fixture_pages(monkeypatch, pages_server)
    # CNF and recipes succeed; the truncated real DRI page (HTTP 200, broken
    # content) makes the real build_dri raise BuildError.
    dri_html = (PAGES_FIXTURE_DIR / "dri_macronutrients.html").read_text(encoding="utf-8")
    pages_server.stage({"dri": truncate_html(dri_html, 5000)})
    zip_path = make_mini_zip(tmp_path / "cnf.zip")

    lines: list[str] = []
    with pytest.raises(SystemExit) as excinfo:
        build_all_module.run_build_all(
            tmp_path / "out",
            cnf_zip=zip_path,
            download_cnf=False,
            skip=[],
            recipes_only=RECIPE_SLUGS,
            log=lines.append,
        )
    assert excinfo.value.code == 1
    joined = "\n".join(lines)
    assert "build all failed: " in joined
    assert "DRI" in joined
    assert not (tmp_path / "out").exists()
