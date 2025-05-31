import sqlite3
import json
import uuid
from typing import List, Dict, Any
from fastmcp import FastMCP
from .connection import get_db_connection
from .schema import initialize_database, create_recipe_session_tables, cleanup_session_tables, list_active_sessions
from .math_tools import register_math_tools
from .ingredient_parser import register_ingredient_tools
from ..models.db_models import RecipeInput, FavoriteInput, SessionInput, RecipeQueryInput
from ..config import MAX_QUERY_ROWS

def register_db_tools(mcp: FastMCP):
    """Register database tools with the MCP server."""

    # Register schema management functions
    mcp.tool()(initialize_database)
    mcp.tool()(create_recipe_session_tables)
    mcp.tool()(cleanup_session_tables)
    mcp.tool()(list_active_sessions)
    
    # Register math and calculation tools
    register_math_tools(mcp)
    
    # Register ingredient parsing tools
    register_ingredient_tools(mcp)

    @mcp.tool()
    def store_recipe_in_session(recipe_input: RecipeInput) -> Dict[str, Any]:
        """
        Store a fetched recipe in temporary session tables for detailed analysis and manipulation.
        
        This tool takes complete recipe data from the Canada's Food Guide and stores it in normalized 
        database tables for the current session. The recipe is broken down into separate tables for 
        ingredients, instructions, and metadata to enable structured analysis and calculations.
        
        Use this tool after fetching a recipe with get_recipe() to enable:
        - Detailed recipe analysis and comparison
        - Ingredient-level manipulation and serving size calculations
        - Persistent storage during the session for multiple recipe workflows
        - Structured access to recipe components for meal planning
        
        The stored data includes:
        - Main recipe metadata (title, servings, timing, categories, tips)
        - Individual ingredients list with ordering
        - Step-by-step instructions with sequence
        - Visual highlights and cooking tips
        
        Args:
            recipe_input: Contains session_id (unique identifier for this recipe session) and 
                         complete recipe_data (dictionary from get_recipe() tool with all recipe details)
            
        Returns:
            Dict with success/error message, generated recipe_id for future reference, 
            recipe title, and counts of ingredients/instructions stored
        """
        session_id = recipe_input.session_id
        recipe_data = recipe_input.recipe_data
        
        # Generate unique recipe ID
        recipe_id = str(uuid.uuid4())
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Ensure session tables exist
                result = create_recipe_session_tables(session_id)
                if "error" in result:
                    return result
                
                # Insert main recipe data
                cursor.execute(f"""
                    INSERT INTO temp_recipes_{session_id} 
                    (recipe_id, title, slug, url, base_servings, prep_time, cook_time, 
                     categories, tips, recipe_highlights, image_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    recipe_id,
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
                
                # Insert ingredients
                ingredients = recipe_data.get('ingredients', [])
                for i, ingredient in enumerate(ingredients):
                    ingredient_id = str(uuid.uuid4())
                    cursor.execute(f"""
                        INSERT INTO temp_recipe_ingredients_{session_id}
                        (ingredient_id, recipe_id, ingredient_name, amount, unit, ingredient_order)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        ingredient_id,
                        recipe_id,
                        ingredient if isinstance(ingredient, str) else str(ingredient),
                        None,  # Amount parsing could be added later
                        None,  # Unit parsing could be added later  
                        i + 1
                    ))
                
                # Insert instructions
                instructions = recipe_data.get('instructions', [])
                for i, instruction in enumerate(instructions):
                    instruction_id = str(uuid.uuid4())
                    cursor.execute(f"""
                        INSERT INTO temp_recipe_instructions_{session_id}
                        (instruction_id, recipe_id, instruction_text, instruction_order)
                        VALUES (?, ?, ?, ?)
                    """, (
                        instruction_id,
                        recipe_id,
                        instruction if isinstance(instruction, str) else str(instruction),
                        i + 1
                    ))
                
                conn.commit()
                return {
                    "success": f"Recipe stored in session {session_id}",
                    "recipe_id": recipe_id,
                    "title": recipe_data.get('title', ''),
                    "ingredients_count": len(ingredients),
                    "instructions_count": len(instructions)
                }
                
        except sqlite3.Error as e:
            return {"error": f"SQLite error storing recipe: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error storing recipe: {e}"}

    @mcp.tool()
    def get_session_recipes(query_input: RecipeQueryInput) -> Dict[str, Any]:
        """
        Retrieve stored recipes from a session with complete normalized data including ingredients and instructions.
        
        This tool fetches recipes that have been stored in the current session's temporary database tables.
        It reconstructs the complete recipe data by joining the normalized tables (recipes, ingredients, instructions)
        and returns fully structured recipe objects ready for analysis, comparison, or further processing.
        
        Use this tool to:
        - Review all recipes stored in the current session
        - Retrieve specific recipe details by recipe_id for focused analysis
        - Compare multiple recipes side-by-side for meal planning
        - Access structured ingredient and instruction data for calculations
        - Prepare recipe data for export or favorites management
        
        The returned data includes:
        - Complete recipe metadata (title, URL, servings, timing, categories)
        - Ordered ingredient lists with amounts and units (if parsed)
        - Sequential cooking instructions with step numbers
        - Recipe highlights, tips, and visual elements
        - Database timestamps and unique identifiers
        
        Args:
            query_input: Contains session_id (required - identifies which session's recipes to retrieve) and 
                        optional recipe_id (if specified, returns only that specific recipe; if omitted, returns all recipes in session)
            
        Returns:
            Dict containing 'recipes' array with complete recipe objects, session_id for reference, 
            or error message if session not found or database issues occur
        """
        session_id = query_input.session_id
        recipe_id = query_input.recipe_id
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Check if session tables exist
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (f"temp_recipes_{session_id}",))
                
                if not cursor.fetchone():
                    return {"error": f"Session {session_id} not found"}
                
                # Query recipes
                if recipe_id:
                    cursor.execute(f"""
                        SELECT * FROM temp_recipes_{session_id} WHERE recipe_id = ?
                    """, (recipe_id,))
                else:
                    cursor.execute(f"""
                        SELECT * FROM temp_recipes_{session_id} ORDER BY created_at DESC
                    """)
                
                recipes = []
                for recipe_row in cursor.fetchall():
                    recipe = dict(recipe_row)
                    
                    # Parse JSON fields
                    recipe['categories'] = json.loads(recipe.get('categories', '[]'))
                    recipe['tips'] = json.loads(recipe.get('tips', '[]'))
                    recipe['recipe_highlights'] = json.loads(recipe.get('recipe_highlights', '[]'))
                    
                    # Get ingredients
                    cursor.execute(f"""
                        SELECT * FROM temp_recipe_ingredients_{session_id} 
                        WHERE recipe_id = ? ORDER BY ingredient_order
                    """, (recipe['recipe_id'],))
                    recipe['ingredients'] = [dict(row) for row in cursor.fetchall()]
                    
                    # Get instructions
                    cursor.execute(f"""
                        SELECT * FROM temp_recipe_instructions_{session_id}
                        WHERE recipe_id = ? ORDER BY instruction_order  
                    """, (recipe['recipe_id'],))
                    recipe['instructions'] = [dict(row) for row in cursor.fetchall()]
                    
                    recipes.append(recipe)
                
                return {"recipes": recipes, "session_id": session_id}
                
        except sqlite3.Error as e:
            return {"error": f"SQLite error retrieving recipes: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error retrieving recipes: {e}"}

    @mcp.tool()
    def add_to_favorites(favorite_input: FavoriteInput) -> Dict[str, str]:
        """
        Add a recipe to user favorites for persistent storage across sessions.
        
        This tool saves recipes to a permanent favorites database that persists between sessions.
        Use this to bookmark recipes you want to return to later. Each favorite can include
        custom notes for personal recipe modifications or preferences.
        
        The favorites system supports:
        - Recipe URL (required) - the Canada's Food Guide recipe link
        - Recipe title for easy identification
        - User session grouping for organization
        - Custom notes for personal recipe modifications
        - Duplicate prevention (same URL won't be added twice per user)
        
        Use this tool when:
        - You want to save a recipe for future reference
        - Building a personal recipe collection
        - Marking recipes to try or cook again
        - Adding personal notes or modifications to recipes
        
        Args:
            favorite_input: Recipe details including recipe_url (required), optional recipe_title, 
                           user_session for grouping, and custom_notes for personal annotations
            
        Returns:
            Dict with success message if added, or info message if already favorited, or error details
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                favorite_id = str(uuid.uuid4())
                
                cursor.execute("""
                    INSERT OR IGNORE INTO user_favorites 
                    (favorite_id, recipe_url, recipe_title, user_session, custom_notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    favorite_id,
                    favorite_input.recipe_url,
                    favorite_input.recipe_title,
                    favorite_input.user_session,
                    favorite_input.custom_notes
                ))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    return {"success": f"Recipe added to favorites: {favorite_input.recipe_title}"}
                else:
                    return {"message": "Recipe was already in favorites"}
                    
        except sqlite3.Error as e:
            return {"error": f"SQLite error adding favorite: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error adding favorite: {e}"}

    @mcp.tool()
    def remove_from_favorites(favorite_input: FavoriteInput) -> Dict[str, str]:
        """
        Remove a recipe from user favorites permanently.
        
        This tool removes recipes from the persistent favorites database. Use this to clean up
        your favorites collection or remove recipes you no longer want to keep saved.
        
        The removal process:
        - Requires the recipe_url to identify which recipe to remove
        - Optionally filters by user_session if provided (for targeted removal)
        - Confirms whether the recipe was actually found and removed
        - Cannot be undone (recipe would need to be re-added manually)
        
        Use this tool when:
        - Cleaning up your favorites collection
        - No longer interested in a previously saved recipe
        - Managing favorites for specific user sessions
        - Correcting accidentally added favorites
        
        Args:
            favorite_input: Recipe details with recipe_url (required for identification) and 
                           optional user_session (if provided, only removes from that specific session)
            
        Returns:
            Dict with success message if removed, info message if not found, or error details
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                where_clause = "recipe_url = ?"
                params = [favorite_input.recipe_url]
                
                if favorite_input.user_session:
                    where_clause += " AND user_session = ?"
                    params.append(favorite_input.user_session)
                
                cursor.execute(f"""
                    DELETE FROM user_favorites WHERE {where_clause}
                """, params)
                
                if cursor.rowcount > 0:
                    conn.commit()
                    return {"success": f"Recipe removed from favorites"}
                else:
                    return {"message": "Recipe was not in favorites"}
                    
        except sqlite3.Error as e:
            return {"error": f"SQLite error removing favorite: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error removing favorite: {e}"}

    @mcp.tool()
    def list_favorites(user_session: str = None) -> Dict[str, Any]:
        """
        List user's favorite recipes from persistent storage.
        
        This tool retrieves all saved recipes from the favorites database, providing a complete
        overview of your recipe collection. Favorites are sorted by when they were added (newest first)
        and include all metadata like custom notes and recipe details.
        
        The returned data includes:
        - Recipe URLs and titles for identification
        - When each recipe was added to favorites
        - Custom notes or modifications you've saved
        - User session information for organization
        - Unique favorite IDs for reference
        
        Use this tool to:
        - Review your complete recipe collection
        - Find previously saved recipes to cook again
        - Organize meal planning around your favorites
        - Check what recipes you've already saved before adding duplicates
        - Export or share your recipe collection
        
        Args:
            user_session: Optional filter to show only favorites from a specific user session. 
                         If omitted, returns all favorites across all sessions.
            
        Returns:
            Dict containing 'favorites' array with complete favorite records including URLs, titles,
            custom notes, timestamps, and session info, or error message if database issues occur
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                if user_session:
                    cursor.execute("""
                        SELECT * FROM user_favorites 
                        WHERE user_session = ? 
                        ORDER BY added_at DESC
                    """, (user_session,))
                else:
                    cursor.execute("""
                        SELECT * FROM user_favorites 
                        ORDER BY added_at DESC
                    """)
                
                favorites = [dict(row) for row in cursor.fetchall()]
                return {"favorites": favorites}
                
        except sqlite3.Error as e:
            return {"error": f"SQLite error listing favorites: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error listing favorites: {e}"}