"""Dataset manifest: hashing, reproducible gzip, build/load/compare.

The manifest describes the built dataset files (CNF sqlite database, recipe
JSON, DRI/EER JSON snapshots) so downstream tooling can tell whether a
rebuild actually changed the data. Content identity is preferred over raw
file hashes: it ignores cosmetic differences (file sizes, record counts of
unchanged tables, build timestamps) while still catching real data changes.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1
DATASET_FILES = (
    "cnf.sqlite",
    "recipes.json",
    "dri_macronutrients.json",
    "eer_equations.json",
)

_COMPRESSED_CNF = "cnf.sqlite.gz"

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


class ManifestError(Exception):
    """Raised for malformed manifests."""


def package_version() -> str:
    """Return the installed foodguide package version, or "0.0.0" if unknown."""
    try:
        return metadata.version("foodguide")
    except Exception:
        return "0.0.0"


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file, streamed in 1 MiB chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_reproducible(src: Path, dst: Path) -> None:
    """Gzip-compress ``src`` into ``dst`` deterministically (mtime=0).

    Identical input bytes always produce identical gzip output bytes, so the
    result can be hashed and compared across rebuilds. ``dst`` must be the
    exact intended output path; its parent directories are created.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as handle:
        # filename="" avoids embedding src's path/name (and thus the build
        # environment) in the gzip header; mtime=0 removes the timestamp.
        with gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=handle, mtime=0
        ) as gz:
            with open(src, "rb") as reader:
                while chunk := reader.read(_CHUNK_SIZE):
                    gz.write(chunk)


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 ``YYYY-MM-DDTHH:MM:SSZ`` string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sqlite_record_counts(path: Path) -> dict[str, int]:
    """Return ``{table: row_count}`` for every user table in a sqlite database.

    Internal sqlite tables (``sqlite_*``) are excluded.
    """
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            if not row[0].startswith("sqlite_")
        ]
        return {
            name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in names
        }
    finally:
        conn.close()


def _recipes_content_hash(doc: dict) -> str:
    """Stable sha256 of a recipes.json document, ignoring build metadata.

    canada.ca serves a dynamic analytics script, so both the build timestamp
    (``source.fetched_at``) and the raw index page hash
    (``source.index_sha256``, which hashes the script bytes too) differ
    between fetches even when the recipe data is identical. The content hash
    canonicalises the parsed document with those two build-metadata fields
    removed so equal recipe data always produces equal bytes; the raw values
    stay recorded under ``upstream`` for provenance.
    """
    stable = copy.deepcopy(doc)
    if isinstance(stable.get("source"), dict):
        stable["source"].pop("fetched_at", None)
        stable["source"].pop("index_sha256", None)
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return sha256_bytes(payload)


def _json_facts(path: Path, kind: str) -> dict:
    """Extract record counts and upstream provenance from a JSON dataset file."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read dataset {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise ManifestError(f"dataset {path} is not a JSON object")
    if kind == "recipes":
        source = doc["source"]
        return {
            "content_hash": _recipes_content_hash(doc),
            "record_count": source["recipe_count"],
            "upstream": {
                "index_sha256": source["index_sha256"],
                "recipe_count": source["recipe_count"],
                "index_url": source.get("index_url"),
            },
        }
    prov = doc["_provenance"]
    record_count = sum(1 for key in doc if key != "_provenance")
    return {
        "record_count": record_count,
        "upstream": {
            "page_sha256": prov["page_sha256"],
            "page_date_modified": prov.get("page_date_modified"),
        },
    }


def _cnf_facts(path: Path) -> dict:
    """Extract content hash, record counts and upstream provenance from the CNF db."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        try:
            rows = conn.execute(
                "SELECT key, value FROM provenance"
            ).fetchall()
        except sqlite3.Error as exc:
            raise ManifestError(f"cnf database has no provenance table: {exc}") from exc
    finally:
        conn.close()
    prov = {key: value for key, value in rows}
    missing = [key for key in ("content_hash", "zip_sha256", "metadata_modified") if key not in prov]
    if missing:
        raise ManifestError(f"cnf provenance table missing keys: {', '.join(missing)}")
    return {
        "content_hash": prov["content_hash"],
        "record_counts": sqlite_record_counts(path),
        "upstream": {
            "metadata_modified": prov["metadata_modified"],
            "zip_sha256": prov["zip_sha256"],
        },
    }


