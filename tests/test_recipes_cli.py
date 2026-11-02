"""CLI tests for the recipes app and the recipes sections of the data app."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from foodguide.cli import app
from foodguide.recipes.fetch import INDEX_URL, recipe_url
from foodguide.recipes.source import recipes_data_path

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"})

FIXTURES = Path(__file__).parent / "fixtures" / "recipes_html"


class StubFetcher:
    """Serves fixture pages instead of the network."""

    def __init__(self, mapping):
        self.mapping = mapping

    def fetch(self, url: str) -> str:
        return self.mapping[url]


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _stub_fetcher() -> StubFetcher:
    return StubFetcher(
        {
            INDEX_URL: _fixture("index.html"),
            recipe_url("test-berry-crisp"): _fixture("two-groups.html"),
            recipe_url("test-fruit-salad"): _fixture("fruit-salad.html"),
            recipe_url("test-oat-bowl"): _fixture("no-tips.html"),
        }
    )


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """A FOODGUIDE_DATA_DIR containing a fixture-built recipes.json."""
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    from foodguide.recipes.builder import build_recipes_json

    build_recipes_json(tmp_path / "recipes.json", fetcher=_stub_fetcher())
    return tmp_path


def test_search_table(data_dir):
    result = runner.invoke(app, ["recipes", "search"])
    assert result.exit_code == 0
    for title in ("Test berry crisp", "Test fruit salad", "Test oat bowl"):
        assert title in result.stdout


def test_search_json(data_dir):
    result = runner.invoke(app, ["recipes", "search", "--format", "json"])
    assert result.exit_code == 0
    results = json.loads(result.stdout)
    assert [r["slug"] for r in results] == [
        "test-berry-crisp",
        "test-fruit-salad",
        "test-oat-bowl",
    ]
    assert set(results[0]) == {"title", "url", "slug", "tags"}


def test_search_csv(data_dir):
    result = runner.invoke(app, ["recipes", "search", "--format", "csv"])
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "title,slug,tags"
    assert "test-berry-crisp" in lines[1]
    assert "collection__vegetarian" in lines[1]


def test_search_tag_and_limit(data_dir):
    result = runner.invoke(app, ["recipes", "search", "--tag", "meal__snack", "--format", "json"])
    assert result.exit_code == 0
    assert [r["slug"] for r in json.loads(result.stdout)] == ["test-berry-crisp"]

    result = runner.invoke(
        app, ["recipes", "search", "--tag", "Snack", "--format", "json"]
    )
    assert result.exit_code == 0
    assert [r["slug"] for r in json.loads(result.stdout)] == ["test-berry-crisp"]

    result = runner.invoke(app, ["recipes", "search", "--limit", "1", "--format", "json"])
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)) == 1


def test_search_no_match(data_dir):
    result = runner.invoke(app, ["recipes", "search", "no-such-thing-xyz"])
    assert result.exit_code == 0
    assert "No recipes match." in result.stdout


def test_show_by_slug_table(data_dir):
    result = runner.invoke(app, ["recipes", "show", "test-berry-crisp"])
    assert result.exit_code == 0
    out = result.stdout
    assert "Title: Test berry crisp" in out
    assert "URL: " in out and "test-berry-crisp.html" in out
    assert "collection__vegetarian" in out
    assert "Prep time: 15 min" in out and "Cook time: 50 min" in out and "Servings: 6" in out
    assert "Ingredients:" in out
    assert "4 apples, cored and chopped" in out
    assert "Topping:" in out
    assert "125 mL (½ cup) large flake oats" in out
    assert "Directions:" in out and "1. Preheat the oven to 180 °C (350 °F)." in out
    assert "Tips:" in out and "Little chefs can stir" in out


def test_show_by_url_json(data_dir):
    result = runner.invoke(
        app,
        [
            "recipes", "show",
            "https://www.canada.ca/en/health-canada/services/food-guide/eating-support"
            "/kitchen/recipes/test-oat-bowl.html",
            "--format", "json",
        ],
    )
    assert result.exit_code == 0
    recipe = json.loads(result.stdout)
    assert recipe["slug"] == "test-oat-bowl"
    assert recipe["ingredients"] == [
        "250 mL (1 cup) rolled oats",
        "250 mL (1 cup) milk",
        "1 apple, diced",
    ]
    assert "page_sha256" not in recipe


def test_show_by_old_food_guide_url(data_dir):
    result = runner.invoke(
        app,
        ["recipes", "show", "https://food-guide.canada.ca/en/recipes/test-fruit-salad/", "--format", "json"],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["slug"] == "test-fruit-salad"


def test_show_unknown_exits_1(data_dir):
    result = runner.invoke(app, ["recipes", "show", "no-such-recipe"])
    assert result.exit_code == 1
    assert "not found in local data" in result.output
    assert "foodguide data build recipes" in result.output


def test_show_csv(data_dir):
    result = runner.invoke(app, ["recipes", "show", "test-berry-crisp", "--format", "csv"])
    assert result.exit_code == 0
    assert result.stdout.startswith("key,value")
    assert "title,Test berry crisp" in result.stdout


def test_filters_formats(data_dir):
    table = runner.invoke(app, ["recipes", "filters"])
    assert table.exit_code == 0
    assert "collection__vegetarian" in table.stdout
    assert "Vegetarian" in table.stdout
    assert table.stdout.index("collection__vegetarian") < table.stdout.index("meal__breakfast")

    csv_result = runner.invoke(app, ["recipes", "filters", "--format", "csv"])
    assert csv_result.exit_code == 0
    lines = csv_result.stdout.strip().splitlines()
    assert lines[0] == "tag,label"
    assert "collection__vegetarian,Vegetarian" in lines

    json_result = runner.invoke(app, ["recipes", "filters", "--format", "json"])
    assert json_result.exit_code == 0
    assert json.loads(json_result.stdout) == {
        "collection__vegetarian": "Vegetarian",
        "meal__breakfast": "Breakfast",
        "meal__snack": "Snack",
    }


def test_data_status_shows_recipes_section(data_dir):
    table = runner.invoke(app, ["data", "status"])
    assert table.exit_code == 0
    assert "Recipes data:" in table.stdout
    assert f"{data_dir / 'recipes.json'}" in table.stdout
    assert "fetched_at:" in table.stdout
    assert "index_sha256:" in table.stdout

    json_result = runner.invoke(app, ["data", "status", "--format", "json"])
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["recipes"]["built"] is True
    assert payload["recipes"]["recipe_count"] == 3
    assert payload["recipes"]["filter_count"] == 3
    assert payload["recipes"]["index_sha256"]

    csv_result = runner.invoke(app, ["data", "status", "--format", "csv"])
    assert csv_result.exit_code == 0
    assert "recipes_json," in csv_result.stdout
    assert "recipes_provenance,fetched_at," in csv_result.stdout


def test_data_status_recipes_not_built(tmp_path, monkeypatch):
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    table = runner.invoke(app, ["data", "status"])
    assert table.exit_code == 0
    assert "Recipes data: not built (run: foodguide data build recipes)" in table.stdout


def test_data_build_recipes(tmp_path, monkeypatch):
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    out_path = tmp_path / "built" / "r.json"

    import foodguide.recipes.builder as builder

    monkeypatch.setattr(
        builder, "PoliteFetcher", lambda delay=1.0: _stub_fetcher()
    )
    result = runner.invoke(app, ["data", "build", "recipes", "--out", str(out_path)])
    assert result.exit_code == 0, result.output
    assert "recipes: 3" in result.stdout
    assert "filters: 3" in result.stdout
    assert out_path.exists()
    assert "index_sha256:" in result.stdout
    assert "build_time:" in result.stdout


def test_recipes_data_path_used_as_default_build_output(tmp_path, monkeypatch):
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    assert recipes_data_path() == tmp_path / "recipes.json"
