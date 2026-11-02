"""Build a SQLite copy of the Canadian Nutrient File (CNF) 2026 from the official zip.

The CNF zip (open.canada.ca dataset 1b6139bd-ed7e-4043-bc28-ff00e10f3109) contains
flat CSV files (UTF-8 with BOM). This builder streams every table row by row into
a deterministic SQLite schema and records provenance, including a content hash
over the canonical table contents (so rebuilds are verifiable even though the
SQLite file bytes themselves may differ between builds).
"""

from __future__ import annotations

import csv
import hashlib
import io
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DATASET_ID = "1b6139bd-ed7e-4043-bc28-ff00e10f3109"
DEFAULT_ZIP_URL = (
    "https://open.canada.ca/data/dataset/1b6139bd-ed7e-4043-bc28-ff00e10f3109"
    "/resource/019f2a90-e3a9-489d-b6e1-f74f4ba1d006/download/cnf_fcen_all-files-data_2026.zip"
)

SCHEMA = """
CREATE TABLE food (
    food_code INTEGER PRIMARY KEY,
    description_en TEXT NOT NULL,
    description_fr TEXT NOT NULL,
    alternate_description_en TEXT,
    alternate_description_fr TEXT,
    food_source_code INTEGER,
    usda_ndb_code INTEGER,
    food_group_code INTEGER,
    comment_en TEXT,
    comment_fr TEXT,
    scientific_name TEXT,
    last_updated_date TEXT
);
CREATE TABLE food_group (
    food_group_code INTEGER PRIMARY KEY,
    name_en TEXT, name_fr TEXT
);
CREATE TABLE food_source (
    food_source_code INTEGER PRIMARY KEY,
    name_en TEXT, name_fr TEXT
);
CREATE TABLE nutrient_name (
    nutrient_code INTEGER PRIMARY KEY,
    symbol TEXT, unit TEXT, name_en TEXT, name_fr TEXT,
    tagname TEXT, decimals INTEGER
);
CREATE TABLE nutrient_amount (
    food_code INTEGER NOT NULL,
    nutrient_code INTEGER NOT NULL,
    amount_text TEXT NOT NULL,
    amount REAL NOT NULL,
    std_error_text TEXT,
    observations_text TEXT,
    nutrient_source_code INTEGER,
    last_updated_date TEXT,
    PRIMARY KEY (food_code, nutrient_code)
);
CREATE TABLE measure_name (
    measure_code INTEGER PRIMARY KEY,
    description_en TEXT, description_fr TEXT
);
CREATE TABLE measure_type (
    measure_type_code INTEGER PRIMARY KEY,
    description_en TEXT, description_fr TEXT
);
CREATE TABLE measure_weight_conversion (
    food_code INTEGER NOT NULL,
    measure_type_code INTEGER,
    measure_code INTEGER NOT NULL,
    conversion_text TEXT NOT NULL,
    conversion REAL NOT NULL,
    last_updated_date TEXT,
    PRIMARY KEY (food_code, measure_code)
);
CREATE TABLE nutrient_source (
    nutrient_source_code INTEGER PRIMARY KEY,
    name_en TEXT, name_fr TEXT
);
CREATE VIRTUAL TABLE food_fts USING fts5(
    food_code UNINDEXED, name_en, name_fr
);
CREATE TABLE provenance (key TEXT PRIMARY KEY, value TEXT);
"""

# The 10 data tables (everything except provenance), in the fixed order used for
# the content hash.
DATA_TABLES = (
    "food",
    "food_group",
    "food_source",
    "nutrient_name",
    "nutrient_amount",
    "measure_name",
    "measure_type",
    "measure_weight_conversion",
    "nutrient_source",
    "food_fts",
)

# Natural-key ORDER BY clause used when hashing each table's contents.
_ORDER_BY = {
    "food": "food_code",
    "food_group": "food_group_code",
    "food_source": "food_source_code",
    "nutrient_name": "nutrient_code",
    "nutrient_amount": "food_code, nutrient_code",
    "measure_name": "measure_code",
    "measure_type": "measure_type_code",
    "measure_weight_conversion": "food_code, measure_code",
    "nutrient_source": "nutrient_source_code",
    "food_fts": "rowid",
}

