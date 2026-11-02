# foodguide: Canada's Food Guide data on the command line and over MCP

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP](https://img.shields.io/badge/MCP-ModelContextProtocol-green.svg)](https://modelcontextprotocol.io/)

`foodguide` is a command-line tool and an MCP server. It gives you Canada's Food Guide data:

- nutrients for any food in the Canadian Nutrient File (CNF) 2026,
- the 141 Food Guide recipes,
- Dietary Reference Intake (DRI) macronutrient tables,
- Estimated Energy Requirement (EER) equations.

All data sits in local files. At run time the tool makes no network calls. You fetch or build the data once, then work offline.

Version 3.0.0. See [CHANGELOG.md](CHANGELOG.md) for what changed.

![demo](docs/demo.gif)

## Install

The package is not on PyPI. The CLI install is light: typer, httpx, beautifulsoup4, pydantic and requests. It needs Python 3.12 or newer.

From a git tag (the repo has tags `1.0` and `v2.0`; for 3.0.0 use the tag the release publishes, written here as `<tag>`):

```bash
pip install git+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada.git@<tag>
```

From a wheel:

```bash
uv build
pip install path/to/foodguide-3.0.0-py3-none-any.whl
```

From a source checkout:

```bash
uv sync
uv run foodguide version
```

The MCP server needs the `mcp` extra (fastmcp, pandas, uvicorn):

```bash
pip install 'foodguide[mcp] @ git+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada.git@<tag>'
# from a checkout: uv sync --extra mcp
```

Check it:

```console
$ foodguide version
foodguide 3.0.0
```

The examples below use `foodguide`. In a checkout, put `uv run` in front.

## Get the data

Data lives in `~/.local/share/foodguide`. Set `FOODGUIDE_DATA_DIR` to use another directory.

Install the published data. This downloads from the `data-latest` GitHub release over plain HTTPS. It checks every file against `manifest.json` before it writes anything, and unpacks `cnf.sqlite.gz` to `cnf.sqlite`. Files that already match are skipped.

```bash
foodguide data fetch
```

Options: `--tag`, `--repo`, `--from-dir <dir>`, `--dest <dir>`, `--only cnf|recipes|dri|eer`.

Or build the data yourself. Download the CNF 2026 zip from open.canada.ca first (see [docs/data.md](docs/data.md)):

```bash
foodguide data build all --cnf-zip cnf_fcen_all-files-data_2026.zip --out-dir ./data
export FOODGUIDE_DATA_DIR=$PWD/data
```

`data build recipes`, `dri` and `eer` read canada.ca pages, send an identifying User-Agent and wait 1 second between requests. `data build cnf --zip <zip> --no-fetch-metadata` works fully offline. Details are in [docs/data.md](docs/data.md).

## Quick tour

Command groups: `cnf`, `recipes`, `dri`, `eer`, `data`, plus `version`. Add `--help` to any command. Most list commands take `--format table|csv|json`.

### cnf: nutrients for foods

Search matches whole food names (full-text search). A multi-word query such as "red lentils" finds nothing. Search one word.

```console
$ foodguide cnf search lentils --limit 3
2113  Lentils, sprouted, raw  /  Lentilles, germées, crues
3392  Lentils, mature seeds, dry  /  Lentilles, grains mûrs, secs
6183  Lentils, flour  /  Lentilles, farine
```

Other commands: `cnf food <code>`, `cnf measures <code>`, `cnf nutrients <code>`.

```console
$ foodguide cnf measures 3393 | head -4
Measure code  EN            FR                             grams
341           100 ml        100 ml                         83.686
383           125 ml        125 ml                         104.607
389           175 ml        175 ml                         146.45

$ foodguide cnf nutrients 3393 --measure "125 ml" | head -5
Nutrients per 125 ml (104.607 g) — Lentils, mature seeds, boiled
Code  Symbol      Name                                                                             Unit                Amount
 203  PROT        Protein                                                                          Gram                9.43555 Gram
 204  FAT         Fat (total lipids)                                                               Gram                0.397507 Gram
 205  CARB        Carbohydrate, total (by difference)                                              Gram                21.0574 Gram
```

The `--measure` value must be one of the measures listed for that food. If it is not, the command says so and exits with an error.

### recipes: Food Guide recipes

```console
$ foodguide recipes search lentil --limit 3
Braised lentils with greens  braised-lentils-greens     collection__10_ingredients_less, collection__vegetarian, meal__lunch_dinner
Cajun lentil soup            cajun-lentil-soup          collection__10_ingredients_less, collection__freezer_friendly, collection__vegetarian, meal__lunch_dinner
Carrot ginger lentil soup    carrot-ginger-lentil-soup  collection__10_ingredients_less, collection__freezer_friendly, collection__vegetarian, meal__lunch_dinner

$ foodguide recipes filters | head -3
collection__10_ingredients_less  10 ingredients or less
collection__30_minutes_less      30 minutes or less
collection__freezer_friendly     Freezer-friendly

$ foodguide recipes show braised-lentils-greens | head -4
Title: Braised lentils with greens
URL: https://www.canada.ca/en/health-canada/services/food-guide/eating-support/kitchen/recipes/braised-lentils-greens.html
Tags: collection__10_ingredients_less, collection__vegetarian, meal__lunch_dinner
Prep time: 20 min / Cook time: 45 min / Servings: 6
```

### dri: Dietary Reference Intakes

`dri tables` lists macronutrient values per sex and age group. `dri amdr` shows Acceptable Macronutrient Distribution Ranges. `dri lookup` gets one nutrient.

```console
$ foodguide dri tables --age-range "19-30 y" | head -8
Males — 19–30 y
  alpha_linolenic_acid: AI (g/day) 1.6 (AI)
  carbohydrate: EAR (g/day) 100, RDA/AI (g/day) 130
  linoleic_acid: AI (g/day) 17 (AI)
  protein: EAR (g/kg/day) 0.66, RDA/AI (g/day) 56, RDA/AI (g/kg/day) 0.8
  total_fat: no values recorded
  total_fibre: AI (g/day) 38 (AI)
  total_water: AI (L/day) 3.7 (AI)
```

```bash
foodguide dri lookup --age-range "19-30 y" --nutrient protein
foodguide dri amdr --age-range "19 years and over"
```

### eer: energy requirements

`--pal` is one of `inactive`, `low_active`, `active` (default) or `very_active`.

```console
$ foodguide eer calc --sex male --age 30 --weight-kg 70 --height-cm 175 --pal low_active
EER (male, 30 y, 70.0 kg, 175.0 cm, low_active): 2754.9 kcal/day
formula: EER = 581.47 + (-10.83 * age) + (8.30 * height_cm) + (14.94 * weight_kg)
```

`foodguide eer equations` prints every equation.

### data: manage the data files

```console
$ foodguide data status
file                     size_bytes  provenance
dri_macronutrients.json       25360  Health Canada DRI Tables
eer_equations.json            12461  Health Canada DRI Tables
DRI data: <data dir>/dri_macronutrients.json (25734 bytes, source: data_dir)
...
CNF database: <data dir>/cnf.sqlite (38559744 bytes)
  dataset_id: 1b6139bd-ed7e-4043-bc28-ff00e10f3109
```

- `data manifest <dir>` writes `manifest.json` for a data directory.
- `data changed old.json new.json` prints the datasets that differ. It exits 0 when they are equivalent and 10 when not.

## MCP server

The server has 46 tools: recipes, CNF nutrients, DRI, EER, recipe maths, user profiles, sessions and favorites. All of them read the local data files. The full list is in [docs/mcp.md](docs/mcp.md).

Start it (stdio is the default):

```bash
foodguide-mcp
foodguide-mcp --transport http --port 8000   # HTTP, endpoint /mcp
```

Client config for stdio clients (Claude Desktop, Cursor and others):

```json
{
  "mcpServers": {
    "foodguide": { "command": "foodguide-mcp" }
  }
}
```

If the command is not on the client's PATH, give the full path to `foodguide-mcp`. In a checkout use `"command": "uv", "args": ["run", "--directory", "<checkout>", "foodguide-mcp"]`. Set `FOODGUIDE_DATA_DIR` in the client's `env` block if your data is not in the default directory.

## Data sources and licences

- **Canadian Nutrient File 2026**, Health Canada, from open.canada.ca. Licence: [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).
- **Food Guide recipes**, Health Canada (141 recipe pages on canada.ca).
- **DRI tables** (reference values for macronutrients) and **EER equations**, Health Canada.

Source URLs and build steps are in [docs/data.md](docs/data.md). The code is MIT licensed (see [LICENSE](LICENSE)).

## How the data stays fresh

A GitHub Actions workflow ([`.github/workflows/data-refresh.yml`](.github/workflows/data-refresh.yml)) runs every Monday. It runs the live tests (`pytest -m live`), rebuilds all datasets, and compares the new `manifest.json` with the published one using the same logic as `foodguide data changed`. It publishes a new `data-latest` release only when the content changed. Run `foodguide data fetch` to pick it up.

## More

- [docs/data.md](docs/data.md): the four datasets, sources, builds, sizes.
- [docs/mcp.md](docs/mcp.md): MCP server and tool list.
- [CONTRIBUTING.md](CONTRIBUTING.md): development and tests.
- [CHANGELOG.md](CHANGELOG.md): release notes.
- [IMPLEMENTATIONS.MD](IMPLEMENTATIONS.MD): how the code is put together.
