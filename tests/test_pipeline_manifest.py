"""Tests for the dataset manifest module (build/load/compare, hashing, gzip)."""

import gzip
import hashlib
import json
import sqlite3

import pytest

from foodguide.pipeline.manifest import (
    DATASET_FILES,
    MANIFEST_SCHEMA_VERSION,
    ManifestError,
    _cnf_facts,
    _json_facts,
    build_manifest,
    changed_datasets,
    dataset_entry,
    dataset_identity,
    gzip_reproducible,
    load_manifest,
    package_version,
    sha256_bytes,
    sha256_file,
    write_manifest,
)

# ---------------------------------------------------------------- hashing ---


def test_sha256_bytes_and_file_agree(tmp_path) -> None:
    data = b"hello foodguide pipeline" * 1000
    path = tmp_path / "blob.bin"
    path.write_bytes(data)
    assert sha256_file(path) == sha256_bytes(data)
    assert sha256_file(path) == hashlib.sha256(data).hexdigest()


def test_sha256_file_streams_large_file(tmp_path) -> None:
    # Larger than one 1 MiB chunk to exercise the streaming loop.
    data = bytes(range(256)) * 8192  # 2 MiB
    path = tmp_path / "big.bin"
    path.write_bytes(data)
    assert sha256_file(path) == sha256_bytes(data)


# ------------------------------------------------------------------- gzip ---


def test_gzip_reproducible_is_deterministic(tmp_path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"deterministic payload\n" * 5000)
    gzip_reproducible(src, tmp_path / "a.gz")
    gzip_reproducible(src, tmp_path / "b.gz")
    a = (tmp_path / "a.gz").read_bytes()
    b = (tmp_path / "b.gz").read_bytes()
    assert a == b


def test_gzip_reproducible_roundtrip_and_mtime(tmp_path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"roundtrip me" * 4096)
    dst = tmp_path / "out.gz"
    gzip_reproducible(src, dst)
    with gzip.open(dst, "rb") as fh:
        assert fh.read() == src.read_bytes()
    # mtime=0 is stored in the 4-byte MTIME header field (offsets 4..8).
    header = dst.read_bytes()[:8]
    assert header[4:8] == b"\x00\x00\x00\x00"


def test_gzip_reproducible_creates_parent_dirs(tmp_path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"nested")
    dst = tmp_path / "nested" / "deep" / "out.gz"
    gzip_reproducible(src, dst)
    assert dst.exists()
    with gzip.open(dst, "rb") as fh:
        assert fh.read() == b"nested"


# --------------------------------------------------------------- version ---


def test_package_version_returns_a_string() -> None:
    version = package_version()
    assert isinstance(version, str)
    assert version
    # The package is installed in the test environment: it must match pyproject.toml.
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    assert version == tomllib.loads(pyproject.read_text())["project"]["version"]


# ------------------------------------------------------------ json facts ---


def _write_recipes_json(tmp_path) -> object:
    doc = {
        "source": {
            "index_url": "https://example.test/index",
            "fetched_at": "2026-01-01T00:00:00Z",
            "recipe_count": 3,
            "index_sha256": "abc",
        },
        "filters": {},
        "recipes": [],
    }
    path = tmp_path / "recipes.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_json_facts_recipes(tmp_path) -> None:
    path = _write_recipes_json(tmp_path)
    facts = _json_facts(path, "recipes")
    assert facts["record_count"] == 3
    assert facts["upstream"] == {
        "index_sha256": "abc",
        "recipe_count": 3,
        "index_url": "https://example.test/index",
    }


def test_dataset_entry_recipes(tmp_path) -> None:
    path = _write_recipes_json(tmp_path)
    entry = dataset_entry(path)
    assert entry["sha256"] == sha256_file(path)
    assert entry["size"] == path.stat().st_size
    assert entry["record_count"] == 3
    assert entry["upstream"]["index_sha256"] == "abc"
    assert entry["upstream"]["recipe_count"] == 3
    assert entry["upstream"]["index_url"] == "https://example.test/index"
    assert "content_hash" in entry


