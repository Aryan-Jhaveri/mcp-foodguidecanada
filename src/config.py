"""
Configuration parameters for the Canada's Food Guide MCP Server
"""

import os

# Database configuration
DB_FILE = os.environ.get("FOODGUIDE_DB_FILE", "foodguide_data.db")

# Query limits
MAX_QUERY_ROWS = 500

# Recipe session management
MAX_TEMP_RECIPES = 50  # Maximum temporary recipes to store per session