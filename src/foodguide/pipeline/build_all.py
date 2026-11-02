"""`data build all`: run every dataset builder into one directory + manifest.

All builders write into a temporary directory next to the output directory;
only when every step succeeded are the files moved into place and the
manifest published. A failure anywhere leaves the output directory untouched
(partial builds are never published).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from foodguide.builders.dri_eer import build_dri, build_eer
from foodguide.cnf.builder import build_cnf_db
from foodguide.pipeline import manifest as manifest_mod
from foodguide.recipes.builder import build_recipes_json

CKAN_PACKAGE_URL = (
    "https://open.canada.ca/data/api/3/action/package_show"
    "?id=1b6139bd-ed7e-4043-bc28-ff00e10f3109"
)

_USER_AGENT = "foodguide-data-build/0.1"
_CHUNK_SIZE = 1024 * 1024  # 1 MiB


class BuildAllError(Exception):
    """Raised when the build-all run must fail loudly."""


def find_cnf_zip_url(timeout: float = 30.0) -> tuple[str, str]:
    """Query the CKAN package record; return (zip_resource_url, metadata_modified).

    GET CKAN_PACKAGE_URL with urllib (User-Agent 'foodguide-data-build/0.1'),
    parse the JSON, and pick the first resource in ``result["resources"]`` whose
    ``format`` equals 'ZIP' (case-insensitive) and has a non-empty ``url``.
    Raise BuildAllError with a clear message if the record has no ZIP resource
    or the request/parse fails.
    """
    request = urllib.request.Request(CKAN_PACKAGE_URL, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildAllError(
            f"cannot query CKAN package record {CKAN_PACKAGE_URL}: {exc}"
        ) from exc
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise BuildAllError(
            f"CKAN package record {CKAN_PACKAGE_URL} has no 'result' object"
        )
    for resource in result.get("resources", []):
        if not isinstance(resource, dict):
            continue
        if str(resource.get("format", "")).strip().upper() != "ZIP":
            continue
        url = resource.get("url")
        # Never fetch the source zip over plaintext (loopback is allowed for local test servers).
        if isinstance(url, str) and url.strip().startswith(
            ("https://", "http://127.0.0.1", "http://localhost")
        ):
            modified = result.get("metadata_modified") or "unknown"
            return url.strip(), modified
    raise BuildAllError(
        f"CKAN package record {CKAN_PACKAGE_URL} has no ZIP resource with a URL"
    )


def download_cnf_zip(url: str, dest_dir: Path, timeout: float = 120.0) -> Path:
    """Stream-download the zip to dest_dir/cnf.zip (create dirs); return the path.

    Uses urllib.request with the build user agent, streams in chunks to a
    ``cnf.zip.part`` temp file and then ``os.replace``s it to ``cnf.zip`` so a
    half-downloaded file is never mistaken for the real zip. Raises
    BuildAllError on failure (removing the ``.part`` file).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    part_path = dest_dir / "cnf.zip.part"
    final_path = dest_dir / "cnf.zip"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with open(part_path, "wb") as handle:
                while True:
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
        os.replace(part_path, final_path)
    except Exception as exc:
        try:
            part_path.unlink()
        except OSError:
            pass
        raise BuildAllError(f"cannot download CNF zip from {url}: {exc}") from exc
    except BaseException:
        # KeyboardInterrupt & friends: clean up the .part, never disguise it.
        try:
            part_path.unlink()
        except OSError:
            pass
        raise
    return final_path


SKIP_ALIASES = {
    "cnf": "cnf.sqlite",
    "cnf.sqlite": "cnf.sqlite",
    "recipes": "recipes.json",
    "recipes.json": "recipes.json",
    "dri": "dri_macronutrients.json",
    "dri_macronutrients.json": "dri_macronutrients.json",
    "eer": "eer_equations.json",
    "eer_equations.json": "eer_equations.json",
}


def normalize_skip(skip) -> set[str]:
    """Map each skip name through SKIP_ALIASES into a canonical file name set.

    Unknown names raise BuildAllError listing the valid names.
    """
    skipped: set[str] = set()
    for item in skip:
        name = SKIP_ALIASES.get(str(item).strip().lower())
        if name is None:
            valid = sorted(set(SKIP_ALIASES))
            raise BuildAllError(
                f"unknown --skip name {item!r}; valid names: {', '.join(valid)}"
            )
        skipped.add(name)
    return skipped