def test_recipes_content_hash_ignores_fetched_at(tmp_path) -> None:
    """Equal recipe data with different fetched_at (and raw index sha) is equal.

    canada.ca serves a dynamic analytics script, so two live crawls of an
    unchanged recipe index produce different index_sha256 values; the
    content_hash (fetched_at and index_sha256 removed) must still match so `data changed`
    reports no change.
    """
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / "recipes.json").write_text(
        json.dumps(
            {
                "source": {
                    "index_url": "u",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "recipe_count": 1,
                    "index_sha256": "dynamic-script-page-a",
                },
                "filters": {},
                "recipes": [{"slug": "apple-pie", "name": "Apple pie"}],
            }
        ),
        encoding="utf-8",
    )
    (second / "recipes.json").write_text(
        json.dumps(
            {
                "source": {
                    "index_url": "u",
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "recipe_count": 1,
                    "index_sha256": "dynamic-script-page-b",
                },
                "filters": {},
                "recipes": [{"slug": "apple-pie", "name": "Apple pie"}],
            }
        ),
        encoding="utf-8",
    )
    m1 = build_manifest(first)
    m2 = build_manifest(second)
    assert changed_datasets(m1, m2) == []
    assert (
        m1["datasets"]["recipes.json"]["content_hash"]
        == m2["datasets"]["recipes.json"]["content_hash"]
    )
    # A real recipe change still shows up.
    (second / "recipes.json").write_text(
        (second / "recipes.json").read_text(encoding="utf-8").replace("Apple pie", "Apple tart"),
        encoding="utf-8",
    )
    assert changed_datasets(build_manifest(first), build_manifest(second)) == ["recipes.json"]


def _write_dri_json(tmp_path, name: str) -> object:
    doc = {
        "_provenance": {
            "page_sha256": "p",
            "page_date_modified": "2026-01-01",
            "fetched_at": "2026-01-02T00:00:00Z",
        },
        "age_groups": {"a": 1},
        "nutrients": {"b": 2},
    }
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_dataset_entry_dri_style(tmp_path) -> None:
    path = _write_dri_json(tmp_path, "dri_macronutrients.json")
    entry = dataset_entry(path)
    assert entry["sha256"] == sha256_file(path)
    assert entry["size"] == path.stat().st_size
    assert entry["record_count"] == 2
    assert entry["upstream"] == {
        "page_sha256": "p",
        "page_date_modified": "2026-01-01",
    }


def test_dataset_entry_eer_style(tmp_path) -> None:
    path = _write_dri_json(tmp_path, "eer_equations.json")
    entry = dataset_entry(path)
    assert entry["record_count"] == 2
    assert entry["upstream"]["page_sha256"] == "p"


# ------------------------------------------------------------ cnf facts ---


def _make_cnf_db(path, food_rows: int = 2) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE provenance (key TEXT, value TEXT)")
        conn.executemany(
            "INSERT INTO provenance (key, value) VALUES (?, ?)",
            [
                ("content_hash", "cnf-content-hash"),
                ("zip_sha256", "cnf-zip-hash"),
                ("metadata_modified", "2025-06-01"),
            ],
        )
        conn.execute("CREATE TABLE food (id INTEGER PRIMARY KEY, name TEXT)")
        conn.executemany(
            "INSERT INTO food (name) VALUES (?)",
            [(f"food-{i}",) for i in range(food_rows)],
        )
        conn.commit()
    finally:
        conn.close()


def test_cnf_facts(tmp_path) -> None:
    path = tmp_path / "cnf.sqlite"
    _make_cnf_db(path)
    facts = _cnf_facts(path)
    assert facts["content_hash"] == "cnf-content-hash"
    assert facts["record_counts"] == {"food": 2, "provenance": 3}
    assert facts["upstream"] == {
        "metadata_modified": "2025-06-01",
        "zip_sha256": "cnf-zip-hash",
    }


def test_cnf_facts_missing_provenance_table(tmp_path) -> None:
    path = tmp_path / "cnf.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE food (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ManifestError):
        _cnf_facts(path)


def test_cnf_facts_missing_provenance_keys(tmp_path) -> None:
    path = tmp_path / "cnf.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE provenance (key TEXT, value TEXT)")
        conn.execute("INSERT INTO provenance VALUES ('content_hash', 'x')")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ManifestError):
        _cnf_facts(path)


