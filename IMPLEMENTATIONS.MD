# Implementation notes

How foodguide (version 3.0.0) is put together. Contributors should read this with
[CONTRIBUTING.md](CONTRIBUTING.md).

foodguide has two front ends, the `foodguide` CLI and the `foodguide-mcp` MCP server. Both read
local dataset files. Neither fetches anything when it answers a question. Only the data builders
use the network.

## Package layout

Everything is under `src/foodguide`.

| Path | What it is |
|---|---|
| `cli.py` | The typer CLI. Groups: `cnf`, `dri`, `eer`, `recipes`, `data` (with `data build`). `main()` is the entry point. |
| `server.py` | The MCP server (fastmcp). `create_server(enable_db)` registers the tools. `main()` uses argparse with `--transport stdio\|http`, `--host`, `--port`. |
| `api/` | Readers and tool registrations. `recipe.py` (recipe tools over `recipes.json`), `cnf_api.py` (returns the local CNF source), `eer.py` (EER maths and profiles), `dri.py` (the DRI page parser, also used by the DRI/EER builder). `cnf.py` is an old scraper of the previous CNF site and is not used. |
| `cnf/` | `builder.py` builds `cnf.sqlite` from the CNF 2026 zip. `db.py` reads it (path helpers, search, nutrients, measures). `mcp_source.py` (`LocalCNFSource`) gives the MCP tools the old CNF client interface on top of `db.py`. |
| `db/` | MCP tool modules (`cnf_tools.py`, `dri_tools.py`, `eer_tools.py`, `math_tools.py`, `queries.py`) and the session store (`connection.py`, `schema.py`, `sql_engine.py`). Session state is SQLite in the state folder. |
| `recipes/` | `fetch.py` (polite fetching, on-disk cache), `parser.py` (recipe page parser), `builder.py` (builds `recipes.json`), `source.py` (`LocalRecipeSource`, reads it). |
| `builders/` | `dri_eer.py`: fetches and parses the Health Canada DRI and EER pages into `dri_macronutrients.json` and `eer_equations.json`. Also holds `calculate_eer`. |
| `pipeline/` | `build_all.py` (`data build all`), `manifest.py` (manifest and change detection), `install.py` (`data fetch`). |
| `data/` | Bundled snapshots of `dri_macronutrients.json` and `eer_equations.json`. They are the fallback when the data folder has no copy. |
| `data_manager.py` | `DRIDataManager` and `EERDataManager`. Read the data-folder file first, then the bundled snapshot. Never touches the network. |
| `config.py` | Settings read from the environment: source base URL, state folder, session DB path, limits. |
| `resources.py` | MCP resources (`dri://...`, `eer://...`) built from the DRI/EER data. |
| `models/` | Pydantic models for tool input and output. |
| `utils/` | Empty package, kept for imports. |

`main.py` in the repo root is a six-line shim that calls `foodguide.cli.main`. Use
`uv run foodguide` instead.

The MCP server has 46 tools on the stdio transport. On the `http` transport the tools that need
the session SQLite database are not registered (`enable_db` is false), so there are fewer.

## Data flow

```text
canada.ca pages (DRI, EER, recipes) ──┐
open.canada.ca CNF 2026 zip ──────────┤
                                      ▼
   builders: builders/dri_eer.py, cnf/builder.py, recipes/builder.py
                                      ▼
   data folder: cnf.sqlite  recipes.json  dri_macronutrients.json
                eer_equations.json  manifest.json
                                      ▼
   readers: cli.py, api/, cnf/db.py, recipes/source.py, data_manager.py
                                      ▼
                    CLI (foodguide)   and   MCP server (foodguide-mcp)
```

- Builders run on demand (`foodguide data build ...`) or in the weekly workflow. They write files
  into the data folder.
- `foodguide data fetch` installs datasets that the workflow already built and published, so most
  users never run a builder. It checks every file against its sha256 before it installs it.
