###  IMPLEMENTATIONS.md
Future improvements, tasks, project roadmap, and notes.

---

## Current Status (March 2026) — Post-HTTP Transport Testing

### Tool Health Summary (from remote/HTTP deployment testing)

| Category | Status | Notes |
|---|---|---|
| Recipe search & retrieval | ✅ Fully functional | `search_recipes`, `get_recipe` both working |
| Filter discovery | ✅ Fully functional | `list_filters` returns full filter set |
| CNF food search | ✅ Works | `search_and_get_cnf_macronutrients` — needs simple search terms |
| CNF macronutrient fetch | ⚠️ Bug | `get_cnf_macronutrients_only` returns 0 nutrients for valid food codes |
| Math calculator | ✅ Fully functional | `bulk_math_calculator` — clean batch processing |
| DRI/AMDR/EER tools | ❌ Network timeout | All tools timeout connecting to `www.canada.ca` |

### Known Bugs

1. **`get_cnf_macronutrients_only` returns 0 macronutrients** — Food code 3183 (farmed Atlantic salmon, baked) reports 5 serving options available but fetches 0 actual nutrient values. The scraper's HTML parsing silently fails. **Root cause: fragile HTML scraping.** This is resolved by the API migration below — the official REST API returns all 152 nutrients as structured JSON without any HTML parsing.

2. **DRI/EER/AMDR tools all timeout** — `www.canada.ca` is unreachable from the deployment environment (10s read timeout). Affected tools: `get_amdrs`, `get_specific_macronutrient_dri`, `get_amino_acid_patterns`, likely `get_macronutrient_dri_tables` and `get_eer_equations`. This is a network-level issue — either the hosting environment blocks outbound connections to `www.canada.ca`, or Health Canada's servers are intermittently unresponsive.

3. **CNF search is too strict** — Searching "salmon Atlantic cooked" returns no results. Only simple terms like "salmon" work. **Resolved by the API migration below** — the full food list (5,690 foods) can be cached in memory and searched client-side with flexible matching.

---

## Next Up — CNF API Migration (replacing web scraper)

### Discovery

Health Canada publishes an **official REST API** for the Canadian Nutrient File at `food-nutrition.canada.ca` (different domain from the failing `www.canada.ca`). It requires no authentication, has no documented rate limits, and returns clean JSON.

**API documentation:** https://produits-sante.canada.ca/api/documentation/cnf-documentation-en.html

**Base URL:** `https://food-nutrition.canada.ca/api/canadian-nutrient-file/`

### API Endpoints (all verified working)

| Endpoint | URL Pattern | Returns | Current Equivalent |
|---|---|---|---|
| **Food** | `food/?id={food_code}&lang=en&type=json` | `food_code`, `food_description` | `scraper.search_food()` |
| **Food (all)** | `food/?lang=en&type=json` | All 5,690 foods | No equivalent (scraper searches via POST) |
| **Nutrient Amount** | `nutrientamount/?id={food_code}&lang=en&type=json` | All nutrients per 100g with values, source IDs | `scraper.get_nutrient_profile()` |
| **Serving Size** | `servingsize/?id={food_code}&lang=en&type=json` | Conversion factors + measure names | `scraper.get_serving_info()` |
| **Refuse Amount** | `refuseamount/?id={food_code}&lang=en&type=json` | Refuse percentage + name | Parsed from HTML in `get_serving_info()` |
| **Yield Amount** | `yieldamount/?id={food_code}&lang=en&type=json` | Yield conversion data | Not implemented |
| **Nutrient Name** | `nutrientname/?lang=en&type=json` | All 152 nutrient definitions with units, symbols, groups | Hardcoded `CORE_MACRONUTRIENTS` list |
| **Nutrient Group** | `nutrientgroup/?lang=en&type=json` | 7 groups (Proximates, Minerals, Vitamins, Amino Acids, Lipids, etc.) | Category names parsed from HTML `<th>` |
| **Nutrient Source** | `nutrientsource/?lang=en&type=json` | Source descriptions (calculated, analytical, etc.) | Not used |

