"""Tests for bundled data files and the data managers (offline)."""

import json
from importlib.resources import files

from foodguide.data_manager import get_eer_data_manager


def test_bundled_dri_macronutrients_loads() -> None:
    payload = json.loads(
        (files("foodguide.data") / "dri_macronutrients.json").read_text()
    )
    assert payload["status"] == "success"


def test_bundled_eer_equations_loads() -> None:
    payload = json.loads((files("foodguide.data") / "eer_equations.json").read_text())
    assert "equations" in payload


def test_eer_data_manager_returns_equations() -> None:
    payload = get_eer_data_manager().get_equations()
    assert payload["equations"], "expected a non-empty equations dict"
