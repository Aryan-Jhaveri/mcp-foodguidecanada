# IMPLEMENTATIONS.md
Future improvements, tasks, project roadmap, and notes.

---

## March 2026 — HTTP Transport & Remote Deployment

### Goal
Make the server deployable as a remote MCP app on Render (free tier) via Streamable HTTP transport, while keeping stdio for local Claude Desktop use.

### -- HTTP Transport Migration
- [x] Update `fastmcp` to v2.3+ (Streamable HTTP support built-in)
- [x] Add `--transport` CLI flag to `src/server.py` (`stdio` default, `http` option)
- [x] Add `--port` and `--host` flags with `$PORT`/`$HOST` env var fallbacks (Render sets `$PORT`)
- [x] Switch `mcp.run()` call based on transport flag:
  - `stdio`: `mcp.run(transport='stdio')` (current behavior, all features)
  - `http`: `mcp.run(transport='streamable-http', host=host, port=port)`

### -- DB Feature Gating (HTTP Mode)
SQLite is not viable for stateless HTTP hosting. Gate DB-dependent tools behind the transport flag.

- [x] Add `enable_db` flag derived from transport mode (`True` for stdio, `False` for http)
- [x] Skip `register_db_tools(mcp)` in HTTP mode — covers: favorites, temp sessions, temp tables
- [x] Split `register_eer_tools()` — DB-dependent: `create_user_profile`, `get_user_profile`, `delete_user_profile`, `list_user_profiles`; always available: `get_eer_equations`, `get_pal_descriptions`
- [x] Split `register_cnf_tools()` — DB-dependent: recipe analysis tools (simple_recipe_setup, calculate_recipe_nutrition_summary, query_recipe_macros_table, update_recipe_macros_decisions); always available: search/fetch tools (with DB writes gated internally)
- [x] Extract `register_math_tools`, `register_dri_tools`, `register_session_dri_tools` from `register_db_tools` — now registered directly from server.py (always available, no DB dependency)
- [x] Guard DB writes in CNF search tools behind `enable_db` (scrape data still returned)
- [x] Ensure virtual sessions (in-memory dicts) still work in HTTP mode — DRI session tools confirmed transport-agnostic
- Tool availability: **46 tools (stdio)** / **24 tools (HTTP)**

### -- MCP Resources (Static Reference Data)
Convert static/semi-static data to MCP Resources to reduce unnecessary tool calls.

- [ ] Create `src/resources.py` with resource registrations
- [ ] `eer://pal-categories` — PAL category descriptions (currently hardcoded in `eer_tools.py`)
- [ ] `dri://macronutrients` — DRI reference tables (cached, from `MacronutrientScraper`)
- [ ] `eer://equations` — Health Canada EER equations (from `EERCalculator`)
- [ ] Register resources in both stdio and HTTP modes

### -- Render Deployment
- [ ] Create `Dockerfile` (python:3.11-slim, install deps, run with `--transport http`)
- [ ] Create `render.yaml` (web service, free plan, `TRANSPORT=http` env var)
- [ ] Test deployment end-to-end with MCP Inspector against HTTP endpoint
- [ ] Document remote connection URL in README

---

## Backlog — Rate Limiting & Web Scraping (from Aug 2025)
- [ ] Exponential backoff with jitter for CNF scraping (fixed 0.5s delay is insufficient for bulk ops)
- [ ] Request chunking for `bulk_get_cnf_macronutrients` (break 20-food requests into 3-5 food chunks)
- [ ] Circuit breaker pattern for repeated CNF failures
- [ ] Increase default `CNF_RATE_LIMIT` from 0.5s to 2-3s
- [ ] Investigate Health Canada official API access to reduce scraping dependency

## Backlog — Tool Consolidation (from Jun 2025)
- [ ] Merge `calculate_recipe_nutrition_summary` + `query_recipe_macros_table` (first sets up table for second)
- [ ] Merge `store_recipe_in_temp_tables` + `simple_recipe_setup` (setup parses stored ingredients)

