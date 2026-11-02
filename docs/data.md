# Data

`foodguide` reads four local files. Nothing is fetched at run time. The files live in `~/.local/share/foodguide`, or in the directory named by `FOODGUIDE_DATA_DIR`.

Two ways to get them:

```bash
foodguide data fetch                      # install the published data-latest release
foodguide data build all --cnf-zip <zip> --out-dir <dir>   # build from the sources
```

Check what is installed:

```bash
foodguide data status
```

## manifest.json and verification

`manifest.json` describes every dataset: SHA-256 and size of the file, a content identity, record counts, and upstream identifiers (zip hash, page hash, page date). `data build all` writes it. `data manifest <dir>` writes it for any data directory.

`foodguide data fetch` downloads `manifest.json` first. It checks every asset against it before it writes anything into the data dir. `cnf.sqlite` is published as `cnf.sqlite.gz` and is unpacked on install. Files that already match are skipped.

`foodguide data changed old.json new.json` compares two manifests by content identity (CNF `content_hash`, recipes index hash and count, DRI/EER page hash and date). It ignores build time, package version and gzip bytes. It prints one changed dataset per line, exits 0 when nothing changed and 10 when something did.

## cnf.sqlite

- **Source:** Canadian Nutrient File 2026, Health Canada. Dataset id `1b6139bd-ed7e-4043-bc28-ff00e10f3109` on open.canada.ca (`https://open.canada.ca/data/en/dataset/1b6139bd-ed7e-4043-bc28-ff00e10f3109`).
- **Licence:** Open Government Licence – Canada.
- **Build:** `foodguide data build cnf --zip <cnf zip> [--out <path>]`. It reads the CNF zip (`cnf_fcen_all-files-data_2026.zip`) and writes a SQLite database with a full-text index on food names. `--no-fetch-metadata` skips the metadata request, so the build runs fully offline. `FOODGUIDE_CNF_ZIP` can name the zip. `SOURCE_DATE_EPOCH` fixes the build time.
- **Size:** 38,559,744 bytes (about 38.5 MB). Published gzipped. It holds 5,993 foods, 173 nutrient names and 565,409 nutrient amounts.
- **Used by:** `foodguide cnf search|food|nutrients|measures` and the four CNF tools of the MCP server.

## recipes.json

- **Source:** the Health Canada Food Guide recipe pages on www.canada.ca. The index page is `https://www.canada.ca/en/health-canada/services/food-guide/eating-support/kitchen/recipes.html`.
- **Licence:** Health Canada content. Check the terms on canada.ca before you reuse it.
- **Build:** `foodguide data build recipes [--out <path>]`. It reads the index page and every recipe page, with an identifying User-Agent and a 1 second delay between requests, and writes one JSON file. `FOODGUIDE_SOURCE_BASE_URL` serves the pages from another base. `FOODGUIDE_RECIPES_CACHE_DIR` serves them from an on-disk cache.
- **Size:** 353,348 bytes, 141 recipes.
- **Used by:** `foodguide recipes search|show|filters` and the recipe tools of the MCP server.

## dri_macronutrients.json

- **Source:** Health Canada, Dietary Reference Intakes, reference values for macronutrients: `https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/reference-values-macronutrients.html`.
- **Licence:** Health Canada content.
- **Build:** `foodguide data build dri [--out-dir <dir>]`. It reads that page and writes the tables (EAR, RDA/AI, AMDR and amino acid patterns) with the page hash and date modified as provenance.
- **Size:** 25,734 bytes: DRI reference values by age/sex group, AMDRs, amino acid patterns, footnotes and page provenance.
- **Used by:** `foodguide dri tables|amdr|lookup` and the DRI tools of the MCP server.

## eer_equations.json

- **Source:** Health Canada, equations to estimate energy requirement: `https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/equations-estimate-energy-requirement.html`.
- **Licence:** Health Canada content.
- **Build:** `foodguide data build eer [--out <path>]`. It reads that page and writes the equations by life stage (infants, children, adults, pregnancy, lactation), sex and physical activity level.
- **Size:** 14,966 bytes, 5 life-stage equation groups plus the PAL descriptions.
- **Used by:** `foodguide eer calc|equations` and the EER tools of the MCP server.

## Build everything

```bash
foodguide data build all --cnf-zip cnf_fcen_all-files-data_2026.zip --out-dir ./data
# or let it find and download the CNF zip from the open.canada.ca record:
foodguide data build all --download-cnf --out-dir ./data
```

This builds the four datasets into one directory and then writes `manifest.json`. Point `FOODGUIDE_DATA_DIR` at that directory to use it.

## Freshness

`.github/workflows/data-refresh.yml` runs every Monday. It runs `pytest -m live`, rebuilds the data, compares the manifests with the `data changed` logic and publishes the `data-latest` release only when the content changed.

## Credits

- Canadian Nutrient File 2026, Health Canada. Open Government Licence – Canada.
- Food Guide recipes, Health Canada.
- DRI and EER tables, Health Canada.
