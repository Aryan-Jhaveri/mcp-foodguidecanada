"""Tests for the DRI/EER data managers (data-dir file first, bundled fallback).

All tests run offline: FOODGUIDE_DATA_DIR points at a tmp_path and every
requests entry point is monkeypatched to raise, proving the managers never
touch the network.
"""

import json
from importlib.resources import files

import pytest
import requests

from foodguide import data_manager
from foodguide.data_manager import (
    get_dri_data_manager,
    get_eer_data_manager,
)

BUNDLED_DRI = json.loads(
    (files("foodguide.data") / "dri_macronutrients.json").read_text(encoding="utf-8")
)
BUNDLED_EER = json.loads((files("foodguide.data") / "eer_equations.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def data_dir_env(tmp_path, monkeypatch):
    """Point FOODGUIDE_DATA_DIR at a tmp dir and reset the manager singletons."""
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FOODGUIDE_SKIP_LIVE_TESTS", raising=False)
    monkeypatch.setattr(data_manager, "_dri_manager", None, raising=False)
    monkeypatch.setattr(data_manager, "_eer_manager", None, raising=False)
    return tmp_path


@pytest.fixture(autouse=True)
def blocked_network(monkeypatch):
    """Any network access during these tests is a hard failure."""

    def _blocked(*args, **kwargs):
        raise AssertionError("network disabled in test")

    monkeypatch.setattr(requests.Session, "request", _blocked)
    monkeypatch.setattr(requests, "request", _blocked)
    monkeypatch.setattr(requests, "get", _blocked)
    monkeypatch.setattr(requests, "post", _blocked)


def _write_data_dir_file(tmp_path, name: str, payload) -> None:
    (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_data_dir_dri_file_wins(tmp_path):
    # Marker-modified copy of the bundled snapshot in the data dir.
    marker = "MARKER-modified-footnote-for-data-dir-test"
    payload = json.loads(json.dumps(BUNDLED_DRI))
    payload["footnotes"]["fn_t2b1"] = marker
    _write_data_dir_file(tmp_path, "dri_macronutrients.json", payload)

    manager = get_dri_data_manager()
    status = manager.get_status()
    assert status["source"] == "data_dir"
    assert status["path"] == str(tmp_path / "dri_macronutrients.json")

    data = manager.get_dri_data()
    assert data["footnotes"]["fn_t2b1"] == marker
    # Everything else still comes from the (modified) snapshot.
    assert data["reference_values"][0]["nutrients"]["protein"]["rda_ai_g_day"] == 9.1
    assert data["_data_freshness"]["source"] == "data_dir"


def test_data_dir_eer_file_wins(tmp_path):
    marker = "MARKER-general-note-for-data-dir-test"
    payload = json.loads(json.dumps(BUNDLED_EER))
    payload["general_note"] = marker
    _write_data_dir_file(tmp_path, "eer_equations.json", payload)

    manager = get_eer_data_manager()
    assert manager.get_status()["source"] == "data_dir"
    assert manager.get_eer_data()["general_note"] == marker
    filtered = manager.get_equations("adult", "active")
    assert filtered["status"] == "success"
    assert filtered["equations"]["adult"]["male"]["active"]["coefficients"]["intercept"] == 1004.82


def test_no_data_dir_file_uses_bundled_snapshot():
    # tmp data dir is empty: the bundled snapshots must be served offline.
    dri = get_dri_data_manager()
    assert dri.get_status()["source"] == "bundled_snapshot"
    assert dri.get_dri_data()["reference_values"]

    eer = get_eer_data_manager()
    assert eer.get_status()["source"] == "bundled_snapshot"
    assert eer.get_eer_data()["equations"]["adult"]


def test_corrupt_data_dir_file_falls_back_to_bundled(tmp_path, capsys):
    # Invalid JSON: must not raise, must log a warning and serve bundled data.
    (tmp_path / "dri_macronutrients.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "eer_equations.json").write_text("[1, 2, ", encoding="utf-8")

    dri = get_dri_data_manager()
    assert dri.get_status()["source"] == "bundled_snapshot"
    assert dri.get_dri_data()["status"] == "success"

    eer = get_eer_data_manager()
    assert eer.get_status()["source"] == "bundled_snapshot"
    assert "equations" in eer.get_eer_data()
    # The fallbacks explained themselves on stderr.
    captured = capsys.readouterr()
    assert "falling back to bundled" in captured.err


def test_non_object_data_dir_file_is_ignored(tmp_path, capsys):
    # A JSON array in the data dir is not a dict: ignored, bundled served.
    (tmp_path / "dri_macronutrients.json").write_text("[]", encoding="utf-8")
    dri = get_dri_data_manager()
    assert dri.get_status()["source"] == "bundled_snapshot"


def test_all_managers_offline_with_requests_blocked(data_dir_env):
    # Explicit belt-and-braces test: even force_refresh must stay offline
    # (it only re-reads local files; no network call is possible).
    dri = get_dri_data_manager()
    assert dri.get_dri_data(force_refresh=True)["status"] == "success"
    assert dri.get_dri_data()["status"] == "success"

    eer = get_eer_data_manager()
    assert eer.get_eer_data()["equations"]
    payload = eer.get_equations()
    assert payload["status"] == "success"
    assert payload["equations"]
    assert "equations" in payload

    assert set(eer.get_pal_descriptions()) >= {"inactive", "active"}


def test_status_provenance_roundtrip(tmp_path):
    # A data-dir file built by `foodguide data build` carries _provenance;
    # get_status() exposes it as-is.
    provenance = {"source_url": "https://example.test", "page_sha256": "abc123"}
    payload = json.loads(json.dumps(BUNDLED_DRI))
    payload["_provenance"] = provenance
    _write_data_dir_file(tmp_path, "dri_macronutrients.json", payload)
    status = get_dri_data_manager().get_status()
    assert status["provenance"] == provenance
