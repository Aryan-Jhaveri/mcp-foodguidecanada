# MCP server

`foodguide-mcp` serves Canada's Food Guide data to MCP clients. It has 46 tools. Every tool reads the local data files (see [data.md](data.md)). No tool fetches anything from the web when you call it. Get the data first with `foodguide data fetch`.

## Install

The server needs the `mcp` extra (fastmcp, pandas, uvicorn):

```bash
pip install 'foodguidecanada[mcp]'
# or: uv tool install 'foodguidecanada[mcp]'
# from a source checkout: uv sync --extra mcp
```

Or install from Git, pinned to a release tag:

```bash
pip install 'foodguidecanada[mcp] @ git+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada.git@v3.0.0'
```

## Changes from 2.0

The recipe tools changed shape when the data went offline. `search_recipes` takes `limit` instead of
`max_pages` and returns `{recipes, count, filters_applied, filters_ignored, ...}`. The fruit, vegetable,
protein, whole-grain and appliance filters are gone (the new canada.ca pages have only meal and
collection tags); they come back in `filters_ignored`. `get_recipe` takes `url_or_slug`.
`list_filters` returns `{group: {tag: label}}`. CNF tools read the local database, so install the data
first (`foodguide data fetch`). See the CHANGELOG for the full list.

## Start

stdio is the default:

```bash
foodguide-mcp
```

Options: `--transport stdio|http` (env `MCP_TRANSPORT`), `--host` (env `HOST`, default `127.0.0.1`), `--port` (env `PORT`, default 8000). The HTTP transport serves `/mcp`:

```bash
foodguide-mcp --transport http --host 127.0.0.1 --port 8000
```

The HTTP transport registers 24 of the 46 tools. The tools that need the session database (favorites, temporary and virtual sessions, recipe analysis tables, user profiles) exist on stdio only. HTTP has no authentication. Bind it to `127.0.0.1` unless you put something in front of it.

## Client config (stdio)

```json
{
  "mcpServers": {
    "foodguide": { "command": "foodguide-mcp" }
  }
}
```

If the command is not on the client's PATH, use the full path. From a source checkout: `"command": "uv", "args": ["run", "--directory", "<checkout>", "foodguide-mcp"]`.

## Environment

| Variable | Meaning | Default |
|---|---|---|
| `FOODGUIDE_DATA_DIR` | Folder with `cnf.sqlite`, `recipes.json`, `dri_macronutrients.json`, `eer_equations.json` | `~/.local/share/foodguide` |
| `FOODGUIDE_STATE_DIR` | Folder for the state database | `~/.local/state/foodguide` |
| `FOODGUIDE_DB_FILE` | State database file (profiles, favorites, temp sessions, recipe analysis tables) | `<state dir>/foodguide_data.db` |
| `FOODGUIDE_LOG_LEVEL` | Log level | `CRITICAL` |

The reference data is read-only. The state database holds what you create through the tools. Virtual sessions live in memory and end with the server process.

Set variables in the client config with an `env` block:

```json
{
  "mcpServers": {
    "foodguide": { "command": "foodguide-mcp", "env": { "FOODGUIDE_DATA_DIR": "<your data dir>" } }
  }
}
```

## Serving it to others

The HTTP transport lets people use the server from their own chat clients. It has no authentication, so treat it like any service on a public address: run it in a container, bind it to loopback, and put TLS and a token in front.

### Docker

The repo has a `Dockerfile` and a `docker-compose.yml`. The image bakes the datasets in at build time (it runs `foodguide data fetch` once), so the running container needs no network.

```bash
docker compose up -d --build        # endpoint on 127.0.0.1:8000/mcp
docker build --build-arg DATA_TAG=data-latest -t foodguide-mcp .   # or build by hand
```

Released versions are also published to `ghcr.io/aryan-jhaveri/mcp-foodguidecanada` (tags `3.0.0` and `latest`).

What the container setup does, and why:

- **Pinned base image** (by digest), so a rebuild gives the same image.
- **Non-root user, read-only root filesystem, no capabilities, `no-new-privileges`.** HTTP mode has no session database, so it writes nothing. Only `/tmp` is writable.
- **Memory limit** of 512 MB.
- **Published on `127.0.0.1` only.** Anything public goes through a reverse proxy.
- **No network at run time.** The data is fixed when the image is built. To pick up new data, rebuild or pull a newer image. The weekly Data refresh workflow publishes new datasets, so rebuilding monthly is enough for most uses.
- **Health check** on `/mcp/`.

### Reverse proxy with a token

Terminate TLS and check a bearer token before the request reaches the server. Example for nginx (put the real token in a secret, not in the file you commit):

```nginx
location /mcp {
    if ($http_authorization != "Bearer CHANGE-ME") { return 401; }
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_buffering off;               # MCP streams responses
}
```

Check how each client sends headers. Some clients can send an `Authorization` header, others only support a URL. Add rate limits at the proxy.

### If you publish a public server