_INSERT = {
    "food": "INSERT INTO food VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    "food_group": "INSERT INTO food_group VALUES (?,?,?)",
    "food_source": "INSERT INTO food_source VALUES (?,?,?)",
    "nutrient_name": "INSERT INTO nutrient_name VALUES (?,?,?,?,?,?,?)",
    "nutrient_amount": "INSERT INTO nutrient_amount VALUES (?,?,?,?,?,?,?,?)",
    "measure_name": "INSERT INTO measure_name VALUES (?,?,?)",
    "measure_type": "INSERT INTO measure_type VALUES (?,?,?)",
    "measure_weight_conversion": "INSERT INTO measure_weight_conversion VALUES (?,?,?,?,?,?)",
    "nutrient_source": "INSERT INTO nutrient_source VALUES (?,?,?)",
}

_CSV_FILES = {
    "food": "Food_Name.csv",
    "food_group": "CNF_Food_Group.csv",
    "food_source": "Food_Source.csv",
    "nutrient_name": "Nutrient_Name.csv",
    "nutrient_amount": "Nutrient_Amount.csv",
    "measure_name": "Measure_Name.csv",
    "measure_type": "Measure_Type.csv",
    "measure_weight_conversion": "Measure_Weight_Conversion.csv",
    "nutrient_source": "Nutrient_Source.csv",
}


@dataclass(frozen=True)
class BuildResult:
    """Summary of a successful CNF database build."""

    out_path: Path
    size_bytes: int
    rows: dict[str, int]
    content_hash: str
    zip_sha256: str
    build_time: str


def _member_map(zf: zipfile.ZipFile) -> dict[str, str]:
    """Map CSV basename -> zip member name (works for flat and nested layouts)."""
    members: dict[str, str] = {}
    for name in zf.namelist():
        base = name.rsplit("/", 1)[-1]
        members.setdefault(base, name)
    return members


def _read_csv(zf: zipfile.ZipFile, member: str):
    """Yield dict rows from a zip member, streaming (never materialised)."""
    with zf.open(member) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            yield from csv.DictReader(text)


def _clean(row: dict[str, str | None], key: str) -> str | None:
    """Empty CSV strings become NULL; strip surrounding whitespace."""
    raw = row.get(key)
    if raw is None:
        return None
    raw = raw.strip()
    return raw if raw else None


def _text(row: dict[str, str | None], key: str) -> str | None:
    return _clean(row, key)


def _int(row: dict[str, str | None], key: str) -> int | None:
    raw = _clean(row, key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"column {key}: invalid integer value {raw!r}") from None


def _float(row: dict[str, str | None], key: str) -> float | None:
    raw = _clean(row, key)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"column {key}: invalid number value {raw!r}") from None


def _required_float_text(row: dict[str, str | None], key: str) -> tuple[str, float]:
    """Raw numeric text that must be non-empty; returns (raw text, parsed float)."""
    raw = row.get(key)
    if raw is None or not raw.strip():
        raise ValueError(f"column {key}: empty value where a number is required")
    try:
        return raw, float(raw)
    except ValueError:
        raise ValueError(f"column {key}: invalid number value {raw!r}") from None


def _food_row(row: dict[str, str | None]) -> tuple:
    return (
        _int(row, "Food_Code"),
        _text(row, "Food_Description_EN"),
        _text(row, "Food_Description_FR"),
        _text(row, "Alternate_Description_EN"),
        _text(row, "Alternate_Description_FR"),
        _int(row, "Food_Source_Code"),
        _int(row, "USDA_NDB_Code"),
        _int(row, "CNF_Food_Group_Code"),
        _text(row, "Comment_EN"),
        _text(row, "Comment_FR"),
        _text(row, "ScientificName"),
        _text(row, "Food_Last_Updated_Date"),
    )


def _food_group_row(row: dict[str, str | None]) -> tuple:
    return (
        _int(row, "CNF_Food_Group_Code"),
        _text(row, "CNF_Food_Group_Description_EN"),
        _text(row, "CNF_Food_Group_Description_FR"),
    )


