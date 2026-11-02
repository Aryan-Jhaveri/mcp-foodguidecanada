"""Build the offline recipes.json document from canada.ca recipe pages."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from foodguide.recipes.fetch import INDEX_URL, PoliteFetcher, recipe_url
from foodguide.recipes.parser import parse_index, parse_recipe


def build_recipes_json(out_path, fetcher=None, index_html=None) -> dict:
    """Crawl the index and every recipe page, then write recipes.json.

    Parse failures propagate as ValueError (the message names the slug) so a
    broken page never fails silently.
    """
    fetcher = fetcher if fetcher is not None else PoliteFetcher()
    out_path = Path(out_path)

    index = index_html if index_html is not None else fetcher.fetch(INDEX_URL)
    parsed_index = parse_index(index)

    recipes = []
    for slug in parsed_index["slugs"]:
        url = recipe_url(slug)
        page = fetcher.fetch(url)
        recipes.append(
            parse_recipe(page, slug, url, parsed_index["tags"].get(slug, []))
        )
    recipes.sort(key=lambda recipe: recipe["slug"])

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = {
        "source": {
            "index_url": INDEX_URL,
            "fetched_at": fetched_at,
            "recipe_count": len(recipes),
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
