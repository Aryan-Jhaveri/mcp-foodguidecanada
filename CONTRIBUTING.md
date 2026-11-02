# Contributing to foodguide

`foodguide` is a command-line tool and an MCP server for Canada's Food Guide data. It reads the
Canadian Nutrient File (CNF) 2026, the Food Guide recipes, and the Health Canada DRI and EER
tables. All data is read from local files at run time. The MCP server exposes 46 tools on the
stdio transport.

Bug fixes, docs and new features are welcome. This page says how to set up, test and change the
code. For how the code fits together, read [IMPLEMENTATIONS.MD](IMPLEMENTATIONS.MD).

## Setup

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and Git.

```bash
git clone https://github.com/Aryan-Jhaveri/mcp-foodguidecanada.git
cd mcp-foodguidecanada
uv sync
uv run foodguide --help
```

`uv sync` installs the package in editable mode and the dev group. The dev group includes pytest,
ruff and the `mcp` extra (fastmcp), so the MCP server tests can run.

Datasets are not in the repo. The CLI reads them from `~/.local/share/foodguide` (override with
`FOODGUIDE_DATA_DIR`). Install them with `uv run foodguide data fetch`, or build them yourself
(see "Change a dataset builder" below). The bundled DRI and EER JSON files in
`src/foodguide/data/` are the fallback for those two datasets.

## Workflow

1. Make a branch: `git checkout -b feat/short-name` or `fix/short-name`.
2. Change the code. Add or update a test.
3. Run lint and the tests (below).
4. Commit with a clear message: `feat:`, `fix:`, `docs:`, `refactor:`, `test:` or `perf:`.
5. Push and open a pull request.

## Lint

```bash
uv run ruff check .
```

Settings are in `pyproject.toml`: line length 100, rules E, F, W and I. E501 is ignored because
older code has long data-table lines; keep new code under 100 characters.
`src/foodguide/server.py` ignores E402 on purpose: it sets warning filters before it imports
fastmcp.

## Tests

```bash
uv run pytest -q -m "not live"   # what CI runs: fast, no internet needed
uv run pytest -q -m live         # slow: fetches live canada.ca pages
```

- `-m "not live"` is the CI run (`.github/workflows/ci.yml`, after `ruff check .`).
- `-m live` runs the full 141-page recipes crawl and the live DRI/EER snapshot comparisons. The
  weekly data-refresh workflow (`.github/workflows/data-refresh.yml`) runs it too.
- `FOODGUIDE_SKIP_LIVE_TESTS=1` skips the live DRI/EER snapshot comparisons
  (`tests/test_dri_eer_snapshot.py`), even in a `-m live` run. It does not skip the live recipes
  crawl.
- Tests that start a local `http.server` skip cleanly in sandboxes that block loopback TCP
  connections. They run in CI.
- `tests/test_cnf_golden.py` needs the CNF 2026 zip. It skips if the zip is missing. Point it at
  your copy with `FOODGUIDE_TEST_CNF_ZIP`. The live recipes test can use a folder of crawled
  pages in `FOODGUIDE_TEST_RECIPE_CACHE`.

### Tests: no mocks (project rule)

We do **not** mock our tests. The suite runs against real inputs: real saved
canada.ca pages (`tests/fixtures/pages/`, served by a real localhost
`http.server` from the `pages_server` fixture), real files, a real SQLite
database, real subprocess runs of the CLI, and answer keys
(`tests/fixtures/golden_*.json`) produced by separate, independent scripts
that share no code with the package. Never edit an answer key by hand.

**Allowed**

- `monkeypatch.setenv` / `monkeypatch.delenv` / `monkeypatch.chdir`. These set
  the environment, they fake nothing. The production code reads all its
  configuration points from the environment at call time
  (`FOODGUIDE_DATA_DIR`, `FOODGUIDE_DB_FILE`, `FOODGUIDE_STATE_DIR`,
  `FOODGUIDE_SOURCE_BASE_URL`, `FOODGUIDE_CKAN_PACKAGE_URL`,
  `FOODGUIDE_RECIPES_CACHE_DIR`, `SOURCE_DATE_EPOCH`), so tests never need to
  patch attributes.
- A real `http.server.ThreadingHTTPServer` on 127.0.0.1 in a background thread
  (`tests/pages_fixture.py`), including "broken" responses derived from real
  pages (truncated HTML, a page with its Ingredients heading removed, HTTP 500).
- Answer keys from independent scripts; build options such as
  `data build recipes --max-recipes/--only` to work with a small fixture set.

**Not allowed**

- `unittest.mock`, `MagicMock`, `pytest`'s `patch`, and any
  `monkeypatch.setattr` / `monkeypatch.setitem` on code under test or on
  libraries (`requests`, `datetime`, builders, fetchers).
