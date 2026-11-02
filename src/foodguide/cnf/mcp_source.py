"""LocalCNFSource — offline drop-in replacement for CNFApiClient.

Same method names and return-dict shapes as foodguide.api.cnf_api.CNFApiClient,
but every answer comes from the local CNF 2026 SQLite database built by
`foodguide data build cnf` (see foodguide.cnf.db). Zero network access.

The SQLite connection is opened lazily on first use (so merely constructing the
object without a database does not fail) and one read-only connection is kept
per instance.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from foodguide.api.cnf_api import CORE_MACRONUTRIENT_IDS, parse_measure_name
from foodguide.cnf.db import get_food, get_measures, get_nutrients, open_cnf_db, search_foods


def _missing_db_error(exc: FileNotFoundError) -> RuntimeError:
    return RuntimeError(
        "CNF SQLite database not available: " + str(exc) + " "
        "Build it offline with `foodguide data build cnf` first."
    )


class LocalCNFSource:
    """CNF data source backed by the offline SQLite database (read-only)."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._food_cache: Optional[List[Dict[str, Any]]] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy, read-only connection to the local CNF database."""
        if self._conn is None:
            try:
                self._conn = open_cnf_db(self._db_path)
            except FileNotFoundError as exc:
                raise _missing_db_error(exc) from exc
        return self._conn

    def close(self) -> None:
        """Close the underlying connection (if one was opened)."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._food_cache = None

    # ── Food search ──────────────────────────────────────────────

    def get_all_foods(self) -> List[Dict[str, Any]]:
        """Full food list (cached like the API client did): food_code + food_description."""
        if self._food_cache is None:
            rows = self.conn.execute(
                "SELECT food_code, description_en FROM food ORDER BY food_code"
            )
            self._food_cache = [
                {"food_code": row[0], "food_description": row[1]} for row in rows
            ]
        return self._food_cache

    def search_food(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Full-text search over the offline database (English names)."""
        results = search_foods(self.conn, query, "en", max_results)
        return [
            {"food_code": str(row["food_code"]), "food_name": row["name_en"]}
            for row in results
        ]

    def get_food(self, food_code: str) -> Optional[Dict]:
        """Single food lookup by code, or None if unknown."""
        try:
            code = int(food_code)
        except (TypeError, ValueError):
            return None
        food = get_food(self.conn, code)
        if food is None:
            return None
        return {"food_code": str(food["food_code"]), "food_description": food["name_en"]}

    # ── Nutrient data ────────────────────────────────────────────

    def get_nutrient_amounts(self, food_code: str) -> List[Dict]:
        """All nutrients for a food (per 100 g), shaped like the raw API list.

        nutrient_name_id is the CNF nutrient code (stable between the REST API
        and the 2026 CSV files).
        """
        try:
            code = int(food_code)
        except (TypeError, ValueError):
            return []
        return [
            {
                "nutrient_name_id": row["code"],
                "nutrient_value": float(row["amount"]),
                "nutrient_web_name": row["name_en"],
                "nutrient_web_unit": row["unit"],
                "nutrient_web_symbol": row["symbol"],
            }
            for row in get_nutrients(self.conn, code)
        ]

    def get_serving_sizes(self, food_code: str) -> List[Dict]:
        """Household measure conversions for a food; [] when it has none."""
        try:
            code = int(food_code)
        except (TypeError, ValueError):
            return []
        return [
            {
                "measure_name": row["description_en"],
                "conversion_factor_value": float(row["grams"]),
            }
            for row in get_measures(self.conn, code)
        ]

    def get_refuse_amount(self, food_code: str) -> Optional[Dict]:
        """Refuse info for a food.

        Always None: the CNF 2026 all-files zip contains no refuse-amount
        table, so there is no refuse data to expose offline.
        """
        return None

    def get_nutrient_names(self) -> List[Dict]:
        """All nutrient definitions (code, web name, unit, symbol)."""
        rows = self.conn.execute(
            """
            SELECT nutrient_code, name_en, unit, symbol
            FROM nutrient_name
            ORDER BY nutrient_code
            """
        )
        return [
            {
                "nutrient_name_id": row[0],
                "nutrient_web_name": row[1],
                "nutrient_web_unit": row[2],
                "nutrient_web_symbol": row[3],
            }
            for row in rows
        ]

    # ── Convenience methods ──────────────────────────────────────

    def get_macronutrients(self, food_code: str) -> Dict[str, Any]:
        """Core macronutrients + serving sizes for a food (same shape as the API client)."""
        raw_nutrients = self.get_nutrient_amounts(food_code)
        servings = self.get_serving_sizes(food_code)

        macros = []
        for n in raw_nutrients:
            nid = n.get("nutrient_name_id")
            if nid in CORE_MACRONUTRIENT_IDS:
                info = CORE_MACRONUTRIENT_IDS[nid]
                macros.append({
                    "nutrient_name_id": nid,
                    "name": info["name"],
                    "value_per_100g": n.get("nutrient_value", 0.0),
                    "unit": info["unit"],
                    "symbol": info["symbol"],
                })

        return {
            "food_code": food_code,
            "nutrients": macros,
            "servings": self._parse_servings(servings),
            "refuse": None,
        }

    def get_full_nutrient_profile(self, food_code: str) -> Dict[str, Any]:
        """ALL nutrients (not just macros) + serving sizes (same shape as the API client)."""
        raw_nutrients = self.get_nutrient_amounts(food_code)
        servings = self.get_serving_sizes(food_code)

        all_nutrients = [
            {
                "nutrient_name_id": n.get("nutrient_name_id"),
                "name": n.get("nutrient_web_name", ""),
                "value_per_100g": n.get("nutrient_value", 0.0),
                "unit": n.get("nutrient_web_unit", ""),
                "symbol": n.get("nutrient_web_symbol", ""),
            }
            for n in raw_nutrients
        ]

        return {
            "food_code": food_code,
            "nutrients": all_nutrients,
            "servings": self._parse_servings(servings),
            "refuse": None,
        }

    @staticmethod
    def _parse_servings(servings: List[Dict]) -> List[Dict[str, Any]]:
        parsed = []
        for s in servings:
            measure = s.get("measure_name", "")
            factor = s.get("conversion_factor_value", 1.0)
            amount, unit = parse_measure_name(measure)
            parsed.append({
                "measure_name": measure,
                "conversion_factor": factor,
                "amount": amount,
                "unit": unit,
            })
        return parsed