- Readers open those files. They never fetch. Tests prove this with a static import check
  (`tests/test_offline_modules.py`) and with subprocess runs that point the proxy variables at a
  dead port (`tests/test_offline_subprocess.py`).
- The DRI and EER readers fall back to the bundled snapshots if the data folder has no copy (or
  the copy is corrupt, which is logged on stderr).

### Fetching rules

All builder fetches use the User-Agent
`foodguide-data-build/0.1 (+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada)`. canada.ca
stalls plain `Mozilla/5.0` agents. Recipe fetches wait at least 1 second between pages and retry
with backoff. Page URLs are built from `FOODGUIDE_SOURCE_BASE_URL` (default
`https://www.canada.ca`), so tests can serve the pages from a local server.

## Manifest and change detection

`src/foodguide/pipeline/manifest.py` writes `manifest.json` next to the datasets. For each file it
records:

- sha256 and size of the file;
- a content hash (CNF database, recipes) that ignores build time and compression;
- record counts (for example foods and nutrient amount rows in the CNF database);
- upstream facts: the CNF zip hash and metadata date, the recipes index hash and count, the DRI and
  EER page hash and date modified;
- the package version and build time.

`changed_datasets(old, new)` compares one content identity per dataset and returns the names that
differ. The identity is the content hash where there is one, otherwise the upstream page hash and
date, otherwise the file sha256. Build time, package version and gzip bytes do not count.

```bash
foodguide data manifest DIR          # write DIR/manifest.json
foodguide data changed OLD NEW       # exit 0 and print nothing if equivalent; exit 10 and list changed datasets otherwise
```

`.github/workflows/data-refresh.yml` runs weekly. It runs the live tests, builds everything with
`foodguide data build all --download-cnf --out-dir out`, checks the manifest with
`scripts/check_manifest.py` (required files, minimum sizes, no shrink of more than 10%), and
publishes to the `data-latest` release only when `data changed` exits 10 (or when forced).

## Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `FOODGUIDE_DATA_DIR` | Folder with the dataset files. | `~/.local/share/foodguide` |
| `FOODGUIDE_STATE_DIR` | Folder for the MCP session database. | `~/.local/state/foodguide` |
| `FOODGUIDE_DB_FILE` | Path of the MCP session SQLite file. | `<state dir>/foodguide_data.db` |
| `FOODGUIDE_SOURCE_BASE_URL` | Base URL builders fetch Health Canada pages from. Used by tests to point at a local server. | `https://www.canada.ca` |
| `FOODGUIDE_CKAN_PACKAGE_URL` | open.canada.ca CKAN `package_show` URL used to find the CNF zip for `--download-cnf`. | the CNF 2026 package record |
| `FOODGUIDE_RECIPES_CACHE_DIR` | Serve recipe pages from this folder instead of fetching (`build recipes`, `build all`). | not set |
| `FOODGUIDE_CNF_ZIP` | Path of the CNF zip for `data build cnf`. The zip is never downloaded by that command. | not set (then a zip in the data folder) |
| `SOURCE_DATE_EPOCH` | Fixed build timestamp, so `data build cnf` is reproducible. | not set (current time) |
| `MCP_TRANSPORT` | MCP transport, `stdio` or `http`. `--transport` overrides it. | `stdio` |
| `HOST` | Bind address for the http transport. `--host` overrides it. | `127.0.0.1` |
| `PORT` | Port for the http transport. `--port` overrides it. | `8000` |
| `SUPPRESS_MCP_LOGS` | `true` hides fastmcp log output on stdio. | `true` |
| `FOODGUIDE_LOG_LEVEL` | Log level for the CNF and server loggers. | `CRITICAL` |
| `TOOL_TIMEOUT_SECONDS`, `BULK_OPERATION_TIMEOUT`, `PROGRESS_REPORT_INTERVAL` | MCP tool limits (seconds). | `30`, `60`, `3` |
| `CNF_RATE_LIMIT`, `CNF_MAX_CONCURRENT`, `CNF_CACHE_TTL` | Limits for the MCP CNF bulk tools. | `0.5`, `3`, `1800` |
| `FOODGUIDE_SKIP_LIVE_TESTS` | Test only: `1` skips the live DRI/EER snapshot tests. | not set |
| `FOODGUIDE_TEST_CNF_ZIP`, `FOODGUIDE_TEST_RECIPE_CACHE`, `FOODGUIDE_TEST_GOLDEN_RECIPES` | Test only: paths for the CNF golden test, the live recipes crawl cache and the recipes golden key. | see the test files |

