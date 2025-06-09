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

# Operation timeout configuration
TOOL_TIMEOUT_SECONDS = int(os.environ.get("TOOL_TIMEOUT_SECONDS", "30"))
BULK_OPERATION_TIMEOUT = int(os.environ.get("BULK_OPERATION_TIMEOUT", "60"))
PROGRESS_REPORT_INTERVAL = int(os.environ.get("PROGRESS_REPORT_INTERVAL", "3"))

# CNF API configuration
CNF_RATE_LIMIT = float(os.environ.get("CNF_RATE_LIMIT", "0.5"))  # Reduced from 1.0 for better performance
CNF_MAX_CONCURRENT = int(os.environ.get("CNF_MAX_CONCURRENT", "3"))  # Max concurrent requests
CNF_CACHE_TTL = int(os.environ.get("CNF_CACHE_TTL", "1800"))  # 30 minutes cache TTL