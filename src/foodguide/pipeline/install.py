"""Install datasets from a release (HTTPS or a local dir) and report status.

A "release" is a directory (local, or a GitHub release asset layout) holding
the dataset files described by ``manifest.json``. Installation is
verification-first: every asset is fetched and hash-checked in a temp dir, and
only then atomically moved into place — a failed fetch never leaves a partial
install behind.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from foodguide.pipeline.manifest import (
    DATASET_FILES,
    MANIFEST_NAME,
    ManifestError,
    load_manifest,
    sha256_bytes,
    sha256_file,
)

__all__ = [
    "DATASET_FILES",
    "DEFAULT_REPO",
    "DEFAULT_TAG",
    "INSTALLABLE",
    "MANIFEST_NAME",
    "ManifestError",
    "USER_AGENT",
    "FetchError",
    "fetch_from_dir",
    "fetch_from_http",
    "release_base_url",
    "status",
]

DEFAULT_REPO = "Aryan-Jhaveri/mcp-foodguidecanada"
DEFAULT_TAG = "data-latest"
USER_AGENT = "foodguide-data-fetch/0.1"
INSTALLABLE = DATASET_FILES + ("cnf.sqlite.gz",)  # canonical datasets + the gz asset

# Short names accepted by the ``only`` filter, mapped to canonical dataset names.
_ALIAS_MAP = {
    "cnf": "cnf.sqlite",
    "recipes": "recipes.json",
    "dri": "dri_macronutrients.json",
    "eer": "eer_equations.json",
}

_COMPRESSED_CNF = "cnf.sqlite.gz"


class FetchError(Exception):
    """Raised when a release cannot be fetched or verified."""


def release_base_url(repo: str, tag: str) -> str:
    """Return the GitHub release download base URL for ``repo``/``tag``."""
    return f"https://github.com/{repo}/releases/download/{tag}"


def _http_get(url: str, timeout: float = 60.0) -> bytes:
    """GET ``url`` with our User-Agent; return the body or raise FetchError."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception as exc:  # urllib raises many types; all mean "download failed"
        raise FetchError(f"download failed: {url}: {exc}") from exc


def fetch_from_dir(
    src_dir: Path,
    dest_dir: Path,
    only: list[str] | None = None,
    log: Callable[[str], None] = print,
) -> list[dict]:
    """Install datasets from a local release directory. See _install_common."""
    src_dir = Path(src_dir)
    manifest_path = src_dir / MANIFEST_NAME
    manifest = load_manifest(manifest_path)

    def get_asset(name: str) -> bytes:
        return (src_dir / name).read_bytes()

    return _install_common(
        manifest, manifest_path.read_bytes(), get_asset, dest_dir, only, str(src_dir), log
    )


