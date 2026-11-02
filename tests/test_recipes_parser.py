"""Tests for the recipes crawler/parser (fixtures + one real-page integration test)."""

import hashlib
import html.parser
import os
import re
from pathlib import Path

import pytest

from foodguide.recipes.parser import parse_index, parse_recipe

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_html"
REAL_CACHE = Path(
    os.environ.get("FOODGUIDE_TEST_RECIPE_CACHE")
    or "/srv/agent/work/foodguide-tasks/data/recipes_cache"
)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_index_fixture():
    parsed = parse_index(_read("index.html"))

    assert parsed["slugs"] == ["test-berry-crisp", "test-fruit-salad", "test-oat-bowl"]
    assert parsed["tags"] == {
        "test-berry-crisp": ["collection__vegetarian", "meal__snack"],
        "test-oat-bowl": ["meal__breakfast"],
        "test-fruit-salad": ["collection__30_minutes_less", "collection__no_cook"],
    }
    assert parsed["filters"] == {
        "collection__vegetarian": "Vegetarian",
        "meal__breakfast": "Breakfast",
        "meal__snack": "Snack",
    }


def test_parse_recipe_two_groups():
    html_text = _read("two-groups.html")
    recipe = parse_recipe(
        html_text,
        "test-berry-crisp",
        "https://www.canada.ca/en/health-canada/services/food-guide/eating-support"
        "/kitchen/recipes/test-berry-crisp.html",
        ["collection__vegetarian", "meal__snack"],
    )

    assert recipe["slug"] == "test-berry-crisp"
    assert recipe["title"] == "Test berry crisp"
    assert recipe["intro"] == (
        "This irresistible test recipe showcases berries. Enjoy it warm with a "
        "dollop of yogurt — it serves a ½ dozen."
    )
    assert recipe["prep_time"] == "15 min"
    assert recipe["cook_time"] == "50 min"
    assert recipe["servings"] == "6"
    assert len(recipe["ingredient_groups"]) == 2
    assert [group["group"] for group in recipe["ingredient_groups"]] == [None, "Topping:"]
    assert [item for group in recipe["ingredient_groups"] for item in group["items"]] == [
        "4 apples, cored and chopped",
        "500 mL (2 cups) frozen blueberries",
        "45 mL (3 tbsp) packed brown sugar",
        "125 mL (½ cup) large flake oats",
        "30 mL (2 tbsp) soft margarine, melted",
    ]
    assert recipe["directions"] == [
        "Preheat the oven to 180 °C (350 °F).",
        "In a large bowl, combine apples and blueberries; sprinkle topping over top.",
    ]
    assert recipe["tips"] == ["Little chefs can stir the topping ingredients together."]
    assert recipe["tags"] == ["collection__vegetarian", "meal__snack"]
    stable = re.sub(
        r"<(script|style|noscript)\b[^>]*>.*?</\1\s*>", "", html_text, flags=re.S | re.I
    )
    assert recipe["page_sha256"] == hashlib.sha256(stable.encode("utf-8")).hexdigest()
    # A dynamic analytics script must not change the hash.
    dynamic = html_text.replace(
        "</title>", "</title><script>var analytics = Math.random();</script>"
    )
    assert parse_recipe(dynamic, "test-apple-crisp", "https://example.com/x.html", [
        "collection__vegetarian",
        "meal__snack",
    ])["page_sha256"] == recipe["page_sha256"]
    assert list(recipe.keys()) == [
        "slug",
        "url",
        "title",
        "intro",
        "prep_time",
        "cook_time",
        "servings",
        "ingredient_groups",
        "directions",
        "tips",
        "tags",
        "page_sha256",
    ]


def test_parse_recipe_no_tips():
    recipe = parse_recipe(_read("no-tips.html"), "test-oat-bowl", "https://example.com/x.html", [])

    assert recipe["title"] == "Test oat bowl"
    assert len(recipe["ingredient_groups"]) == 1
    assert recipe["ingredient_groups"][0]["group"] is None
    assert recipe["ingredient_groups"][0]["items"] == [
        "250 mL (1 cup) rolled oats",
        "250 mL (1 cup) milk",
        "1 apple, diced",
    ]
    assert recipe["servings"] == "2"
    assert recipe["cook_time"] is None
    assert recipe["tips"] == []


def test_parse_recipe_missing_directions_raises():
    with pytest.raises(ValueError, match="test-broken"):
        parse_recipe(_read("broken.html"), "test-broken", "https://example.com/broken.html", [])


class _StripScriptsParser(html.parser.HTMLParser):
    """Independent script/style stripper used to cross-check _page_sha256.

    Implements 'hash the page without script/style/noscript subtrees' with a
    different mechanism (real HTML tree walking) than the regex the parser
    uses, so a wrong regex cannot pass its own test.
    """

    _SKIP = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._depth += 1
        elif not self._depth:
            self.parts.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._depth:
            self._depth -= 1
        elif not self._depth:
            self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        if tag not in self._SKIP and not self._depth:
            self.parts.append(self.get_starttag_text() or "")

    def handle_data(self, data):
        if not self._depth:
            self.parts.append(data)

    def handle_comment(self, data):
        if not self._depth:
            self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        if not self._depth:
            self.parts.append(f"<!{decl}>")

    def handle_entityref(self, name):
        if not self._depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self._depth:
            self.parts.append(f"&#{name};")


def test_page_sha256_matches_independent_htmlparser_stripping():
    """The regex-based stable hash agrees with a real HTML-tree stripper."""
    from foodguide.recipes.parser import _page_sha256

    for name in ("fruit-salad.html", "two-groups.html", "no-tips.html"):
        html_text = _read(name)
        stripper = _StripScriptsParser()
        stripper.feed(html_text)
        stripper.close()
        independent = hashlib.sha256("".join(stripper.parts).encode("utf-8")).hexdigest()
        assert _page_sha256(html_text) == independent, name


@pytest.mark.skipif(
    not (REAL_CACHE / "apple-berry-crisp.html").exists(),
    reason="real cached recipe page not available",
)
def test_real_page_sha256_is_reproducible_across_dynamic_scripts():
    """Injecting the dynamic analytics script must not change the hash."""
    from foodguide.recipes.parser import _page_sha256

    html_text = (REAL_CACHE / "apple-berry-crisp.html").read_text(encoding="utf-8")
    poisoned = html_text.replace(
        "</body>",
        "<script>var analytics = Math.random();</script></body>",
    )
    assert _page_sha256(html_text) == _page_sha256(poisoned)


@pytest.mark.skipif(
    not (REAL_CACHE / "apple-berry-crisp.html").exists(),
    reason="real cached recipe page not available",
)
def test_parse_real_apple_berry_crisp():
    html_text = (REAL_CACHE / "apple-berry-crisp.html").read_text(encoding="utf-8")
    recipe = parse_recipe(
        html_text,
        "apple-berry-crisp",
        "https://www.canada.ca/en/health-canada/services/food-guide/eating-support"
        "/kitchen/recipes/apple-berry-crisp.html",
        ["collection__kid_friendly", "collection__vegetarian", "meal__snack"],
    )

    assert recipe["title"] == "Apple berry crisp"
    assert recipe["prep_time"] == "15 min"
    assert recipe["cook_time"] == "50 min"
    assert recipe["servings"] == "8"
    assert recipe["ingredient_groups"][0]["items"][0] == "4 apples, cored and chopped"
