"""Data manager for DRI/EER reference data — pure offline, two-level priority.

This module never touches the network: tool calls and CLI commands must work
with no connectivity at all. Data priority per dataset:

1. Data-dir file (``$FOODGUIDE_DATA_DIR``/``~/.local/share/foodguide``, from
   ``foodguide data build dri`` / ``eer``) — the fresher, buildable source.
2. Bundled snapshot shipped inside the package (``foodguide/data/*.json``)
   via importlib.resources — always available, works from an installed wheel.

If a data-dir file exists but is corrupt or unreadable, we log to stderr and
fall back to the bundled snapshot; a missing file is not an error either.
There is no background refresh, no thread, and no runtime ``cache/`` dir.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from importlib.resources import files as _pkg_files
from typing import Any, Dict, Optional

from foodguide.cnf.db import get_data_dir

# Bundled data ships inside the package (foodguide/data/*.json) and is loaded
# with importlib.resources so it works from an installed wheel or zipapp.
_BUNDLED_DATA_DIR = _pkg_files("foodguide.data")

_BUNDLED_PATH_LABELS = {
    "dri_macronutrients.json": "foodguide/data/dri_macronutrients.json",
    "eer_equations.json": "foodguide/data/eer_equations.json",
}


def _load_bundled_json(name: str) -> Optional[Dict[str, Any]]:
    """Read a JSON file bundled in foodguide/data via importlib.resources."""
    try:
        with (_BUNDLED_DATA_DIR / name).open('r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, FileNotFoundError) as e:
        print(f"Failed to load bundled data file {name}: {e}", file=sys.stderr)
        return None


def _read_data_dir_json(path) -> Optional[Dict[str, Any]]:
    """Read a JSON file from the data dir; None if missing, corrupt or unreadable."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"Data file {path} is not a JSON object; ignoring it", file=sys.stderr)
            return None
        return data
    except (json.JSONDecodeError, OSError) as e:
        # Corrupt or unreadable data-dir file: warn and fall back to bundled.
        print(f"Data file {path} is unreadable ({e}); falling back to bundled snapshot", file=sys.stderr)
        return None


def _loaded_from(
    data_dir_name: str, bundled_name: str, require_success: bool = False
) -> tuple[Dict[str, Any], str, Optional[str], Optional[Dict[str, Any]]]:
    """Two-level load: data-dir file first, then the bundled snapshot.

    Returns (payload, source, active_path, provenance). Never raises; if the
    data-dir file is missing or corrupt it silently falls back to bundled.
    """
    data_dir_path = get_data_dir() / data_dir_name
    data = _read_data_dir_json(data_dir_path)
    if data is not None and (not require_success or data.get("status") == "success"):
        provenance = data.get("_provenance")
        if not isinstance(provenance, dict):
            provenance = None
        return data, "data_dir", str(data_dir_path), provenance

    bundled = _load_bundled_json(bundled_name)
    if bundled is not None and (not require_success or bundled.get("status") == "success"):
        provenance = bundled.get("_provenance")
        if not isinstance(provenance, dict):
            provenance = None
        return bundled, "bundled_snapshot", _BUNDLED_PATH_LABELS[bundled_name], provenance

    # This should never happen — bundled data is shipped with the package.
    return {}, "missing", None, None


