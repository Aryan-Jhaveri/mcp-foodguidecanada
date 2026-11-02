"""Tests for the DRI/EER MCP tools (fastmcp in-memory client, offline).

Pattern follows tests/test_recipes_mcp.py: create_server(enable_db=False),
an in-memory fastmcp Client, asyncio.run. Every requests entry point is
monkeypatched to raise BEFORE any tool runs, proving the DRI/EER tools work
purely from the bundled/data-dir snapshots (the session DRI tools cache that
snapshot in the in-memory virtual session store).
"""

import asyncio
import json
import os
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest
import requests
from fastmcp import Client

from foodguide import data_manager
from foodguide.db import schema
from foodguide.server import create_server

SESSION_ID = "test-dri-eer-session"
PROFILE_NAME = "tester"


@pytest.fixture(scope="module")
def data_dir_env():
    """Deterministic (empty) data dir so the bundled snapshot is served."""
    tmp = Path("/tmp/foodguide-dri-eer-mcp-test")
    tmp.mkdir(parents=True, exist_ok=True)
    previous = os.environ.get("FOODGUIDE_DATA_DIR")
    os.environ["FOODGUIDE_DATA_DIR"] = str(tmp)
    data_manager._dri_manager = None
    data_manager._eer_manager = None
    yield tmp
    if previous is None:
        os.environ.pop("FOODGUIDE_DATA_DIR", None)
    else:
        os.environ["FOODGUIDE_DATA_DIR"] = previous
    data_manager._dri_manager = None
    data_manager._eer_manager = None


@pytest.fixture(scope="module")
def server(data_dir_env):
    return create_server(enable_db=False)


@pytest.fixture()
def blocked_network(monkeypatch):
    """Network access during a tool call is a hard failure."""

    def _blocked(*args, **kwargs):
        raise AssertionError("network disabled in test")

    monkeypatch.setattr(requests.Session, "request", _blocked)
    monkeypatch.setattr(requests, "request", _blocked)
    monkeypatch.setattr(requests, "get", _blocked)
    monkeypatch.setattr(requests, "post", _blocked)


@pytest.fixture(scope="module")
def session_with_profile():
    """A virtual session holding the cached DRI tables plus a user profile.

    calculate_dri_from_eer is a session tool: it needs the DRI tables cached
    (via the store_dri_tables_in_session tool) and a profile in
    session['dri_user_profiles'] (nothing registers a tool that creates one,
    so the test inserts it directly into the in-memory session store).
    """
    assert schema.ensure_dri_session_structure(SESSION_ID)
    data = schema.get_virtual_session_data(SESSION_ID)
    data["dri_user_profiles"] = {
        "p1": {"profile_name": PROFILE_NAME, "session_id": SESSION_ID}
    }
    yield
    schema.cleanup_virtual_session(SESSION_ID)


def call_tool(server, name, arguments):
    """call_tool via an in-memory Client; returns the unwrapped .data payload."""

    async def _run():
        async with Client(server) as client:
            result = await client.call_tool(name, arguments)
            assert not result.is_error, f"{name} returned an error result: {result}"
            return result.data

    return asyncio.run(_run())


def test_get_macronutrient_dri_tables_offline(server, blocked_network):
    payload = call_tool(server, "get_macronutrient_dri_tables", {"force_refresh": False})
    assert payload["status"] == "success"
    assert payload["reference_values"]
    assert payload["reference_values"][0]["nutrients"]["protein"]["rda_ai_g_day"] is not None
    assert payload["amdrs"]
    assert payload["_data_freshness"]["source"] in ("data_dir", "bundled_snapshot")


def test_get_eer_equations_offline(server, blocked_network):
    payload = call_tool(
        server,
        "get_eer_equations",
        {"equation_type": "adult", "pal_category": "active"},
    )
    assert payload["status"] == "success"
    adult = payload["equations"]["adult"]
    assert adult["male"]["active"]["coefficients"]["intercept"] == 1004.82
    assert payload["filtered_equations_count"] == 1


def test_get_pal_descriptions_offline(server, blocked_network):
    payload = call_tool(server, "get_pal_descriptions", {})
    assert payload["success"] is True
    assert set(payload["pal_categories"]) >= {"inactive", "low_active", "active", "very_active"}
    assert payload["usage_guidance"]


def test_calculate_dri_from_eer_offline(
    server, blocked_network, session_with_profile
):
    # Cache the DRI tables in the session with the store tool (offline data).
    stored = call_tool(
        server, "store_dri_tables_in_session", {"session_id": SESSION_ID}
    )
    assert stored["status"] == "success"
    assert stored["data_summary"]["total_age_groups"] > 0

    # AMDR keys on the page use NBSPs ('19\xa0years and over'): pick a real one.
    bundled = json.loads(
        (pkg_files("foodguide.data") / "dri_macronutrients.json").read_text(encoding="utf-8")
    )
    age_range = next(iter(bundled["amdrs"]))

    payload = call_tool(
        server,
        "calculate_dri_from_eer",
        {
            "session_id": SESSION_ID,
            "profile_name": PROFILE_NAME,
            "eer_energy_kcal": 2934.6,
            "age_range": age_range,
        },
    )
    assert payload["status"] == "success"
    assert payload["eer_energy_kcal"] == 2934.6
    assert payload["profile_name"] == PROFILE_NAME
    assert payload["amdr_ranges"]
    assert payload["calculation_constants"] == {
        "carbohydrate_kcal_per_gram": 4,
        "protein_kcal_per_gram": 4,
        "fat_kcal_per_gram": 9,
    }


def test_calculate_dri_from_eer_unknown_profile(server, blocked_network, session_with_profile):
    payload = call_tool(
        server,
        "calculate_dri_from_eer",
        {
            "session_id": SESSION_ID,
            "profile_name": "no-such-profile",
            "eer_energy_kcal": 2000.0,
            "age_range": "19 years and over",
        },
    )
    assert payload["status"] == "error"
    assert "not found in session" in payload["error"]
