"""
Configuration parameters for the Canada's Food Guide MCP Server
"""

import os

# Canonical live base URL for every canada.ca page the builders fetch. The
# URLs in the builder modules are defined against this constant so the default
# behaviour stays byte-identical, while source_base_url() lets tests point the
# build tools at another base (e.g. a local http.server fixture) purely via
# the FOODGUIDE_SOURCE_BASE_URL environment variable.
DEFAULT_SOURCE_BASE_URL = "https://www.canada.ca"


def source_base_url() -> str:
    """Base URL the data builders fetch Health Canada pages from, at call time.

    Defaults to the live canada.ca site. Set ``FOODGUIDE_SOURCE_BASE_URL`` to
    serve the Health Canada pages from another base (e.g. a local http.server
    fixture in tests); the value is read at call time, never at import time.
    A single trailing slash is stripped so paths can be appended directly.
    """
    return os.environ.get("FOODGUIDE_SOURCE_BASE_URL", DEFAULT_SOURCE_BASE_URL).rstrip("/")

# Database configuration. The SQLite database is NOT bundled with the package;
# it is built separately (see HOM-76). Default location is a per-user state
# directory so an installed package never writes into its own source tree.
_default_db_dir = os.environ.get(
    "FOODGUIDE_STATE_DIR", os.path.expanduser("~/.local/state/foodguide")
)
_default_db_path = os.path.join(_default_db_dir, "foodguide_data.db")

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
