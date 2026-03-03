"""
Data manager for DRI/EER reference data.

Provides bundled static data as the guaranteed fallback, with optional
live refresh from Health Canada's website. This eliminates the dependency
on www.canada.ca being reachable at tool-call time.

Data priority:
1. In-memory cache (if populated and not expired)
2. Runtime cache file (cache/*.json, from successful scrape)
3. Bundled static data (data/*.json, always available)

The scraper is only used for background refresh — never blocks tool calls.
"""

import json
import os
import sys
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Resolve project paths
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)

# Data file paths
_DATA_DIR = os.path.join(_project_root, 'data')
_CACHE_DIR = os.path.join(_project_root, 'cache')

_BUNDLED_DRI_PATH = os.path.join(_DATA_DIR, 'dri_macronutrients.json')
_BUNDLED_EER_PATH = os.path.join(_DATA_DIR, 'eer_equations.json')
_CACHE_DRI_PATH = os.path.join(_CACHE_DIR, 'dri_macronutrients.json')

# Cache duration for runtime cache validity
_CACHE_DURATION = timedelta(hours=24)


class DRIDataManager:
    """
    Manages DRI macronutrient reference data with bundled fallback.

    Returns data in the exact format that fetch_macronutrient_data() produces,
    so all existing tools work without modification.
    """

    def __init__(self):
        self._data: Optional[Dict[str, Any]] = None
        self._data_source: str = "not_loaded"
        self._last_loaded: Optional[datetime] = None
        self._refresh_lock = threading.Lock()
        self._refresh_attempted = False

    def get_dri_data(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get DRI macronutrient data. Never fails — always returns bundled data at minimum.

        Returns the same dict structure as MacronutrientScraper.fetch_macronutrient_data().
        """
        # Return cached in-memory data if available and not forcing refresh
        if self._data and not force_refresh:
            return self._add_freshness_info(self._data)

        # Try runtime cache first (from previous successful scrape)
        if not force_refresh:
            cache_data = self._load_runtime_cache()
            if cache_data:
                self._data = cache_data
                self._data_source = "runtime_cache"
                self._last_loaded = datetime.now()
                return self._add_freshness_info(cache_data)

        # Fall back to bundled static data (always available)
        bundled = self._load_bundled_data()
        if bundled:
            self._data = bundled
            self._data_source = "bundled_snapshot"
            self._last_loaded = datetime.now()
            return self._add_freshness_info(bundled)

        # This should never happen — bundled data is shipped with the package
        return {
            "status": "error",
            "error": "No DRI data available (bundled data missing)",
            "error_type": "data_unavailable"
        }

    def try_background_refresh(self):
        """
        Attempt to refresh DRI data from the live website in a background thread.
        Non-blocking — tools never wait for this.
        """
        if self._refresh_attempted:
            return

        def _refresh():
            with self._refresh_lock:
                if self._refresh_attempted:
                    return
                self._refresh_attempted = True

                try:
                    # Import scraper lazily to avoid circular imports
                    try:
                        from src.api.dri import MacronutrientScraper
                    except ImportError:
                        from api.dri import MacronutrientScraper

                    scraper = MacronutrientScraper()
                    result = scraper.fetch_macronutrient_data(force_refresh=True)

                    if result.get("status") == "success":
                        self._data = result
                        self._data_source = "live_refresh"
                        self._last_loaded = datetime.now()
                        print("DRI data refreshed from Health Canada website", file=sys.stderr)
                    else:
                        print(f"DRI background refresh failed: {result.get('error', 'unknown')}", file=sys.stderr)

                except Exception as e:
                    print(f"DRI background refresh error: {e}", file=sys.stderr)

        thread = threading.Thread(target=_refresh, daemon=True)
        thread.start()

    def _load_runtime_cache(self) -> Optional[Dict[str, Any]]:
        """Load from runtime cache file if it exists and is fresh enough."""
        try:
            if not os.path.exists(_CACHE_DRI_PATH):
                return None

            # Check file age
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(_CACHE_DRI_PATH))
            if file_age > _CACHE_DURATION:
                return None

            with open(_CACHE_DRI_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if data.get("status") == "success":
                return data
            return None

        except (json.JSONDecodeError, OSError):
            return None

    def _load_bundled_data(self) -> Optional[Dict[str, Any]]:
        """Load bundled static data. This should always succeed."""
        try:
            with open(_BUNDLED_DRI_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if data.get("status") == "success":
                return data
            return None

        except (json.JSONDecodeError, OSError, FileNotFoundError) as e:
            print(f"Failed to load bundled DRI data: {e}", file=sys.stderr)
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
        if self._data_source == "live_refresh":
            return "Data freshly verified from Health Canada website"
        elif self._data_source == "runtime_cache":
            return "Data from recent scrape cache (within 24 hours)"
        elif self._data_source == "bundled_snapshot":
            return "Using bundled snapshot. DRI values are updated very rarely by Health Canada (last major update ~2005/2010)."
        return "Data source unknown"


class EERDataManager:
    """
    Manages EER equation reference data with bundled fallback.

    EER equations are mathematical constants that essentially never change.
    The bundled data is the primary source; live scraping is a bonus.
    """

    def __init__(self):
        self._data: Optional[Dict[str, Any]] = None
        self._last_loaded: Optional[datetime] = None

    def get_eer_data(self) -> Dict[str, Any]:
        """Get EER equation data. Always returns bundled data."""
        if self._data:
            return self._data

        try:
            with open(_BUNDLED_EER_PATH, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
                self._last_loaded = datetime.now()
                return self._data
        except (json.JSONDecodeError, OSError, FileNotFoundError) as e:
            return {
                "status": "error",
                "error": f"Failed to load EER equation data: {e}"
            }

    def get_pal_descriptions(self) -> Dict[str, Any]:
        """Get PAL category descriptions from bundled data."""
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
                "source": "bundled_snapshot",
                "note": "EER equations are mathematical constants from Health Canada DRI tables. They essentially never change."
            }
        }

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
