"""
CNF API Client — Health Canada's Canadian Nutrient File REST API.

Replaces the NutrientFileScraper (src/api/cnf.py) with clean JSON API calls.
API docs: https://produits-sante.canada.ca/api/documentation/cnf-documentation-en.html
Base URL: https://food-nutrition.canada.ca/api/canadian-nutrient-file/
"""

import re
import requests
from typing import Optional, List, Dict, Any, Tuple

# Nutrient name IDs for core macronutrients (from nutrientname endpoint)
CORE_MACRONUTRIENT_IDS = {
    208: {"name": "Energy (kcal)", "unit": "kCal", "symbol": "KCAL"},
    268: {"name": "Energy (kJ)", "unit": "kJ", "symbol": "KJ"},
    203: {"name": "Protein", "unit": "g", "symbol": "PROT"},
    204: {"name": "Total Fat", "unit": "g", "symbol": "FAT"},
    205: {"name": "Carbohydrate", "unit": "g", "symbol": "CARB"},
    606: {"name": "Fatty acids, saturated, total", "unit": "g", "symbol": "TSAT"},
    645: {"name": "Fatty acids, monounsaturated, total", "unit": "g", "symbol": "MUFA"},
    646: {"name": "Fatty acids, polyunsaturated, total", "unit": "g", "symbol": "PUFA"},
    605: {"name": "Fatty acids, trans, total", "unit": "g", "symbol": "TRFA"},
    291: {"name": "Fibre, total dietary", "unit": "g", "symbol": "TDF"},
    269: {"name": "Sugars, total", "unit": "g", "symbol": "TSUG"},
    307: {"name": "Sodium, Na", "unit": "mg", "symbol": "NA"},
    601: {"name": "Cholesterol", "unit": "mg", "symbol": "CHOL"},
}


def parse_measure_name(measure_name: str) -> Tuple[float, str]:
    """Extract numeric amount and unit from CNF API measure_name strings.

    Examples:
        "1 food guide serving = 75g" → (75.0, "g")
        "250ml"                      → (250.0, "ml")
        "1/2 fillet"                 → (0.5, "fillet")
        "100ml flaked"               → (100.0, "ml")
        "125ml"                      → (125.0, "ml")
    """
    # Handle "X food guide serving = Yunit" — use the gram equivalent after '='
    eq_match = re.search(r'=\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)', measure_name)
    if eq_match:
        return float(eq_match.group(1)), eq_match.group(2).lower()

    # Handle standard patterns like "250ml", "100ml flaked", "1/2 fillet"
    frac_match = re.search(r'(\d+/\d+)\s*([a-zA-Z]+)', measure_name)
    if frac_match:
        num, denom = frac_match.group(1).split('/')
        return float(num) / float(denom), frac_match.group(2).lower()

    num_match = re.search(r'(\d+(?:\.\d+)?)\s*([a-zA-Z]+)', measure_name)
    if num_match:
        return float(num_match.group(1)), num_match.group(2).lower()

    # Fallback: return the whole string as the unit with amount 1.0
    return 1.0, measure_name.strip().lower()