- Credit the data sources and licences (see [data.md](data.md)). The recipes are Crown copyright.
- Say plainly that the numbers are reference values, not medical advice.
- The server has 24 tools in this mode: lookups and calculations, with no per-user storage.

## Tools (46)

The text after each name comes from the first line of the tool's own description (the warning mark on `create_temp_nutrition_session` is dropped).

### Recipes (3)

- `search_recipes`: Search Health Canada's Food Guide recipes from a local offline copy.
- `get_recipe`: Retrieve the complete details of one Food Guide recipe, offline.
- `list_filters`: List the recipe search filters available in the local snapshot.

### CNF nutrients (4)

- `search_and_get_cnf_macronutrients`: Search Canadian Nutrient File foods and retrieve core macronutrient data.
- `get_cnf_macronutrients_only`: Retrieve core macronutrients for a specific CNF food code with automatic ingredient linking.
- `bulk_get_cnf_macronutrients`: Process multiple CNF food codes efficiently with automatic ingredient linking for streamlined recipe nutrition analysis.
- `get_cnf_nutrient_profile`: Retrieve complete nutrient profile with all available nutrients for research-grade analysis.

### DRI (9)

- `get_macronutrient_dri_tables`: Get complete DRI macronutrient reference tables from Health Canada.
- `get_specific_macronutrient_dri`: Get DRI values for a specific macronutrient, age group, and gender.
- `get_amdrs`: Get Acceptable Macronutrient Distribution Ranges (AMDRs) for an age group.
- `get_amino_acid_patterns`: Get amino acid patterns for protein quality evaluation using PDCAAS method.
- `compare_intake_to_dri`: Compare actual macronutrient intake against DRI recommendations.
- `store_dri_tables_in_session`: Cache complete DRI macronutrient tables in virtual session storage.
- `get_dri_lookup_from_session`: Retrieve specific DRI values from session-cached data.
- `calculate_dri_from_eer`: Calculate specific macronutrient targets based on EER energy requirements and AMDR ranges.
- `list_session_dri_analysis`: View all DRI calculations and analysis stored in a virtual session.

### EER (2)

- `get_eer_equations`: Get specific EER equations from Health Canada DRI tables in JSON format.
- `get_pal_descriptions`: Get descriptions and examples for Physical Activity Level (PAL) categories.

### Maths and recipe scaling (6)

- `simple_math_calculator`: Perform simple mathematical calculations with string variables.
- `bulk_math_calculator`: Perform multiple mathematical calculations in a single operation.
- `scale_recipe_servings`: Scale all ingredients in a recipe to match a target number of servings.
- `scale_individual_ingredient`: Scale a specific ingredient amount by a custom multiplication factor.
- `scale_multiple_ingredients`: Scale multiple ingredients with different factors in a single operation.
- `compare_recipe_servings`: Compare multiple recipes by servings, ingredients, or portion analysis.

### User profiles (4)

- `create_user_profile`: Create a user profile for EER calculations with optional persistent storage.
- `get_user_profile`: Retrieve a user profile by ID from virtual or persistent storage.
- `list_user_profiles`: List all available user profiles from both virtual and persistent storage.
- `delete_user_profile`: Delete a user profile from virtual or persistent storage.

### Sessions and favorites (13)

- `create_virtual_recipe_session`: Create virtual in-memory storage for a recipe session to store fetched recipe data.
- `cleanup_virtual_session`: Remove virtual in-memory storage for a completed recipe session.
- `list_active_virtual_sessions`: List all active recipe sessions currently stored in memory.
- `create_temp_nutrition_session`: Create a temporary nutrition session. Check for existing sessions first.
- `store_recipe_in_temp_tables`: Store recipe data in temporary SQLite tables instead of virtual memory.
- `get_temp_session_recipes`: Retrieve recipes from temporary persistent storage.
- `cleanup_temp_sessions`: Clean up temporary session data - can target specific session or clean all sessions.
- `list_temp_sessions`: List all active temporary nutrition sessions.
- `store_recipe_in_session`: Store a fetched recipe in virtual memory session for detailed analysis and manipulation.
- `get_session_recipes`: Retrieve stored recipes from a virtual session with complete normalized data including ingredients and instructions.
- `add_to_favorites`: Add a recipe to user favorites for persistent storage across sessions.
- `remove_from_favorites`: Remove a recipe from user favorites permanently.
- `list_favorites`: List user's favorite recipes from persistent storage.

### Database and recipe analysis (5)

- `initialize_database`: Initialize the Canada's Food Guide recipe database with required tables.
- `simple_recipe_setup`: Transfer recipe data to analysis tables with comprehensive ingredient parsing for streamlined nutrition analysis preparation.
- `calculate_recipe_nutrition_summary`: Analyze unit matching for recipe ingredients and populate temp_recipe_macros table.
- `query_recipe_macros_table`: Query temp_recipe_macros table with joined CNF nutrition data for recipe calculations.
- `update_recipe_macros_decisions`: Update temp_recipe_macros table with LLM conversion decisions and reasoning.
