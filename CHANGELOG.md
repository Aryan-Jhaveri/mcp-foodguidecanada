# Changelog

## 3.0.0 (2026-11-02)

A rewrite around an installable package and offline data. The old `v2.0` was the MCP server alone.

- **Package:** published as `foodguidecanada` (import name and commands stay `foodguide`): a typer CLI
  (`foodguide`) and the MCP server (`foodguide-mcp`, install with the `mcp` extra). The CLI install is light (no pandas, no fastmcp).
- **Offline data, no network at run time:** Canadian Nutrient File 2026 as SQLite (EN/FR full-text search),
  the Food Guide recipes (141, from the new canada.ca pages), Health Canada DRI and EER tables.
- **CLI:** `cnf`, `recipes`, `dri`, `eer`, `data` (build, status, fetch, manifest, changed).
- **Data pipeline:** `foodguide data build all` plus a weekly GitHub Actions workflow that rebuilds the
  datasets and publishes them to the `data-latest` release only when the content changed.
- **MCP fixes:** state folder is created, session tables are created at startup, `list_filters` validates,
  recipe tools work again against the local data.
- **Tests:** no mocks. Real saved pages, local servers and real subprocesses; golden answer keys made by a
  separate script.
- **Breaking changes for MCP clients (recipes):**
  - `search_recipes`: `max_pages` is replaced by `limit` (default 20); it returns an object
    `{recipes, count, filters_applied, filters_ignored, ...}` instead of a list.
  - `fruits`, `vegetables`, `proteins`, `whole_grains` and `appliances` filters no longer exist on the
    new canada.ca pages; they are reported in `filters_ignored`. Use `search_text`, `meals` and
    `collections`.
  - `get_recipe`: the `url` argument is now `url_or_slug` (a slug or a canada.ca recipe URL).
  - `list_filters` returns `{group: {tag: label}}`.
  - CNF tools read the local SQLite database. Run `foodguide data fetch` (or `data build cnf`) first.
- **Security default:** the MCP HTTP transport now listens on `127.0.0.1` (it was `0.0.0.0` with no
  authentication). Use `--host` or `HOST` to expose it deliberately.
- **Docker:** a `Dockerfile` and `docker-compose.yml` for the HTTP MCP server (pinned base image, non-root,
  read-only, data baked in), and images published to GHCR on release.
- **Removed:** the live scrapers of the old `food-guide.canada.ca` host and `uv.lock`.