## Known limits

- **No refuse amounts in CNF 2026.** The source has no refuse (waste) percentages. The measure row
  `total refuse` is always 0 g. For example, `foodguide cnf measures 3392` shows
  `total refuse` with 0 grams. Do not read it as "no waste".
- **`eer calc` does not do pregnancy or lactation.** It covers the infant, child and adult
  equations from age, sex, height, weight and activity level. The pregnancy and lactation
  equations are in the data (`foodguide eer equations --type pregnancy`) but the calculator does
  not apply them.
- **MCP `calculate_dri_from_eer` needs a session profile — and nothing can store one yet.**
  The tool requires a `session_id` whose session data already holds a matching profile under
  `dri_user_profiles`, DRI tables in the session (`store_dri_tables_in_session`), the EER in
  kcal, and an age range that matches an AMDR key. But no registered tool writes
  `dri_user_profiles`: the storing tool the code's error messages point to
  (`store_dri_user_profile_in_session`) does not exist, and `create_user_profile` keeps its
  virtual profiles in a per-call object, not in the session. In practice the tool errors with
  "User profile ... not found" until a profile is put into the session by other means. It gives
  gram ranges and formulas; it does the arithmetic through the calculator tools, not itself.
- **Data is as old as its last build.** DRI and EER values come from the last build or the bundled
  snapshot. Recipes and CNF come from the last build or release. Check with
  `foodguide data status`.
- **Page parsers depend on the page layout.** If Health Canada redesigns a DRI, EER or recipe page,
  the build can fail or return less data. `scripts/check_manifest.py` blocks publishing a build
  that is missing files or much smaller than the last one.
- **Session tools are stdio only.** Favorites, temporary recipe tables and session SQL are not
  registered on the http transport.

## Open items

- Merge `calculate_recipe_nutrition_summary` and `query_recipe_macros_table`, and
  `store_recipe_in_temp_tables` and `simple_recipe_setup`, to cut the number of tool calls an LLM
  needs.
- Split `db/cnf_tools.py`, which is large.
- Clean up unused legacy code in `api/` (`cnf.py`, and the HTTP client in `cnf_api.py`).
- Extend DRI support to micronutrients, vitamins and minerals.
- Add a Dockerfile for the http transport.
- Check whether Health Canada offers DRI or EER data through an API instead of web pages.
- Ideas: weekly meal planning, tracking ingredients in stock, personal nutrition goals, more export
  formats, Smithery or npm packaging, and keeping `temp_recipe_` data permanently with a configurable
  retention period.

## Design notes

- FastMCP 2.3 and later use Streamable HTTP as the HTTP transport. SSE is deprecated.
- Virtual sessions (Python dictionaries) work the same on stdio and HTTP. The SQLite-backed session
  tools are registered on stdio only.
- Many chat clients can crawl the web themselves, so scraping DRI and EER pages at question time
  would be redundant. The scrapers still matter for smaller or local models with no web access,
  which is why the data is built into files ahead of time.
- canada.ca stalls requests that send a `Mozilla/5.0` User-Agent from some clients. The builders send
  an identifying User-Agent and wait 1 second between requests.

## Credits

- Canadian Nutrient File 2026, Health Canada (Open Government Licence – Canada).
- Food Guide recipes, Health Canada.
- DRI and EER tables, Health Canada.
