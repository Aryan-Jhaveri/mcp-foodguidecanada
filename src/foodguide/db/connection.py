import os
import sqlite3

from foodguide import config

# Kept for backwards compatibility: the import-time default database path.
# New code (and tests) should call db_file(), which resolves at call time.
DB_FILE = config.DB_FILE


def db_file() -> str:
    """SQLite database path, resolved at call time from the environment.

    Resolution order: ``FOODGUIDE_DB_FILE`` if set, else
    ``<FOODGUIDE_STATE_DIR>/foodguide_data.db`` if ``FOODGUIDE_STATE_DIR`` is
    set, else the module-level ``DB_FILE`` (the import-time default,
    ``config.DB_FILE``, kept as a module global for backwards compatibility).
    Reading the environment at call time (not import time) lets tests point
    the database at a temporary directory with ``monkeypatch.setenv`` alone —
    no attribute patching required.
    """
    env_db = os.environ.get("FOODGUIDE_DB_FILE")
    if env_db:
        return env_db
    env_state_dir = os.environ.get("FOODGUIDE_STATE_DIR")
    if env_state_dir:
        return os.path.join(env_state_dir, "foodguide_data.db")
    return DB_FILE


def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    # db_file() (not the import-time DB_FILE constant) so tests can point the
    # database at a temporary directory via FOODGUIDE_DB_FILE /
    # FOODGUIDE_STATE_DIR alone; no attribute patching needed.
    path = db_file()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    # Return rows as dictionary-like objects
    conn.row_factory = sqlite3.Row
    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