def fetch_from_http(
    repo: str,
    tag: str,
    dest_dir: Path,
    only: list[str] | None = None,
    base_url: str | None = None,
    log: Callable[[str], None] = print,
) -> list[dict]:
    """Install datasets from a GitHub release layout. base_url overrides
    https://github.com/<repo>/releases/download/<tag> (for tests / mirrors).
    See _install_common."""
    root = base_url.rstrip("/") if base_url is not None else release_base_url(repo, tag)

    def asset_url(name: str) -> str:
        if base_url is not None:
            return f"{root}/{tag}/{name}"
        return f"{root}/{name}"

    manifest_url = asset_url(MANIFEST_NAME)
    manifest_bytes = _http_get(manifest_url)
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise FetchError(f"invalid manifest from {manifest_url}: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("datasets"), dict):
        raise FetchError(f"invalid manifest from {manifest_url}: not a manifest document")

    def get_asset(name: str) -> bytes:
        return _http_get(asset_url(name))

    return _install_common(
        manifest, manifest_bytes, get_asset, dest_dir, only, manifest_url, log
    )


def _normalize_only(only: list[str] | None) -> set[str] | None:
    """Map ``only`` entries (aliases or file names) to canonical dataset names.

    ``None`` or an empty list means "no filter" (install everything).
    """
    if not only:
        return None
    valid = sorted(set(_ALIAS_MAP) | set(INSTALLABLE))
    selected: set[str] = set()
    for raw in only:
        canonical = _ALIAS_MAP.get(raw.strip(), raw.strip())
        if canonical == _COMPRESSED_CNF:
            canonical = "cnf.sqlite"  # the gz asset installs the plain database
        if canonical not in DATASET_FILES:
            raise FetchError(f"unknown dataset {raw!r}; valid names: {', '.join(valid)}")
        selected.add(canonical)
    return selected


def _build_plans(datasets: dict, selected: set[str] | None) -> list[tuple[str, str, str]]:
    """Plan (asset, dest name, mode) tuples present in the manifest.

    mode "file" installs the asset verbatim; mode "decompress" gunzips it.
    """
    plans: list[tuple[str, str, str]] = []
    for name in DATASET_FILES:
        if selected is not None and name not in selected:
            continue
        if name == "cnf.sqlite":
            if _COMPRESSED_CNF in datasets:
                # The gz is both the transport and a published asset: install it
                # verbatim AND decompressed, and never separately download the
                # plain cnf.sqlite asset (it is the same content).
                plans.append((_COMPRESSED_CNF, _COMPRESSED_CNF, "file"))
                plans.append((_COMPRESSED_CNF, "cnf.sqlite", "decompress"))
            elif "cnf.sqlite" in datasets:
                plans.append(("cnf.sqlite", "cnf.sqlite", "file"))
        elif name in datasets:
            plans.append((name, name, "file"))
    return plans


def _is_up_to_date(
    dest: Path, asset: str, name: str, mode: str, datasets: dict
) -> bool:
    """True when the dest file already matches the manifest sha256."""
    if not dest.exists():
        return False
    if mode == "decompress":
        # The gz asset's sha covers the compressed bytes, not the installed file;
        # only a plain "cnf.sqlite" manifest entry can verify the decompressed db.
        plain = datasets.get(name)
        if not plain or not plain.get("sha256"):
            return False
        return sha256_file(dest) == plain["sha256"]
    return sha256_file(dest) == datasets[asset]["sha256"]


def _install_manifest_bytes(
    dest_dir: Path, manifest_bytes: bytes, log: Callable[[str], None]
) -> None:
    """Install manifest.json into dest atomically, unless it is already there."""
    dest = dest_dir / MANIFEST_NAME
    if dest.exists() and dest.read_bytes() == manifest_bytes:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_dir / f".{MANIFEST_NAME}.tmp"
    tmp_path.write_bytes(manifest_bytes)
    os.replace(tmp_path, dest)
    log(f"{MANIFEST_NAME}: installed ({len(manifest_bytes)} bytes)")


def _install_common(
    manifest: dict,
    manifest_bytes: bytes,
    get_asset: Callable[[str], bytes],
    dest_dir: Path,
    only: list[str] | None,
    source_label: str,
    log: Callable[[str], None],
) -> list[dict]:
    """Shared install algorithm. get_asset(name) -> bytes for asset file `name`.

    Algorithm:
    1. Build the work list from manifest["datasets"] (dict):
       - For canonical name in DATASET_FILES, if `only` filter given (normalize with
         the alias map below), skip names not selected.
       - cnf.sqlite: if "cnf.sqlite.gz" in datasets -> plan the gz asset BOTH as a
         verbatim file ("cnf.sqlite.gz") AND decompressed ("cnf.sqlite"), and never
         separately plan the plain "cnf.sqlite" asset (it is the same content).
         elif "cnf.sqlite" in datasets -> plan ("cnf.sqlite", "cnf.sqlite", "file").
       - recipes.json / dri_macronutrients.json / eer_equations.json: plan directly if present.
       Names in `only` may be "cnf", "recipes", "dri", "eer" or full file names (alias map).
       Unknown alias -> FetchError listing valid names.
    2. Empty work list -> log("nothing to install (all requested datasets absent)") and return [].
    3. Idempotence: for each plan, if the dest file exists and sha256_file(dest) matches
       the manifest sha for that plan (for the gz->cnf.sqlite decompress plan: the plain
       "cnf.sqlite" entry's sha256), log(f"{name}: up to date") and drop from the plan.
    4. Verification-first: fetch each asset once (plans may share an asset) and verify
       sha256 against the manifest entry. On ANY mismatch: remove the temp dir, raise
       FetchError("sha256 mismatch for {asset}: expected ..., got ...").
       (Nothing is installed unless EVERY asset verified.)
    5. For decompress plans: gunzip the verified gz bytes and, if the manifest has a
       plain "cnf.sqlite" entry, verify the decompressed sha256 against it -> else
       FetchError("cnf.sqlite from gz does not match manifest").
    6. Atomic install: write each dest file as dest_dir/.<name>.tmp then os.replace to
       dest_dir/<name>. Then install manifest.json itself (unless already identical),
       so `data status` can verify the install later.
    7. Return a record per installed canonical dataset (not the gz, not the manifest):
       [{"name": dest file name, "asset": asset name, "size": len(bytes),
         "sha256": ..., "content_hash": (cnf only), "upstream": entry.get("upstream"),
         "source": source_label}]
    """
    datasets = manifest.get("datasets", {})
    selected = _normalize_only(only)
    plans = _build_plans(datasets, selected)
    if not plans:
        log("nothing to install (all requested datasets absent)")
        return []

    dest_dir = Path(dest_dir)
    remaining: list[tuple[str, str, str]] = []
    for asset, name, mode in plans:
        if _is_up_to_date(dest_dir / name, asset, name, mode, datasets):
            log(f"{name}: up to date")
        else:
            remaining.append((asset, name, mode))

    installed: list[dict] = []
    if remaining:
        dest_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix=".foodguide-fetch-", dir=dest_dir))
        try:
            # Verification-first: fetch each asset once (several plans can share
            # one asset) and hash-check every asset before any install.
            fetched: dict[str, bytes] = {}
            for asset in sorted({asset for asset, _name, _mode in remaining}):
                data = get_asset(asset)
                expected = datasets[asset].get("sha256")
                actual = sha256_bytes(data)
                if actual != expected:
                    raise FetchError(
                        f"sha256 mismatch for {asset}: expected {expected}, got {actual}"
                    )
                fetched[asset] = data

            contents: list[tuple[str, str, bytes]] = []
            for asset, name, mode in remaining:
                data = fetched[asset]
                if mode == "decompress":
                    data = gzip.decompress(data)
                    plain_entry = datasets.get(name)
                    if plain_entry and sha256_bytes(data) != plain_entry.get("sha256"):
                        raise FetchError("cnf.sqlite from gz does not match manifest")
                contents.append((name, asset, data))

            for name, _asset, data in contents:
                tmp_path = dest_dir / f".{name}.tmp"
                tmp_path.write_bytes(data)
                os.replace(tmp_path, dest_dir / name)
                log(f"{name}: installed ({len(data)} bytes)")

            for name, asset, data in contents:
                if name == _COMPRESSED_CNF:
                    continue  # the gz is transport/storage, not a dataset record
                entry = datasets.get(name, {})
                record: dict = {
                    "name": name,
                    "asset": asset,
                    "size": len(data),
                    "sha256": sha256_bytes(data),
                    "upstream": entry.get("upstream"),
                    "source": source_label,
                }
                if name == "cnf.sqlite" and "content_hash" in entry:
                    record["content_hash"] = entry["content_hash"]
                installed.append(record)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # The manifest itself is part of the install: `data status` reads it.
    _install_manifest_bytes(dest_dir, manifest_bytes, log)
    return installed


def status(dest_dir: Path) -> dict:
    """Report install status of ``dest_dir`` against its manifest.json."""
    dest_dir = Path(dest_dir)
    manifest_path = dest_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {"installed": False, "path": str(dest_dir)}
    manifest = load_manifest(manifest_path)
    datasets = manifest.get("datasets", {})
    files: list[dict] = []
    all_ok = True
    for name in sorted(datasets):
        entry = datasets[name]
        actual_path = dest_dir / name
        expected = entry.get("sha256")
        if not actual_path.exists():
            state, actual = "missing", None
        else:
            actual = sha256_file(actual_path)
            state = "ok" if actual == expected else "modified"
        if state != "ok":
            all_ok = False
        files.append(
            {
                "name": name,
                "state": state,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "size": entry.get("size"),
            }
        )
    return {
        "installed": True,
        "path": str(dest_dir),
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "built_at": manifest.get("built_at"),
            "package_version": manifest.get("package_version"),
        },
        "files": files,
        "all_ok": all_ok,
    }