def _food_source_row(row: dict[str, str | None]) -> tuple:
    return (
        _int(row, "Food_Source_Code"),
        _text(row, "Food_Source_Description_EN"),
        _text(row, "Food_Source_Description_FR"),
    )


def _nutrient_name_row(row: dict[str, str | None]) -> tuple:
    return (
        _int(row, "Nutrient_Code"),
        _text(row, "Nutrient_Symbol"),
        _text(row, "Nutrient_Unit"),
        _text(row, "Nutrient_Name_EN"),
        _text(row, "Nutrient_Name_FR"),
        _text(row, "Tagname"),
        _int(row, "Nutrient_Decimals"),
    )


def _nutrient_amount_row(row: dict[str, str | None]) -> tuple:
    amount_text, amount = _required_float_text(row, "Nutrient_Amount")
    return (
        _int(row, "Food_Code"),
        _int(row, "Nutrient_Code"),
        amount_text,
        amount,
        _text(row, "STD_Error"),
        _text(row, "Observations"),
        _int(row, "Nutrient_Source_Code"),
        _text(row, "Nutrient_Last_Updated_Date"),
    )


def _measure_name_row(row: dict[str, str | None]) -> tuple:
    return (
        _int(row, "Measure_Code"),
        _text(row, "Measure_Description_and_Unit_EN"),
        _text(row, "Measure_Description_and_Unit_FR"),
    )


def _measure_type_row(row: dict[str, str | None]) -> tuple:
    return (
        _int(row, "Measure_Type_Code"),
        _text(row, "Measure_Type_Description_EN"),
        _text(row, "Measure_Type_Description_FR"),
    )


def _measure_weight_row(row: dict[str, str | None]) -> tuple:
    conversion_text, conversion = _required_float_text(row, "Measure_Weight_Conversion")
    return (
        _int(row, "Food_Code"),
        _int(row, "Measure_Type_Code"),
        _int(row, "Measure_Code"),
        conversion_text,
        conversion,
        _text(row, "Measure_Weight_Conversion_Last_Updated_Date"),
    )


def _nutrient_source_row(row: dict[str, str | None]) -> tuple:
    return (
        _int(row, "Nutrient_Source_Code"),
        _text(row, "Nutrient_Source_Description_EN"),
        _text(row, "Nutrient_Source_Description_FR"),
    )


_ROW_BUILDERS = {
    "food": _food_row,
    "food_group": _food_group_row,
    "food_source": _food_source_row,
    "nutrient_name": _nutrient_name_row,
    "nutrient_amount": _nutrient_amount_row,
    "measure_name": _measure_name_row,
    "measure_type": _measure_type_row,
    "measure_weight_conversion": _measure_weight_row,
    "nutrient_source": _nutrient_source_row,
}