def test_dataset_entry_cnf(tmp_path) -> None:
    path = tmp_path / "cnf.sqlite"
    _make_cnf_db(path)
    entry = dataset_entry(path)
    assert entry["content_hash"] == "cnf-content-hash"
    assert entry["record_counts"] == {"food": 2, "provenance": 3}
    assert entry["upstream"]["zip_sha256"] == "cnf-zip-hash"


def test_dataset_entry_unknown_name(tmp_path) -> None:
    path = tmp_path / "mystery.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ManifestError):
        dataset_entry(path)


# --------------------------------------------------------- build_manifest ---


def test_build_manifest_gz_and_recipes(tmp_path) -> None:
    (tmp_path / "recipes.json").write_text(
        json.dumps(
            {
                "source": {"index_url": "u", "fetched_at": "x",
                           "recipe_count": 1, "index_sha256": "abc"},
                "filters": {},
                "recipes": [],
            }
        ),
        encoding="utf-8",
    )
    # Random bytes with a .gz name: accepted with sha/size only.
    (tmp_path / "cnf.sqlite.gz").write_bytes(b"\x1f\x8bnot-really-gzip")
    manifest = build_manifest(tmp_path)
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["built_at"]
    assert manifest["package_version"] == package_version()
    assert sorted(manifest["datasets"]) == ["cnf.sqlite.gz", "recipes.json"]
    gz_entry = manifest["datasets"]["cnf.sqlite.gz"]
    assert set(gz_entry) == {"sha256", "size"}
    assert gz_entry["sha256"] == sha256_file(tmp_path / "cnf.sqlite.gz")


def test_build_manifest_empty_dir(tmp_path) -> None:
    with pytest.raises(ManifestError):
        build_manifest(tmp_path)


def test_build_manifest_gz_without_cnf_sqlite(tmp_path) -> None:
    # cnf.sqlite absent but cnf.sqlite.gz present -> fine.
    (tmp_path / "cnf.sqlite.gz").write_bytes(b"\x1f\x8bxyz")
    manifest = build_manifest(tmp_path)
    assert "cnf.sqlite.gz" in manifest["datasets"]
    assert "cnf.sqlite" not in manifest["datasets"]


# -------------------------------------------------------- write / load ---


def test_write_and_load_manifest_roundtrip(tmp_path) -> None:
    _make_cnf_db(tmp_path / "cnf.sqlite")
    _write_recipes_json(tmp_path)
    manifest = write_manifest(tmp_path)
    path = tmp_path / "manifest.json"
    assert path.exists()
    loaded = load_manifest(path)
    assert loaded == manifest
    # Canonical JSON formatting: sorted keys, indent 2, trailing newline.
    text = path.read_text(encoding="utf-8")
    assert text == json.dumps(manifest, indent=2, sort_keys=True,
                              ensure_ascii=False) + "\n"


