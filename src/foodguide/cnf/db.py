"""Read layer for the offline CNF SQLite database (built by foodguide.cnf.builder).

Path helpers read the environment at call time so callers (and tests) can point
FOODGUIDE_DATA_DIR wherever they like without reloading the module.
"""

from __future__ import annotations

import os
import sqlite3
import urllib.parse
from pathlib import Path


def get_data_dir() -> Path:
    """Directory where foodguide keeps its offline data files."""
    env = os.environ.get("FOODGUIDE_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".local" / "share" / "foodguide"


def get_cnf_db_path() -> Path:
    """Default location of the CNF SQLite database."""
    return get_data_dir() / "cnf.sqlite"


def open_cnf_db(path: Path | None = None) -> sqlite3.Connection:
    """Open the CNF database read-only; raise FileNotFoundError with guidance if missing."""
    db_path = Path(path).expanduser() if path is not None else get_cnf_db_path()
    if not db_path.exists():
        raise FileNotFoundError(
            f"CNF database not found at {db_path}. "
            "Build it from the official CNF zip first: `foodguide data build cnf --zip <path-to-cnf-zip>`."
        )
    uri = "file:" + urllib.parse.quote(str(db_path.resolve())) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def search_foods(conn: sqlite3.Connection, query: str, lang: str = "en", limit: int = 10) -> list[dict]:
    """Full-text food search; tokens are AND-ed prefixes, results ordered by food_code."""
    if lang not in ("en", "fr"):
        raise ValueError(f"lang must be 'en' or 'fr', got {lang!r}")
    tokens = query.split()
    if not tokens:
        return []
    column = "name_en" if lang == "en" else "name_fr"
    # Quote each token and make it a prefix term ("lentille"* also matches "lentilles").
    # Strip embedded double quotes first so the token cannot break out of the quoted string.
    terms = [f'"{token.replace(chr(34), "")}"*' for token in tokens if token.replace(chr(34), "")]
    if not terms:
        return []
    match = "{" + column + "} : " + " ".join(terms)
    codes = [
        row[0]
        for row in conn.execute(
            "SELECT food_code FROM food_fts WHERE food_fts MATCH ? ORDER BY rank LIMIT ?", (match, limit)
        )
    ]
    if not codes:
        return []
    placeholders = ",".join("?" * len(codes))
    rows = conn.execute(
        f"SELECT food_code, description_en, description_fr FROM food WHERE food_code IN ({placeholders}) ORDER BY food_code",
        codes,
    )
    return [{"food_code": row[0], "name_en": row[1], "name_fr": row[2]} for row in rows]


def get_food(conn: sqlite3.Connection, code: int) -> dict | None:
    """One food with its group and source names joined in, or None if unknown."""
    row = conn.execute(
        """
        SELECT f.food_code, f.description_en, f.description_fr,
               f.alternate_description_en, f.alternate_description_fr,
               f.food_group_code, g.name_en AS group_name_en, g.name_fr AS group_name_fr,
               f.food_source_code, s.name_en AS source_name_en, s.name_fr AS source_name_fr,
               f.usda_ndb_code, f.scientific_name, f.last_updated_date
        FROM food f
        LEFT JOIN food_group g ON g.food_group_code = f.food_group_code
        LEFT JOIN food_source s ON s.food_source_code = f.food_source_code
        WHERE f.food_code = ?
        """,
        (code,),
    ).fetchone()
    if row is None:
        return None
    return {
        "food_code": row["food_code"],
        "name_en": row["description_en"],
        "name_fr": row["description_fr"],
        "alternate_name_en": row["alternate_description_en"],
        "alternate_name_fr": row["alternate_description_fr"],
        "group_code": row["food_group_code"],
        "group_name_en": row["group_name_en"],
        "group_name_fr": row["group_name_fr"],
        "source_code": row["food_source_code"],
        "source_name_en": row["source_name_en"],
        "source_name_fr": row["source_name_fr"],
        "usda_ndb_code": row["usda_ndb_code"],
        "scientific_name": row["scientific_name"],
        "last_updated_date": row["last_updated_date"],
    }


def get_nutrients(conn: sqlite3.Connection, code: int) -> list[dict]:
    """All nutrient amounts for one food, ordered by nutrient_code."""
    rows = conn.execute(
        """
        SELECT n.nutrient_code, n.symbol, n.unit, n.name_en, n.name_fr,
               a.amount, a.amount_text
        FROM nutrient_amount a
        JOIN nutrient_name n ON n.nutrient_code = a.nutrient_code
        WHERE a.food_code = ?
        ORDER BY a.nutrient_code
        """,
        (code,),
    )
    return [
        {
            "code": row["nutrient_code"],
            "symbol": row["symbol"],
            "unit": row["unit"],
            "name_en": row["name_en"],
            "name_fr": row["name_fr"],
            "amount": row["amount"],
            "amount_text": row["amount_text"],
        }
        for row in rows
    ]


def get_measures(conn: sqlite3.Connection, code: int) -> list[dict]:
    """Household measure conversions for one food, ordered by measure_code."""
    rows = conn.execute(
        """
        SELECT w.measure_code, m.description_en, m.description_fr,
               w.measure_type_code, w.conversion, w.conversion_text
        FROM measure_weight_conversion w
        JOIN measure_name m ON m.measure_code = w.measure_code
        WHERE w.food_code = ?
        ORDER BY w.measure_code
        """,
        (code,),
    )
    return [
        {
            "measure_code": row["measure_code"],
            "description_en": row["description_en"],
            "description_fr": row["description_fr"],
            "measure_type_code": row["measure_type_code"],
            "grams": row["conversion"],
            "conversion_text": row["conversion_text"],
        }
        for row in rows
    ]


def get_provenance(conn: sqlite3.Connection) -> dict[str, str]:
    """The provenance table as a plain dict."""
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM provenance")}


def db_status(db_path: Path | None = None) -> dict | None:
    """Summary of the CNF database file, or None if it does not exist."""
    path = Path(db_path).expanduser() if db_path is not None else get_cnf_db_path()
    if not path.exists():
        return None
    conn = open_cnf_db(path)
    try:
        provenance = get_provenance(conn)
    finally:
        conn.close()
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "provenance": provenance,
    }
