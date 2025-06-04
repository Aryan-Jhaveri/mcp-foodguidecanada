"""
Configuration parameters for the Canada's Food Guide MCP Server
"""

import os

# Database configuration - use absolute path to ensure proper location
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
_default_db_path = os.path.join(_project_root, "foodguide_data.db")

DB_FILE = os.environ.get("FOODGUIDE_DB_FILE", _default_db_path)

# Query limits
MAX_QUERY_ROWS = 500

# Recipe session management
MAX_TEMP_RECIPES = 50  # Maximum temporary recipes to store per session