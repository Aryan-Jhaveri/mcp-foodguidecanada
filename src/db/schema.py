import sqlite3
from typing import Dict, Any
from .connection import get_db_connection

def initialize_database() -> Dict[str, str]:
    """
    Initialize the Canada's Food Guide recipe database with required tables.
    
    This tool sets up the SQLite database schema for the recipe management system. It creates
    the persistent storage table for user favorites that will persist across all sessions.
    This must be run once before using any favorites-related tools.
    
    What this tool creates:
    - user_favorites table for persistent recipe bookmarking
    - Proper indexing and constraints for data integrity
    - Database structure ready for session-based temporary recipe storage
    
    Use this tool when:
    - First time setting up the recipe database
    - After database corruption or reset
    - Ensuring database schema is current
    - Before using any favorites or session storage tools
    
    Returns:
        Dict with success confirmation or detailed error message if database setup fails
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Create persistent USER_FAVORITES table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_favorites (
                    favorite_id TEXT PRIMARY KEY,
                    recipe_url TEXT NOT NULL,
                    recipe_title TEXT,
                    user_session TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    custom_notes TEXT,
                    UNIQUE(recipe_url, user_session)
                )
            """)
            
            conn.commit()
            return {"success": "Database initialized successfully"}
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error initializing database: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error initializing database: {e}"}

def create_recipe_session_tables(session_id: str) -> Dict[str, str]:
    """
    Create temporary database tables for a recipe session to store fetched recipe data.
    
    This tool sets up normalized temporary tables for storing and analyzing multiple recipes
    during a session. The tables are automatically created when needed but this tool allows
    manual creation for advanced workflows or pre-planning.
    
    What this tool creates for the session:
    - temp_recipes_{session_id}: Main recipe metadata and details
    - temp_recipe_ingredients_{session_id}: Individual ingredients with ordering
    - temp_recipe_instructions_{session_id}: Step-by-step cooking instructions
    - Foreign key relationships for data integrity
    
    Use this tool when:
    - Pre-creating session storage for batch recipe processing
    - Setting up dedicated recipe analysis workflows
    - Manually managing session lifecycle
    - Ensuring session tables exist before bulk operations
    
    Note: Session tables are automatically created when storing recipes, so this tool
    is optional for normal workflows but useful for advanced session management.
    
    Args:
        session_id: Unique identifier for this recipe session (use descriptive names like 
                   'meal_planning_2024' or 'thanksgiving_recipes' for organization)
        
    Returns:
        Dict with success confirmation and session details, or error message if creation fails
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Main recipes table for this session
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS temp_recipes_{session_id} (
                    recipe_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    slug TEXT,
                    url TEXT NOT NULL,
                    base_servings INTEGER,
                    prep_time TEXT,
                    cook_time TEXT,
                    categories TEXT,  -- JSON string
                    tips TEXT,        -- JSON string
                    recipe_highlights TEXT,  -- JSON string
                    image_url TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Recipe ingredients table for this session
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS temp_recipe_ingredients_{session_id} (
                    ingredient_id TEXT PRIMARY KEY,
                    recipe_id TEXT NOT NULL,
                    ingredient_name TEXT NOT NULL,
                    amount TEXT,
                    unit TEXT,
                    ingredient_order INTEGER,
                    FOREIGN KEY (recipe_id) REFERENCES temp_recipes_{session_id}(recipe_id)
                )
            """)
            
            # Recipe instructions table for this session
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS temp_recipe_instructions_{session_id} (
                    instruction_id TEXT PRIMARY KEY,
                    recipe_id TEXT NOT NULL,
                    instruction_text TEXT NOT NULL,
                    instruction_order INTEGER,
                    FOREIGN KEY (recipe_id) REFERENCES temp_recipes_{session_id}(recipe_id)
                )
            """)
            
            conn.commit()
            return {"success": f"Recipe session tables created for session {session_id}"}
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error creating session tables: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error creating session tables: {e}"}

def cleanup_session_tables(session_id: str) -> Dict[str, str]:
    """
    Remove temporary database tables for a completed recipe session.
    
    This tool permanently deletes all temporary recipe data for a specific session to free up
    database space and maintain clean storage. Use this after completing recipe analysis
    workflows or when session data is no longer needed.
    
    What this tool removes:
    - All recipe data stored in the session (recipes, ingredients, instructions)
    - Associated database tables for the session
    - All temporary calculations and analysis data
    
    Important: This action cannot be undone. Ensure you've saved any important recipe data
    to favorites or exported it before cleanup.
    
    Use this tool when:
    - Finished with a recipe analysis session
    - Cleaning up old or unused session data
    - Managing database storage space
    - Completing meal planning workflows
    - Preparing for new recipe sessions
    
    Args:
        session_id: Identifier of the session to clean up (must match exactly with existing session)
        
    Returns:
        Dict with confirmation of cleanup completion or error message if session not found
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Drop session tables
            tables_to_drop = [
                f"temp_recipe_instructions_{session_id}",
                f"temp_recipe_ingredients_{session_id}", 
                f"temp_recipes_{session_id}"
            ]
            
            for table in tables_to_drop:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
            
            conn.commit()
            return {"success": f"Session tables cleaned up for session {session_id}"}
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error cleaning up session: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error cleaning up session: {e}"}

def list_active_sessions() -> Dict[str, Any]:
    """
    List all active recipe sessions currently stored in the database.
    
    This tool discovers all recipe sessions that have temporary data stored in the database
    by scanning for session table patterns. Use this to manage multiple recipe workflows,
    find forgotten sessions, or get an overview of current recipe analysis work.
    
    The returned information includes:
    - Session IDs for all active recipe sessions
    - Implicit indication of which sessions have stored recipe data
    - Overview of database storage usage for sessions
    
    Use this tool to:
    - Find existing recipe sessions to continue working with
    - Identify sessions that may need cleanup
    - Get an overview of current recipe analysis projects
    - Manage multiple concurrent recipe workflows
    - Check if specific session names are already in use
    
    Returns:
        Dict containing 'sessions' array with all active session identifiers,
        or error message if database scanning fails
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Find tables matching temp_recipes_* pattern
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name LIKE 'temp_recipes_%'
            """)
            
            session_tables = cursor.fetchall()
            sessions = []
            
            for table in session_tables:
                # Extract session ID from table name
                table_name = table['name']
                if table_name.startswith('temp_recipes_'):
                    session_id = table_name.replace('temp_recipes_', '')
                    sessions.append(session_id)
            
            return {"sessions": sessions}
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error listing sessions: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error listing sessions: {e}"}