### What This Fixes

1. **Bug #1 (0 macronutrients)** — Eliminated entirely. API returns structured `nutrient_value` floats directly. No HTML table parsing, no regex, no "trace"/<value cleaning needed.
2. **Bug #3 (strict search)** — Cache the full 5,690-food list in memory. Search becomes client-side substring/fuzzy matching with zero network calls.
3. **Scraping fragility** — No more CSRF tokens, POST forms, DataTables params, or HTML parsing that breaks when Health Canada updates their page structure.
4. **Rate limiting concerns** — No documented rate limits on the API. Eliminates need for `CNF_RATE_LIMIT`, `CNF_MAX_CONCURRENT`, exponential backoff, circuit breakers.
5. **robots.txt compliance** — This is an official API, not web scraping. No robots.txt issues.
6. **Code volume** — Eliminates ~400-line scraper (`src/api/cnf.py`) and ~300 lines of HTML parsing logic in `cnf_tools.py`.

### What Does NOT Change

- **Tool names** — All 8 MCP tool names stay identical
- **Tool signatures** — All Pydantic input/output models stay identical
- **LLM-facing behavior** — Same JSON response structure, same `next_steps` guidance
- **SQLite schema** — `temp_cnf_foods`, `temp_cnf_nutrients` tables unchanged
- **`enable_db` gating** — Same stdio/HTTP split logic
- **Recipe workflow** — Tools 5-8 (recipe setup, nutrition summary, query, update decisions) are untouched (they consume stored data, don't call the scraper)
- **`server.py`** — Still calls `register_cnf_tools(mcp)` from `src.db.cnf_tools`

---

### Phase 1: New API Client (`src/api/cnf_api.py`)

Replace `src/api/cnf.py` (the `NutrientFileScraper` class) with a clean API client. clear the file and the start inside it fresh. 

#### 1.1 — Create New clise (~200 lines)

```python
class CNFApiClient:
    """Client for Health Canada's Canadian Nutrient File REST API."""

    BASE_URL = "https://food-nutrition.canada.ca/api/canadian-nutrient-file"
```

**Methods to implement:**

- **`__init__(self, timeout=30, lang="en")`**
  - `self._session = requests.Session()` (reuse connections)
  - `self._timeout = timeout`
  - `self._lang = lang`
  - `self._food_cache: Optional[List[Dict]] = None` (lazy-loaded full food list)

- **`_get(self, endpoint: str, params: dict) -> list`** — shared GET helper
  - URL: `{BASE_URL}/{endpoint}/`
  - Default params: `lang=self._lang`, `type=json`
  - Returns parsed JSON (always a list)
  - Raises on HTTP errors with clear messages

- **`get_all_foods(self) -> List[Dict[str, Any]]`** — fetch + cache full food list
  - Calls `_get("food", {})` → returns all 5,690 foods
  - Caches in `self._food_cache` (only fetched once per process lifetime)
  - Each item: `{"food_code": int, "food_description": str}`

- **`search_food(self, food_name: str, max_results: int = 10) -> List[Dict[str, str]]`**
  - Calls `get_all_foods()` (cached after first call)
  - **Matching strategy (in priority order):**
    1. Exact substring match (case-insensitive) on full `food_description`
    2. All-tokens match: split `food_name` into words, keep foods where ALL tokens appear in description
    3. Any-token match: keep foods where ANY token appears (ranked by token hit count)
  - Returns: `[{"food_code": str, "food_name": str}, ...]` (same format as current scraper)
  - Limit to `max_results`

- **`get_food(self, food_code: str) -> Optional[Dict]`** — single food lookup
  - Calls `_get("food", {"id": food_code})`
  - Returns: `{"food_code": str, "food_description": str}` or None

- **`get_nutrient_amounts(self, food_code: str) -> List[Dict]`** — all nutrients for a food
  - Calls `_get("nutrientamount", {"id": food_code})`
  - Returns raw list: `[{"food_code", "nutrient_value", "standard_error", "number_observation", "nutrient_name_id", "nutrient_web_name", "nutrient_source_id"}, ...]`

- **`get_serving_sizes(self, food_code: str) -> List[Dict]`** — serving size conversion factors
  - Calls `_get("servingsize", {"id": food_code})`
  - Returns: `[{"food_code", "food_description", "conversion_factor_value", "measure_name"}, ...]`
  - **Key:** `conversion_factor_value` is the multiplier to convert per-100g values to per-serving values (e.g., 0.75 for 75g food guide serving)

- **`get_refuse_amount(self, food_code: str) -> Optional[Dict]`**
  - Calls `_get("refuseamount", {"id": food_code})`
  - Returns first result or None: `{"refuse_amount": float, "refuse_name": str}`

- **`get_macronutrients(self, food_code: str) -> Dict[str, Any]`** — convenience method (replaces scraper's `get_nutrient_profile(filter="macronutrients")`)
  - Calls `get_nutrient_amounts(food_code)`
  - Filters to core macronutrient IDs only (see constant below)
  - Calls `get_serving_sizes(food_code)` for conversion factors
  - Returns structured dict matching what tools currently expect

**Constants:**

```python
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
```

#### 1.2 — Singleton factory

```python
_cnf_api_instance: Optional[CNFApiClient] = None

def get_cnf_api_client() -> CNFApiClient:
    global _cnf_api_instance
    if _cnf_api_instance is None:
        _cnf_api_instance = CNFApiClient()
    return _cnf_api_instance
```

Replaces `get_cnf_scraper()` in `cnf_tools.py`.

#### 1.3 — Serving size math (critical difference from scraper)

The scraper returns nutrient values **already calculated** per serving size (each column in the HTML table has the actual value). The API returns:
- `nutrientamount` → nutrient values **per 100g only**
- `servingsize` → `conversion_factor_value` multipliers

To get per-serving values: `serving_value = per_100g_value * conversion_factor_value`

Example for salmon 3183, Protein (22.1g per 100g):
- "1 food guide serving = 75g" → factor 0.75 → `22.1 * 0.75 = 16.575g`
- "1/2 fillet" → factor 1.78 → `22.1 * 1.78 = 39.338g`
- "250ml" → factor 1.43702 → `22.1 * 1.43702 = 31.758g`

This calculation replaces the regex-heavy column name parsing (e.g., extracting "5ml" from "5ml / 5 g" column headers) that is currently copy-pasted 3 times in `cnf_tools.py`.

---

### Phase 2: Update `cnf_tools.py` — Swap Scraper for API Client

Replace all `NutrientFileScraper` calls with `CNFApiClient` calls inside the 4 scraper-dependent tools. Tools 5-8 (recipe workflow) are untouched.

#### 2.1 — Tool 1: `search_and_get_cnf_macronutrients`

**Current flow:**
1. `scraper.search_food(food_name)` → POST to `/cnf-fce/doSearch` with CSRF
2. If 1 result: `scraper.get_serving_info()` → GET HTML, parse checkboxes
3. `scraper.get_nutrient_profile(filter="macronutrients")` → POST, parse HTML table
4. 100-line regex block to extract values + store in SQLite

**New flow:**
1. `api.search_food(food_name)` → client-side filter on cached food list (zero network calls after first)
2. If 1 result: `api.get_nutrient_amounts(food_code)` → GET JSON, filter to `CORE_MACRONUTRIENT_IDS`
3. `api.get_serving_sizes(food_code)` → GET JSON, get conversion factors
4. Compute `value * factor` for each serving, store in SQLite

**Changes in detail:**
- Replace `scraper = get_cnf_scraper()` → `api = get_cnf_api_client()`
- Replace `scraper.search_food(input_data.food_name)` → `api.search_food(input_data.food_name, max_results=input_data.max_results)`
- Return format is identical: `[{"food_code": str, "food_name": str}]`
- Delete the ~100-line nutrient parsing block (lines ~580-696). Replace with:
  ```python
  nutrients = api.get_nutrient_amounts(food_code)
  servings = api.get_serving_sizes(food_code)
  macros = [n for n in nutrients if n["nutrient_name_id"] in CORE_MACRONUTRIENT_IDS]
  ```
- Serving value calculation becomes:
  ```python
  for macro in macros:
      # Store 100g baseline
      store_nutrient(macro["nutrient_web_name"], macro["nutrient_value"], 100.0, "g")
      # Store per-serving values
      for serving in servings:
          serving_value = macro["nutrient_value"] * serving["conversion_factor_value"]
          # Parse measure_name for amount and unit (e.g., "250ml" → 250.0, "ml")
          amount, unit = parse_measure_name(serving["measure_name"])
          store_nutrient(macro["nutrient_web_name"], serving_value, amount, unit)
  ```
- Refuse info: replace HTML parsing with `api.get_refuse_amount(food_code)`

#### 2.2 — Tool 2: `get_cnf_macronutrients_only`

**Current flow:**
1. `scraper.get_serving_info(food_code)` → parse HTML checkboxes
2. `scraper.get_nutrient_profile(food_code, serving_options, filter="macronutrients")` → parse HTML table
3. Copy-pasted nutrient parsing block (marked "COPIED FROM get_cnf_nutrient_profile")
4. Optional ingredient linking (UPDATE `temp_recipe_ingredients`)

**New flow:**
1. `api.get_nutrient_amounts(food_code)` → filter to `CORE_MACRONUTRIENT_IDS`
2. `api.get_serving_sizes(food_code)` → get conversion factors
3. Compute `value * factor` for each serving (same shared logic as Tool 1)
4. Optional ingredient linking (unchanged)

**Changes in detail:**
- Delete copy-pasted parsing block (~lines 700-900)
- Replace with same API call + compute pattern as Tool 1
- Ingredient linking logic (lines 700-712) stays exactly as-is
- `serving_options_available` count now comes from `len(api.get_serving_sizes(food_code))`

#### 2.3 — Tool 3: `bulk_get_cnf_macronutrients`

**Current flow:**
1. `ThreadPoolExecutor` → `process_single_food_code()` per food code
2. Each worker: cache check → `scraper.get_serving_info()` → `scraper.get_nutrient_profile()`
3. Third copy-pasted nutrient parsing block
4. Ingredient mappings update

**New flow:**
1. `ThreadPoolExecutor` → new `process_single_food_code_api()` per food code
2. Each worker: cache check → `api.get_nutrient_amounts()` + `api.get_serving_sizes()`
3. Same shared compute logic
4. Ingredient mappings update (unchanged)

**Changes in detail:**
- Replace `process_single_food_code()` (lines 141-239) with `process_single_food_code_api()`
- New worker makes 2 API GET calls instead of 2 scraper calls (GET serving info + POST report)
- `CNFCache` still applies — cache key is `food_code`, cached value is the API response dict
- `CNF_MAX_CONCURRENT` (3) can likely be increased since API is lighter than scraping, but keep at 3 initially
- `CNF_RATE_LIMIT` (0.5s) can be removed — no documented rate limits on the API

#### 2.4 — Tool 4: `get_cnf_nutrient_profile`

**Current flow:**
1. `scraper.get_serving_info(food_code)` → parse HTML
2. `scraper.get_nutrient_profile(food_code, filter="all")` → parse full HTML table (146+ nutrients)
3. Complex value parsing: "trace" → 0.0, "<0.1" → 0.0, regex cleanup
4. Store all nutrients in SQLite + legacy virtual session

**New flow:**
1. `api.get_nutrient_amounts(food_code)` → all 152 nutrients as JSON (no filter)
2. `api.get_serving_sizes(food_code)` → conversion factors
3. Values are already clean floats — no "trace"/"<value" parsing needed
4. Store in SQLite + legacy virtual session (structure unchanged)

**Changes in detail:**
- Delete the entire value-cleaning pipeline (lines ~1275-1287): no regex for "trace", "<0.1", fraction handling
- API returns `nutrient_value: float` directly — already parsed
- `nutrient_web_name` from API matches the existing nutrient names used in SQLite
- Full profile now returns `standard_error` and `number_observation` (bonus data not available from scraper)
- Category grouping: use `nutrient_group_id` from `nutrientname` endpoint to group by "Proximates", "Minerals", "Vitamins", "Amino Acids", "Lipids", "Other Carbohydrates", "Other components"

---

### Phase 3: Shared Helper — `parse_measure_name()`

The API's `servingsize` endpoint returns `measure_name` strings like:
- `"100ml flaked"` → amount=100.0, unit="ml"
- `"250ml"` → amount=250.0, unit="ml"
- `"1 food guide serving = 75g"` → amount=75.0, unit="g"
- `"1/2 fillet"` → amount=0.5, unit="fillet"

Create a small helper to parse these into `(amount: float, unit: str)` tuples. This replaces the 3 copy-pasted regex blocks that currently parse HTML column headers like `"5ml / 5 g"`.

```python
def parse_measure_name(measure_name: str) -> tuple[float, str]:
    """Extract numeric amount and unit from CNF API measure_name strings."""
    # Handle "1 food guide serving = 75g" → use the gram equivalent
    # Handle "250ml" → 250.0, "ml"
    # Handle "1/2 fillet" → 0.5, "fillet"
    # Handle "100ml flaked" → 100.0, "ml"
```

Place in `src/api/cnf_api.py` alongside the client class.

---

### Phase 4: Improve Search with Cached Food List

The API returns all 5,690 foods from `food/?lang=en&type=json`. Cache this in memory on first call.

**Search strategy in `CNFApiClient.search_food()`:**

```python
def search_food(self, query: str, max_results: int = 10) -> List[Dict]:
    foods = self.get_all_foods()  # cached after first call
    query_lower = query.lower()
    tokens = query_lower.split()

    # Tier 1: Exact substring match
    exact = [f for f in foods if query_lower in f["food_description"].lower()]

    # Tier 2: All tokens present (order-independent)
    if not exact:
        all_tokens = [f for f in foods
                      if all(t in f["food_description"].lower() for t in tokens)]
    else:
        all_tokens = []

    # Tier 3: Any token match, ranked by hit count
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
    return [{"food_code": str(f["food_code"]), "food_name": f["food_description"]}
            for f in results[:max_results]]
```

**Before (scraper):** "salmon Atlantic cooked" → POST to Health Canada → 0 results
**After (API):** "salmon Atlantic cooked" → tokens ["salmon", "atlantic", "cooked"] → Tier 2 all-tokens match → returns "Fish, salmon, atlantic, farmed, baked or broiled" and "Fish, salmon, atlantic, wild, baked or broiled"

---

### Phase 5: Delete Scraper & Clean Up

#### 5.1 — Delete `src/api/cnf.py`
- Remove the entire `NutrientFileScraper` class (~400 lines)
- Remove `CORE_MACRONUTRIENTS` list (replaced by `CORE_MACRONUTRIENT_IDS` dict in `cnf_api.py`)
- Remove `beautifulsoup4` from requirements if no other file uses it (check `dri.py`, `eer.py` first — they still scrape `www.canada.ca`)

#### 5.2 — Update imports in `cnf_tools.py`
- Replace: `from src.api.cnf import NutrientFileScraper` → `from src.api.cnf_api import get_cnf_api_client`
- Replace: `get_cnf_scraper()` → `get_cnf_api_client()`
- Remove the dual try/except import for the scraper (simplify to single import)

#### 5.3 — Remove dead code from `cnf_tools.py`
- Delete `process_single_food_code()` (lines 141-239) — replaced by `process_single_food_code_api()`
- Delete all 3 copy-pasted nutrient parsing blocks
- Delete CSRF-related error handling
- Delete HTML-specific error messages ("Could not parse nutrient table", etc.)

#### 5.4 — Update config
- `CNF_RATE_LIMIT` (0.5s) — can be removed or reduced to 0, no documented API rate limits
- `CNF_CACHE_TTL` (1800s) — keep for `CNFCache`, still useful to avoid re-fetching same food code
- `CNF_MAX_CONCURRENT` (3) — keep initially, can increase later since API calls are lighter

#### 5.5 — Update `get_cnf_tools_status()`
- Fix stale tool names (currently lists deprecated `link_ingredient_to_cnf_simple`)
- Update tool count from 7 to 8
- Change data source description from "web scraping" to "Health Canada CNF REST API"

---

### Phase 6: Verification

#### 6.1 — Functional parity tests
For each of the 4 modified tools, verify output matches expected format:

- [ ] `search_and_get_cnf_macronutrients("salmon")` — returns same 5+ results with food_code/food_name
- [ ] `search_and_get_cnf_macronutrients("honey")` — single match auto-fetches, returns macronutrients_stored > 0
- [ ] `search_and_get_cnf_macronutrients("salmon Atlantic cooked")` — NOW returns results (was 0 before)
- [ ] `get_cnf_macronutrients_only(food_code="3183")` — returns macronutrients_stored = 13 (was 0 before, the bug)
- [ ] `get_cnf_macronutrients_only(food_code="3183")` — serving_options_available matches API serving count (4 for salmon)
- [ ] `bulk_get_cnf_macronutrients(food_codes=["3183", "4294", "461"])` — all succeed, no timeouts
- [ ] `get_cnf_nutrient_profile(food_code="3183")` — returns 100+ nutrients (was full profile)

#### 6.2 — SQLite storage verification
- [ ] `temp_cnf_foods` rows have correct `food_description` from API
- [ ] `temp_cnf_nutrients` rows have correct `nutrient_value` per 100g baseline
- [ ] `temp_cnf_nutrients` rows have correct per-serving values (100g value * conversion_factor)
- [ ] Composite PK `(session_id, cnf_food_code, nutrient_name, per_amount, unit)` still unique — no duplicate inserts

#### 6.3 — Recipe workflow integration
- [ ] Tools 5-8 still work end-to-end (they read from SQLite, not the scraper — should be unaffected)
- [ ] `calculate_recipe_nutrition_summary` unit matching works with API-sourced serving sizes
- [ ] `query_recipe_macros_table` JOIN returns correct concatenated nutrition values

#### 6.4 — HTTP mode
- [ ] API calls work from remote/Render environment (different domain than `www.canada.ca`)
- [ ] `enable_db=False` gating still prevents SQLite writes in HTTP mode
- [ ] Search still works (food list cache is in-memory, transport-agnostic)

---

### Estimated Impact

| Metric | Before (scraper) | After (API) |
|---|---|---|
| `src/api/cnf.py` | ~400 lines (scraper) | ~200 lines (API client) |
| `src/db/cnf_tools.py` | ~2,325 lines | ~1,600 lines (est. -700 lines of parsing) |
| Network calls per food lookup | 3 (CSRF + POST search + POST report) | 2 (GET nutrients + GET servings) |
| Network calls for search | 2 (CSRF + POST) | 0 (cached food list) |
| HTML parsing dependencies | BeautifulSoup + regex | None |
| Failure modes | CSRF expiry, HTML structure changes, rate limiting | API down (single failure mode) |
| Search capability | Exact match only | Substring + tokenized + ranked |
| Data freshness | Live scrape | Live API (same underlying database) |

---

## March 2026 — HTTP Transport & Remote Deployment

### -- HTTP Transport Migration ✅ Complete
- [x] Update `fastmcp` to v2.3+ (Streamable HTTP support built-in)
- [x] Add `--transport` CLI flag to `src/server.py` (`stdio` default, `http` option)
- [x] Add `--port` and `--host` flags with `$PORT`/`$HOST` env var fallbacks (Render sets `$PORT`)
- [x] Switch `mcp.run()` call based on transport flag:
  - `stdio`: `mcp.run(transport='stdio')` (current behavior, all features)
  - `http`: `mcp.run(transport='streamable-http', host=host, port=port)`

### -- DB Feature Gating (HTTP Mode) ✅ Complete
SQLite is not viable for stateless HTTP hosting. Gate DB-dependent tools behind the transport flag.

- [x] Add `enable_db` flag derived from transport mode (`True` for stdio, `False` for http)
- [x] Skip `register_db_tools(mcp)` in HTTP mode — covers: favorites, temp sessions, temp tables
- [x] Split `register_eer_tools()` — DB-dependent: `create_user_profile`, `get_user_profile`, `delete_user_profile`, `list_user_profiles`; always available: `get_eer_equations`, `get_pal_descriptions`
- [x] Split `register_cnf_tools()` — DB-dependent: recipe analysis tools (simple_recipe_setup, calculate_recipe_nutrition_summary, query_recipe_macros_table, update_recipe_macros_decisions); always available: search/fetch tools (with DB writes gated internally)
- [x] Extract `register_math_tools`, `register_dri_tools`, `register_session_dri_tools` from `register_db_tools` — now registered directly from server.py (always available, no DB dependency)
- [x] Guard DB writes in CNF search tools behind `enable_db` (scrape data still returned)
- [x] Ensure virtual sessions (in-memory dicts) still work in HTTP mode — DRI session tools confirmed transport-agnostic
- Tool availability: **46 tools (stdio)** / **24 tools (HTTP)**

### -- MCP Resources (Static Reference Data) ✅ Complete
Bundled static JSON snapshots + MCP Resources eliminate dependency on `www.canada.ca` at tool-call time.

**Architecture:**
- `data/dri_macronutrients.json` — Bundled DRI reference tables (exact format from scraper cache)
- `data/eer_equations.json` — Bundled EER equations with extracted coefficients + PAL categories
- `src/data_manager.py` — `DRIDataManager` / `EERDataManager` singletons with priority: in-memory → runtime cache → bundled data
- `src/resources.py` — MCP Resource registrations (read-only reference data for LLM context)
- DRI/EER tools updated to use data manager instead of live scraping

**Resources registered (6):**
- [x] `dri://macronutrient-tables` — Complete DRI reference values by age/gender
- [x] `dri://amdrs` — Acceptable Macronutrient Distribution Ranges
- [x] `dri://amino-acid-patterns` — PDCAAS reference patterns
- [x] `dri://additional-recommendations` — Saturated fat, trans fat, cholesterol, added sugars guidance
- [x] `dri://footnotes` — Official footnotes from Health Canada tables
- [x] `eer://equations` — All EER equations with coefficients (infant through adult, pregnancy, lactation)
- [x] `eer://pal-categories` — PAL category descriptions + definitions + activity examples
- [x] Registered in both stdio and HTTP modes via `register_resources(mcp)` in `server.py`

**Data freshness strategy:**
- Bundled snapshots always available (zero network dependency)
- Background refresh attempted on first DRI tool use (non-blocking)
- If live scrape succeeds → updates in-memory cache + saves to `cache/dri_macronutrients.json`
- If live scrape fails → bundled data used with freshness note
- DRI values updated very rarely by Health Canada (last major update ~2005/2010)

### -- Render Deployment
- [x] Server runs on HTTP transport with correct feature gating
- [ ] Create `Dockerfile` (python:3.11-slim, install deps, run with `--transport http`)
- [ ] Create `render.yaml` (web service, free plan, `TRANSPORT=http` env var)
- [ ] Test deployment end-to-end with MCP Inspector against HTTP endpoint
- [ ] Document remote connection URL in README
- [x] **Resolve `www.canada.ca` connectivity** — Resolved by bundling static JSON snapshots in `data/` + MCP Resources. DRI/EER tools now serve data from bundled files with optional background refresh. No network dependency at tool-call time.

---

## Backlog — DRI/EER Network Resilience (mostly resolved)
- [x] Pre-scrape DRI tables and bundle as static JSON fallback data (via `data/dri_macronutrients.json`)
- [x] Return bundled/cached data with freshness note when live fetch fails (via `DRIDataManager`)
- [x] EER equations bundled as static JSON (via `data/eer_equations.json`, `EERDataManager`)
- [ ] Investigate if Health Canada has DRI/EER APIs similar to the CNF API

## Backlog — Tool Consolidation (from Jun 2025)
- [ ] Merge `calculate_recipe_nutrition_summary` + `query_recipe_macros_table` (first sets up table for second)
- [ ] Merge `store_recipe_in_temp_tables` + `simple_recipe_setup` (setup parses stored ingredients)

## Backlog — `cnf_tools.py` Refactor (post-API migration)

After the API migration shrinks `cnf_tools.py` from ~2,325 to ~1,600 lines, the remaining refactor is simpler:

- [ ] **`src/db/cnf_unit_matching.py`** (~150 lines) — extract unit analysis helpers
  - `_normalize_unit()`
  - `_can_convert_units()`
  - `_analyze_unit_matching()`

- [ ] **`src/utils/cnf_sqlite_utils.py`** (~150 lines) — extract standalone SQLite helpers
  - `populate_cnf_food_in_sqlite()` — currently unused externally
  - `populate_cnf_nutrient_in_sqlite()` — currently unused externally
  - `clear_cnf_data_from_sqlite()` — currently unused externally
  - `get_cnf_tools_status()` — fix stale tool names

- [ ] **Slim `src/db/cnf_tools.py`** (~600 lines) — tools only
  - All 8 `@mcp.tool()` definitions
  - Import helpers from new modules
  - Keep `CNF_TOOLS_AVAILABLE` flag and dual import try/except pattern

**Note:** The `src/utils/cnf_helpers.py` extraction (CNFCache, bulk worker, parse_and_store) is now largely unnecessary — the API migration eliminates the parsing duplication and simplifies the bulk worker. `CNFCache` can stay in `cnf_tools.py`.

## Backlog — Feature Ideas
- [ ] Extend DRI support to include micronutrients, vitamins, and minerals
- [ ] Allow users to persist `temp_recipe_` data to permanent DB for pantry/stock tracking
- [ ] Configurable retention periods for stored recipe information
- [ ] Update CLI (`cli.py`) to include DB, EER, and CNF compatibility
- [ ] Add tests and tool-call frequency evaluation for sustainability
- [ ] Simplify installation with npm/Smithery packaging

---

## Notes
- **CNF data access options:** (1) Web scraping `food-nutrition.canada.ca/cnf-fce/` — current, fragile; (2) Official REST API `food-nutrition.canada.ca/api/canadian-nutrient-file/` — new, recommended; (3) Database file download — offline option, static data. We are migrating from (1) to (2).
- Current LLM clients (Claude, ChatGPT) have strong built-in web crawlers. The HTML scraping approach for DRI/EER may become redundant — but remains valuable for smaller/local models without web access.
- CNF API is hosted on `food-nutrition.canada.ca` (not `www.canada.ca`) — verified accessible from local and likely from cloud environments.
- FastMCP v2.3+ makes Streamable HTTP the default HTTP transport, replacing deprecated SSE.
- Virtual sessions (Python dicts) are transport-agnostic and work in both stdio and HTTP modes.
- Render free tier supports Docker web services with `$PORT` injection.
- `www.canada.ca` (DRI/EER) may require specific User-Agent headers or have geo-restrictions affecting cloud-hosted servers.
