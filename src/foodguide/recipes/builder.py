"""Build the offline recipes.json document from canada.ca recipe pages."""

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from foodguide.recipes.fetch import PoliteFetcher, index_url, recipe_url
from foodguide.recipes.parser import parse_index, parse_recipe


def build_recipes_json(
    out_path,
    fetcher=None,
    index_html=None,
    only: Sequence[str] | None = None,
    max_recipes: int | None = None,
) -> dict:
    """Crawl the index and every recipe page, then write recipes.json.

    Parse failures propagate as ValueError (the message names the slug) so a
    broken page never fails silently.

    Development options (used to work against a partial fixture set):

    - ``only``: crawl exactly these slugs, in index order. Every requested
      slug must exist in the parsed index, otherwise ValueError is raised
      naming the missing slugs. Takes precedence over ``max_recipes``.
    - ``max_recipes``: crawl only the first N slugs in index order; applies
      only when ``only`` is not given.

    The document's ``source`` records ``index_recipe_count`` (number of recipe
    links on the index) while ``recipe_count`` stays the number of recipes
    actually built, and ``index_url`` records the URL the index would have been
    fetched from (or was, when no ``index_html`` was passed).
    """
    fetcher = fetcher if fetcher is not None else PoliteFetcher()
    out_path = Path(out_path)

    fetched_index_url = index_url()
    index = index_html if index_html is not None else fetcher.fetch(fetched_index_url)
    parsed_index = parse_index(index)

    if only is not None:
        requested = list(only)
        index_slugs = set(parsed_index["slugs"])
        missing = [slug for slug in requested if slug not in index_slugs]
        if missing:
            raise ValueError(
                "recipe slug(s) not found in the index: " + ", ".join(missing)
            )
        slugs = requested
    elif max_recipes is not None:
        slugs = parsed_index["slugs"][:max_recipes]
    else:
        slugs = parsed_index["slugs"]

    recipes = []
    for slug in slugs:
        url = recipe_url(slug)
        page = fetcher.fetch(url)
        recipes.append(
            parse_recipe(page, slug, url, parsed_index["tags"].get(slug, []))
        )
    recipes.sort(key=lambda recipe: recipe["slug"])

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = {
        "source": {
            "index_url": fetched_index_url,
            "fetched_at": fetched_at,
            "recipe_count": len(recipes),
            "index_recipe_count": len(parsed_index["slugs"]),
            "index_sha256": hashlib.sha256(index.encode("utf-8")).hexdigest(),
        },
        "filters": dict(sorted(parsed_index["filters"].items())),
        "recipes": recipes,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    return {
        "path": str(out_path),
        "recipe_count": len(recipes),
        "filter_count": len(parsed_index["filters"]),
        "index_sha256": document["source"]["index_sha256"],
        "build_time": fetched_at,
        "size_bytes": out_path.stat().st_size,
    }