def test_load_manifest_malformed(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(bad)
    bad.write_text(json.dumps({"datasets": [1, 2]}), encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(bad)


def test_load_manifest_missing_file(tmp_path) -> None:
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "nope.json")


# --------------------------------------------------- dataset_identity ---


def _recipe_manifest(index_sha256: str, recipe_count: int = 3,
                     **extra_datasets) -> dict:
    datasets = {
        "recipes.json": {
            "sha256": "filehash",
            "size": 100,
            "record_count": recipe_count,
            "upstream": {
                "index_sha256": index_sha256,
                "recipe_count": recipe_count,
                "index_url": "u",
            },
        }
    }
    for name, entry in extra_datasets.items():
        datasets[name] = entry
    return {"schema_version": 1, "package_version": "3.0.0",
            "built_at": "2026-01-01T00:00:00Z", "datasets": datasets}


def test_dataset_identity_absent_returns_none() -> None:
    manifest = {"schema_version": 1, "datasets": {}}
    for name in DATASET_FILES:
        assert dataset_identity(manifest, name) is None


def test_dataset_identity_cnf_prefers_content_hash() -> None:
    manifest = {"datasets": {"cnf.sqlite": {"sha256": "fh", "size": 1,
                                            "content_hash": "ch"}}}
    assert dataset_identity(manifest, "cnf.sqlite") == "ch"
    gz_manifest = {"datasets": {"cnf.sqlite.gz": {"sha256": "gzh", "size": 1}}}
    assert dataset_identity(gz_manifest, "cnf.sqlite") == "gzh"


def test_dataset_identity_recipes_uses_upstream() -> None:
    manifest = _recipe_manifest("abc", 3)
    assert dataset_identity(manifest, "recipes.json") == "abc:3"


def test_dataset_identity_recipes_falls_back_to_sha256() -> None:
    manifest = {"datasets": {"recipes.json": {"sha256": "fh", "size": 1}}}
    assert dataset_identity(manifest, "recipes.json") == "fh"


def test_dataset_identity_dri_uses_upstream() -> None:
    manifest = {
        "datasets": {
            "dri_macronutrients.json": {
                "sha256": "fh",
                "size": 1,
                "upstream": {"page_sha256": "p", "page_date_modified": "2026-01-01"},
            }
        }
    }
    assert dataset_identity(manifest, "dri_macronutrients.json") == "p:2026-01-01"


# ----------------------------------------------------- changed_datasets ---


def _dri_entry(page_sha256: str, sha256: str = "fh", size: int = 1) -> dict:
    return {
        "sha256": sha256,
        "size": size,
        "upstream": {"page_sha256": page_sha256,
                     "page_date_modified": "2026-01-01"},
    }


def test_changed_datasets_identical() -> None:
    m = _recipe_manifest("abc")
    assert changed_datasets(m, m) == []


def test_changed_datasets_ignores_metadata_differences() -> None:
    old = _recipe_manifest("abc")
    new = _recipe_manifest("abc")
    new["built_at"] = "2030-01-01T00:00:00Z"
    new["package_version"] = "9.9.9"
    new["schema_version"] = 2
    new["datasets"]["recipes.json"]["size"] = 999
    new["datasets"]["recipes.json"]["record_count"] = 4
    new["datasets"]["recipes.json"]["sha256"] = "different-file-hash"
    assert changed_datasets(old, new) == []


def test_changed_datasets_recipes_index_changed() -> None:
    old = _recipe_manifest("abc")
    new = _recipe_manifest("def")
    assert changed_datasets(old, new) == ["recipes.json"]


def test_changed_datasets_cnf_gz_sha_changed() -> None:
    old = {"datasets": {"cnf.sqlite.gz": {"sha256": "aaa", "size": 1}}}
    new = {"datasets": {"cnf.sqlite.gz": {"sha256": "bbb", "size": 1}}}
    assert changed_datasets(old, new) == ["cnf.sqlite"]


def test_changed_datasets_cnf_content_hash_changed() -> None:
    old = {"datasets": {"cnf.sqlite": {"sha256": "a", "size": 1,
                                       "content_hash": "h1"}}}
    new = {"datasets": {"cnf.sqlite": {"sha256": "b", "size": 1,
                                       "content_hash": "h2"}}}
    assert changed_datasets(old, new) == ["cnf.sqlite"]


def test_changed_datasets_added_and_removed() -> None:
    old = _recipe_manifest("abc")
    new = _recipe_manifest("abc", **{"dri_macronutrients.json": _dri_entry("p1")})
    assert changed_datasets(old, new) == ["dri_macronutrients.json"]
    # And the reverse (removed) is also reported.
    assert changed_datasets(new, old) == ["dri_macronutrients.json"]


def test_changed_datasets_malformed_manifest() -> None:
    with pytest.raises(ManifestError):
        changed_datasets([], {})
    good = {"datasets": {}}
    with pytest.raises(ManifestError):
        changed_datasets(good, {"datasets": None})
    with pytest.raises(ManifestError):
        changed_datasets({"no": "datasets"}, good)


def test_changed_datasets_multiple_sorted() -> None:
    old = _recipe_manifest("abc", **{"dri_macronutrients.json": _dri_entry("p1"),
                                     "eer_equations.json": _dri_entry("p2")})
    new = _recipe_manifest("xyz", **{"dri_macronutrients.json": _dri_entry("p1"),
                                     "eer_equations.json": _dri_entry("p3")})
    assert changed_datasets(old, new) == ["eer_equations.json", "recipes.json"]