class DRIDataManager:
    """
    Manages DRI macronutrient reference data (data-dir file, bundled fallback).

    Returns data in the exact format that fetch_macronutrient_data() produces,
    so all existing tools work without modification. A data-dir file written by
    `foodguide data build dri` may carry a top-level ``_provenance`` object; it
    is exposed as-is in the returned payload.
    """

    def __init__(self):
        self._data: Optional[Dict[str, Any]] = None
        self._data_source: str = "not_loaded"
        self._loaded_path: Optional[str] = None
        self._provenance: Optional[Dict[str, Any]] = None
        self._last_loaded: Optional[datetime] = None

    def get_dri_data(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get DRI macronutrient data. Never fails and never touches the network.

        ``force_refresh`` is kept for API compatibility and only forces a
        reload from local files (data dir, then bundled); it performs no
        network access in any case.
        """
        if self._data is None or force_refresh:
            self._reload()

        if self._data is not None:
            return self._add_freshness_info(self._data)

        # This should never happen — bundled data is shipped with the package.
        return {
            "status": "error",
            "error": "No DRI data available (bundled data missing)",
            "error_type": "data_unavailable"
        }

    def get_status(self) -> Dict[str, Any]:
        """Describe the active DRI data source (loads it if not loaded yet)."""
        if self._data is None:
            self._reload()
        size_bytes = self._active_size_bytes("dri_macronutrients.json")
        return {
            "source": self._data_source,
            "path": self._loaded_path,
            "size_bytes": size_bytes,
            "provenance": self._provenance,
        }

    def _reload(self) -> None:
        data, source, path, provenance = _loaded_from(
            "dri_macronutrients.json", "dri_macronutrients.json", require_success=True
        )
        self._data = data or None
        self._data_source = source
        self._loaded_path = path
        self._provenance = provenance
        self._last_loaded = datetime.now()

    def _active_size_bytes(self, bundled_name: str) -> Optional[int]:
        try:
            if self._data_source == "data_dir" and self._loaded_path:
                return os.path.getsize(self._loaded_path)
            if self._data_source == "bundled_snapshot":
                return (_BUNDLED_DATA_DIR / bundled_name).stat().st_size
        except OSError as e:
            print(f"Could not stat DRI data file: {e}", file=sys.stderr)
        return None

    def _add_freshness_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add freshness metadata to the response without mutating original."""
        result = dict(data)
        result["_data_freshness"] = {
            "source": self._data_source,
            "loaded_at": self._last_loaded.isoformat() if self._last_loaded else None,
            "original_timestamp": data.get("last_updated"),
            "note": self._freshness_note()
        }
        return result

    def _freshness_note(self) -> str:
        if self._data_source == "data_dir":
            return (
                "Loaded from the local data-dir snapshot (built with "
                "`foodguide data build dri`); no network access at query time."
            )
        elif self._data_source == "bundled_snapshot":
            return "Using bundled snapshot. DRI values are updated very rarely by Health Canada (last major update ~2005/2010)."
        return "Data source unknown"


class EERDataManager:
    """
    Manages EER equation reference data (data-dir file, bundled fallback).

    EER equations are mathematical constants that essentially never change;
    the bundled snapshot is always available offline, and a data-dir file from
    `foodguide data build eer` takes priority when present.
    """

    def __init__(self):
        self._data: Optional[Dict[str, Any]] = None
        self._data_source: str = "not_loaded"
        self._loaded_path: Optional[str] = None
        self._provenance: Optional[Dict[str, Any]] = None
        self._last_loaded: Optional[datetime] = None

    def get_eer_data(self) -> Dict[str, Any]:
        """Get EER equation data from the data dir or the bundled snapshot."""
        if self._data is None:
            self._reload()

        if self._data is not None:
            return self._data
        return {
            "status": "error",
            "error": "Failed to load EER equation data (bundled data missing or invalid)"
        }

    def get_status(self) -> Dict[str, Any]:
        """Describe the active EER data source (loads it if not loaded yet)."""
        if self._data is None:
            self._reload()
        size_bytes = self._active_size_bytes("eer_equations.json")
        return {
            "source": self._data_source,
            "path": self._loaded_path,
            "size_bytes": size_bytes,
            "provenance": self._provenance,
        }

    def _reload(self) -> None:
        data, source, path, provenance = _loaded_from(
            "eer_equations.json", "eer_equations.json", require_success=False
        )
        self._data = data or None
        self._data_source = source
        self._loaded_path = path
        self._provenance = provenance
        self._last_loaded = datetime.now()

    def _active_size_bytes(self, bundled_name: str) -> Optional[int]:
        try:
            if self._data_source == "data_dir" and self._loaded_path:
                return os.path.getsize(self._loaded_path)
            if self._data_source == "bundled_snapshot":
                return (_BUNDLED_DATA_DIR / bundled_name).stat().st_size
        except OSError as e:
            print(f"Could not stat EER data file: {e}", file=sys.stderr)
        return None

    def get_pal_descriptions(self) -> Dict[str, Any]:
        """Get PAL category descriptions from the active EER data."""
        data = self.get_eer_data()
        return data.get("pal_descriptions", {})

    def get_equations(self, equation_type: str = "all", pal_category: str = "all") -> Dict[str, Any]:
        """
        Get EER equations, filtered by type and PAL category.

        Returns in a format compatible with the existing get_eer_equations tool output.
        """
        data = self.get_eer_data()
        if "error" in data:
            return {"status": "error", "error": data["error"], "equations": {}}

        equations = data.get("equations", {})
        url = data.get("_metadata", {}).get("url", "https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/equations-estimate-energy-requirement.html")

        # Filter equations based on type
        filtered = {}
        type_map = {
            "adult": ["adult"],
            "child": ["infant_toddler", "child_adolescent"],
            "pregnancy": ["pregnancy"],
            "lactation": ["lactation"],
        }

        target_keys = type_map.get(equation_type, list(equations.keys())) if equation_type != "all" else list(equations.keys())

        for key in target_keys:
            if key in equations:
                eq_section = equations[key]

                # If filtering by PAL category, extract only matching equations
                if pal_category != "all":
                    filtered[key] = self._filter_by_pal(eq_section, pal_category)
                else:
                    filtered[key] = eq_section

        return {
            "status": "success",
            "equation_type": equation_type,
            "pal_category": pal_category,
            "equations": filtered,
            "source": "Health Canada DRI Tables",
            "url": url,
            "total_equations_found": len(equations),
            "filtered_equations_count": len(filtered),
            "_data_freshness": {
                "source": self._data_source,
                "note": self._freshness_note()
            }
        }

    def _freshness_note(self) -> str:
        if self._data_source == "data_dir":
            return (
                "Loaded from the local data-dir snapshot (built with "
                "`foodguide data build eer`); no network access at query time."
            )
        return "EER equations are mathematical constants from Health Canada DRI tables. They essentially never change."

    def _filter_by_pal(self, section: Dict, pal_category: str) -> Dict:
        """Filter an equation section to only include matching PAL category."""
        result = {}
        for key, value in section.items():
            if key == pal_category:
                result[key] = value
            elif isinstance(value, dict):
                if pal_category in value:
                    result[key] = {pal_category: value[pal_category]}
                    # Preserve non-PAL metadata
                    for k, v in value.items():
                        if k not in ("inactive", "low_active", "active", "very_active"):
                            result[key][k] = v
                elif key not in ("inactive", "low_active", "active", "very_active"):
                    result[key] = value
            else:
                result[key] = value
        return result


# Singleton instances
_dri_manager: Optional[DRIDataManager] = None
_eer_manager: Optional[EERDataManager] = None


def get_dri_data_manager() -> DRIDataManager:
    """Get or create the DRI data manager singleton."""
    global _dri_manager
    if _dri_manager is None:
        _dri_manager = DRIDataManager()
    return _dri_manager


def get_eer_data_manager() -> EERDataManager:
    """Get or create the EER data manager singleton."""
    global _eer_manager
    if _eer_manager is None:
        _eer_manager = EERDataManager()
    return _eer_manager
