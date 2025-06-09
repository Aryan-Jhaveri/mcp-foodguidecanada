from fastmcp import FastMCP
import sys
import os
import logging
import traceback
import signal
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

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
    from src.db.eer_tools import register_eer_tools
    from src.db.cnf_tools import register_cnf_tools
    from src.config import DB_FILE, TOOL_TIMEOUT_SECONDS
except ImportError:
    try:
        from api.recipe import RecipeFetcher
        from src.api.recipe import register_recipe_tools
        from api.search import RecipeSearcher
        from models.filters import SearchFilters
        from db.queries import register_db_tools
        from db.eer_tools import register_eer_tools
        from db.cnf_tools import register_cnf_tools
        from config import DB_FILE, TOOL_TIMEOUT_SECONDS
    except ImportError as e:
        print(f"Error importing modules: {e}", file=sys.stderr)
        sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
#logger = logging.getLogger(__name__)

# Global flag to track if server should shutdown gracefully
_shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    _shutdown_requested = True
    #logger.info(f"Received signal {signum}, initiating graceful shutdown...")

@contextmanager
def connection_error_handler(operation_name: str):
    """Context manager to handle connection errors gracefully."""
    try:
        yield
    except BrokenPipeError as e:
        #logger.warning(f"Client disconnected during {operation_name}: {e}")
        # Don't re-raise - this is expected when client disconnects
        pass
    except ConnectionResetError as e:
        #logger.warning(f"Connection reset during {operation_name}: {e}")
        # Don't re-raise - this is expected when client disconnects
        pass
    except Exception as e:
        # Check if it's a broken resource error from FastMCP
        if "BrokenResourceError" in str(type(e)) or "broken" in str(e).lower():
            #logger.warning(f"Resource broken during {operation_name}: {e}")
            # Don't re-raise - this is expected when client disconnects
            pass
        else:
            #logger.error(f"Unexpected error during {operation_name}: {e}")
            #logger.error(traceback.format_exc())
            raise

def create_server() -> FastMCP:
    """Create and configure the MCP server with all tools registered."""
    # Remove all metadata from constructor
    mcp = FastMCP()
    
    try:
        with connection_error_handler("tool registration"):
            register_recipe_tools(mcp)
            register_db_tools(mcp)
            try:
                register_eer_tools(mcp)
                #logger.info("EER tools registered successfully")
            except Exception as e:
                #logger.warning(f"EER tools not available: {e}")
                pass
            try:
                register_cnf_tools(mcp)
                #logger.info("CNF tools registered successfully")
            except Exception as e:
                #logger.warning(f"CNF tools not available: {e}")
                pass
    except Exception as e:
        #logger.error(f"ERROR during tool registration: {e}")
        #logger.error(traceback.format_exc())
        raise
    
    #logger.info("MCP server created successfully with all available tools")
    return mcp

if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        #logger.info(f"Starting MCP server with database: {os.path.abspath(DB_FILE)}")
        #logger.info(f"Tool timeout configured: {TOOL_TIMEOUT_SECONDS} seconds")
        
        mcp = create_server()
        
        # Use connection error handler around the main server run
        with connection_error_handler("server execution"):
            #logger.info("MCP server starting...")
            mcp.run()
            
    except KeyboardInterrupt:
        #logger.info("Server shutdown requested by user")
        pass
    except Exception as e:
        if "BrokenResourceError" in str(type(e)) or "broken" in str(e).lower():
            #logger.warning(f"Client connection lost, shutting down gracefully: {e}")
            pass
        else:
            #logger.error(f"Server error: {e}")
            #logger.error(traceback.format_exc())
            sys.exit(1)
    finally:
        #logger.info("MCP server shutdown complete")
        pass