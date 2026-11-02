"""Tests for foodguide.pipeline.install: release fetching and install status."""

from __future__ import annotations

import functools
import hashlib
import json
import shutil
import socket
import sqlite3
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from foodguide.pipeline.install import (
    FetchError,
    fetch_from_dir,
    fetch_from_http,
    status,
)
from foodguide.pipeline.manifest import (
    MANIFEST_NAME,
    gzip_reproducible,
    sha256_file,
    write_manifest,
)

# Sorted order, as install.status reports manifest dataset names.
CANONICAL = sorted(["cnf.sqlite", "recipes.json", "dri_macronutrients.json", "eer_equations.json"])


def _loopback_available() -> bool:
    """True when a loopback TCP connect succeeds (blocked in some sandboxes)."""
    server = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except OSError:
            return False
    finally:
        server.close()


LOOPBACK_OK = _loopback_available()


def _make_cnf_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE provenance (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO provenance (key, value) VALUES (?, ?)",
            [
                ("content_hash", "cnf-content-hash"),
                ("zip_sha256", "fake-zip-sha256"),
                ("metadata_modified", "2024-01-01"),
            ],
        )
        conn.execute("CREATE TABLE nutrient (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO nutrient (id, name) VALUES (1, 'protein')")
        conn.commit()
    finally:
        conn.close()


def _make_release(tmp_path: Path) -> tuple[Path, dict]:
    """Build a realistic release directory (datasets + gz + manifest.json)."""
    release = tmp_path / "release"
    release.mkdir()

    _make_cnf_db(release / "cnf.sqlite")
    gzip_reproducible(release / "cnf.sqlite", release / "cnf.sqlite.gz")

    recipes = {
        "source": {
            "index_url": "u",
            "fetched_at": "t",
            "recipe_count": 1,
            "index_sha256": hashlib.sha256(b"index").hexdigest(),
        },
        "filters": {},
        "recipes": [],
    }
    (release / "recipes.json").write_text(json.dumps(recipes), encoding="utf-8")

    provenance = {
        "source_url": "u",
        "page_sha256": hashlib.sha256(b"page").hexdigest(),
        "fetched_at": "t",
        "page_date_modified": "2024-01-01",
    }
    dri = {"_provenance": dict(provenance), "amdrs": {"fat": 30}, "footnotes": ["n"]}
    (release / "dri_macronutrients.json").write_text(json.dumps(dri), encoding="utf-8")
    eer = {"_provenance": dict(provenance), "reference_values": {"a": 1}}
    (release / "eer_equations.json").write_text(json.dumps(eer), encoding="utf-8")

    manifest = write_manifest(release)
    return release, manifest


def _flip_byte(path: Path) -> None:
    """Rewrite a file with one byte flipped, without touching any manifest."""
    data = bytearray(path.read_bytes())
    data[0] ^= 0x01
    path.write_bytes(bytes(data))


def test_fetch_from_dir_installs_all(tmp_path):
    release, manifest = _make_release(tmp_path)
    dest = tmp_path / "dest"
    log: list[str] = []

    records = fetch_from_dir(release, dest, log=log.append)

    # All four canonical files installed, plus the gz asset and the manifest
    # itself (so `data status` can verify the install later).
    assert sorted(p.name for p in dest.iterdir()) == sorted(
        CANONICAL + ["cnf.sqlite.gz", MANIFEST_NAME]
    )
    assert len(records) == 4
    assert sorted(r["name"] for r in records) == CANONICAL

    # Hashes of installed files match the manifest.
    for name in CANONICAL:
        entry = manifest["datasets"][name]
        assert sha256_file(dest / name) == entry["sha256"]

    by_name = {r["name"]: r for r in records}
    cnf = by_name["cnf.sqlite"]
    assert cnf["asset"] == "cnf.sqlite.gz"  # installed via the gz transport
    assert cnf["content_hash"] == manifest["datasets"]["cnf.sqlite"]["content_hash"]
    # Records carry upstream provenance from the manifest.
    for name in CANONICAL:
        assert by_name[name]["upstream"] == manifest["datasets"][name]["upstream"]
        assert by_name[name]["upstream"]  # provenance is present for our fixtures
        assert by_name[name]["source"] == str(release)
        assert by_name[name]["size"] == manifest["datasets"][name]["size"]

    # Log lines were emitted for each installed file (4 datasets + gz + manifest).
    assert len(log) == 6
    assert all("installed" in line for line in log)


