"""MCP recipe tools backed by the offline recipes.json document (HOM-79).

The old live scraper is gone: every answer comes from the local recipes.json
file built by `foodguide data build recipes` (see foodguide.recipes.source
and foodguide.recipes.builder). Zero network access at query time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from foodguide.cnf.db import get_data_dir
from foodguide.recipes.source import LocalRecipeSource

SOURCE_NAME = "Health Canada's Food Guide"
DATA_PROVENANCE = "local recipes.json (offline)"

# One shared source per server process; the underlying document is loaded
# lazily and cached, so a missing file only fails when a tool actually runs.
# The singleton remembers which data dir it was created under (get_data_dir()
# honours FOODGUIDE_DATA_DIR) and is recreated whenever that dir changes: tests
# point FOODGUIDE_DATA_DIR wherever they like with monkeypatch.setenv and
# always get a source that reads that dir — no attribute resets needed.
_source: LocalRecipeSource | None = None
_source_data_dir: str | None = None


def _get_source() -> LocalRecipeSource:
    """Return the shared LocalRecipeSource for the current FOODGUIDE_DATA_DIR.

    The environment is read on every call; when the data dir differs from the
    one the cached source was created under, a fresh source is built for the
    new dir. Keeps tests to ``setenv`` only — no attribute patching or manual
    singleton resets.
    """
    global _source, _source_data_dir
    data_dir = str(get_data_dir())
    if _source is None or _source_data_dir != data_dir:
        _source = LocalRecipeSource()
        _source_data_dir = data_dir
    return _source


def _resolve_filter_values(
    values: List[str], prefix: Optional[str], filters_map: dict
) -> tuple[list[str], list[str]]:
    """Map user filter values onto raw tags via the filters map.

    Accepts raw tags ("meal__snack"), prefixed short forms ("snack" with
    prefix "meal__"), or human labels ("Snack", case-insensitive). Returns
    (resolved_raw_tags, unrecognized_values).
    """
    label_map = {str(label).lower(): tag for tag, label in filters_map.items()}
    resolved: list[str] = []
    ignored: list[str] = []
    for value in values:
        if value in filters_map:
            resolved.append(value)
        elif prefix is not None and prefix + value in filters_map:
            resolved.append(prefix + value)
        elif value.lower() in label_map:
            resolved.append(label_map[value.lower()])
        else:
            ignored.append(value)
    return resolved, ignored


def _filter_family(filters_map: dict, prefix: str) -> dict:
    """The subset of the filters map whose tags carry the given prefix."""
    return {tag: label for tag, label in filters_map.items() if tag.startswith(prefix)}


def register_recipe_tools(mcp: FastMCP):
    """Register the offline recipe tools with the MCP server."""

    @mcp.tool()
    def search_recipes(
        search_text: str = "",
        fruits: Optional[List[str]] = None,
        vegetables: Optional[List[str]] = None,
        proteins: Optional[List[str]] = None,
        whole_grains: Optional[List[str]] = None,
        meals: Optional[List[str]] = None,
        appliances: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Search Health Canada's Food Guide recipes from a local offline copy.

        The search runs against recipes.json, an offline snapshot of
        Health Canada's Food Guide kitchen recipe pages built with
        `foodguide data build recipes`. Each recipe is government-verified,
        nutrition-focused content designed to help Canadians eat well.

        Each result includes title, url, slug and the recipe's raw tags.

        Args:
            search_text: Free-text search across recipe titles, intros,
                ingredients and directions (e.g. "lentil", "apple crisp").
                Empty matches everything.
            fruits: No longer supported: the new canada.ca recipe pages have
                no fruit tags. Values are returned in "filters_ignored"; use
                search_text instead (e.g. search_text="apple").
            vegetables: No longer supported: no vegetable tags exist on the
                new recipe pages; use search_text instead.
            proteins: No longer supported: no protein tags exist on the new
                recipe pages; use search_text instead.
            whole_grains: No longer supported: no whole-grain tags exist on
                the new recipe pages; use search_text instead.
            meals: Filter by meal tags (e.g. ["breakfast", "snack"]). Values
                may be raw tags ("meal__snack") or human labels ("Snack");
                see list_filters.
            appliances: No longer supported: no appliance tags exist on the
                new recipe pages; use search_text instead.
            collections: Filter by collection tags (e.g. ["vegetarian"]).
                Values may be raw tags ("collection__vegetarian") or human
                labels ("Vegetarian"); see list_filters.
            limit: Maximum number of results to return (default: 20); there
                is no pagination offline, so raise this to see more. A value
                of 0 or less means no limit.

        Returns:
            Dict with "recipes" (list of {title, url, slug, tags}), "count",
            "filters_applied", "filters_ignored", "source" and "data". If the
            local data file has not been built yet, returns {"error": ...}
            telling you to run `foodguide data build recipes`.

        Source: Health Canada's Food Guide (local recipes.json, offline).
        """
        try:
            source = _get_source()
            filters_map = source.list_filters()
            meals_resolved, meals_ignored = _resolve_filter_values(
                list(meals or []), "meal__", filters_map
            )
            collections_resolved, collections_ignored = _resolve_filter_values(
                list(collections or []), "collection__", filters_map
            )
            retired: list[str] = []
            for values in (fruits, vegetables, proteins, whole_grains, appliances):
                retired.extend(values or [])
            tags = meals_resolved + collections_resolved
            results = source.search(
                search_text=search_text, tags=tags or None, limit=limit
            )
        except RuntimeError as exc:
            return {"error": str(exc)}
        return {
            "recipes": results,
            "count": len(results),
            "filters_applied": tags,
            "filters_ignored": retired + meals_ignored + collections_ignored,
            "source": SOURCE_NAME,
            "data": DATA_PROVENANCE,
        }

    @mcp.tool()
    def get_recipe(url_or_slug: str) -> Dict[str, Any]:
        """Retrieve the complete details of one Food Guide recipe, offline.

        Everything comes from the local recipes.json snapshot built with
        `foodguide data build recipes`; no page is fetched.

        Args:
            url_or_slug: A bare recipe slug ("apple-berry-crisp") or a recipe
                URL. Both the current canada.ca form
                (https://www.canada.ca/.../recipes/<slug>.html) and the old
                https://food-guide.canada.ca/en/recipes/<slug>/ form are
                accepted; the slug is extracted automatically.

        Returns:
            Dict with slug, url, title, intro, prep_time, cook_time,
            servings, ingredients (flattened across groups, in order),
            ingredient_groups, directions, tips, tags, plus "source" and
            "attribution". Unknown slugs return {"error": ...}.

        Source: Health Canada's Food Guide (local recipes.json, offline).
        """
        if not url_or_slug or not url_or_slug.strip():
            return {"error": "Provide a recipe slug or a canada.ca recipe URL."}
        try:
            recipe = _get_source().get_recipe(url_or_slug)
        except RuntimeError as exc:
            return {"error": str(exc)}
        if recipe is None:
            return {
                "error": (
                    f"Recipe '{url_or_slug}' not found in local data. "
                    "Run `foodguide data build recipes` to refresh."
                )
            }
        return recipe

    @mcp.tool()
    def list_filters(filter_type: Optional[str] = None) -> Dict[str, Any]:
        """List the recipe search filters available in the local snapshot.

        The new canada.ca recipe pages only tag two families:
        "collection__*" (e.g. collection__vegetarian) and "meal__*"
        (e.g. meal__snack). Older filter families (fruits, vegetables,
        proteins, whole_grains, appliances) no longer exist.

        Args:
            filter_type: Optional family to list: "collection"/"collections"
                or "meal"/"meals". Omit to list both families.

        Returns:
            Dict mapping family names to {raw_tag: human label} maps, plus
            "source" and "data". Invalid families return
            {"error": "Invalid filter type: <x>"}.
        """
        try:
            filters_map = _get_source().list_filters()
        except RuntimeError as exc:
            return {"error": str(exc)}
        if filter_type in ("collection", "collections"):
            payload: Dict[str, Any] = {
                "collection": _filter_family(filters_map, "collection__")
            }
        elif filter_type in ("meal", "meals"):
            payload = {"meal": _filter_family(filters_map, "meal__")}
        elif filter_type is None:
            payload = {
                "collection": _filter_family(filters_map, "collection__"),
                "meal": _filter_family(filters_map, "meal__"),
            }
        else:
            payload = {"error": f"Invalid filter type: {filter_type}"}
        payload["source"] = SOURCE_NAME
        payload["data"] = DATA_PROVENANCE
        return payload