### -- `cnf_tools.py` Refactor (2,325 lines → ~4 focused modules)

The file contains 8 MCP tools, a cache class, a bulk worker, 3 unit-matching helpers, 3 SQLite utility functions, and a status function. The nutrient parsing/storing logic is copy-pasted 3 times across `get_cnf_macronutrients_only`, `bulk_get_cnf_macronutrients`, and `get_cnf_nutrient_profile` (marked with inline comments "COPIED FROM get_cnf_nutrient_profile").

**Extraction plan:**

- [ ] **`src/utils/cnf_helpers.py`** (~350 lines) — general-purpose CNF utilities
  - `CNFCache` class (thread-safe TTL cache, lines 92–129)
  - `get_cnf_scraper()` singleton factory (lines 134–139)
  - `process_single_food_code()` bulk worker (lines 141–239)
  - **New `parse_and_store_cnf_nutrients()`** — deduplicates the ~100-line nutrient parsing block copied 3x (handles 100g baseline parsing, trace/`<value` cleaning, serving size column detection, fraction handling, `temp_cnf_foods` + `temp_cnf_nutrients` INSERT)
  - Move `import re` to module-level (currently re-imported inside loops)

- [ ] **`src/db/cnf_unit_matching.py`** (~150 lines) — unit analysis (stays in db/, used by tools)
  - `_normalize_unit()` (lines 2055–2081)
  - `_can_convert_units()` (lines 2162–2185)
  - `_analyze_unit_matching()` (lines 2083–2160)

- [ ] **`src/utils/cnf_sqlite_utils.py`** (~150 lines) — standalone SQLite helpers
  - `populate_cnf_food_in_sqlite()` (lines 2190–2229) — currently unused externally
  - `populate_cnf_nutrient_in_sqlite()` (lines 2231–2264) — currently unused externally
  - `clear_cnf_data_from_sqlite()` (lines 2266–2301) — currently unused externally
  - `get_cnf_tools_status()` (lines 2303–2326) — fix stale tool names (lists deprecated names like `link_ingredient_to_cnf_simple`, count says 7 but actual is 8)

- [ ] **Slim `src/db/cnf_tools.py`** (~600 lines) — tools only
  - Keep all 8 `@mcp.tool()` definitions inside `register_cnf_tools(mcp)`
  - Replace 3 copy-pasted nutrient parsing blocks with `parse_and_store_cnf_nutrients()` calls
  - Import helpers from new modules
  - Keep `CNF_TOOLS_AVAILABLE` flag and dual import try/except pattern
  - Keep all tool docstrings unchanged (they guide LLM behavior)
  - `server.py` unchanged — still calls `register_cnf_tools(mcp)` from `src.db.cnf_tools`

**What does NOT change:** tool names, signatures, docstrings, models (`cnf_models.py`), `server.py`, `__init__.py`. Pure structural refactor.

## Backlog — Feature Ideas
- [ ] Extend DRI support to include micronutrients, vitamins, and minerals
- [ ] Allow users to persist `temp_recipe_` data to permanent DB for pantry/stock tracking
- [ ] Configurable retention periods for stored recipe information
- [ ] Update CLI (`cli.py`) to include DB, EER, and CNF compatibility
- [ ] Add tests and tool-call frequency evaluation for sustainability
- [ ] Simplify installation with npm/Smithery packaging

---

## Notes
- Current LLM clients (Claude, ChatGPT) have strong built-in web crawlers. The HTML scraping approach may become redundant — but remains valuable for smaller/local models without web access (e.g., phone in a kitchen).
- CNF robot.txt limits affect bulk operations — macronutrient analysis is the most resource-consuming toolset.
- FastMCP v2.3+ makes Streamable HTTP the default HTTP transport, replacing deprecated SSE.
- Virtual sessions (Python dicts) are transport-agnostic and work in both stdio and HTTP modes.
- Render free tier supports Docker web services with `$PORT` injection.
