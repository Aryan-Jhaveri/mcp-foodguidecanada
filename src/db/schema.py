import sqlite3
import json
from typing import Dict, Any, List
from .connection import get_db_connection

def initialize_database() -> Dict[str, str]:
    """
    Initialize the Canada's Food Guide recipe database with required tables.
    
    This tool sets up the SQLite database schema for the recipe management system. It creates
    only the persistent storage table for user favorites. All recipe session data is now
    stored in memory using virtual tables and views to prevent database bloat.
    
    What this tool creates:
    - user_favorites table for persistent recipe bookmarking (ONLY persistent table)
    - Proper indexing and constraints for data integrity
    - Virtual table infrastructure for in-memory recipe storage
    
    Use this tool when:
    - First time setting up the recipe database
    - After database corruption or reset
    - Ensuring database schema is current
    - Before using any favorites-related tools
    
    Returns:
        Dict with success confirmation or detailed error message if database setup fails
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Create persistent USER_FAVORITES table (ONLY persistent table)
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
            return {"success": "Database initialized successfully - only persistent favorites table created"}
            
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
                'recipes': {},
                'ingredients': {},
                'instructions': {},
                'created_at': None
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
        
        # Store ingredients
        ingredients = recipe_data.get('ingredients', [])
        for i, ingredient in enumerate(ingredients):
            ingredient_id = f"{recipe_id}_ingredient_{i+1}"
            session['ingredients'][ingredient_id] = {
                'ingredient_id': ingredient_id,
                'recipe_id': recipe_id,
                'ingredient_list_org': ingredient if isinstance(ingredient, str) else str(ingredient),
                'ingredient_name': None,  # To be parsed by LLM using SQL tools
                'amount': None,           # To be parsed by LLM using SQL tools
                'unit': None,             # To be parsed by LLM using SQL tools
                'ingredient_order': i + 1
            }
        
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