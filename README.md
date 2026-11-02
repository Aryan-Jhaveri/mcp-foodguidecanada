# 🍲 Canada's Food Guide: CLI and MCP server

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP](https://img.shields.io/badge/MCP-ModelContextProtocol-green.svg)](https://modelcontextprotocol.io/)

![foodguide demo](docs/demo.gif)

`foodguide` is a command-line tool and an MCP server. It gives you Canada's Food Guide data:

- nutrients for any food in the Canadian Nutrient File (CNF) 2026,
- the 141 Food Guide recipes,
- Dietary Reference Intake (DRI) macronutrient tables,
- Estimated Energy Requirement (EER) equations.

All data sits in local files. At run time the tool makes no network calls. You fetch or build the data once, then work offline.

Version 3.0.0. See [CHANGELOG.md](CHANGELOG.md) for what changed.

## See it in action

Watch the [trailer on YouTube](https://youtu.be/CjWSxeWg-O0). Each example below jumps to its part of the video.

| Example | Video |
| ------------- | ------------- |
| Find themed recipes for a week | <a href="https://youtu.be/CjWSxeWg-O0?t=223" target="_blank">![themed-recipe-spedup](https://github.com/user-attachments/assets/284795c7-17df-4715-a7b2-98a7c6b1241a)</a> |
| Suggest recipes from an image of your groceries | <a href="https://youtu.be/CjWSxeWg-O0?t=307" target="_blank">![from-image-to-show-recipes-spedup](https://github.com/user-attachments/assets/75bc1976-2a3c-4b5e-b1cd-45006b190b5b)</a> |
| Calculate your estimated macros intake and energy requirements | <a href="https://youtu.be/CjWSxeWg-O0?t=40" target="_blank">![calculate-eer-spedup](https://github.com/user-attachments/assets/ba30be42-e4d0-4d86-a379-35fe51cdeb40)</a> |
| Calculate macros for a recipe | <a href="https://youtu.be/CjWSxeWg-O0?t=116" target="_blank">![calculate-macros-spedup](https://github.com/user-attachments/assets/c7912d00-773f-4781-959b-56d0b8d86727)</a> |

The trailer was recorded with version 2.0, which fetched recipes and nutrients from the Health Canada websites while you chatted. Version 3.0 reads the same data from local files, so the answers come back faster and work offline. A few recipe tool arguments changed (see [docs/mcp.md](docs/mcp.md)).

You can use this [Google Sheet](https://docs.google.com/spreadsheets/d/1TELVtKLN35yxGFC10751WnByRtpWndYPjC4WKWw4Cgo/edit?usp=sharing) to check the EER and CNF calculations shown in the trailer.

## Install

The PyPI package is named `foodguidecanada`. The import package and the commands are `foodguide` and `foodguide-mcp`. It needs Python 3.12 or newer.

From PyPI:

```bash
pip install foodguidecanada             # light CLI install (typer, httpx, beautifulsoup4, pydantic, requests)
pip install 'foodguidecanada[mcp]'      # adds the MCP server (fastmcp, pandas, uvicorn)
uv tool install foodguidecanada         # or install the CLI as a uv tool
```

Or straight from Git, pinned to a release tag:

```bash
pip install git+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada.git@v3.0.0
pip install 'foodguidecanada[mcp] @ git+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada.git@v3.0.0'
```

From a wheel you built yourself:

```bash
uv build
pip install dist/foodguidecanada-3.0.0-py3-none-any.whl
```

From a source checkout:

```bash
uv sync                  # add --extra mcp for the MCP server
uv run foodguide version
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
  carbohydrate: EAR (g/day) 100, RDA/AI (g/day) 130
  protein: EAR (g/kg/day) 0.66, RDA/AI (g/kg/day) 0.8, RDA/AI (g/day) 56
  total_fat: no values recorded
  linoleic_acid: AI (g/day) 17 (AI)
  alpha_linolenic_acid: AI (g/day) 1.6 (AI)
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

`data status` shows where each dataset is read from, its size, and its provenance. It reads the bundled DRI and EER files when the data folder has none.

```console
$ foodguide data status | head -8
file                     size_bytes  provenance
dri_macronutrients.json       25360  Health Canada DRI Tables
eer_equations.json            12461  Health Canada DRI Tables
DRI data: foodguide/data/dri_macronutrients.json (25360 bytes, source: bundled_snapshot)
  provenance: -
EER data: foodguide/data/eer_equations.json (12461 bytes, source: bundled_snapshot)
  provenance: -
CNF database: /home/you/.local/share/foodguide/cnf.sqlite (38559744 bytes)
```

- `data manifest <dir>` writes `manifest.json` for a data directory. It needs DRI and EER files that carry build provenance, so run it on a directory made by `data build`, not on the bundled files.
- `data changed old.json new.json` prints the datasets that differ. It exits 0 when they are equivalent and 10 when not.

## MCP server

`foodguide-mcp` serves the same data to AI clients such as Claude Desktop, Claude Code, Cursor and VS Code. Install it with the `mcp` extra (`pip install 'foodguidecanada[mcp]'`), and get the data first (see [Get the data](#get-the-data)).

| Mode | Tools | Session database | Best for |
|---|---|---|---|
| **stdio** (default) | 46 | yes | Most users: recipe search, nutrients, EER and DRI, recipe macros, favourites, profiles |
| **HTTP** | 24 | no | A shared or remote server: lookups and calculations only |

The tools are listed in [docs/mcp.md](docs/mcp.md).

### Set up by client

**Claude Desktop**: Settings (⌘,) → Developer → Edit Config, then restart the app.

```json
{
  "mcpServers": {
    "foodguide": { "command": "foodguide-mcp" }
  }
}
```

**Claude Code**

```bash
claude mcp add foodguide -- foodguide-mcp
```

**Cursor**: `.cursor/mcp.json` in a project, or `~/.cursor/mcp.json` for all projects.

```json
{
  "mcpServers": {
    "foodguide": { "command": "foodguide-mcp" }
  }
}
```

**VS Code (GitHub Copilot)**: `.vscode/mcp.json`

```json
{
  "servers": {
    "foodguide": { "type": "stdio", "command": "foodguide-mcp" }
  }
}
```

If the client cannot find `foodguide-mcp`, give the full path (`which foodguide-mcp`). From a source checkout use `"command": "uv", "args": ["run", "--directory", "/path/to/checkout", "foodguide-mcp"]`. Set `FOODGUIDE_DATA_DIR` in the client's `env` if the data is not in the default folder.

### HTTP mode

Start the server in its own terminal and leave it running:

```bash
foodguide-mcp --transport http --port 8000      # endpoint: http://127.0.0.1:8000/mcp
```

It listens on `127.0.0.1` only and has no authentication. Do not expose it without something in front of it (`--host` or `HOST` changes the address).

```bash
claude mcp add foodguide --transport http http://127.0.0.1:8000/mcp     # Claude Code
```

Claude Desktop and most other clients bridge stdio to HTTP with [`mcp-proxy`](https://github.com/sparfenyuk/mcp-proxy):

```json
{
  "mcpServers": {
    "foodguide": {
      "command": "uvx",
      "args": ["mcp-proxy", "--transport", "streamablehttp", "http://127.0.0.1:8000/mcp"]
    }
  }
}
```

Environment variables instead of flags: `MCP_TRANSPORT=http PORT=8000 foodguide-mcp`.

To serve it to other people, use the Docker image and put TLS and a token in front: see [Serving it to others](docs/mcp.md#serving-it-to-others).

### Troubleshooting

- The server does not appear in the client: check the client's logs (for Claude Desktop, the MCP log files) and run `foodguide-mcp` in a terminal to see the error.
- "needs the MCP extra": install `foodguidecanada[mcp]`.
- Tools answer "no data": run `foodguide data fetch` and check `foodguide data status`.
- HTTP mode: check that the server is up with `curl http://127.0.0.1:8000/mcp/`. If the port is taken (Anki's AnkiConnect uses 8765), pick another with `--port`.

## Data sources and licences

- **Canadian Nutrient File 2026**, Health Canada, from open.canada.ca. Licence: [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).
- **Food Guide recipes**, Crown copyright, Health Canada (141 recipe pages on canada.ca).
- **DRI tables** (reference values for macronutrients) and **EER equations**, Health Canada (canada.ca pages, dated 2025-11-19).

Source URLs and build steps are in [docs/data.md](docs/data.md). The code is MIT licensed (see [LICENSE](LICENSE)).

## How the data stays fresh

A GitHub Actions workflow ([`.github/workflows/data-refresh.yml`](.github/workflows/data-refresh.yml)) runs every Monday. It runs the live tests (`pytest -m live`), rebuilds all datasets, and compares the new `manifest.json` with the published one using the same logic as `foodguide data changed`. It publishes a new `data-latest` release only when the content changed. Run `foodguide data fetch` to pick it up.

## More

- [docs/data.md](docs/data.md): the four datasets, sources, builds, sizes.
- [docs/mcp.md](docs/mcp.md): MCP server and tool list.
- [CONTRIBUTING.md](CONTRIBUTING.md): development and tests.
- [docs/RELEASING.md](docs/RELEASING.md): how a release is cut.
- [CHANGELOG.md](CHANGELOG.md): release notes.
- [IMPLEMENTATIONS.MD](IMPLEMENTATIONS.MD): how the code is put together.

---

<div align="center">
<p>Made with ❤️ for Canada's Food Guide</p>
<p><a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide</a> ·
<a href="https://food-nutrition.canada.ca/cnf-fce/?lang=eng" target="_blank">Canadian Nutrient File</a> ·
<a href="https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables.html" target="_blank">Dietary Reference Intakes</a></p>
<p>Built with <a href="https://github.com/jlowin/fastmcp" target="_blank">FastMCP</a></p>
</div>
