"""Real end-to-end offline proof: the REAL CLI and MCP server run in a SUBPROCESS.

No mocks anywhere. Every subprocess gets HTTP(S)_PROXY / http(s)_proxy pointed
at the dead proxy from pages_fixture.dead_proxy_env() (127.0.0.1:9, the discard
port) and NO_PROXY cleared, so any HTTP(S) request attempt dies immediately.
Whatever data comes back must therefore come from local files (the bundled
snapshots or files built into FOODGUIDE_DATA_DIR).

Each subprocess costs ~1-2s (interpreter + imports); keep the file small.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from cnf_fixture import make_mini_zip
from pages_fixture import dead_proxy_env, fixture_recipe_cache_dir

from foodguide.cnf.builder import build_cnf_db
from foodguide.recipes.builder import build_recipes_json
from foodguide.recipes.fetch import CachedFetcher

TIMEOUT = 120


def _run(cmd: list[str], extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run *cmd* in a subprocess with every proxy pointed at a dead port."""
    return subprocess.run(
        cmd,
        env={**os.environ, **dead_proxy_env(), **extra_env},
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def _run_cli(args: list[str], extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the real `foodguide` CLI entry point (foodguide.cli:app) via -c.

    sys.argv is set inside the child script because `python -c` starts with
    argv = ['-c'].
    """
    code = (
        "import sys; sys.argv = ['foodguide'] + " + json.dumps(args) + ";\n"
        "from foodguide.cli import app; app()"
    )
    return _run([sys.executable, "-c", code], extra_env)


@pytest.fixture()
def empty_data_dir(tmp_path) -> str:
    """A fresh empty data dir: the bundled snapshots must be served offline."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return str(data_dir)


# --------------------------------------------------------------------------- #
# a) CLI DRI from the bundled snapshot
# --------------------------------------------------------------------------- #


def test_cli_dri_tables_bundled_snapshot_offline(empty_data_dir):
    result = _run_cli(["dri", "tables", "--format", "json"], {"FOODGUIDE_DATA_DIR": empty_data_dir})
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    rows = json.loads(result.stdout)
    assert rows
    ages = {row["age_range"] for row in rows}
    # The bundled snapshot keys on an en dash and NBSPs: '19\u201330\u00a0y'.
    adult_range = "19\u201330\u00a0y"
    assert adult_range in ages, f"missing adult row in {sorted(ages)}"
    males = next(
        row for row in rows if row["age_range"] == adult_range and row["category"] == "Males"
    )
    assert males["nutrients"]["protein"]["rda_ai_g_day"] == 56.0


# --------------------------------------------------------------------------- #
# b) CLI EER
# --------------------------------------------------------------------------- #


def test_cli_eer_calc_offline(empty_data_dir):
    result = _run_cli(
        [
            "eer", "calc", "--sex", "male", "--age", "30",
            "--weight-kg", "70", "--height-cm", "175",
            "--pal", "active", "--format", "json",
        ],
        {"FOODGUIDE_DATA_DIR": empty_data_dir},
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    payload = json.loads(result.stdout)
    assert payload["eer_kcal"] == 2934.6
    assert payload["inputs"] == {
        "sex": "male",
        "age_years": 30,
        "weight_kg": 70,
        "height_cm": 175,
        "pal": "active",
    }


# --------------------------------------------------------------------------- #
# c) MCP tool in a subprocess
# --------------------------------------------------------------------------- #


def test_mcp_dri_tool_offline(empty_data_dir):
    # The real fastmcp server with the real DRI tools, driven by the real
    # in-process fastmcp Client; same unwrap pattern as test_dri_eer_mcp.py
    # (result.data is the unwrapped JSON payload).
    script = (
        "import asyncio, json\n"
        "from fastmcp import Client\n"
        "from foodguide.server import create_server\n"
        "\n"
        "async def main():\n"
        "    server = create_server(enable_db=False)\n"
        "    async with Client(server) as client:\n"
        "        result = await client.call_tool(\n"
        "            'get_macronutrient_dri_tables', {'force_refresh': False}\n"
        "        )\n"
        "        assert not result.is_error, str(result)\n"
        "        print(json.dumps(result.data, ensure_ascii=False))\n"
        "\n"
        "asyncio.run(main())\n"
    )
    result = _run([sys.executable, "-c", script], {"FOODGUIDE_DATA_DIR": empty_data_dir})
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    payload = json.loads(result.stdout)
    assert "error" not in payload
    assert payload["status"] == "success"
    assert payload["reference_values"]
    assert payload["_data_freshness"]["source"] in ("data_dir", "bundled_snapshot")


# --------------------------------------------------------------------------- #
# d) recipes CLI offline (recipes.json built once from the committed pages)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def recipes_data_dir(tmp_path_factory) -> str:
    """Build recipes.json ONCE with the production CachedFetcher.

    All pages come from the real committed fixture cache dir; any cache miss
    would hit the network, which the dead proxies only make a concern for
    fetches we do not make (all three slugs are committed).
    """
    tmp = tmp_path_factory.mktemp("recipes-offline")
    data_dir = tmp / "data"
    data_dir.mkdir()
    cache = fixture_recipe_cache_dir(tmp)
    build_recipes_json(
        data_dir / "recipes.json",
        fetcher=CachedFetcher(cache, delay=0.0),
        only=["apple-sandwiches", "baked-fish-chips", "tofu-masala-curry"],
    )
    return str(data_dir)


def test_cli_recipes_search_offline(recipes_data_dir):
    result = _run_cli(
        ["recipes", "search", "apple", "--format", "json"], {"FOODGUIDE_DATA_DIR": recipes_data_dir}
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    hits = json.loads(result.stdout)
    assert hits, "search for 'apple' returned nothing"
    by_slug = {hit["slug"]: hit for hit in hits}
    assert "apple-sandwiches" in by_slug
    assert by_slug["apple-sandwiches"]["title"]
    assert all(hit["slug"] and hit["title"] for hit in hits)


# --------------------------------------------------------------------------- #
# e) CNF CLI offline (mini CNF zip built once into the data dir)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def cnf_data_dir(tmp_path_factory) -> str:
    """Build the tiny cnf_fixture mini zip into a data dir once."""
    tmp = tmp_path_factory.mktemp("cnf-offline")
    data_dir = tmp / "data"
    data_dir.mkdir()
    zip_path = make_mini_zip(tmp / "mini_cnf.zip")
    build_cnf_db(zip_path, data_dir / "cnf.sqlite")
    return str(data_dir)


def test_cli_cnf_search_offline(cnf_data_dir):
    result = _run_cli(
        ["cnf", "search", "lentils", "--format", "json", "--limit", "3"],
        {"FOODGUIDE_DATA_DIR": cnf_data_dir},
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    hits = json.loads(result.stdout)
    assert hits
    # cnf_fixture: food 100 = Red lentils, cooked; 102 = Boiled lentils.
    assert {hit["food_code"] for hit in hits} == {100, 102}
    assert all(hit["name_en"] and hit["name_fr"] for hit in hits)
