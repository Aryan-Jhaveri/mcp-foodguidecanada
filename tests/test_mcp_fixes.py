"""Regression tests for MCP fixes found while testing the packaged server (HOM-74)."""
import os

from foodguide.db import connection


def test_connection_creates_missing_state_dir(tmp_path, monkeypatch):
    db = tmp_path / "nested" / "state" / "foodguide_data.db"
    monkeypatch.setenv("FOODGUIDE_DB_FILE", str(db))
    conn = connection.get_db_connection()
    conn.close()
    assert os.path.isfile(db)


def test_create_server_initializes_session_tables(tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "fresh" / "foodguide_data.db"
    monkeypatch.setenv("FOODGUIDE_DB_FILE", str(db))
    from foodguide.server import create_server

    create_server(enable_db=True)
    tables = {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master")}
    assert {"user_favorites", "user_profiles", "temp_cnf_foods"} <= tables
