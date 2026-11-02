"""LocalRecipeSource — offline reads of the recipes.json document.

Drop-in replacement for the old live recipe scraper: same ideas as
LocalCNFSource (foodguide.cnf.mcp_source), but every answer comes from the
local recipes.json file built by `foodguide data build recipes`
(see foodguide.recipes.builder). Zero network access.

The document is loaded lazily on first use, so merely constructing the object
without a data file does not fail. The path is resolved at access time so
callers (and tests) can point FOODGUIDE_DATA_DIR wherever they like.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from foodguide.cnf.db import get_data_dir


def recipes_data_path() -> Path:
    """Default location of the offline recipes.json document."""
    return get_data_dir() / "recipes.json"


def _missing_data_error(path: Path) -> RuntimeError:
    return RuntimeError(
        f"Recipes data not found at {path}. "
        "Build it with `foodguide data build recipes`."
    )


class LocalRecipeSource:
    """Recipe data source backed by the offline recipes.json file (read-only)."""

    def __init__(self, path: Path | None = None):
        self._path = Path(path).expanduser() if path is not None else None
        self._data: Optional[dict] = None

    @property
    def path(self) -> Path:
        """Where this source reads recipes.json from."""
        return self._path if self._path is not None else recipes_data_path()

    @property
    def data(self) -> dict:
        """The parsed recipes.json document (loaded on first access)."""
        if self._data is None:
            if not self.path.exists():
                raise _missing_data_error(self.path)
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        return self._data

    def close(self) -> None:
        """No-op, kept for API symmetry with LocalCNFSource."""

    # ── Search ───────────────────────────────────────────────────

    def _resolve_tags(self, requested: list[str]) -> list[str]:
        """Map requested tags onto raw tag values via the filters map.

        Accepts raw tags ("meal__snack") or human labels ("Snack",
        case-insensitive). Raises KeyError for unknown tags (they match
        nothing).
        """
        filters = self.data.get("filters", {})
        label_map = {str(label).lower(): tag for tag, label in filters.items()}
        resolved = []
        for tag in requested:
            if tag in filters:
                resolved.append(tag)
            elif tag.lower() in label_map:
                resolved.append(label_map[tag.lower()])
            else:
                raise KeyError(tag)
        return resolved

    def _text_matches(self, recipe: dict, needle: str) -> bool:
        """True when needle appears in title, intro, an ingredient, or a direction."""
        haystacks = [recipe.get("title") or "", recipe.get("intro") or ""]
        for group in recipe.get("ingredient_groups", []):
            haystacks.extend(group.get("items", []))
        haystacks.extend(recipe.get("directions", []))
        return any(needle in (field or "").lower() for field in haystacks)

    def search(
        self,
        search_text: str = "",
        tags: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Search recipes; tags are AND-ed, search_text is a substring filter.

        Tags may be raw tag values or human labels (case-insensitive); an
        unknown tag simply matches nothing. Results are sorted by
        (title.lower(), slug); limit is applied after sorting (None/<=0 means
        no limit).
        """
        needle = (search_text or "").strip().lower()
        wanted: list[str] | None = None
        if tags:
            try:
                wanted = self._resolve_tags(list(tags))
            except KeyError:
                return []
        results = []
        for recipe in self.data.get("recipes", []):
            if wanted is not None:
                recipe_tags = set(recipe.get("tags", []))
                if not all(tag in recipe_tags for tag in wanted):
                    continue
            if needle and not self._text_matches(recipe, needle):
                continue
            results.append(
                {
                    "title": recipe.get("title") or "",
                    "url": recipe.get("url") or "",
                    "slug": recipe.get("slug") or "",
                    "tags": list(recipe.get("tags", [])),
                }
            )
        results.sort(key=lambda r: (r["title"].lower(), r["slug"]))
        if limit is not None and limit > 0:
            results = results[:limit]
        return results

    # ── Single recipe ────────────────────────────────────────────

    @staticmethod
    def _slug_from_argument(slug_or_url: str) -> str:
        """Accept a bare slug or a recipe URL; always return the bare slug."""
        if "://" in slug_or_url:
            tail = slug_or_url.rstrip("/")
            slug = tail.rsplit("/", 1)[-1]
            if slug.endswith(".html"):
                slug = slug[: -len(".html")]
            return slug
        return slug_or_url.strip()

    def get_recipe(self, slug_or_url: str) -> dict | None:
        """Full record for one recipe by slug or URL, or None if unknown."""
        slug = self._slug_from_argument(slug_or_url)
        for recipe in self.data.get("recipes", []):
            if recipe.get("slug") == slug:
                ingredients = [
                    item
                    for group in recipe.get("ingredient_groups", [])
                    for item in group.get("items", [])
                ]
                return {
                    "slug": recipe.get("slug"),
                    "url": recipe.get("url"),
                    "title": recipe.get("title"),
                    "intro": recipe.get("intro"),
                    "prep_time": recipe.get("prep_time"),
                    "cook_time": recipe.get("cook_time"),
                    "servings": recipe.get("servings"),
                    "ingredients": ingredients,
                    "ingredient_groups": recipe.get("ingredient_groups", []),
                    "directions": list(recipe.get("directions", [])),
                    "tips": list(recipe.get("tips", [])),
                    "tags": list(recipe.get("tags", [])),
                    "source": "Health Canada's Food Guide",
                    "attribution": (
                        "Recipe sourced from Health Canada's Food Guide kitchen (canada.ca)"
                    ),
                }
        return None

    # ── Filters and status ───────────────────────────────────────

    def list_filters(self) -> dict:
        """The filters map (raw tag -> human label), keys sorted."""
        return dict(sorted(self.data.get("filters", {}).items()))

    def status(self) -> dict:
        """Summary of the recipes.json file, or {"built": False} when missing."""
        path = self.path
        if not path.exists():
            return {"built": False}
        source = self.data.get("source", {})
        return {
            "built": True,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "recipe_count": len(self.data.get("recipes", [])),
            "filter_count": len(self.data.get("filters", {})),
            "fetched_at": source.get("fetched_at"),
            "index_sha256": source.get("index_sha256"),
        }
