import os
import sqlite3

from foodguide.config import DB_FILE


def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_FILE)), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    # Return rows as dictionary-like objects
    conn.row_factory = sqlite3.Row
    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
