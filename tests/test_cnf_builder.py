"""Unit tests for the offline CNF 2026 SQLite builder and read layer."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from cnf_fixture import make_mini_zip

from foodguide.cnf.builder import DEFAULT_DATASET_ID, DEFAULT_ZIP_URL, build_cnf_db
from foodguide.cnf.db import (
    db_status,
    get_cnf_db_path,
    get_data_dir,
    get_food,
    get_measures,
    get_nutrients,
    get_provenance,
    open_cnf_db,
    search_foods,
)


@pytest.fixture()
def mini_zip(tmp_path: Path) -> Path:
    return make_mini_zip(tmp_path / "mini_cnf.zip")


@pytest.fixture()
def built(mini_zip: Path, tmp_path: Path):
    result = build_cnf_db(mini_zip, tmp_path / "cnf.sqlite")
    conn = open_cnf_db(result.out_path)
    yield result, conn
    conn.close()


def test_build_row_counts_and_size(built) -> None:
    result, _conn = built
    assert result.rows["food"] == 3
    assert result.rows["nutrient_amount"] == 8
    assert result.rows["measure_name"] == 3
    assert result.rows["measure_weight_conversion"] == 5
    assert result.rows["nutrient_name"] == 3
    assert result.rows["food_group"] == 2
    assert result.rows["food_source"] == 1
    assert result.rows["measure_type"] == 1
    assert result.rows["nutrient_source"] == 1
    assert result.rows["food_fts"] == 3
    assert result.size_bytes > 0
    assert result.out_path.exists()


def test_amount_text_stored_exactly(built) -> None:
    _result, conn = built
    row = conn.execute(
        "SELECT amount_text, amount FROM nutrient_amount WHERE food_code = 100 AND nutrient_code = 203"
    ).fetchone()
    assert row["amount_text"] == "9.020000000"
    assert row["amount"] == 9.02


def test_get_food_joins(built) -> None:
    _result, conn = built
    food = get_food(conn, 100)
    assert food is not None
    assert food["name_en"] == "Red lentils, cooked"
    assert food["name_fr"] == "Lentilles rouges, cuites"
    assert food["alternate_name_en"] is None
    assert food["group_code"] == 10
    assert food["group_name_en"] == "Vegetables and vegetable products"
    assert food["group_name_fr"] == "Légumes et produits végétaux"
    assert food["source_code"] == 20
    assert food["source_name_en"] == "Health Canada"
    assert food["source_name_fr"] == "Santé Canada"
    assert food["usda_ndb_code"] == 16069

    bread = get_food(conn, 101)
    assert bread is not None
    assert bread["alternate_name_en"] == "loaf"
    assert bread["usda_ndb_code"] is None
    assert bread["group_name_en"] == "Baked goods"

    assert get_food(conn, 999) is None


def test_get_nutrients(built) -> None:
    _result, conn = built
    nutrients = get_nutrients(conn, 100)
    assert [n["code"] for n in nutrients] == [203, 208, 301]
    assert nutrients[0]["symbol"] == "PROT"
    assert nutrients[0]["unit"] == "Gram"
    assert nutrients[0]["name_en"] == "Protein"
    assert nutrients[0]["name_fr"] == "Protéines"
    assert nutrients[0]["amount"] == 9.02
    assert nutrients[0]["amount_text"] == "9.020000000"
    assert get_nutrients(conn, 999) == []


def test_get_measures(built) -> None:
    _result, conn = built
    measures = get_measures(conn, 100)
    assert [m["measure_code"] for m in measures] == [1, 2, 3]
    assert [m["grams"] for m in measures] == [100.0, 198.0, 13.5]
    assert measures[0]["description_en"] == "100 g"
    assert measures[0]["measure_type_code"] == 1
    assert measures[2]["conversion_text"] == "13.5"
    # Food 102 has only the "100 g" conversion.
    only = get_measures(conn, 102)
    assert [m["measure_code"] for m in only] == [1]
    assert only[0]["grams"] == 100.0


def test_search_foods(built) -> None:
    _result, conn = built
    hits = search_foods(conn, "lentils", "en")
    assert [h["food_code"] for h in hits] == [100, 102]
    assert hits[0]["name_en"] == "Red lentils, cooked"
    fr_hits = search_foods(conn, "lentilles", "fr")
    assert [h["food_code"] for h in fr_hits] == [100, 102]
    assert fr_hits[0]["name_fr"] == "Lentilles rouges, cuites"
    # lang restricted to en/fr
    with pytest.raises(ValueError):
        search_foods(conn, "lentils", "de")
    # empty / whitespace query
    assert search_foods(conn, "", "en") == []
    assert search_foods(conn, "   ", "en") == []
    # no match
    assert search_foods(conn, "lasagna", "en") == []
    # multi-token query still works (tokens quoted, implicit AND)
    multi = search_foods(conn, "red cooked", "en")
    assert [h["food_code"] for h in multi] == [100]


def test_build_determinism(mini_zip: Path, tmp_path: Path) -> None:
    first = build_cnf_db(mini_zip, tmp_path / "a.sqlite", build_time="2026-01-01T00:00:00+00:00")
    second = build_cnf_db(mini_zip, tmp_path / "b.sqlite", build_time="2026-01-02T00:00:00+00:00")
    assert first.content_hash == second.content_hash
    assert first.zip_sha256 == second.zip_sha256
    prov_a = get_provenance(open_cnf_db(first.out_path))
    prov_b = get_provenance(open_cnf_db(second.out_path))
    assert prov_a.keys() == prov_b.keys()
    differing = {k for k in prov_a if prov_a[k] != prov_b[k]}
    assert differing == {"build_time"}


def test_source_date_epoch_fixes_build_time(mini_zip: Path, tmp_path: Path, monkeypatch) -> None:
    """SOURCE_DATE_EPOCH pins the recorded build_time for reproducible builds."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1765000000")
    result = build_cnf_db(mini_zip, tmp_path / "e.sqlite")
    assert result.build_time == "2025-12-06T05:46:40+00:00"

    # A different epoch gives a different recorded time (and thus different raw
    # bytes), while the content identity is unaffected.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1765000001")
    other = build_cnf_db(mini_zip, tmp_path / "e2.sqlite")
    assert other.build_time == "2025-12-06T05:46:41+00:00"
    assert other.content_hash == result.content_hash

    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    wall = build_cnf_db(mini_zip, tmp_path / "w.sqlite")
    assert wall.build_time != result.build_time