def build_all(
    out_dir: Path,
    *,
    cnf_zip: Path | None = None,
    download_cnf: bool = False,
    skip=(),
    metadata_modified: str | None = None,
) -> dict:
    """Run all (non-skipped) dataset builders into out_dir, then write manifest.json.

    Everything is built into a temporary ``.foodguide-build-*`` directory
    beside ``out_dir``; the files (including ``manifest.json``) are moved into
    ``out_dir`` only after every step succeeded, so a failure never leaves a
    partial build behind. Returns the manifest dict.
    """
    out_dir = Path(out_dir)
    skipped = normalize_skip(skip)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".foodguide-build-", dir=out_dir.parent))
    try:
        # --- CNF sqlite database (+ optional zip download) -------------------
        if "cnf.sqlite" not in skipped:
            if download_cnf:
                zip_url, ckan_modified = find_cnf_zip_url()
                zip_path = download_cnf_zip(zip_url, tmp)
                effective_modified = metadata_modified or ckan_modified
                downloaded = True
            elif cnf_zip is not None:
                zip_path = Path(cnf_zip)
                if not zip_path.exists():
                    raise BuildAllError(f"CNF zip not found: {zip_path}")
                effective_modified = metadata_modified or "unknown"
                downloaded = False
            else:
                raise BuildAllError(
                    "no CNF zip: pass --cnf-zip or --download-cnf, or --skip cnf"
                )
            try:
                build_cnf_db(zip_path, tmp / "cnf.sqlite", metadata_modified=effective_modified)
            finally:
                if downloaded:
                    # The downloaded zip is temporary, never an asset.
                    try:
                        zip_path.unlink()
                    except OSError:
                        pass

        # --- recipes.json -----------------------------------------------------
        if "recipes.json" not in skipped:
            fetcher = None
            cache_dir = os.environ.get("FOODGUIDE_RECIPES_CACHE_DIR")
            if cache_dir:
                from foodguide.recipes.fetch import CachedFetcher

                fetcher = CachedFetcher(cache_dir, delay=0.0)
            build_recipes_json(tmp / "recipes.json", fetcher=fetcher)

        # --- DRI / EER snapshots ----------------------------------------------
        if "dri_macronutrients.json" not in skipped:
            build_dri(tmp / "dri_macronutrients.json")
        if "eer_equations.json" not in skipped:
            build_eer(tmp / "eer_equations.json")

        # --- reproducible gzip of the CNF database -----------------------------
        if "cnf.sqlite" not in skipped:
            manifest_mod.gzip_reproducible(tmp / "cnf.sqlite", tmp / "cnf.sqlite.gz")

        # --- manifest -----------------------------------------------------------
        manifest = manifest_mod.write_manifest(tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    # --- publish: nothing moves into out_dir until every step succeeded -------
    out_dir.mkdir(parents=True, exist_ok=True)
    built_names = {entry.name for entry in tmp.iterdir()}
    for entry in sorted(tmp.iterdir()):
        os.replace(entry, out_dir / entry.name)
    shutil.rmtree(tmp, ignore_errors=True)

    # The manifest describes the whole directory: dataset files it no longer
    # lists (e.g. after a --skip rebuild into an existing dir) must go, so a
    # release dir never ships unverified stale files next to a manifest.
    for stale_name in ("cnf.sqlite", "cnf.sqlite.gz", "recipes.json",
                       "dri_macronutrients.json", "eer_equations.json"):
        if stale_name not in built_names:
            stale_path = out_dir / stale_name
            if stale_path.exists():
                stale_path.unlink()
    return manifest


def _quiet(message: str) -> None:
    """Default no-op logger for run_build_all."""


def run_build_all(
    out_dir: Path,
    cnf_zip: Path | None = None,
    download_cnf: bool = False,
    skip: list[str] = (),
    log=_quiet,
    metadata_modified: str | None = None,
) -> dict:
    """CLI entry: run build_all, print a per-dataset summary, exit 1 on failure.

    Any exception from build_all is reported via ``log`` and turned into
    ``SystemExit(1)``; the (unpublished) output directory is left untouched.
    """
    try:
        manifest = build_all(
            out_dir,
            cnf_zip=cnf_zip,
            download_cnf=download_cnf,
            skip=skip,
            metadata_modified=metadata_modified,
        )
    except Exception as exc:  # noqa: BLE001 - the CLI turns any failure into exit 1
        log(f"build all failed: {exc}")
        raise SystemExit(1) from exc

    datasets = manifest.get("datasets", {})
    for name in sorted(datasets):
        entry = datasets[name]
        size = entry.get("size", "?")
        if name == "cnf.sqlite":
            upstream = entry.get("upstream", {})
            log(
                f"cnf.sqlite: {size} bytes, content_hash={entry.get('content_hash')}, "
                f"zip_sha256={upstream.get('zip_sha256')}"
            )
        elif name == "recipes.json":
            log(f"recipes.json: {size} bytes, recipe_count={entry.get('record_count')}")
        elif name in ("dri_macronutrients.json", "eer_equations.json"):
            upstream = entry.get("upstream", {})
            log(f"{name}: {size} bytes, page_sha256={upstream.get('page_sha256')}")
        else:
            log(f"{name}: {size} bytes, sha256={entry.get('sha256')}")
    log(f"Wrote {out_dir}/manifest.json")
    return manifest