def test_fetch_from_dir_is_idempotent(tmp_path):
    release, _manifest = _make_release(tmp_path)
    dest = tmp_path / "dest"
    fetch_from_dir(release, dest)

    log: list[str] = []
    records = fetch_from_dir(release, dest, log=log.append)

    assert records == []
    # gz + 4 datasets report "up to date"; the identical manifest is silent.
    assert len(log) == 5
    assert all("up to date" in line for line in log)
    # Nothing changed on disk.
    assert sorted(p.name for p in dest.iterdir()) == sorted(
        CANONICAL + ["cnf.sqlite.gz", MANIFEST_NAME]
    )


def test_fetch_from_dir_corrupted_json_asset_installs_nothing(tmp_path):
    release, _manifest = _make_release(tmp_path)
    broken = tmp_path / "broken-release"
    shutil.copytree(release, broken)
    _flip_byte(broken / "recipes.json")

    dest = tmp_path / "dest"
    with pytest.raises(FetchError, match="sha256 mismatch for recipes.json"):
        fetch_from_dir(broken, dest)

    # Verification happens before any install: nothing at all was written.
    assert not dest.exists() or list(dest.iterdir()) == []


def test_fetch_from_dir_gz_decompressing_to_wrong_content_refused(tmp_path):
    """A gz whose compressed sha matches but decompresses to other bytes is refused."""
    release, manifest = _make_release(tmp_path)
    broken = tmp_path / "broken-release"
    shutil.copytree(release, broken)
    # Same sqlite content as cnf.sqlite except one extra row -> different sha,
    # then recompressed so the GZ sha256 stays equal to the manifest's gz entry.
    import gzip as _gzip

    plain_path = broken / "cnf.sqlite"
    conn = sqlite3.connect(plain_path)
    try:
        conn.execute("INSERT INTO nutrient (id, name) VALUES (2, 'fat')")
        conn.commit()
    finally:
        conn.close()
    gz_bytes = _gzip.compress(plain_path.read_bytes(), mtime=0)
    (broken / "cnf.sqlite.gz").write_bytes(gz_bytes)
    # Update the manifest's gz sha (simulating an attacker or a bug that only
    # touches the transport copy); the plain cnf.sqlite entry keeps the OLD sha.
    manifest_path = broken / "manifest.json"
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["datasets"]["cnf.sqlite.gz"]["sha256"] = hashlib.sha256(gz_bytes).hexdigest()
    manifest_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")

    dest = tmp_path / "dest"
    with pytest.raises(FetchError, match="cnf.sqlite from gz does not match manifest"):
        fetch_from_dir(broken, dest)
    assert not dest.exists() or list(dest.iterdir()) == []


def test_fetch_from_dir_filtered_install_status_all_ok(tmp_path):
    """A --only install records a manifest subset, so status is all_ok."""
    release, _manifest = _make_release(tmp_path)
    dest = tmp_path / "dest"
    fetch_from_dir(release, dest, only=["recipes"])

    st = status(dest)
    assert st["installed"] is True
    assert st["all_ok"] is True
    assert [f["name"] for f in st["files"]] == ["recipes.json"]

    # A full fetch replaces the manifest with the complete release one.
    fetch_from_dir(release, dest)
    st = status(dest)
    assert st["all_ok"] is True
    assert len(st["files"]) == 5


def test_fetch_from_dir_corrupted_gz_asset_installs_nothing(tmp_path):
    release, _manifest = _make_release(tmp_path)
    broken = tmp_path / "broken-release"
    shutil.copytree(release, broken)
    _flip_byte(broken / "cnf.sqlite.gz")

    dest = tmp_path / "dest"
    with pytest.raises(FetchError, match="sha256 mismatch for cnf.sqlite.gz"):
        fetch_from_dir(broken, dest)

    assert not dest.exists() or list(dest.iterdir()) == []


