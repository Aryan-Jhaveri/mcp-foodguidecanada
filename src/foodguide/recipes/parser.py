"""Parse Health Canada recipe index and recipe pages (stdlib only, regex-based).

The text normalization in ``_text`` must stay exactly as it is: an independent
answer key was produced with this normalization and any deviation fails the
golden test.
"""

import hashlib
import html
import re

SLUG_RE = r"recipes/([a-z0-9-]+)\.html"


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def parse_index(html_text: str) -> dict:
    """Parse the recipe index page into slugs, per-slug tags, and filter labels."""
    slugs = sorted(set(re.findall(SLUG_RE, html_text)))

    tag_matches = list(re.finditer(r'<div[^>]*data-wb-tags="([^"]+)"[^>]*>', html_text))
    tags: dict[str, list[str]] = {}
    for i, match in enumerate(tag_matches):
        start = match.end()
        end = tag_matches[i + 1].start() if i + 1 < len(tag_matches) else len(html_text)
        slug_match = re.search(SLUG_RE, html_text[start:end])
        if slug_match:
            slug = slug_match.group(1)
            card_tags = match.group(1).split()
            tags.setdefault(slug, []).extend(card_tags)

    filters: dict[str, str] = {}
    for match in re.finditer(
        r'<input[^>]*value="([^"]+)"[^>]*>\s*([^<]+?)\s*</label>', html_text
    ):
        value, label = match.group(1), match.group(2)
        if "__" in value:
            filters[value] = _text(label)

    return {"slugs": slugs, "tags": tags, "filters": filters}


def _stats(html_text: str, label: str) -> str | None:
    match = re.search(
        rf"<strong>{label}</strong>\s*<br\s*/?>(.*?)</div>", html_text, re.S
    )
    if not match:
        return None
    value = _text(match.group(1))
    return value or None


def _ingredient_groups(block: str, slug: str) -> list[dict]:
    groups: list[dict] = []
    ul_matches = list(re.finditer(r"<ul[^>]*>(.*?)</ul>", block, re.S))
    previous_end = 0
    for ul in ul_matches:
        heading_chunk = block[previous_end : ul.start()]
        heading = _text(heading_chunk) or None
        items = [_text(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", ul.group(1), re.S)]
        groups.append({"group": heading, "items": items})
        previous_end = ul.end()
    total = sum(len(g["items"]) for g in groups)
    if total == 0:
        raise ValueError(f"{slug}: no ingredients parsed")
    return groups


def parse_recipe(html_text: str, slug: str, url: str, tags: list[str]) -> dict:
    """Parse one recipe page into a plain dict ready for recipes.json."""
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.S)
    if not h1_match:
        raise ValueError(f"{slug}: no <h1> title found")
    title = _text(h1_match.group(1))

    intro_match = re.search(r"<p[^>]*>(.*?)</p>", html_text[h1_match.end() :], re.S)
    intro = _text(intro_match.group(1)) or None if intro_match else None

    prep_time = _stats(html_text, "Prep time")
    cook_time = _stats(html_text, "Cook time")
    servings = _stats(html_text, "Servings")

    block_match = re.search(
        r"<h2[^>]*>Ingredients</h2>(.*?)<h2[^>]*>Directions</h2>", html_text, re.S
    )
    if not block_match:
        raise ValueError(f"{slug}: no Ingredients/Directions section found")
    ingredient_groups = _ingredient_groups(block_match.group(1), slug)

    directions_match = re.search(r"<h2[^>]*>Directions</h2>(.*?)(?=<h2\b|$)", html_text, re.S)
    if not directions_match:
        raise ValueError(f"{slug}: no Directions section found")
    directions_block = directions_match.group(1)
    # Most pages have one <ol> right after the heading, but a few have a <p>
    # sub-heading (e.g. "Prepare marinated eggs:") between the heading and the
    # <ol>, or several <ol> blocks; collect the steps of every <ol> in order.
    directions = [
        _text(li)
        for ol_block in re.findall(r"<ol[^>]*>(.*?)</ol>", directions_block, re.S)
        for li in re.findall(r"<li[^>]*>(.*?)</li>", ol_block, re.S)
    ]
    if not directions:
        raise ValueError(f"{slug}: no directions parsed")

    tips: list[str] = []
    tips_match = re.search(r"<h2[^>]*>Tips</h2>", html_text)
    if tips_match:
        after_tips = html_text[tips_match.end() :]
        next_h2 = re.search(r"<h2[^>]*>", after_tips)
        scope = after_tips[: next_h2.start()] if next_h2 else after_tips
        tips_ul = re.search(r"<ul[^>]*>(.*?)</ul>", scope, re.S)
        if tips_ul:
            tips = [
                _text(li)
                for li in re.findall(r"<li[^>]*>(.*?)</li>", tips_ul.group(1), re.S)
            ]

    return {
        "slug": slug,
        "url": url,
        "title": title,
        "intro": intro,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "servings": servings,
        "ingredient_groups": ingredient_groups,
        "directions": directions,
        "tips": tips,
        "tags": list(tags),
        "page_sha256": hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
    }