def _sha256_file(path: Path) -> str:
    """Sha256 of a file, streamed in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_hash(conn: sqlite3.Connection) -> str:
    """Deterministic hash over the canonical contents of the 10 data tables."""
    digest = hashlib.sha256()
    for table in DATA_TABLES:
        digest.update(f"TABLE {table}\n".encode("utf-8"))
        sql = f"SELECT * FROM {table} ORDER BY {_ORDER_BY[table]}"  # noqa: S608 - fixed map
        for row in conn.execute(sql):
            line = "\x1f".join("" if value is None else str(value) for value in row)
            digest.update((line + "\n").encode("utf-8"))
    return digest.hexdigest()


def _insert_food_fts(conn: sqlite3.Connection) -> int:
    """Populate the FTS index, one row per food ordered by food_code."""
    select = "SELECT food_code, description_en, description_fr FROM food ORDER BY food_code"
    count = 0
    batch = []
    for food_code, name_en, name_fr in conn.execute(select):
        batch.append((food_code, name_en or "", name_fr or ""))
        count += 1
        if len(batch) >= 1000:
            conn.executemany("INSERT INTO food_fts (food_code, name_en, name_fr) VALUES (?,?,?)", batch)
            batch.clear()
    if batch:
        conn.executemany("INSERT INTO food_fts (food_code, name_en, name_fr) VALUES (?,?,?)", batch)
    return count


def build_cnf_db(
    zip_path: Path,
    out_path: Path,
    *,
    zip_url: str = DEFAULT_ZIP_URL,
    dataset_id: str = DEFAULT_DATASET_ID,
    metadata_modified: str = "unknown",
    build_time: str | None = None,
) -> BuildResult:
    """Build the CNF SQLite database from the official (or fixture) CNF zip.

    All CSV tables are streamed row by row from the zip; the 565k-row
    Nutrient_Amount table never touches memory as a whole.
    """
    if build_time is None:
        build_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
    zip_path = Path(zip_path)
    out_path = Path(out_path)

    zip_sha256 = _sha256_file(zip_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for stale in (out_path, Path(f"{out_path}-wal"), Path(f"{out_path}-shm"), Path(f"{out_path}-journal")):
        if stale.exists():
            stale.unlink()

    rows: dict[str, int] = {table: 0 for table in DATA_TABLES}
    conn = sqlite3.connect(out_path)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.executescript(SCHEMA)

        with zipfile.ZipFile(zip_path) as zf:
            members = _member_map(zf)

            # Small reference tables, in a fixed order, sorted by their integer
            # primary key for deterministic insertion order.
            for table in ("food_group", "food_source", "nutrient_name", "measure_name", "measure_type", "nutrient_source"):
                builder = _ROW_BUILDERS[table]
                tuples = sorted(
                    (builder(row) for row in _read_csv(zf, members[_CSV_FILES[table]])),
                    key=lambda t: t[0],
                )
                conn.executemany(_INSERT[table], tuples)
                rows[table] = len(tuples)

            # Foods: sort by integer food code before inserting.
            food_tuples = sorted(
                (_food_row(row) for row in _read_csv(zf, members[_CSV_FILES["food"]])),
                key=lambda t: t[0],
            )
            conn.executemany(_INSERT["food"], food_tuples)
            rows["food"] = len(food_tuples)
            del food_tuples

            # Nutrient_Amount: 565k rows, streamed straight into the DB in file
            # order (zip member + line order are fixed, so this is deterministic).
            amount_rows = _nutrient_amount_row
            batch: list[tuple] = []
            for row in _read_csv(zf, members[_CSV_FILES["nutrient_amount"]]):
                batch.append(amount_rows(row))
                if len(batch) >= 10000:
                    conn.executemany(_INSERT["nutrient_amount"], batch)
                    rows["nutrient_amount"] += len(batch)
                    batch.clear()
            if batch:
                conn.executemany(_INSERT["nutrient_amount"], batch)
                rows["nutrient_amount"] += len(batch)
                batch.clear()

            # Measure_Weight_Conversion: file order (fixed), streamed per table.
            conversions = [
                _measure_weight_row(row) for row in _read_csv(zf, members[_CSV_FILES["measure_weight_conversion"]])
            ]
            conn.executemany(_INSERT["measure_weight_conversion"], conversions)
            rows["measure_weight_conversion"] = len(conversions)
            del conversions

        # FTS index: one row per food, ordered by food_code.
        rows["food_fts"] = _insert_food_fts(conn)

        content_hash = _content_hash(conn)

        provenance: dict[str, str] = {
            "dataset_id": dataset_id,
            "zip_url": zip_url,
            "zip_sha256": zip_sha256,
            "metadata_modified": metadata_modified,
            "build_time": build_time,
            "content_hash": content_hash,
        }
        for table in DATA_TABLES:
            provenance[f"rows_{table}"] = str(rows[table])
        conn.executemany("INSERT INTO provenance (key, value) VALUES (?, ?)", sorted(provenance.items()))

        conn.commit()
    finally:
        conn.close()

    return BuildResult(
        out_path=out_path,
        size_bytes=out_path.stat().st_size,
        rows=rows,
        content_hash=content_hash,
        zip_sha256=zip_sha256,
        build_time=build_time,
    )