def test_provenance(built, mini_zip: Path) -> None:
    result, conn = built
    provenance = get_provenance(conn)
    assert provenance["dataset_id"] == DEFAULT_DATASET_ID
    assert provenance["zip_url"] == DEFAULT_ZIP_URL
    assert provenance["zip_sha256"] == hashlib.sha256(mini_zip.read_bytes()).hexdigest()
    assert provenance["content_hash"] == result.content_hash
    assert provenance["rows_food"] == "3"
    assert provenance["rows_nutrient_amount"] == "8"
    assert provenance["build_time"].endswith("+00:00")
    conn.close()


def test_db_status(built, tmp_path: Path) -> None:
    result, _conn = built
    missing = db_status(tmp_path / "nope.sqlite")
    assert missing is None
    status = db_status(result.out_path)
    assert status is not None
    assert status["size_bytes"] == result.size_bytes
    assert status["path"] == str(result.out_path)
    assert status["provenance"]["rows_food"] == "3"


def test_path_helpers_env_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOODGUIDE_DATA_DIR", raising=False)
    default_dir = get_data_dir()
    assert default_dir == Path.home() / ".local" / "share" / "foodguide"
    assert get_cnf_db_path() == default_dir / "cnf.sqlite"
    monkeypatch.setenv("FOODGUIDE_DATA_DIR", "~/fooddata")
    assert get_data_dir() == Path.home() / "fooddata"
    assert get_cnf_db_path() == Path.home() / "fooddata" / "cnf.sqlite"


def test_open_cnf_db_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="foodguide data build cnf"):
        open_cnf_db(tmp_path / "missing.sqlite")


def test_build_error_on_empty_amount(mini_zip: Path, tmp_path: Path) -> None:
    # A fixture with an empty Nutrient_Amount must fail with a clear error.
    make_mini_zip(tmp_path / "mini_cnf.zip")
    import csv
    import io
    import zipfile as zf_mod

    src = zf_mod.ZipFile(mini_zip)
    out = tmp_path / "broken.zip"
    with zf_mod.ZipFile(out, "w") as dest:
        for name in src.namelist():
            with src.open(name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="").read()
            if name == "Nutrient_Amount.csv":
                rows = list(csv.reader(io.StringIO(text)))
                rows[1][2] = ""
                buffer = io.StringIO()
                csv.writer(buffer, lineterminator="\n").writerows(rows)
                text = buffer.getvalue()
            dest.writestr(name, text.encode("utf-8-sig"))
    with pytest.raises(ValueError, match="Nutrient_Amount"):
        build_cnf_db(out, tmp_path / "broken.sqlite")


def test_fts_rank_query_works(built) -> None:
    """Sanity: the '{name_en} : ...' MATCH syntax is valid FTS5."""
    _result, conn = built
    rows = conn.execute(
        'SELECT food_code FROM food_fts WHERE food_fts MATCH ? ORDER BY rank LIMIT ?',
        ('{name_en} : "lentils"', 10),
    )
    codes = sorted(r[0] for r in rows)
    assert codes == [100, 102]


def test_db_is_read_only(built) -> None:
    _result, conn = built
    assert isinstance(conn, sqlite3.Connection)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO food VALUES (999, 'x', 'y', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)")
