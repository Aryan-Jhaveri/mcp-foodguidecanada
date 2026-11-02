"""Golden end-to-end test for the CNF 2026 pipeline (HOM-76 Piece D).

Compares the CLI output against an independently produced answer key
(tests/fixtures/golden_cnf.json), which was generated straight from the official
CNF 2026 zip with a script that shares no code with the implementation. All
expectations come from the fixture file — nothing is hardcoded here.

The zip can be overridden for local runs via FOODGUIDE_TEST_CNF_ZIP; by default
it is looked for at the task data path.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from foodguide.cli import app
from foodguide.cnf.builder import build_cnf_db

GOLDEN_ZIP_ENV = "FOODGUIDE_TEST_CNF_ZIP"
DEFAULT_ZIP = "/srv/agent/work/foodguide-tasks/data/cnf_fcen_all-files-data_2026.zip"

runner = CliRunner()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module")
def golden() -> dict:
    fixture = Path(__file__).parent / "fixtures" / "golden_cnf.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cnf_db(tmp_path_factory: pytest.TempPathFactory, golden: dict, request: pytest.FixtureRequest) -> Path:
    """Build the real CNF database once per module and point the CLI at it.

    Yields the data dir; FOODGUIDE_DATA_DIR stays set to it for the module.
    """
    zip_path = Path(os.environ.get(GOLDEN_ZIP_ENV, DEFAULT_ZIP))
    if not zip_path.is_file():
        pytest.skip(f"CNF zip not found at {zip_path}; download it and set {GOLDEN_ZIP_ENV}")

    expected_sha = golden["source"]["zip_sha256"]
    actual_sha = _sha256_file(zip_path)
    if actual_sha != expected_sha:
        pytest.fail(
            "upstream CNF zip changed; golden key was built from a different zip "
            f"(sha256 mismatch: expected {expected_sha}, got {actual_sha})"
        )

    data_dir = tmp_path_factory.mktemp("cnf_golden")
    build_cnf_db(
        zip_path,
        data_dir / "cnf.sqlite",
        metadata_modified=golden["source"]["metadata_modified"],
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", str(data_dir))
    request.addfinalizer(monkeypatch.undo)
    return data_dir


def test_cnf_golden(cnf_db: Path, golden: dict) -> None:
    """Every golden food must reproduce exactly through the CLI."""
    for food in golden["foods"]:
        code = food["code"]
        where = f"food {code}"

        # a. nutrients (default per-100g basis; amount_text is populated there)
        result = runner.invoke(app, ["cnf", "nutrients", code, "--format", "json"])
        assert result.exit_code == 0, f"{where}: nutrients exited {result.exit_code}: {result.stderr}"
        payload = json.loads(result.stdout)
        assert payload["name_en"] == food["name_en"], f"{where}: name_en mismatch"
        assert payload["name_fr"] == food["name_fr"], f"{where}: name_fr mismatch"
        nutrients = payload["nutrients"]
        assert isinstance(nutrients, list), f"{where}: nutrients is not a list"
        assert {str(n["code"]) for n in nutrients} == {n["code"] for n in food["nutrients"]}, (
            f"{where}: nutrient code sets differ"
        )
        by_code = {str(n["code"]): n for n in nutrients}
        for want in food["nutrients"]:
            got = by_code[want["code"]]
            w = f"{where} nutrient {want['code']}"
            assert got["symbol"] == want["symbol"], f"{w}: symbol mismatch"
            assert got["unit"] == want["unit"], f"{w}: unit mismatch"
            assert got["name"] == want["name_en"], f"{w}: name mismatch"
            assert got["amount"] == float(want["amount"]), f"{w}: amount mismatch"
            assert got["amount_text"] == want["amount"], (
                f"{w}: amount_text {got['amount_text']!r} != raw CSV text {want['amount']!r}"
            )

        # b. measures
        result = runner.invoke(app, ["cnf", "measures", code, "--format", "json"])
        assert result.exit_code == 0, f"{where}: measures exited {result.exit_code}: {result.stderr}"
        payload = json.loads(result.stdout)
        measures = payload["measures"]
        assert len(measures) == len(food["measures"]), f"{where}: measure count mismatch"
        by_mcode = {str(m["measure_code"]): m for m in measures}
        for want in food["measures"]:
            got = by_mcode[want["measure_code"]]
            w = f"{where} measure {want['measure_code']}"
            assert got["description_en"] == want["description_en"], f"{w}: description_en mismatch"
            assert got["grams"] == float(want["conversion"]), f"{w}: grams mismatch"

        # c. food
        result = runner.invoke(app, ["cnf", "food", code, "--format", "json"])
        assert result.exit_code == 0, f"{where}: food exited {result.exit_code}: {result.stderr}"
        payload = json.loads(result.stdout)
        assert payload["name_en"] == food["name_en"], f"{where}: food name_en mismatch"
        assert payload["name_fr"] == food["name_fr"], f"{where}: food name_fr mismatch"