def test_status(tmp_path):
    release, manifest = _make_release(tmp_path)
    dest = tmp_path / "dest"
    fetch_from_dir(release, dest)

    # The installer installs manifest.json into dest, so status works directly.
    st = status(dest)
    assert st["installed"] is True
    assert st["all_ok"] is True
    assert st["path"] == str(dest)
    assert st["manifest"]["schema_version"] == manifest["schema_version"]
    assert st["manifest"]["built_at"] == manifest["built_at"]
    # The gz asset is installed too and listed as ok.
    assert [f["name"] for f in st["files"]] == sorted(
        CANONICAL + ["cnf.sqlite.gz"]
    )
    assert all(f["state"] == "ok" for f in st["files"])
    assert all(f["actual_sha256"] == f["expected_sha256"] for f in st["files"])

    # Modify one file -> modified state, all_ok flips.
    (dest / "recipes.json").write_text('{"tampered": true}', encoding="utf-8")
    st = status(dest)
    by_name = {f["name"]: f for f in st["files"]}
    assert by_name["recipes.json"]["state"] == "modified"
    assert by_name["recipes.json"]["actual_sha256"] != by_name["recipes.json"]["expected_sha256"]
    assert st["all_ok"] is False

    # Missing manifest -> not installed.
    assert status(tmp_path / "nowhere") == {"installed": False, "path": str(tmp_path / "nowhere")}


class _ReleaseHandler(SimpleHTTPRequestHandler):
    """Serve a directory laid out as <docroot>/releases/download/<tag>/<file>."""

    def __init__(self, *args, docroot: Path, **kwargs):
        super().__init__(*args, directory=str(docroot), **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        pass  # keep test output clean


@pytest.mark.skipif(
    not LOOPBACK_OK,
    reason="loopback TCP connect is blocked in this environment (sandbox)",
)
def test_fetch_from_http(tmp_path):
    release, manifest = _make_release(tmp_path)
    docroot = tmp_path / "www"
    layout = docroot / "releases" / "download" / "data-latest"
    layout.mkdir(parents=True)
    for path in release.iterdir():
        shutil.copy2(path, layout / path.name)

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_ReleaseHandler, docroot=docroot))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}/releases/download"
    try:
        dest = tmp_path / "dest"
        log: list[str] = []
        records = fetch_from_http(
            repo="x/y", tag="data-latest", dest_dir=dest, base_url=base_url, log=log.append
        )

        assert sorted(p.name for p in dest.iterdir()) == sorted(
            CANONICAL + ["cnf.sqlite.gz", MANIFEST_NAME]
        )
        assert len(records) == 4
        by_name = {r["name"]: r for r in records}
        for name in CANONICAL:
            assert sha256_file(dest / name) == manifest["datasets"][name]["sha256"]
            assert by_name[name]["upstream"] == manifest["datasets"][name]["upstream"]
        assert by_name["cnf.sqlite"]["asset"] == "cnf.sqlite.gz"
        assert len(log) == 6

        # Unknown tag -> the release assets 404 and FetchError names the URL.
        with pytest.raises(FetchError) as excinfo:
            fetch_from_http(
                repo="x/y", tag="nope", dest_dir=tmp_path / "dest2", base_url=base_url
            )
        assert "download failed" in str(excinfo.value)
        assert "nope" in str(excinfo.value)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_only_filter_and_aliases(tmp_path):
    release, _manifest = _make_release(tmp_path)

    # Alias "cnf" installs only the CNF database (from the gz asset), plus the
    # gz asset itself and the manifest.
    dest = tmp_path / "dest-cnf"
    records = fetch_from_dir(release, dest, only=["cnf"])
    assert sorted(p.name for p in dest.iterdir()) == sorted(
        ["cnf.sqlite", "cnf.sqlite.gz", MANIFEST_NAME]
    )
    assert len(records) == 1
    assert records[0]["name"] == "cnf.sqlite"
    assert records[0]["asset"] == "cnf.sqlite.gz"
    assert records[0]["content_hash"] == "cnf-content-hash"
    assert records[0]["upstream"] == {"metadata_modified": "2024-01-01", "zip_sha256": "fake-zip-sha256"}

    # Full file names work too.
    dest = tmp_path / "dest-recipes"
    records = fetch_from_dir(release, dest, only=["recipes.json"])
    assert sorted(p.name for p in dest.iterdir()) == sorted(
        ["recipes.json", MANIFEST_NAME]
    )
    assert len(records) == 1

    # Multiple aliases at once.
    dest = tmp_path / "dest-dri-eer"
    records = fetch_from_dir(release, dest, only=["dri", "eer"])
    assert sorted(p.name for p in dest.iterdir()) == [
        "dri_macronutrients.json",
        "eer_equations.json",
        MANIFEST_NAME,
    ]
    assert len(records) == 2

    # Unknown alias -> FetchError listing valid names.
    dest = tmp_path / "dest-bogus"
    with pytest.raises(FetchError, match="valid names"):
        fetch_from_dir(release, dest, only=["bogus"])
    assert not dest.exists() or list(dest.iterdir()) == []