- "Network is blocked" fixtures that swap `requests.Session.request` for a
  raiser. Prove offline-ness instead with the static import check
  (`tests/test_offline_modules.py`) and real subprocess runs with
  `HTTP_PROXY`/`HTTPS_PROXY` pointed at a dead port
  (`tests/test_offline_subprocess.py`).

### Golden answer keys

- `tests/fixtures/golden_cnf.json`: CNF foods, nutrient values and measures, taken straight from the
  CNF 2026 zip. Used by `tests/test_cnf_golden.py`.
- `tests/fixtures/golden_recipes.json`: recipe titles, ingredients, directions, times and servings.
  Used by `tests/test_recipes_golden.py`.

The tests compare CLI output against these keys. The keys are checked in. The generator scripts
are **not** in this repo: they were written separately on purpose, so that they share no code with
the package, and there is no command here that regenerates them. Do not edit the files by hand. If
upstream data changes and a golden test fails, raise it in the pull request and regenerate the
key with an independent script that reads the source directly (the CNF zip or the canada.ca
pages), then commit the new key.

## Add a CLI command

The CLI is one typer app in `src/foodguide/cli.py`.

- `app` is the root app. Each group is its own `typer.Typer` (`cnf_app`, `dri_app`, `eer_app`,
  `recipes_app`, `data_app`, and `data_build_app` under `data_app`), attached with
  `app.add_typer(...)`.
- A command is a function with `@<group>_app.command("name")`.
- The global `--format table|csv|json` option is the `OutputFormat` enum. It is stored in
  `ctx.obj["format"]`. Commands also accept their own `--format` and fall back to the global one:
  `fmt = format if format is not None else ctx.obj["format"]`.
- **stdout is data only.** Print results with `typer.echo` (or `csv.writer(sys.stdout)`). Print
  log lines, warnings and errors with `_log(message)`, which writes to stderr.
- Exit codes: `raise typer.Exit(code=0)` on success, `1` on an error, `2` for bad usage. The
  exception is `data changed`, which exits `10` when datasets differ.

Steps:

1. Add `@<group>_app.command("name")` in `src/foodguide/cli.py`, with a docstring and an example.
2. Support the three output formats. Keep stdout data-only.
3. Add a test in `tests/` that runs the command against real data (the CLI tests use
   `typer.testing.CliRunner` or a real subprocess).
4. Run `uv run ruff check .` and `uv run pytest -q -m "not live"`.
5. Update the command list in README.md.

## Add an MCP tool

Tools are registered in `src/foodguide/server.py` through the `register_*` functions in
`src/foodguide/db/` and `src/foodguide/api/`, with `@mcp.tool()`. Tools that need SQLite session
state are only registered on the stdio transport. Add a test in `tests/` (see
`tests/test_dri_eer_mcp.py` and `tests/test_recipes_mcp.py`).

## Change a dataset builder

Builders live here:

- DRI and EER: `src/foodguide/builders/dri_eer.py`
- CNF: `src/foodguide/cnf/builder.py` (reads the CNF zip from open.canada.ca)
- Recipes: `src/foodguide/recipes/` (`fetch.py`, `parser.py`, `builder.py`)

Rules for anything that fetches a page:

- Send the identifying User-Agent
  `foodguide-data-build/0.1 (+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada)`. canada.ca
  stalls plain `Mozilla/5.0` agents. Do not change it.
- Wait at least 1 second between fetches (`PoliteFetcher`).
- Retry with backoff on network errors and 5xx responses.
- Build page URLs from `source_base_url()` in `src/foodguide/config.py`. It returns
  `FOODGUIDE_SOURCE_BASE_URL`, default `https://www.canada.ca`. Tests use this to point the
  builders at the local fixture server. Never hard-code the host.

After you change a builder:

```bash
uv run foodguide data build dri          # or: eer, recipes, cnf, all
uv run pytest -q -m "not live"
```

If the output changed, regenerate the golden key with its independent generator (see "Golden
answer keys") and explain the change in the pull request. For a full build into a clean folder
with a manifest, use `uv run foodguide data build all --out-dir out`. Use `--download-cnf` to
download the CNF zip, or `--cnf-zip PATH`.

## Pull requests

Before you open one:

- `uv run ruff check .` passes.
- `uv run pytest -q -m "not live"` passes.
- Docs are updated if behaviour changed (README.md, IMPLEMENTATIONS.MD).
- If you tested the MCP server, say which client and transport.

A pull request should say what changed and why, the type of change (fix, feature, breaking, docs),
how you tested it, and any issue it closes. Maintainers review within a few days.

## Community

Be respectful, collaborative, constructive and patient. Use GitHub Issues for bugs and feature
requests, with clear titles and steps to reproduce. When you discuss nutrition behaviour, link the
Health Canada page it comes from.

## Data credits

- Canadian Nutrient File 2026, Health Canada, under the Open Government Licence – Canada.
- Food Guide recipes, Health Canada.
- Dietary Reference Intakes (DRI) and Estimated Energy Requirement (EER) tables, Health Canada.
