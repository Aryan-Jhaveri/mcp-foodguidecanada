import sqlite3
import os
import sys

# Handle imports using absolute path resolution
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Add paths to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.config import DB_FILE
except ImportError:
    try:
        from config import DB_FILE
    except ImportError as e:
        print(f"Error importing config: {e}", file=sys.stderr)
        # Fallback to default
        DB_FILE = "foodguide_data.db"

def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    # Return rows as dictionary-like objects
    conn.row_factory = sqlite3.Row
    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    return conn