class CNFApiClient:
    """Client for Health Canada's Canadian Nutrient File REST API."""

    BASE_URL = "https://food-nutrition.canada.ca/api/canadian-nutrient-file"

    def __init__(self, timeout: int = 30, lang: str = "en"):
        self._session = requests.Session()
        self._timeout = timeout
        self._lang = lang
        self._food_cache: Optional[List[Dict]] = None

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> list:
        """Shared GET helper. Returns parsed JSON (always a list)."""
        url = f"{self.BASE_URL}/{endpoint}/"
        request_params = {"lang": self._lang, "type": "json"}
        if params:
            request_params.update(params)

        response = self._session.get(url, params=request_params, timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        # API always returns a list
        if isinstance(data, list):
            return data
        return [data] if data else []

    # ── Food search ──────────────────────────────────────────────

    def get_all_foods(self) -> List[Dict[str, Any]]:
        """Fetch and cache the full food list (5,690 foods). Only fetched once per process."""
        if self._food_cache is None:
            self._food_cache = self._get("food")
        return self._food_cache

    def search_food(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Search foods using cached food list with tiered matching.

        Tiers:
            1. Exact substring match (case-insensitive)
            2. All tokens present (order-independent)
            3. Any token match, ranked by hit count
        """
        foods = self.get_all_foods()
        query_lower = query.lower()
        tokens = query_lower.split()

        # Tier 1: Exact substring
        exact = [f for f in foods if query_lower in f["food_description"].lower()]

        # Tier 2: All tokens present
        if not exact:
            all_tokens = [
                f for f in foods
                if all(t in f["food_description"].lower() for t in tokens)
            ]
        else:
            all_tokens = []

        # Tier 3: Any token, ranked by hit count
        if not exact and not all_tokens:
            scored = []
            for f in foods:
                desc = f["food_description"].lower()
                hits = sum(1 for t in tokens if t in desc)
                if hits > 0:
                    scored.append((hits, f))
            scored.sort(key=lambda x: -x[0])
            any_tokens = [f for _, f in scored]
        else:
            any_tokens = []

        results = exact or all_tokens or any_tokens
        return [
            {"food_code": str(f["food_code"]), "food_name": f["food_description"]}
            for f in results[:max_results]
        ]

    def get_food(self, food_code: str) -> Optional[Dict]:
        """Single food lookup by code."""
        data = self._get("food", {"id": food_code})
        if data:
            item = data[0]
            return {"food_code": str(item["food_code"]), "food_description": item["food_description"]}
        return None

    # ── Nutrient data ────────────────────────────────────────────

    def get_nutrient_amounts(self, food_code: str) -> List[Dict]:
        """All nutrients for a food (per 100g). Returns raw API list."""
        return self._get("nutrientamount", {"id": food_code})

    def get_serving_sizes(self, food_code: str) -> List[Dict]:
        """Serving size conversion factors for a food."""
        return self._get("servingsize", {"id": food_code})

    def get_refuse_amount(self, food_code: str) -> Optional[Dict]:
        """Refuse info for a food. Returns first result or None."""
        data = self._get("refuseamount", {"id": food_code})
        return data[0] if data else None

    def get_nutrient_names(self) -> List[Dict]:
        """All 152 nutrient definitions with units, symbols, groups."""
        return self._get("nutrientname")

    # ── Convenience methods ──────────────────────────────────────

    def get_macronutrients(self, food_code: str) -> Dict[str, Any]:
        """Fetch core macronutrients + serving sizes for a food.

        Returns a structured dict with:
            - food_code
            - nutrients: list of {nutrient_name_id, name, value_per_100g, unit, symbol}
            - servings: list of {measure_name, conversion_factor, amount, unit}
            - refuse: optional refuse info
        """
        raw_nutrients = self.get_nutrient_amounts(food_code)
        servings = self.get_serving_sizes(food_code)
        refuse = self.get_refuse_amount(food_code)

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

        parsed_servings = []
        for s in servings:
            measure = s.get("measure_name", "")
            factor = s.get("conversion_factor_value", 1.0)
            amount, unit = parse_measure_name(measure)
            parsed_servings.append({
                "measure_name": measure,
                "conversion_factor": factor,
                "amount": amount,
                "unit": unit,
            })

        return {
            "food_code": food_code,
            "nutrients": macros,
            "servings": parsed_servings,
            "refuse": refuse,
        }

    def get_full_nutrient_profile(self, food_code: str) -> Dict[str, Any]:
        """Fetch ALL nutrients (not just macros) + serving sizes for a food.

        Returns same structure as get_macronutrients but with all 152 nutrients.
        """
        raw_nutrients = self.get_nutrient_amounts(food_code)
        servings = self.get_serving_sizes(food_code)
        refuse = self.get_refuse_amount(food_code)

        all_nutrients = []
        for n in raw_nutrients:
            all_nutrients.append({
                "nutrient_name_id": n.get("nutrient_name_id"),
                "name": n.get("nutrient_web_name", ""),
                "value_per_100g": n.get("nutrient_value", 0.0),
                "unit": n.get("nutrient_web_unit", ""),
                "symbol": n.get("nutrient_web_symbol", ""),
            })

        parsed_servings = []
        for s in servings:
            measure = s.get("measure_name", "")
            factor = s.get("conversion_factor_value", 1.0)
            amount, unit = parse_measure_name(measure)
            parsed_servings.append({
                "measure_name": measure,
                "conversion_factor": factor,
                "amount": amount,
                "unit": unit,
            })

        return {
            "food_code": food_code,
            "nutrients": all_nutrients,
            "servings": parsed_servings,
            "refuse": refuse,
        }


# ── Singleton factory ────────────────────────────────────────────

_cnf_api_instance: Optional[CNFApiClient] = None


def get_cnf_api_client() -> CNFApiClient:
    """Get or create the global CNF API client instance."""
    global _cnf_api_instance
    if _cnf_api_instance is None:
        _cnf_api_instance = CNFApiClient()
    return _cnf_api_instance
