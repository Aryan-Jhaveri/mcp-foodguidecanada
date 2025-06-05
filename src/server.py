from fastmcp import FastMCP
import sys
import os
from typing import List, Dict, Any, Optional

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
src_dir = script_dir

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.api.recipe import RecipeFetcher
    from src.api.recipe import register_recipe_tools
    from src.api.search import RecipeSearcher
    from src.models.filters import SearchFilters
    from src.db.queries import register_db_tools
    from src.config import DB_FILE
except ImportError:
    try:
        from api.recipe import RecipeFetcher
        from src.api.recipe import register_recipe_tools
        from api.search import RecipeSearcher
        from models.filters import SearchFilters
        from db.queries import register_db_tools
        from config import DB_FILE
    except ImportError as e:
        print(f"Error importing modules: {e}", file=sys.stderr)
        sys.exit(1)
def create_server() -> FastMCP:
    """Create and configure the MCP server with all tools registered."""
    # Remove all metadata from constructor
    mcp = FastMCP()
    
    try:
        register_recipe_tools(mcp)
        register_db_tools(mcp)
    except Exception as e:
        print(f"ERROR during tool registration: {e}", file=sys.stderr)
        raise
    
    return mcp

if __name__ == "__main__":
    try:
        print(f"Database file location: {os.path.abspath(DB_FILE)}", file=sys.stderr)
        mcp = create_server()
        
        # Call run() without any parameters
        mcp.run()
        
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)