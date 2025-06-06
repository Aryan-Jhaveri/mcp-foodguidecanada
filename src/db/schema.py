import sqlite3
import json
from typing import Dict, Any, List
from .connection import get_db_connection

def initialize_database() -> Dict[str, str]:
    """
    Initialize the Canada's Food Guide recipe database with required tables.
    
    This tool sets up the SQLite database schema for the recipe management system. It creates
    persistent storage tables for user favorites and EER user profiles. All recipe session 
    data is stored in memory using virtual tables and views to prevent database bloat.
    
    What this tool creates:
    - user_favorites table for persistent recipe bookmarking
    - user_profiles table for persistent EER user profile storage
    - Proper indexing and constraints for data integrity
    - Virtual table infrastructure for in-memory recipe storage
    
    Use this tool when:
    - First time setting up the recipe database
    - After database corruption or reset
    - Ensuring database schema is current
    - Before using any favorites-related or EER profile tools
    
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
            
            # Create persistent USER_PROFILES table for EER calculations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    profile_id TEXT PRIMARY KEY,
                    age INTEGER NOT NULL,
                    gender TEXT NOT NULL CHECK(gender IN ('male', 'female')),
                    height_cm REAL NOT NULL,
                    weight_kg REAL NOT NULL,
                    pal_category TEXT NOT NULL CHECK(pal_category IN ('inactive', 'low_active', 'active', 'very_active')),
                    pregnancy_status TEXT NOT NULL DEFAULT 'not_pregnant' CHECK(pregnancy_status IN ('not_pregnant', 'first_trimester', 'second_trimester', 'third_trimester')),
                    lactation_status TEXT NOT NULL DEFAULT 'not_lactating' CHECK(lactation_status IN ('not_lactating', 'lactating_0_6_months', 'lactating_7_12_months')),
                    gestation_weeks INTEGER,
                    pre_pregnancy_bmi REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create TEMPORARY NUTRITION ANALYSIS TABLES (session-based, auto-cleanup)
            
            # Session tracking for cleanup
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Temporary recipes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_recipes (
                    session_id TEXT NOT NULL,
                    recipe_id TEXT NOT NULL,
                    title TEXT,
                    slug TEXT,
                    url TEXT,
                    base_servings INTEGER,
                    prep_time TEXT,
                    cook_time TEXT,
                    categories TEXT,
                    tips TEXT,
                    recipe_highlights TEXT,
                    image_url TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id, recipe_id)
                )
            """)
            
            # Temporary recipe ingredients table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_recipe_ingredients (
                    session_id TEXT NOT NULL,
                    ingredient_id TEXT NOT NULL,
                    recipe_id TEXT NOT NULL,
                    ingredient_name TEXT,
                    amount REAL,
                    unit TEXT,
                    cnf_food_code TEXT,
                    ingredient_order INTEGER,
                    ingredient_list_org TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id, ingredient_id),
                    FOREIGN KEY (session_id, recipe_id) REFERENCES temp_recipes(session_id, recipe_id)
                )
            """)
            
            # Temporary CNF foods table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_cnf_foods (
                    session_id TEXT NOT NULL,
                    cnf_food_code TEXT NOT NULL,
                    food_description TEXT,
                    food_group TEXT,
                    refuse_flag BOOLEAN,
                    refuse_amount REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id, cnf_food_code)
                )
            """)
            
            # Temporary CNF nutrients table  
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_cnf_nutrients (
                    session_id TEXT NOT NULL,
                    cnf_food_code TEXT NOT NULL,
                    nutrient_name TEXT NOT NULL,
                    nutrient_value REAL,
                    per_amount REAL,
                    unit TEXT,
                    nutrient_symbol TEXT,
                    standard_error TEXT,
                    number_observations INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id, cnf_food_code, nutrient_name),
                    FOREIGN KEY (session_id, cnf_food_code) REFERENCES temp_cnf_foods(session_id, cnf_food_code)
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_temp_sessions_last_accessed ON temp_sessions(last_accessed)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_temp_recipe_ingredients_recipe_id ON temp_recipe_ingredients(session_id, recipe_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_temp_recipe_ingredients_cnf_code ON temp_recipe_ingredients(session_id, cnf_food_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_temp_cnf_nutrients_food_code ON temp_cnf_nutrients(session_id, cnf_food_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_temp_cnf_nutrients_nutrient_name ON temp_cnf_nutrients(session_id, nutrient_name)")
            
            conn.commit()
            return {"success": "Database initialized successfully - persistent favorites, user profiles, and temporary nutrition analysis tables created"}
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error initializing database: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error initializing database: {e}"}

# Global in-memory storage for recipe sessions
_recipe_sessions = {}

def create_virtual_recipe_session(session_id: str) -> Dict[str, str]:
    """
    Create virtual in-memory storage for a recipe session to store fetched recipe data.
    
    This tool sets up in-memory data structures for storing and analyzing multiple recipes
    during a session. All data is stored in memory and automatically cleaned up when the
    session ends, preventing database bloat from temporary recipe storage.
    
    What this tool creates for the session:
    - In-memory recipes storage: Main recipe metadata and details
    - In-memory ingredients storage: Individual ingredients with ordering
    - In-memory instructions storage: Step-by-step cooking instructions
    - Virtual relationships for data integrity
    
    Use this tool when:
    - Starting a new recipe analysis session
    - Pre-creating session storage for batch recipe processing
    - Setting up dedicated recipe analysis workflows
    - Ensuring session storage exists before bulk operations
    
    Note: Virtual sessions are automatically created when storing recipes, so this tool
    is optional for normal workflows but useful for advanced session management.
    
    Args:
        session_id: Unique identifier for this recipe session (use descriptive names like 
                   'meal_planning_2024' or 'thanksgiving_recipes' for organization)
        
    Returns:
        Dict with success confirmation and session details
    """
    try:
        if session_id not in _recipe_sessions:
            _recipe_sessions[session_id] = {
                # Legacy dictionary structures (for backward compatibility)
                'recipes': {},
                'ingredients': {},
                'instructions': {},
                'created_at': None,
                
                # NEW: SQL-ready table structures following v2.0 schema
                'recipe_ingredients': [],          # Table: ingredient_id, recipe_id, ingredient_name, amount, unit, cnf_food_code
                'cnf_foods': [],                   # Table: cnf_food_code, food_description  
                'cnf_nutrients': [],               # Table: cnf_food_code, nutrient_name, nutrient_value, per_amount, unit
                'recipe_calculations': [],         # Table: calc_id, recipe_id, serving_multiplier, nutritional_totals
                
                # Legacy CNF data structures (to be phased out)
                'nutrient_profiles': {},           # CNF nutrient data by food_code
                'ingredient_cnf_matches': {},      # Links ingredient_id to CNF food_code
                'nutrition_summaries': {},         # Calculated recipe nutrition data
                'cnf_search_results': {},          # Cached CNF search results
                
                # DRI (Dietary Reference Intake) data structures
                'dri_reference_tables': {},        # Cached complete DRI tables
                'dri_user_profiles': {},           # User demographics for DRI analysis
                'dri_lookups': {},                 # Specific DRI value lookups
                'dri_comparisons': {},             # Stored adequacy assessments
                'dri_macro_calculations': {}       # EER-based macronutrient targets
            }
        
        return {"success": f"Virtual recipe session created for session {session_id}"}
        
    except Exception as e:
        return {"error": f"Unexpected error creating virtual session: {e}"}

def cleanup_virtual_session(session_id: str) -> Dict[str, str]:
    """
    Remove virtual in-memory storage for a completed recipe session.
    
    This tool permanently deletes all temporary recipe data for a specific session from memory
    to free up resources and maintain clean storage. Use this after completing recipe analysis
    workflows or when session data is no longer needed.
    
    What this tool removes:
    - All recipe data stored in the session (recipes, ingredients, instructions)
    - Associated in-memory data structures for the session
    - All temporary calculations and analysis data
    
    Important: This action cannot be undone. Ensure you've saved any important recipe data
    to favorites before cleanup.
    
    Use this tool when:
    - Finished with a recipe analysis session
    - Cleaning up old or unused session data
    - Managing memory usage
    - Completing meal planning workflows
    - Preparing for new recipe sessions
    
    Args:
        session_id: Identifier of the session to clean up (must match exactly with existing session)
        
    Returns:
        Dict with confirmation of cleanup completion or error message if session not found
    """
    try:
        if session_id in _recipe_sessions:
            del _recipe_sessions[session_id]
            return {"success": f"Virtual session cleaned up for session {session_id}"}
        else:
            return {"message": f"Session {session_id} not found or already cleaned up"}
            
    except Exception as e:
        return {"error": f"Unexpected error cleaning up virtual session: {e}"}

def list_active_virtual_sessions() -> Dict[str, Any]:
    """
    List all active recipe sessions currently stored in memory.
    
    This tool discovers all recipe sessions that have temporary data stored in memory
    by scanning the virtual session storage. Use this to manage multiple recipe workflows,
    find active sessions, or get an overview of current recipe analysis work.
    
    The returned information includes:
    - Session IDs for all active virtual recipe sessions
    - Recipe counts for each session
    - Memory usage overview for sessions
    
    Use this tool to:
    - Find existing recipe sessions to continue working with
    - Identify sessions that may need cleanup
    - Get an overview of current recipe analysis projects
    - Manage multiple concurrent recipe workflows
    - Check if specific session names are already in use
    
    Returns:
        Dict containing 'sessions' array with session details including recipe counts
    """
    try:
        sessions = []
        for session_id, session_data in _recipe_sessions.items():
            session_info = {
                'session_id': session_id,
                'recipe_count': len(session_data['recipes']),
                'created_at': session_data['created_at']
            }
            sessions.append(session_info)
        
        return {"sessions": sessions}
        
    except Exception as e:
        return {"error": f"Unexpected error listing virtual sessions: {e}"}

def get_virtual_session_data(session_id: str) -> Dict[str, Any]:
    """Get virtual session data for internal use by other modules."""
    return _recipe_sessions.get(session_id, None)

def store_recipe_in_virtual_session(session_id: str, recipe_id: str, recipe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Store recipe data in virtual session for internal use by other modules."""
    try:
        # Ensure session exists
        if session_id not in _recipe_sessions:
            create_virtual_recipe_session(session_id)
        
        session = _recipe_sessions[session_id]
        
        # Store recipe data
        session['recipes'][recipe_id] = {
            'recipe_id': recipe_id,
            'title': recipe_data.get('title', ''),
            'slug': recipe_data.get('slug', ''),
            'url': recipe_data.get('url', ''),
            'base_servings': recipe_data.get('servings'),
            'prep_time': recipe_data.get('prep_time', ''),
            'cook_time': recipe_data.get('cook_time', ''),
            'categories': recipe_data.get('categories', []),
            'tips': recipe_data.get('tips', []),
            'recipe_highlights': recipe_data.get('recipe_highlights', []),
            'image_url': recipe_data.get('image_url', ''),
            'created_at': recipe_data.get('created_at')
        }
        
        # Store ingredients (legacy format)
        ingredients = recipe_data.get('ingredients', [])
        for i, ingredient in enumerate(ingredients):
            ingredient_id = f"{recipe_id}_ingredient_{i+1}"
            
            # Legacy dictionary structure
            session['ingredients'][ingredient_id] = {
                'ingredient_id': ingredient_id,
                'recipe_id': recipe_id,
                'ingredient_list_org': ingredient if isinstance(ingredient, str) else str(ingredient),
                'ingredient_name': None,  # To be parsed by LLM using SQL tools
                'amount': None,           # To be parsed by LLM using SQL tools
                'unit': None,             # To be parsed by LLM using SQL tools
                'ingredient_order': i + 1
            }
            
            # NEW: SQL table structure (will be populated during parsing)
            session['recipe_ingredients'].append({
                'ingredient_id': ingredient_id,
                'recipe_id': recipe_id,
                'ingredient_name': None,  # To be parsed
                'amount': None,           # To be parsed
                'unit': None,             # To be parsed  
                'ingredient_order': i + 1,
                'cnf_food_code': None    # To be linked to CNF
            })
        
        # Store instructions
        instructions = recipe_data.get('instructions', [])
        for i, instruction in enumerate(instructions):
            instruction_id = f"{recipe_id}_instruction_{i+1}"
            session['instructions'][instruction_id] = {
                'instruction_id': instruction_id,
                'recipe_id': recipe_id,
                'instruction_text': instruction if isinstance(instruction, str) else str(instruction),
                'instruction_order': i + 1
            }
        
        return {
            "success": f"Recipe stored in virtual session {session_id}",
            "recipe_id": recipe_id,
            "title": recipe_data.get('title', ''),
            "ingredients_count": len(ingredients),
            "instructions_count": len(instructions)
        }
        
    except Exception as e:
        return {"error": f"Unexpected error storing recipe in virtual session: {e}"}

def get_virtual_session_recipes(session_id: str, recipe_id: str = None) -> Dict[str, Any]:
    """Get recipes from virtual session for internal use by other modules."""
    try:
        if session_id not in _recipe_sessions:
            return {"error": f"Virtual session {session_id} not found"}
        
        session = _recipe_sessions[session_id]
        recipes = []
        
        if recipe_id:
            # Get specific recipe
            if recipe_id in session['recipes']:
                recipe = session['recipes'][recipe_id].copy()
                
                # Add ingredients
                recipe['ingredients'] = [
                    ing for ing in session['ingredients'].values() 
                    if ing['recipe_id'] == recipe_id
                ]
                recipe['ingredients'].sort(key=lambda x: x['ingredient_order'])
                
                # Add instructions
                recipe['instructions'] = [
                    inst for inst in session['instructions'].values() 
                    if inst['recipe_id'] == recipe_id
                ]
                recipe['instructions'].sort(key=lambda x: x['instruction_order'])
                
                recipes.append(recipe)
        else:
            # Get all recipes
            for recipe in session['recipes'].values():
                recipe_copy = recipe.copy()
                
                # Add ingredients
                recipe_copy['ingredients'] = [
                    ing for ing in session['ingredients'].values() 
                    if ing['recipe_id'] == recipe['recipe_id']
                ]
                recipe_copy['ingredients'].sort(key=lambda x: x['ingredient_order'])
                
                # Add instructions
                recipe_copy['instructions'] = [
                    inst for inst in session['instructions'].values() 
                    if inst['recipe_id'] == recipe['recipe_id']
                ]
                recipe_copy['instructions'].sort(key=lambda x: x['instruction_order'])
                
                recipes.append(recipe_copy)
        
        return {"recipes": recipes, "session_id": session_id}
        
    except Exception as e:
        return {"error": f"Unexpected error retrieving virtual session recipes: {e}"}

# CNF (Canadian Nutrient File) helper functions

def ensure_cnf_session_structure(session_id: str) -> bool:
    """
    Ensure CNF data structures exist in a virtual session.
    
    Args:
        session_id: Session to check/update
        
    Returns:
        bool: True if session exists and CNF structures are ready, False otherwise
    """
    try:
        if session_id not in _recipe_sessions:
            create_virtual_recipe_session(session_id)
        
        session = _recipe_sessions[session_id]
        
        # Ensure all CNF and DRI structures exist
        cnf_structures = [
            'nutrient_profiles',
            'ingredient_cnf_matches', 
            'nutrition_summaries',
            'cnf_search_results',
            'dri_reference_tables',
            'dri_user_profiles',
            'dri_lookups',
            'dri_comparisons',
            'dri_macro_calculations'
        ]
        
        for structure in cnf_structures:
            if structure not in session:
                session[structure] = {}
        
        return True
        
    except Exception:
        return False

def get_cnf_session_summary(session_id: str) -> Dict[str, Any]:
    """
    Get summary of CNF data in a virtual session.
    
    Args:
        session_id: Session to summarize
        
    Returns:
        Dict with CNF data counts and status
    """
    try:
        session_data = get_virtual_session_data(session_id)
        if session_data is None:
            return {"error": f"Session {session_id} not found"}
        
        return {
            "session_id": session_id,
            "nutrient_profiles_count": len(session_data.get('nutrient_profiles', {})),
            "ingredient_matches_count": len(session_data.get('ingredient_cnf_matches', {})),
            "nutrition_summaries_count": len(session_data.get('nutrition_summaries', {})),
            "search_results_count": len(session_data.get('cnf_search_results', {})),
            "dri_reference_tables_count": len(session_data.get('dri_reference_tables', {})),
            "dri_user_profiles_count": len(session_data.get('dri_user_profiles', {})),
            "dri_lookups_count": len(session_data.get('dri_lookups', {})),
            "dri_comparisons_count": len(session_data.get('dri_comparisons', {})),
            "dri_macro_calculations_count": len(session_data.get('dri_macro_calculations', {})),
            "recipes_count": len(session_data.get('recipes', {})),
            "ingredients_count": len(session_data.get('ingredients', {}))
        }
        
    except Exception as e:
        return {"error": f"Error getting CNF session summary: {e}"}

def clear_cnf_data_from_session(session_id: str, data_type: str = "all") -> Dict[str, Any]:
    """
    Clear specific CNF data from a virtual session.
    
    Args:
        session_id: Session to clean
        data_type: Type of data to clear ('profiles', 'matches', 'summaries', 'searches', 'all')
        
    Returns:
        Dict with cleanup confirmation
    """
    try:
        session_data = get_virtual_session_data(session_id)
        if session_data is None:
            return {"error": f"Session {session_id} not found"}
        
        cleared_items = []
        
        if data_type in ('all', 'profiles'):
            if 'nutrient_profiles' in session_data:
                count = len(session_data['nutrient_profiles'])
                session_data['nutrient_profiles'] = {}
                cleared_items.append(f"{count} nutrient profiles")
        
        if data_type in ('all', 'matches'):
            if 'ingredient_cnf_matches' in session_data:
                count = len(session_data['ingredient_cnf_matches'])
                session_data['ingredient_cnf_matches'] = {}
                cleared_items.append(f"{count} ingredient matches")
        
        if data_type in ('all', 'summaries'):
            if 'nutrition_summaries' in session_data:
                count = len(session_data['nutrition_summaries'])
                session_data['nutrition_summaries'] = {}
                cleared_items.append(f"{count} nutrition summaries")
        
        if data_type in ('all', 'searches'):
            if 'cnf_search_results' in session_data:
                count = len(session_data['cnf_search_results'])
                session_data['cnf_search_results'] = {}
                cleared_items.append(f"{count} search result sets")
        
        return {
            "success": f"Cleared CNF data from session {session_id}",
            "session_id": session_id,
            "data_type": data_type,
            "cleared_items": cleared_items
        }
        
    except Exception as e:
        return {"error": f"Error clearing CNF data: {e}"}

# DRI (Dietary Reference Intake) helper functions

def ensure_dri_session_structure(session_id: str) -> bool:
    """
    Ensure DRI data structures exist in a virtual session.
    
    Args:
        session_id: Session to check/update
        
    Returns:
        bool: True if session exists and DRI structures are ready, False otherwise
    """
    try:
        if session_id not in _recipe_sessions:
            create_virtual_recipe_session(session_id)
        
        session = _recipe_sessions[session_id]
        
        # Ensure all DRI structures exist
        dri_structures = [
            'dri_reference_tables',
            'dri_user_profiles', 
            'dri_lookups',
            'dri_comparisons',
            'dri_macro_calculations'
        ]
        
        for structure in dri_structures:
            if structure not in session:
                session[structure] = {}
        
        return True
        
    except Exception:
        return False

def get_dri_session_summary(session_id: str) -> Dict[str, Any]:
    """
    Get summary of DRI data in a virtual session.
    
    Args:
        session_id: Session to summarize
        
    Returns:
        Dict with DRI data counts and status
    """
    try:
        session_data = get_virtual_session_data(session_id)
        if session_data is None:
            return {"error": f"Session {session_id} not found"}
        
        return {
            "session_id": session_id,
            "dri_reference_tables_count": len(session_data.get('dri_reference_tables', {})),
            "dri_user_profiles_count": len(session_data.get('dri_user_profiles', {})),
            "dri_lookups_count": len(session_data.get('dri_lookups', {})),
            "dri_comparisons_count": len(session_data.get('dri_comparisons', {})),
            "dri_macro_calculations_count": len(session_data.get('dri_macro_calculations', {})),
            "has_dri_data": any([
                session_data.get('dri_reference_tables'),
                session_data.get('dri_user_profiles'),
                session_data.get('dri_lookups'),
                session_data.get('dri_comparisons'),
                session_data.get('dri_macro_calculations')
            ])
        }
        
    except Exception as e:
        return {"error": f"Error getting DRI session summary: {e}"}

def clear_dri_data_from_session(session_id: str, data_type: str = "all") -> Dict[str, Any]:
    """
    Clear specific DRI data from a virtual session.
    
    Args:
        session_id: Session to clean
        data_type: Type of data to clear ('tables', 'profiles', 'lookups', 'comparisons', 'calculations', 'all')
        
    Returns:
        Dict with cleanup confirmation
    """
    try:
        session_data = get_virtual_session_data(session_id)
        if session_data is None:
            return {"error": f"Session {session_id} not found"}
        
        cleared_items = []
        
        if data_type in ('all', 'tables'):
            if 'dri_reference_tables' in session_data:
                count = len(session_data['dri_reference_tables'])
                session_data['dri_reference_tables'] = {}
                cleared_items.append(f"{count} DRI reference tables")
        
        if data_type in ('all', 'profiles'):
            if 'dri_user_profiles' in session_data:
                count = len(session_data['dri_user_profiles'])
                session_data['dri_user_profiles'] = {}
                cleared_items.append(f"{count} DRI user profiles")
        
        if data_type in ('all', 'lookups'):
            if 'dri_lookups' in session_data:
                count = len(session_data['dri_lookups'])
                session_data['dri_lookups'] = {}
                cleared_items.append(f"{count} DRI lookups")
        
        if data_type in ('all', 'comparisons'):
            if 'dri_comparisons' in session_data:
                count = len(session_data['dri_comparisons'])
                session_data['dri_comparisons'] = {}
                cleared_items.append(f"{count} DRI comparisons")
        
        if data_type in ('all', 'calculations'):
            if 'dri_macro_calculations' in session_data:
                count = len(session_data['dri_macro_calculations'])
                session_data['dri_macro_calculations'] = {}
                cleared_items.append(f"{count} DRI macro calculations")
        
        return {
            "success": f"Cleared DRI data from session {session_id}",
            "session_id": session_id,
            "data_type": data_type,
            "cleared_items": cleared_items
        }
        
    except Exception as e:
        return {"error": f"Error clearing DRI data: {e}"}

# TEMPORARY PERSISTENT STORAGE FUNCTIONS

def create_temp_nutrition_session(session_id: str) -> Dict[str, Any]:
    """
    Create a new temporary nutrition analysis session with persistent SQLite storage.
    
    This replaces virtual in-memory sessions with persistent SQLite tables that provide
    better reliability and data integrity while maintaining the temporary nature.
    
    What this creates:
    - Session tracking record for cleanup management
    - Temporary table space ready for recipe and nutrition data
    - Better persistence than in-memory virtual sessions
    - Automatic cleanup capabilities
    
    Args:
        session_id: Unique identifier for the nutrition analysis session
        
    Returns:
        Dict with success confirmation or error details
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Register this session for tracking and cleanup
            cursor.execute("""
                INSERT OR REPLACE INTO temp_sessions (session_id, created_at, last_accessed)
                VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (session_id,))
            
            conn.commit()
            
            # Also create virtual session as fallback for backward compatibility
            if session_id not in _recipe_sessions:
                create_virtual_recipe_session(session_id)
            
            return {
                "success": f"Temporary nutrition session created: {session_id}",
                "session_id": session_id,
                "storage_type": "persistent_sqlite",
                "auto_cleanup": True
            }
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error creating temp session: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error creating temp session: {e}"}

def update_session_access_time(session_id: str) -> bool:
    """Update the last accessed time for a temporary session."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE temp_sessions 
                SET last_accessed = CURRENT_TIMESTAMP 
                WHERE session_id = ?
            """, (session_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception:
        return False

def store_recipe_in_temp_tables(session_id: str, recipe_id: str, recipe_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store recipe data in temporary SQLite tables instead of virtual memory.
    
    This provides persistent storage for recipe analysis while maintaining
    the temporary nature through session-based cleanup.
    
    Args:
        session_id: Session identifier for data organization
        recipe_id: Unique recipe identifier  
        recipe_data: Complete recipe data from get_recipe() tool
        
    Returns:
        Dict with storage confirmation and counts
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Update session access time
            update_session_access_time(session_id)
            
            # Store recipe metadata
            cursor.execute("""
                INSERT OR REPLACE INTO temp_recipes 
                (session_id, recipe_id, title, slug, url, base_servings, prep_time, cook_time, 
                 categories, tips, recipe_highlights, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, recipe_id,
                recipe_data.get('title', ''),
                recipe_data.get('slug', ''),
                recipe_data.get('url', ''),
                recipe_data.get('servings'),
                recipe_data.get('prep_time', ''),
                recipe_data.get('cook_time', ''),
                json.dumps(recipe_data.get('categories', [])),
                json.dumps(recipe_data.get('tips', [])),
                json.dumps(recipe_data.get('recipe_highlights', [])),
                recipe_data.get('image_url', '')
            ))
            
            # Store ingredients
            ingredients = recipe_data.get('ingredients', [])
            for i, ingredient in enumerate(ingredients):
                ingredient_id = f"{recipe_id}_ingredient_{i+1}"
                
                cursor.execute("""
                    INSERT OR REPLACE INTO temp_recipe_ingredients
                    (session_id, ingredient_id, recipe_id, ingredient_name, amount, unit, 
                     ingredient_order, ingredient_list_org, cnf_food_code)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id, ingredient_id, recipe_id,
                    None,  # To be parsed
                    None,  # To be parsed
                    None,  # To be parsed
                    i + 1,
                    ingredient if isinstance(ingredient, str) else str(ingredient),
                    None   # To be linked
                ))
            
            conn.commit()
            
            # Also store in virtual session for backward compatibility
            store_recipe_in_virtual_session(session_id, recipe_id, recipe_data)
            
            return {
                "success": f"Recipe stored in temporary persistent storage",
                "session_id": session_id,
                "recipe_id": recipe_id,
                "title": recipe_data.get('title', ''),
                "ingredients_count": len(ingredients),
                "storage_type": "persistent_sqlite"
            }
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error storing recipe: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error storing recipe: {e}"}

def get_temp_session_recipes(session_id: str, recipe_id: str = None) -> Dict[str, Any]:
    """
    Retrieve recipes from temporary persistent storage.
    
    Args:
        session_id: Session to query
        recipe_id: Optional specific recipe ID
        
    Returns:
        Dict with recipe data or error
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Update session access time
            update_session_access_time(session_id)
            
            if recipe_id:
                # Get specific recipe
                cursor.execute("""
                    SELECT * FROM temp_recipes 
                    WHERE session_id = ? AND recipe_id = ?
                """, (session_id, recipe_id))
                recipe_row = cursor.fetchone()
                
                if not recipe_row:
                    return {"error": f"Recipe {recipe_id} not found in session {session_id}"}
                
                recipe = dict(recipe_row)
                
                # Get ingredients
                cursor.execute("""
                    SELECT * FROM temp_recipe_ingredients 
                    WHERE session_id = ? AND recipe_id = ?
                    ORDER BY ingredient_order
                """, (session_id, recipe_id))
                
                recipe['ingredients'] = [dict(row) for row in cursor.fetchall()]
                recipes = [recipe]
            else:
                # Get all recipes in session
                cursor.execute("""
                    SELECT * FROM temp_recipes WHERE session_id = ?
                """, (session_id,))
                
                recipes = []
                for recipe_row in cursor.fetchall():
                    recipe = dict(recipe_row)
                    
                    # Get ingredients for this recipe
                    cursor.execute("""
                        SELECT * FROM temp_recipe_ingredients 
                        WHERE session_id = ? AND recipe_id = ?
                        ORDER BY ingredient_order
                    """, (session_id, recipe['recipe_id']))
                    
                    recipe['ingredients'] = [dict(row) for row in cursor.fetchall()]
                    recipes.append(recipe)
            
            return {
                "recipes": recipes,
                "session_id": session_id,
                "storage_type": "persistent_sqlite"
            }
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error retrieving recipes: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error retrieving recipes: {e}"}

def cleanup_temp_session(session_id: str) -> Dict[str, Any]:
    """
    Clean up all temporary data for a session.
    
    Args:
        session_id: Session to clean up
        
    Returns:
        Dict with cleanup summary
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Count records before cleanup
            counts = {}
            for table in ['temp_recipe_ingredients', 'temp_cnf_nutrients', 'temp_cnf_foods', 'temp_recipes']:
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id = ?", (session_id,))
                counts[table] = cursor.fetchone()[0]
            
            # Delete session data (cascading deletes will handle related records)
            cursor.execute("DELETE FROM temp_recipe_ingredients WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM temp_cnf_nutrients WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM temp_cnf_foods WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM temp_recipes WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM temp_sessions WHERE session_id = ?", (session_id,))
            
            conn.commit()
            
            # Also cleanup virtual session
            if session_id in _recipe_sessions:
                del _recipe_sessions[session_id]
            
            return {
                "success": f"Temporary session cleaned up: {session_id}",
                "session_id": session_id,
                "cleaned_records": counts,
                "storage_type": "persistent_sqlite"
            }
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error cleaning up session: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error cleaning up session: {e}"}

def cleanup_old_temp_sessions(hours_old: int = 24) -> Dict[str, Any]:
    """
    Clean up temporary sessions that haven't been accessed recently.
    
    Args:
        hours_old: Hours of inactivity before cleanup (default 24)
        
    Returns:
        Dict with cleanup summary
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Find old sessions
            cursor.execute("""
                SELECT session_id FROM temp_sessions 
                WHERE last_accessed < datetime('now', '-{} hours')
            """.format(hours_old))
            
            old_sessions = [row[0] for row in cursor.fetchall()]
            
            cleaned_count = 0
            for session_id in old_sessions:
                result = cleanup_temp_session(session_id)
                if "success" in result:
                    cleaned_count += 1
            
            return {
                "success": f"Cleaned up {cleaned_count} old temporary sessions",
                "cleaned_sessions": old_sessions,
                "hours_threshold": hours_old
            }
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error cleaning old sessions: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error cleaning old sessions: {e}"}

def list_temp_sessions() -> Dict[str, Any]:
    """
    List all active temporary nutrition sessions.
    
    Returns:
        Dict with session information
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    s.session_id,
                    s.created_at,
                    s.last_accessed,
                    COUNT(DISTINCT r.recipe_id) as recipe_count,
                    COUNT(DISTINCT i.ingredient_id) as ingredient_count,
                    COUNT(DISTINCT f.cnf_food_code) as cnf_food_count
                FROM temp_sessions s
                LEFT JOIN temp_recipes r ON s.session_id = r.session_id
                LEFT JOIN temp_recipe_ingredients i ON s.session_id = i.session_id
                LEFT JOIN temp_cnf_foods f ON s.session_id = f.session_id
                GROUP BY s.session_id, s.created_at, s.last_accessed
                ORDER BY s.last_accessed DESC
            """)
            
            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    "session_id": row[0],
                    "created_at": row[1],
                    "last_accessed": row[2],
                    "recipe_count": row[3],
                    "ingredient_count": row[4],
                    "cnf_food_count": row[5]
                })
            
            return {
                "sessions": sessions,
                "total_sessions": len(sessions),
                "storage_type": "persistent_sqlite"
            }
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error listing sessions: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error listing sessions: {e}"}