def dataset_entry(path: Path) -> dict:
    """Build one manifest ``datasets`` entry for a known dataset file."""
    name = path.name
    if name not in DATASET_FILES and not name.endswith(".gz"):
        raise ManifestError(f"not a known dataset file: {name}")
    entry: dict = {"sha256": sha256_file(path), "size": path.stat().st_size}
    try:
        if name == "cnf.sqlite":
            entry.update(_cnf_facts(path))
        elif name == "recipes.json":
            entry.update(_json_facts(path, "recipes"))
        elif name in ("dri_macronutrients.json", "eer_equations.json"):
            entry.update(
                _json_facts(path, "dri" if name == "dri_macronutrients.json" else "eer")
            )
    except KeyError as exc:
        raise ManifestError(f"dataset {path} is missing required field {exc}") from exc
    # Compressed files (.gz) carry only sha256 + size; their facts live in the
    # uncompressed counterpart's entry.
    return entry


def build_manifest(out_dir: Path) -> dict:
    """Scan ``out_dir`` for dataset files and return a manifest dict."""
    out_dir = Path(out_dir)
    datasets: dict[str, dict] = {}
    for name in DATASET_FILES:
        path = out_dir / name
        if path.exists():
            datasets[name] = dataset_entry(path)
    gz_path = out_dir / _COMPRESSED_CNF
    if gz_path.exists():
        datasets[_COMPRESSED_CNF] = dataset_entry(gz_path)
    if not datasets:
        raise ManifestError(f"no dataset files in {out_dir}")
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "package_version": package_version(),
        "built_at": _utc_now(),
        "datasets": dict(sorted(datasets.items())),
    }


def write_manifest(out_dir: Path) -> dict:
    """Build the manifest for ``out_dir`` and write ``manifest.json`` there."""
    manifest = build_manifest(out_dir)
    (Path(out_dir) / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_manifest(path: Path) -> dict:
    """Load and shape-check a manifest JSON file."""
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("datasets"), dict):
        raise ManifestError(f"malformed manifest: {path}")
    return manifest


def _require_sha(entry: dict, name: str) -> str:
    """Return the entry sha256, or raise ManifestError if it is missing."""
    sha = entry.get("sha256")
    if not sha:
        raise ManifestError(f"manifest entry {name!r} has no sha256")
    return str(sha)


def dataset_identity(manifest: dict, name: str) -> str | None:
    """Return a stable content identity for canonical dataset ``name``.

    Returns ``None`` when the dataset is absent from the manifest (for the CNF
    database, both the raw and the ``.gz`` variants being absent counts as
    absent). The identity prefers upstream/content hashes over the local file
    hash so that compression or cosmetic rebuilds do not register as changes.
    """
    datasets = manifest.get("datasets", {})
    if name == "cnf.sqlite":
        if name in datasets:
            entry = datasets[name]
            return entry.get("content_hash") or _require_sha(entry, name)
        if _COMPRESSED_CNF in datasets:
            return _require_sha(datasets[_COMPRESSED_CNF], _COMPRESSED_CNF)
        return None
    entry = datasets.get(name)
    if entry is None:
        return None
    if name == "recipes.json":
        # content_hash ignores the build timestamp (and the dynamic analytics
        # script baked into the raw index sha256), so prefer it.
        if entry.get("content_hash"):
            return str(entry["content_hash"])
        upstream = entry.get("upstream")
        if isinstance(upstream, dict) and "index_sha256" in upstream:
            return f"{upstream['index_sha256']}:{upstream.get('recipe_count')}"
        return _require_sha(entry, name)
    upstream = entry.get("upstream")
    if isinstance(upstream, dict) and "page_sha256" in upstream:
        return f"{upstream['page_sha256']}:{upstream.get('page_date_modified')}"
    return _require_sha(entry, name)


def changed_datasets(old: dict, new: dict) -> list[str]:
    """Return the canonical dataset names whose content identity changed."""
    for label, manifest in (("old", old), ("new", new)):
        if not isinstance(manifest, dict) or not isinstance(manifest.get("datasets"), dict):
            raise ManifestError(f"malformed manifest: {label}")
    changed = []
    for name in DATASET_FILES:
        identity_old = dataset_identity(old, name)
        identity_new = dataset_identity(new, name)
        if identity_old != identity_new:
            changed.append(name)
    return sorted(changed)
