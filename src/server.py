# Suppress Pydantic deprecation warnings to reduce server startup noise
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")
warnings.filterwarnings("ignore", message=".*PydanticDeprecatedSince20.*")
warnings.filterwarnings("ignore", message=".*min_items.*deprecated.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*max_items.*deprecated.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*@validator.*deprecated.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*class-based.*config.*deprecated.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*Valid config keys have changed.*", category=UserWarning, module="pydantic")

from fastmcp import FastMCP
import sys
import os
import logging
import traceback
import signal
import argparse
from typing import List, Dict, Any, Optional
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO

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
    from src.db.math_tools import register_math_tools
    from src.db.dri_tools import register_dri_tools, register_session_dri_tools
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
        from db.math_tools import register_math_tools
        from db.dri_tools import register_dri_tools, register_session_dri_tools
        from db.eer_tools import register_eer_tools
        from db.cnf_tools import register_cnf_tools
        from config import DB_FILE, TOOL_TIMEOUT_SECONDS
    except ImportError as e:
        print(f"Error importing modules: {e}", file=sys.stderr)
        sys.exit(1)

# Configure logging suppression based on environment variables
SUPPRESS_MCP_LOGS = os.getenv('SUPPRESS_MCP_LOGS', 'true').lower() == 'true'
LOG_LEVEL = os.getenv('FOODGUIDE_LOG_LEVEL', 'CRITICAL')

if SUPPRESS_MCP_LOGS:
    # Completely disable logging to prevent FastMCP protocol leakage
    logging.basicConfig(
        level=logging.CRITICAL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[]  # No handlers = no output
    )
    
    # Suppress ALL framework logging completely
    logging.getLogger('fastmcp').disabled = True
    logging.getLogger('mcp').disabled = True
    logging.getLogger('rich').disabled = True
    logging.getLogger('uvicorn').disabled = True
    logging.getLogger('uvicorn.access').disabled = True
    logging.getLogger('uvicorn.error').disabled = True
    logging.getLogger('asyncio').disabled = True
    
    # Disable all logging below CRITICAL globally
    logging.disable(logging.CRITICAL)
else:
    # Standard logging configuration for debugging
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )

# Redirect stdout/stderr to suppress protocol communication leakage
class QuietStream:
    def write(self, data): pass
    def flush(self): pass
    def isatty(self): return False

# Create quiet stderr for FastMCP stdio handling
_original_stderr = sys.stderr
_quiet_stderr = QuietStream() if SUPPRESS_MCP_LOGS else sys.stderr

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

def create_server(enable_db: bool = True) -> FastMCP:
    """Create and configure the MCP server with all tools registered.

    Args:
        enable_db: When True (stdio mode), all tools including SQLite-dependent ones
                   are registered. When False (HTTP mode), only web-scraping, in-memory,
                   and pure calculation tools are registered.
    """
    # Conditionally suppress stderr during FastMCP creation to prevent protocol leakage
    if SUPPRESS_MCP_LOGS:
        with redirect_stderr(_quiet_stderr):
            mcp = FastMCP()
    else:
        mcp = FastMCP()

    try:
        with connection_error_handler("tool registration"):
            # Always available: recipe scraping tools
            register_recipe_tools(mcp)

            # Always available: pure math/calculation tools
            try:
                register_math_tools(mcp)
            except Exception:
                pass

            # Always available: DRI web scraping + in-memory session tools
            try:
                register_dri_tools(mcp)
                register_session_dri_tools(mcp)
            except Exception:
                pass

            # EER tools: calc always, profile tools gated by enable_db
            try:
                register_eer_tools(mcp, enable_db=enable_db)
            except Exception:
                pass

            # CNF tools: search/scrape always, recipe-analysis gated by enable_db
            try:
                register_cnf_tools(mcp, enable_db=enable_db)
            except Exception:
                pass

            # DB-dependent tools: favorites, sessions, schema management
            if enable_db:
                register_db_tools(mcp)
    except Exception as e:
        # Only output critical errors to original stderr
        print(f"CRITICAL: Tool registration failed: {e}", file=_original_stderr)
        raise

    return mcp

if __name__ == "__main__":
    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="MCP Food Guide Canada Server")
    parser.add_argument(
        '--transport', choices=['stdio', 'http'], default=None,
        help='Transport type (default: stdio). Env var: MCP_TRANSPORT'
    )
    parser.add_argument(
        '--host', type=str, default=None,
        help='Host for HTTP transport (default: 0.0.0.0). Env var: HOST'
    )
    parser.add_argument(
        '--port', type=int, default=None,
        help='Port for HTTP transport (default: 8000). Env var: PORT'
    )
    args = parser.parse_args()

    # Resolve settings: CLI flag > env var > default
    transport = args.transport or os.getenv('MCP_TRANSPORT', 'stdio')
    host = args.host or os.getenv('HOST', '0.0.0.0')
    port = args.port or int(os.getenv('PORT', '8000'))
    enable_db = (transport == 'stdio')

    # In HTTP mode, logs can safely go to stderr (no protocol leakage concern)
    if transport == 'http':
        SUPPRESS_MCP_LOGS = False
        logging.disable(logging.NOTSET)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Create server with DB gating based on transport mode
        mcp = create_server(enable_db=enable_db)

        if transport == 'http':
            mcp.run(transport='streamable-http', host=host, port=port)
        else:
            # stdio mode: suppress stderr to prevent protocol leakage
            if SUPPRESS_MCP_LOGS:
                with redirect_stderr(_quiet_stderr):
                    with connection_error_handler("server execution"):
                        mcp.run(transport='stdio')
            else:
                with connection_error_handler("server execution"):
                    mcp.run(transport='stdio')

    except KeyboardInterrupt:
        pass
    except Exception as e:
        if "BrokenResourceError" in str(type(e)) or "broken" in str(e).lower():
            pass
        else:
            print(f"CRITICAL: Server error: {e}", file=_original_stderr)
            sys.exit(1)
    finally:
        pass