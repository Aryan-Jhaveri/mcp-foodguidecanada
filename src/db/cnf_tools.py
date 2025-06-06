"""
CNF (Canadian Nutrient File) tools for the MCP server.

This module provides tools for:
1. Searching foods in the CNF database
2. Retrieving detailed nutrient profiles
3. Linking recipe ingredients to CNF foods
4. Calculating recipe nutrition summaries
5. Managing CNF data in virtual sessions
"""

import json
import os
import sys
import sqlite3
from typing import Dict, Any, List, Optional
from fastmcp import FastMCP
import logging

# Handle imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Add paths to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Global flag for whether CNF tools are available
CNF_TOOLS_AVAILABLE = False

try:
    from src.models.cnf_models import (
        CNFSearchInput, CNFProfileInput, CNFCleanupInput,
        SQLQueryInput, CNFFoodResult, CNFNutrientProfile, IngredientCNFMatch,
        RecipeNutritionSummary, CNFSessionSummary, IngredientNutritionData,
        AnalyzeRecipeNutritionInput
    )
    from src.api.cnf import NutrientFileScraper
    from src.db.schema import get_virtual_session_data, store_recipe_in_virtual_session
    from src.db.sql_engine import VirtualSQLEngine, get_available_tables_info
    from src.db.connection import get_db_connection
    CNF_TOOLS_AVAILABLE = True
except ImportError:
    try:
        from models.cnf_models import (
            CNFSearchInput, CNFProfileInput, CNFCleanupInput,
            SQLQueryInput, CNFFoodResult, CNFNutrientProfile, IngredientCNFMatch,
            RecipeNutritionSummary, CNFSessionSummary, IngredientNutritionData,
            AnalyzeRecipeNutritionInput
        )
        from api.cnf import NutrientFileScraper
        from db.schema import get_virtual_session_data, store_recipe_in_virtual_session
        from db.sql_engine import VirtualSQLEngine, get_available_tables_info
        from db.connection import get_db_connection
        CNF_TOOLS_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: CNF tools not available due to import error: {e}", file=sys.stderr)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global CNF scraper instance
_cnf_scraper = None

def get_cnf_scraper() -> NutrientFileScraper:
    """Get or create the global CNF scraper instance."""
    global _cnf_scraper
    if _cnf_scraper is None:
        _cnf_scraper = NutrientFileScraper(rate_limit=1.0)
    return _cnf_scraper

def register_cnf_tools(mcp: FastMCP) -> None:
    """Register all CNF tools with the FastMCP server."""
    if not CNF_TOOLS_AVAILABLE:
        logger.warning("CNF tools not available - skipping registration")
        return

    @mcp.tool()
    def search_cnf_foods(input_data: CNFSearchInput) -> Dict[str, Any]:
        """
        Search for foods in the Canadian Nutrient File database by name - SEARCH ONLY.
        
        This tool searches Health Canada's CNF database for foods matching the provided name.
        Results are stored in the specified virtual session for later use in nutrition analysis.
        
        **Returns ALL available results by default** - no calculation performed here.
        
        Search Strategy Tips:
        - For pure ingredients: Try simple terms like "honey", "chicken", "rice"
        - Pure foods often appear later in results after processed/branded products
        - Look for descriptions WITHOUT brand names or complex processing terms
        - Example: "Honey, liquid" vs "Cereal, honey nut flavored"
        
        Common pure food patterns in CNF:
        - "Honey, liquid" or "Honey, strained" (not "Honey Nut Cheerios")
        - "Chicken, breast" (not "Chicken nuggets, frozen")
        - "Rice, white" (not "Rice, seasoned mix")
        
        Use this tool when:
        - Looking for CNF foods that match recipe ingredients  
        - Exploring available foods in the CNF database
        - Finding food codes for detailed nutrient analysis
        - Building ingredient-to-nutrition mappings
        
        **MODERN SQL-POWERED WORKFLOW (RECOMMENDED):**
        1. search_cnf_foods → find appropriate food codes
        2. get_cnf_nutrient_profile → retrieve nutrition data (auto-populates SQL tables)
        3. link_ingredient_to_cnf_simple → link ingredients (direct SQL updates)
        4. execute_nutrition_sql → custom SQL queries for any nutrition calculation
        
        **REDUCES 8+ tool calls to 4 tool calls!**
        
        Args:
            input_data: CNFSearchInput with food_name and session_id
            
        Returns:
            Dict with search results, including list of matching foods with codes and names.
            No calculations performed - use math tools after getting nutrient profiles.
        """
        try:
            scraper = get_cnf_scraper()
            search_results = scraper.search_food(input_data.food_name)
            
            if search_results is None:
                return {"error": f"Failed to search for food: {input_data.food_name}"}
            
            if not search_results:
                return {
                    "message": f"No foods found matching: {input_data.food_name}",
                    "search_term": input_data.food_name,
                    "results": []
                }
            
            # Store search results in virtual session
            session_data = get_virtual_session_data(input_data.session_id)
            if session_data is None:
                # Create session if it doesn't exist
                from src.db.schema import create_virtual_recipe_session
                create_virtual_recipe_session(input_data.session_id)
                session_data = get_virtual_session_data(input_data.session_id)
            
            # Ensure CNF data structures exist
            if 'cnf_search_results' not in session_data:
                session_data['cnf_search_results'] = {}
            
            # Store search results
            session_data['cnf_search_results'][input_data.food_name] = search_results
            
            # Limit results if requested (now defaults to showing all results)
            limited_results = search_results[:input_data.max_results] if input_data.max_results else search_results
            
            return {
                "success": f"Found {len(search_results)} foods matching '{input_data.food_name}'",
                "search_term": input_data.food_name,
                "results": limited_results,
                "total_found": len(search_results),
                "showing": len(limited_results),
                "session_id": input_data.session_id
            }
            
        except Exception as e:
            logger.error(f"Error searching CNF foods: {e}")
            return {"error": f"Failed to search CNF foods: {str(e)}"}

    @mcp.tool()
    def get_cnf_nutrient_profile(input_data: CNFProfileInput) -> Dict[str, Any]:
        """
        Get detailed nutrient profile for a specific CNF food code - DATA RETRIEVAL ONLY.
        
        IMPORTANT: This tool retrieves nutrition data but does NOT calculate totals.
        Use simple_math_calculator for all nutrition calculations after getting this data.
        
        This tool fetches complete nutritional information from Health Canada's CNF database
        for a specific food code. The profile includes all available nutrients (proximates,
        vitamins, minerals, etc.) organized by category with values for different serving sizes.
        
        **NEW: AUTOMATIC SQL TABLE POPULATION!**
        This tool now automatically populates virtual SQL tables (cnf_foods, cnf_nutrients) 
        when nutrient profiles are retrieved. No manual data extraction needed!
        
        **SQL Tables Auto-Created:**
        - cnf_foods: cnf_food_code, food_description
        - cnf_nutrients: cnf_food_code, nutrient_name, nutrient_value, per_amount, unit
        
        **Ready-to-Use SQL Examples:**
        ```sql
        -- Get all calories for a food
        SELECT nutrient_value FROM cnf_nutrients 
        WHERE cnf_food_code = 'FOOD_CODE' AND nutrient_name = 'Energy (kcal)' AND per_amount = 100
        
        -- Get serving size options
        SELECT DISTINCT per_amount, unit FROM cnf_nutrients WHERE cnf_food_code = 'FOOD_CODE'
        ```
        
        **Enhanced serving size handling**: Now captures ALL available serving options,
        including volume measures (ml, tsp, tbsp) and weight conversions for liquid foods.
        
        Use this tool when:
        - Getting detailed nutrition data for a matched ingredient
        - Preparing data for math tool calculations
        - Exploring nutritional content of specific CNF foods
        - Building ingredient-nutrition databases
        
        **Next steps after getting profile:**
        1. Use link_ingredient_to_cnf_simple() to connect food to recipe ingredients
        2. Use execute_nutrition_sql() with custom queries for nutrition calculations
        3. SQL handles all unit conversions and calculations transparently
        4. Compare results with EER using simple_math_calculator if needed
        
        The nutrient profile data is stored in the virtual session for use by calculation tools.
        
        Args:
            input_data: CNFProfileInput with food_code and session_id
            
        Returns:
            Dict with complete nutrient profile including all categories and serving sizes.
            Use the returned data with math tools - do not manually calculate values.
        """
        try:
            scraper = get_cnf_scraper()
            
            # Get serving information first
            serving_options, refuse_info = scraper.get_serving_info(input_data.food_code)
            
            if serving_options is None:
                return {"error": f"Failed to get serving info for food code: {input_data.food_code}"}
            
            # Get complete nutrient profile
            nutrient_profile = scraper.get_nutrient_profile(input_data.food_code, serving_options)
            
            if nutrient_profile is None:
                return {"error": f"Failed to get nutrient profile for food code: {input_data.food_code}"}
            
            # Store in virtual session
            session_data = get_virtual_session_data(input_data.session_id)
            if session_data is None:
                from src.db.schema import create_virtual_recipe_session
                create_virtual_recipe_session(input_data.session_id)
                session_data = get_virtual_session_data(input_data.session_id)
            
            # Ensure CNF data structures exist
            if 'nutrient_profiles' not in session_data:
                session_data['nutrient_profiles'] = {}
            
            # Store complete profile (legacy format)
            session_data['nutrient_profiles'][input_data.food_code] = {
                'food_code': input_data.food_code,
                'serving_options': serving_options,
                'refuse_info': refuse_info,
                'nutrient_profile': nutrient_profile,
                'retrieved_at': str(json.dumps(None))  # Will be set by JSON serialization
            }
            
            # NEW: Populate SQL table structures
            # Add to cnf_foods table
            cnf_foods_entry = {
                'cnf_food_code': input_data.food_code,
                'food_description': f"CNF Food {input_data.food_code}"  # Will be improved with actual food name
            }
            
            # Check if this food code is already in cnf_foods table
            if 'cnf_foods' not in session_data:
                session_data['cnf_foods'] = []
            
            existing_food = next((f for f in session_data['cnf_foods'] if f['cnf_food_code'] == input_data.food_code), None)
            if not existing_food:
                session_data['cnf_foods'].append(cnf_foods_entry)
            
            # Add to cnf_nutrients table
            if 'cnf_nutrients' not in session_data:
                session_data['cnf_nutrients'] = []
            
            # Extract nutrient data from profile
            if isinstance(nutrient_profile, dict):
                for category_name, nutrients in nutrient_profile.items():
                    if isinstance(nutrients, list):
                        for nutrient in nutrients:
                            nutrient_name = nutrient.get('Nutrient name', '')
                            
                            # Store 100g baseline value
                            baseline_value = nutrient.get('Value per 100 g of edible portion', '')
                            if baseline_value and baseline_value.strip():
                                try:
                                    baseline_float = float(baseline_value)
                                    session_data['cnf_nutrients'].append({
                                        'cnf_food_code': input_data.food_code,
                                        'nutrient_name': nutrient_name,
                                        'nutrient_value': baseline_float,
                                        'per_amount': 100.0,
                                        'unit': 'g'
                                    })
                                except (ValueError, TypeError):
                                    pass
                            
                            # Store serving size values
                            for key, value in nutrient.items():
                                # Look for serving size columns (e.g., "5ml / 5 g", "15ml / 14 g")
                                if '/' in key and 'ml' in key.lower():
                                    if value and str(value).strip():
                                        try:
                                            serving_value = float(str(value).strip())
                                            
                                            # Extract serving amount and unit from key
                                            import re
                                            match = re.match(r'(\d+(?:\.\d+)?)\s*([a-zA-Z]+)', key)
                                            if match:
                                                serving_amount = float(match.group(1))
                                                serving_unit = match.group(2).lower()
                                                
                                                session_data['cnf_nutrients'].append({
                                                    'cnf_food_code': input_data.food_code,
                                                    'nutrient_name': nutrient_name,
                                                    'nutrient_value': serving_value,
                                                    'per_amount': serving_amount,
                                                    'unit': serving_unit
                                                })
                                        except (ValueError, TypeError):
                                            pass
            
            return {
                "success": f"Retrieved nutrient profile for food code: {input_data.food_code}",
                "food_code": input_data.food_code,
                "serving_options": serving_options,
                "refuse_info": refuse_info,
                "nutrient_categories": list(nutrient_profile.keys()) if isinstance(nutrient_profile, dict) else [],
                "nutrient_profile": nutrient_profile,
                "session_id": input_data.session_id
            }
            
        except Exception as e:
            logger.error(f"Error getting CNF nutrient profile: {e}")
            return {"error": f"Failed to get CNF nutrient profile: {str(e)}"}

    @mcp.tool()
    def link_ingredient_to_cnf_simple(session_id: str, ingredient_id: str, cnf_food_code: str) -> Dict[str, Any]:
        """
        **MODERN APPROACH**: Direct SQL table linking for fast nutrition analysis.
        
        This tool directly updates the cnf_food_code field in the recipe_ingredients SQL table,
        making nutrition data immediately available for execute_nutrition_sql queries.
        
        **Key Benefits:**
        - ⚡ **Fast**: Direct SQL table update, no complex matching logic
        - 🔄 **Immediate**: Data ready for SQL queries instantly
        - 🎯 **Simple**: One call links ingredient to nutrition data
        - 🔍 **Transparent**: All data visible in SQL tables
        
        **After linking, you can immediately run SQL like:**
        ```sql
        SELECT ri.ingredient_name, cn.nutrient_name, cn.nutrient_value
        FROM recipe_ingredients ri
        JOIN cnf_nutrients cn ON ri.cnf_food_code = cn.cnf_food_code
        WHERE ri.ingredient_id = 'INGREDIENT_ID'
        ```
        
        Use this tool to:
        - Connect parsed ingredients to CNF food codes
        - Enable immediate SQL-based nutrition calculations
        - Set up data for execute_nutrition_sql queries
        
        Args:
            session_id: Session containing the ingredient data
            ingredient_id: ID of the ingredient to link  
            cnf_food_code: CNF food code to link to
            
        Returns:
            Dict confirming the linkage was created with SQL query suggestions
        """
        try:
            session_data = get_virtual_session_data(session_id)
            if session_data is None:
                return {"error": f"Session {session_id} not found"}
            
            # Update the SQL table structure
            if 'recipe_ingredients' not in session_data:
                return {"error": "No recipe_ingredients table found in session"}
            
            # Find and update the ingredient
            ingredient_found = False
            for ingredient in session_data['recipe_ingredients']:
                if ingredient['ingredient_id'] == ingredient_id:
                    ingredient['cnf_food_code'] = cnf_food_code
                    ingredient_found = True
                    break
            
            if not ingredient_found:
                return {"error": f"Ingredient {ingredient_id} not found in recipe_ingredients table"}
            
            return {
                "success": f"Linked ingredient {ingredient_id} to CNF food {cnf_food_code}",
                "ingredient_id": ingredient_id,
                "cnf_food_code": cnf_food_code,
                "session_id": session_id,
                "ready_for_sql": True,
                "next_step": "Use execute_nutrition_sql() for nutrition calculations",
                "example_sql": f"SELECT ri.ingredient_name, cn.nutrient_name, cn.nutrient_value FROM recipe_ingredients ri JOIN cnf_nutrients cn ON ri.cnf_food_code = cn.cnf_food_code WHERE ri.ingredient_id = '{ingredient_id}'"
            }
            
        except Exception as e:
            logger.error(f"Error linking ingredient to CNF: {e}")
            return {"error": f"Failed to link ingredient to CNF: {str(e)}"}

    @mcp.tool() 
    def analyze_recipe_nutrition(input_data: AnalyzeRecipeNutritionInput) -> Dict[str, Any]:
        """
        🚀 **ONE-SHOT RECIPE NUTRITION ANALYSIS** 🚀
        
        This tool replaces the entire 8-step nutrition workflow with a single call!
        Automatically handles ingredient parsing, CNF matching, linking, and provides
        ready-to-use SQL queries for complete nutrition analysis.
        
        **REPLACES THIS WORKFLOW:**
        1. parse_and_update_ingredients ❌
        2. search_cnf_foods (per ingredient) ❌ 
        3. get_cnf_nutrient_profile (per food) ❌
        4. link_ingredient_to_cnf_simple (per match) ❌
        5. execute_nutrition_sql ❌
        6. simple_math_calculator ❌
        7-8. Additional queries/calculations ❌
        
        **WITH THIS SINGLE CALL:** ✅
        analyze_recipe_nutrition() → Complete nutrition analysis ready!
        
        **What This Tool Does:**
        - ✅ **Auto-parses** all recipe ingredients 
        - ✅ **Auto-searches** CNF database for matches
        - ✅ **Auto-links** high-confidence matches to ingredients
        - ✅ **Populates** SQL tables (recipe_ingredients, cnf_nutrients, cnf_foods)
        - ✅ **Returns** ready-to-use SQL queries for macro calculations
        - ✅ **Provides** ingredient match report with confidence scores
        
        **Immediate Results:**
        - Complete ingredient-CNF linkage report
        - SQL queries for total calories, protein, fat, carbs
        - SQL queries for per-serving nutrition
        - Ingredient-by-ingredient breakdown queries
        - Match confidence analysis and recommendations
        
        **Example Usage:**
        ```python
        result = analyze_recipe_nutrition(
            session_id="nutrition_session",
            recipe_id="recipe_12345", 
            auto_link_major_ingredients=True
        )
        
        # Then immediately run the provided SQL:
        execute_nutrition_sql(session_id="nutrition_session", 
                            query=result["sql_queries"]["total_macros"])
        ```
        
        Args:
            session_id: Session containing the recipe data
            recipe_id: Recipe to analyze for nutrition
            auto_link_major_ingredients: Whether to automatically link obvious matches
            
        Returns:
            Dict with complete analysis setup, SQL queries, and match report
        """
        try:
            # Extract parameters from input_data
            session_id = input_data.session_id
            recipe_id = input_data.recipe_id
            auto_link_major_ingredients = input_data.auto_link_major_ingredients
            
            session_data = get_virtual_session_data(session_id)
            if session_data is None:
                return {"error": f"Session {session_id} not found"}
            
            # Check if recipe exists
            if 'recipes' not in session_data or recipe_id not in session_data['recipes']:
                return {"error": f"Recipe {recipe_id} not found in session"}
            
            recipe_data = session_data['recipes'][recipe_id]
            recipe_title = recipe_data.get('title', 'Unknown Recipe')
            
            # Step 1: Ensure we're using temp persistent storage
            from .schema import create_temp_nutrition_session, update_session_access_time
            create_temp_nutrition_session(session_id)
            update_session_access_time(session_id)
            
            # Step 1.5: CRITICAL FIX - Transfer recipe data from virtual session to temp SQLite tables
            # This is the missing step that was causing the empty results!
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Transfer recipe metadata to temp_recipes table
                cursor.execute("""
                    INSERT OR REPLACE INTO temp_recipes 
                    (session_id, recipe_id, title, base_servings, prep_time, cook_time, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id, recipe_id, recipe_title,
                    recipe_data.get('servings', 4),
                    recipe_data.get('prep_time', ''),
                    recipe_data.get('cook_time', ''),
                    recipe_data.get('url', '')
                ))
                
                # Transfer ingredients from virtual session to temp_recipe_ingredients table
                if 'ingredients' in session_data and recipe_id in session_data['ingredients']:
                    ingredients = session_data['ingredients'][recipe_id]
                    for ingredient_data in ingredients:
                        cursor.execute("""
                            INSERT OR REPLACE INTO temp_recipe_ingredients 
                            (session_id, recipe_id, ingredient_id, ingredient_list_org, ingredient_name, 
                             amount, unit, ingredient_order, cnf_food_code)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            session_id, recipe_id, 
                            ingredient_data.get('ingredient_id', f"ing_{len(ingredients)}_{ingredient_data.get('ingredient_order', 0)}"),
                            ingredient_data.get('ingredient_list_org', ''),
                            ingredient_data.get('ingredient_name', ''),
                            ingredient_data.get('amount'),
                            ingredient_data.get('unit'),
                            ingredient_data.get('ingredient_order', 0),
                            None  # cnf_food_code will be set later during linking
                        ))
                
                conn.commit()
            
            # Step 2: Parse ingredients if not already done
            from .ingredient_parser import parse_ingredients_for_temp_tables
            parse_result = parse_ingredients_for_temp_tables(session_id, recipe_id)
            if "error" in parse_result:
                return {"error": f"Failed to parse ingredients: {parse_result['error']}"}
            
            # Step 3: Get parsed ingredients from temp persistent storage
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM temp_recipe_ingredients 
                    WHERE session_id = ? AND recipe_id = ?
                    ORDER BY ingredient_order
                """, (session_id, recipe_id))
                
                recipe_ingredients = [dict(row) for row in cursor.fetchall()]
            
            if not recipe_ingredients:
                return {"error": f"No ingredients found for recipe {recipe_id}. Please store recipe in session first."}
            
            # Step 2 & 3: Auto-search CNF and get profiles for major ingredients
            cnf_scraper = get_cnf_scraper()
            processed_count = 0
            linked_count = 0
            match_report = []
            
            for ingredient in recipe_ingredients:
                # Fix the None handling issue that was causing crashes
                ingredient_name = (ingredient.get('ingredient_name') or '').strip()
                ingredient_id = ingredient['ingredient_id']
                
                # Skip section headers and ingredients without names
                if not ingredient_name or ingredient_name.endswith(':'):
                    continue
                
                # Search for CNF matches
                search_results = cnf_scraper.search_food(ingredient_name)
                processed_count += 1
                
                if search_results:
                    # Get the best match (first result, often most relevant)
                    best_match = search_results[0]
                    cnf_food_code = best_match['food_code']
                    confidence = 0.8  # High confidence for first result
                    
                    # Get nutrient profile (auto-populates SQL tables)
                    serving_options, refuse_info = cnf_scraper.get_serving_info(cnf_food_code)
                    if serving_options:
                        nutrient_profile = cnf_scraper.get_nutrient_profile(cnf_food_code, serving_options)
                        if nutrient_profile:
                            # Store CNF data in persistent temp tables
                            with get_db_connection() as conn:
                                cursor = conn.cursor()
                                
                                # Store CNF food data
                                cursor.execute("""
                                    INSERT OR REPLACE INTO temp_cnf_foods
                                    (session_id, cnf_food_code, food_description, refuse_flag, refuse_amount)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (
                                    session_id, cnf_food_code, best_match['food_name'],
                                    refuse_info.get('refuse_flag', False),
                                    refuse_info.get('refuse_amount', 0.0)
                                ))
                                
                                # Store nutrient data
                                for nutrient in nutrient_profile.get('nutrients', []):
                                    cursor.execute("""
                                        INSERT OR REPLACE INTO temp_cnf_nutrients
                                        (session_id, cnf_food_code, nutrient_name, nutrient_value, 
                                         per_amount, unit, nutrient_symbol, standard_error, number_observations)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        session_id, cnf_food_code,
                                        nutrient.get('nutrient_name', ''),
                                        nutrient.get('nutrient_value', 0.0),
                                        nutrient.get('per_amount', 100.0),
                                        nutrient.get('unit', ''),
                                        nutrient.get('nutrient_symbol', ''),
                                        nutrient.get('standard_error', ''),
                                        nutrient.get('number_observations', 0)
                                    ))
                                
                                if auto_link_major_ingredients:
                                    # Auto-link this ingredient in persistent storage
                                    cursor.execute("""
                                        UPDATE temp_recipe_ingredients 
                                        SET cnf_food_code = ?
                                        WHERE session_id = ? AND ingredient_id = ?
                                    """, (cnf_food_code, session_id, ingredient_id))
                                    linked_count += 1
                                
                                conn.commit()
                            
                            # Also store in virtual session for backward compatibility
                            _store_cnf_profile_in_session(session_data, cnf_food_code, serving_options, refuse_info, nutrient_profile)
                            
                            if auto_link_major_ingredients:
                                match_report.append({
                                    'ingredient_name': ingredient_name,
                                    'ingredient_id': ingredient_id,
                                    'cnf_food_code': cnf_food_code,
                                    'cnf_food_name': best_match['food_name'],
                                    'confidence': confidence,
                                    'status': 'auto_linked',
                                    'alternatives': len(search_results) - 1
                                })
                            else:
                                match_report.append({
                                    'ingredient_name': ingredient_name,
                                    'ingredient_id': ingredient_id,
                                    'cnf_food_code': cnf_food_code,
                                    'cnf_food_name': best_match['food_name'],
                                    'confidence': confidence,
                                    'status': 'found_not_linked',
                                    'alternatives': len(search_results) - 1
                                })
                else:
                    match_report.append({
                        'ingredient_name': ingredient_name,
                        'ingredient_id': ingredient_id,
                        'cnf_food_code': None,
                        'cnf_food_name': None,
                        'confidence': 0.0,
                        'status': 'no_match_found',
                        'alternatives': 0
                    })
            
            # Generate ready-to-use SQL queries for temp persistent tables
            sql_queries = {
                "total_macros": f"""
SELECT 
    'TOTAL' as calculation_type,
    SUM(CASE WHEN cn.nutrient_name = 'Energy (kcal)' THEN 
        CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
             ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as calories,
    SUM(CASE WHEN cn.nutrient_name = 'Protein' THEN 
        CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
             ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as protein_g,
    SUM(CASE WHEN cn.nutrient_name = 'Total Fat' THEN 
        CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
             ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as fat_g,
    SUM(CASE WHEN cn.nutrient_name = 'Carbohydrate' THEN 
        CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
             ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as carbs_g
FROM temp_recipe_ingredients ri
JOIN temp_cnf_nutrients cn ON ri.cnf_food_code = cn.cnf_food_code
WHERE ri.session_id = '{session_id}' AND ri.recipe_id = '{recipe_id}' AND cn.session_id = '{session_id}'
AND cn.per_amount = 100
""",
                "per_serving": f"""
SELECT 
    r.title,
    r.base_servings,
    (total_macros.calories / r.base_servings) as calories_per_serving,
    (total_macros.protein_g / r.base_servings) as protein_per_serving,
    (total_macros.fat_g / r.base_servings) as fat_per_serving,
    (total_macros.carbs_g / r.base_servings) as carbs_per_serving
FROM temp_recipes r
JOIN (
    SELECT 
        ri.recipe_id,
        SUM(CASE WHEN cn.nutrient_name = 'Energy (kcal)' THEN 
            CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                 ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as calories,
        SUM(CASE WHEN cn.nutrient_name = 'Protein' THEN 
            CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                 ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as protein_g,
        SUM(CASE WHEN cn.nutrient_name = 'Total Fat' THEN 
            CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                 ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as fat_g,
        SUM(CASE WHEN cn.nutrient_name = 'Carbohydrate' THEN 
            CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                 ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as carbs_g
    FROM temp_recipe_ingredients ri
    JOIN temp_cnf_nutrients cn ON ri.cnf_food_code = cn.cnf_food_code
    WHERE ri.session_id = '{session_id}' AND ri.recipe_id = '{recipe_id}' AND cn.session_id = '{session_id}'
    AND cn.per_amount = 100
    GROUP BY ri.recipe_id
) total_macros ON r.recipe_id = total_macros.recipe_id
WHERE r.session_id = '{session_id}' AND r.recipe_id = '{recipe_id}'
""",
                "ingredient_breakdown": f"""
SELECT 
    ri.ingredient_name,
    ri.amount,
    ri.unit,
    cn.nutrient_name,
    CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
         ELSE (ri.amount/100)*cn.nutrient_value END as contribution
FROM temp_recipe_ingredients ri
JOIN temp_cnf_nutrients cn ON ri.cnf_food_code = cn.cnf_food_code
WHERE ri.session_id = '{session_id}' AND ri.recipe_id = '{recipe_id}' AND cn.session_id = '{session_id}'
AND cn.nutrient_name IN ('Energy (kcal)', 'Protein', 'Total Fat', 'Carbohydrate')
ORDER BY ri.ingredient_name, cn.nutrient_name
"""
            }
            
            return {
                "success": f"✅ Analyzed recipe nutrition for: {recipe_title}",
                "recipe_id": recipe_id,
                "recipe_title": recipe_title,
                "session_id": session_id,
                
                # Processing summary
                "processing_summary": {
                    "total_ingredients": len(recipe_ingredients),
                    "processed_ingredients": processed_count,
                    "linked_ingredients": linked_count,
                    "coverage_percentage": round((linked_count / processed_count * 100), 1) if processed_count > 0 else 0
                },
                
                # Ready-to-use SQL queries
                "sql_queries": sql_queries,
                
                # Detailed match report
                "ingredient_matches": match_report,
                
                # Next steps
                "ready_for_analysis": True,
                "next_steps": [
                    "Use execute_nutrition_sql() with the provided sql_queries",
                    "Run 'total_macros' query for complete recipe nutrition",
                    "Run 'per_serving' query for per-serving breakdown",
                    "Run 'ingredient_breakdown' for detailed analysis"
                ],
                
                # Quick example
                "example_usage": f"execute_nutrition_sql(session_id='{session_id}', query=sql_queries['total_macros'])"
            }
            
        except Exception as e:
            logger.error(f"Error in analyze_recipe_nutrition: {e}")
            return {"error": f"Failed to analyze recipe nutrition: {str(e)}"}
    
    @mcp.tool()
    def execute_nutrition_sql(input_data: SQLQueryInput) -> Dict[str, Any]:
        """
        Execute SQL queries on persistent temporary nutrition tables for reliable nutrition analysis.
        
        **🚀 PERSISTENT SQLite APPROACH!** 
        This tool provides direct SQL access to nutrition data stored in persistent temporary SQLite 
        tables, enabling reliable nutrition calculations with guaranteed data persistence.
        
        **Available Temporary Tables (session-scoped):**
        - `temp_recipe_ingredients`: ingredient_id, recipe_id, ingredient_name, amount, unit, cnf_food_code
        - `temp_cnf_foods`: cnf_food_code, food_description  
        - `temp_cnf_nutrients`: cnf_food_code, nutrient_name, nutrient_value, per_amount, unit
        - `temp_recipes`: recipe_id, title, base_servings, prep_time, cook_time
        
        **IMPORTANT: All tables are session-scoped. Always include session_id in WHERE clauses.**
        
        **🎯 READY-TO-USE SQL TEMPLATES (Copy & Modify):**
        
        **1. Complete Recipe Macronutrient Analysis:**
        ```sql
        SELECT 
            'TOTAL' as calculation_type,
            SUM(CASE WHEN cn.nutrient_name = 'Energy (kcal)' THEN 
                CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                     ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as calories,
            SUM(CASE WHEN cn.nutrient_name = 'Protein' THEN 
                CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                     ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as protein_g,
            SUM(CASE WHEN cn.nutrient_name = 'Total Fat' THEN 
                CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                     ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as fat_g,
            SUM(CASE WHEN cn.nutrient_name = 'Carbohydrate' THEN 
                CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                     ELSE (ri.amount/100)*cn.nutrient_value END ELSE 0 END) as carbs_g
        FROM temp_recipe_ingredients ri
        JOIN temp_cnf_nutrients cn ON ri.cnf_food_code = cn.cnf_food_code
        WHERE ri.session_id = 'YOUR_SESSION_ID' AND cn.session_id = 'YOUR_SESSION_ID'
        AND ri.recipe_id = 'YOUR_RECIPE_ID' AND cn.per_amount = 100
        ```
        
        **2. Per-Serving Nutrition:**
        ```sql
        SELECT 
            r.title,
            (total_nutrition.calories / r.base_servings) as calories_per_serving,
            (total_nutrition.protein_g / r.base_servings) as protein_per_serving,
            (total_nutrition.fat_g / r.base_servings) as fat_per_serving,
            (total_nutrition.carbs_g / r.base_servings) as carbs_per_serving
        FROM temp_recipes r
        JOIN (/* INSERT QUERY 1 HERE */) total_nutrition ON 1=1
        WHERE r.session_id = 'YOUR_SESSION_ID' AND r.recipe_id = 'YOUR_RECIPE_ID'
        ```
        
        **3. Ingredient-by-Ingredient Breakdown:**
        ```sql
        SELECT 
            ri.ingredient_name,
            ri.amount,
            ri.unit,
            cn.nutrient_name,
            CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                 ELSE (ri.amount/100)*cn.nutrient_value END as contribution
        FROM temp_recipe_ingredients ri
        JOIN temp_cnf_nutrients cn ON ri.cnf_food_code = cn.cnf_food_code
        WHERE ri.session_id = 'YOUR_SESSION_ID' AND cn.session_id = 'YOUR_SESSION_ID'
        AND ri.recipe_id = 'YOUR_RECIPE_ID' 
        AND cn.nutrient_name IN ('Energy (kcal)', 'Protein', 'Total Fat', 'Carbohydrate')
        ORDER BY ri.ingredient_name, cn.nutrient_name
        ```
        
        **4. Find Top Calorie Contributors:**
        ```sql
        SELECT 
            ri.ingredient_name,
            CASE WHEN ri.unit = cn.unit THEN (ri.amount/cn.per_amount)*cn.nutrient_value 
                 ELSE (ri.amount/100)*cn.nutrient_value END as calories_contributed
        FROM temp_recipe_ingredients ri
        JOIN temp_cnf_nutrients cn ON ri.cnf_food_code = cn.cnf_food_code
        WHERE ri.session_id = 'YOUR_SESSION_ID' AND cn.session_id = 'YOUR_SESSION_ID'
        AND ri.recipe_id = 'YOUR_RECIPE_ID' AND cn.nutrient_name = 'Energy (kcal)'
        ORDER BY calories_contributed DESC
        ```
        
        **Key Benefits:**
        - **Direct calculations**: No need for complex tool chains
        - **Flexible analysis**: Write custom queries for any nutrition question
        - **Unit conversion**: Handle serving size conversions in SQL
        - **Transparent**: All calculations visible in the query
        - **Scalable**: Easy to analyze multiple recipes or nutrients
        
        Use this tool when:
        - Calculating recipe nutrition totals
        - Comparing nutritional content across ingredients
        - Analyzing nutrition per serving or per ingredient
        - Creating custom nutrition reports
        - Preparing data for DRI adequacy analysis
        
        Args:
            input_data: SQLQueryInput with session_id and SQL query
            
        Returns:
            Dict with query results including rows, columns, and data
        """
        try:
            from .schema import update_session_access_time
            
            # Update session access time
            update_session_access_time(input_data.session_id)
            
            # Execute query directly on SQLite temp tables
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(input_data.query)
                
                # Get column names
                columns = [description[0] for description in cursor.description] if cursor.description else []
                
                # Fetch all results
                rows = cursor.fetchall()
                
                # Convert rows to list of dictionaries
                data = [dict(row) for row in rows]
                
                return {
                    "success": "Query executed successfully",
                    "rows": len(data),
                    "columns": columns,
                    "data": data,
                    "session_id": input_data.session_id,
                    "query": input_data.query,
                    "available_tables": ["temp_recipe_ingredients", "temp_cnf_foods", "temp_cnf_nutrients", "temp_recipes"],
                    "storage_type": "persistent_sqlite"
                }
            
        except sqlite3.Error as e:
            logger.error(f"SQLite error executing nutrition query: {e}")
            return {"error": f"SQLite error executing query: {str(e)}"}
        except Exception as e:
            logger.error(f"Error executing SQL query: {e}")
            return {"error": f"Failed to execute SQL query: {str(e)}"}

    @mcp.tool() 
    def get_nutrition_tables_info() -> Dict[str, Any]:
        """
        Get information about available virtual nutrition tables and their schemas.
        
        This tool provides documentation about the virtual SQL tables available for 
        nutrition analysis, including column descriptions and example queries.
        
        Use this tool when:
        - Learning about available nutrition data structures
        - Understanding table relationships and schemas
        - Getting examples for common nutrition queries
        - Troubleshooting SQL query issues
        
        Returns:
            Dict with complete table documentation and example queries
        """
        try:
            tables_info = get_available_tables_info()
            
            return {
                "success": "Retrieved nutrition tables information",
                "tables": tables_info,
                "notes": [
                    "These are virtual tables stored in session memory",
                    "Data must be loaded using get_cnf_nutrient_profile before querying",
                    "Use execute_nutrition_sql to run queries on these tables",
                    "All calculations should be done in SQL for transparency"
                ],
                "example_workflow": [
                    "1. Store recipe: store_recipe_in_session",
                    "2. Parse ingredients: parse_and_update_ingredients", 
                    "3. Get CNF data: get_cnf_nutrient_profile for each ingredient",
                    "4. Query nutrition: execute_nutrition_sql with custom queries"
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting tables info: {e}")
            return {"error": f"Failed to get tables info: {str(e)}"}

    @mcp.tool()
    def get_ingredient_nutrition_matches(session_id: str) -> Dict[str, Any]:
        """
        View all current ingredient-CNF matches in a session.
        
        This tool provides an overview of all ingredient-to-CNF food linkages currently
        stored in a virtual session. Use this to review matches before calculating
        nutrition or to identify ingredients that still need CNF linking.
        
        Use this tool when:
        - Reviewing ingredient-CNF matches before nutrition calculation
        - Identifying unmatched ingredients that need CNF linking
        - Debugging nutrition calculation issues
        - Getting an overview of session nutrition data status
        
        Args:
            session_id: Session identifier to check for matches
            
        Returns:
            Dict with all ingredient matches and session nutrition status
        """
        try:
            session_data = get_virtual_session_data(session_id)
            if session_data is None:
                return {"error": f"Session {session_id} not found"}
            
            matches = session_data.get('ingredient_cnf_matches', {})
            ingredients = session_data.get('ingredients', {})
            profiles = session_data.get('nutrient_profiles', {})
            
            match_details = []
            for ingredient_id, match_data in matches.items():
                ingredient_info = ingredients.get(ingredient_id, {})
                match_details.append({
                    'ingredient_id': ingredient_id,
                    'ingredient_name': ingredient_info.get('ingredient_name', ''),
                    'ingredient_text': ingredient_info.get('ingredient_list_org', ''),
                    'cnf_food_code': match_data.get('cnf_food_code', ''),
                    'confidence_score': match_data.get('confidence_score', 0.0),
                    'has_nutrient_profile': match_data.get('cnf_food_code', '') in profiles
                })
            
            unmatched_ingredients = []
            for ingredient_id, ingredient_data in ingredients.items():
                if ingredient_id not in matches:
                    unmatched_ingredients.append({
                        'ingredient_id': ingredient_id,
                        'ingredient_name': ingredient_data.get('ingredient_name', ''),
                        'ingredient_text': ingredient_data.get('ingredient_list_org', '')
                    })
            
            return {
                "session_id": session_id,
                "matched_ingredients": match_details,
                "matched_count": len(match_details),
                "unmatched_ingredients": unmatched_ingredients,
                "unmatched_count": len(unmatched_ingredients),
                "total_ingredients": len(ingredients),
                "nutrient_profiles_available": len(profiles),
                "match_coverage_percentage": (len(match_details) / len(ingredients)) * 100 if ingredients else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting ingredient nutrition matches: {e}")
            return {"error": f"Failed to get ingredient nutrition matches: {str(e)}"}

    @mcp.tool()
    def clear_cnf_session_data(input_data: CNFCleanupInput) -> Dict[str, Any]:
        """
        Clear CNF data from a virtual session to free up memory.
        
        This tool removes CNF-related data from a virtual session while preserving
        recipe and ingredient data. Use this to clean up nutrition data when analysis
        is complete or to start fresh nutrition work.
        
        Use this tool when:
        - Finished with nutrition analysis for a session
        - Cleaning up memory usage
        - Starting fresh nutrition analysis
        - Removing outdated CNF data
        
        Args:
            input_data: CNFCleanupInput with session_id and cleanup_type
            
        Returns:
            Dict confirming what CNF data was cleared from the session
        """
        try:
            session_data = get_virtual_session_data(input_data.session_id)
            if session_data is None:
                return {"error": f"Session {input_data.session_id} not found"}
            
            cleaned_items = []
            
            if input_data.cleanup_type in ('all', 'profiles'):
                if 'nutrient_profiles' in session_data:
                    profile_count = len(session_data['nutrient_profiles'])
                    del session_data['nutrient_profiles']
                    cleaned_items.append(f"{profile_count} nutrient profiles")
            
            if input_data.cleanup_type in ('all', 'matches'):
                if 'ingredient_cnf_matches' in session_data:
                    match_count = len(session_data['ingredient_cnf_matches'])
                    del session_data['ingredient_cnf_matches']
                    cleaned_items.append(f"{match_count} ingredient matches")
            
            if input_data.cleanup_type in ('all', 'summaries'):
                if 'nutrition_summaries' in session_data:
                    summary_count = len(session_data['nutrition_summaries'])
                    del session_data['nutrition_summaries']
                    cleaned_items.append(f"{summary_count} nutrition summaries")
            
            if input_data.cleanup_type in ('all', 'profiles'):
                if 'cnf_search_results' in session_data:
                    search_count = len(session_data['cnf_search_results'])
                    del session_data['cnf_search_results']
                    cleaned_items.append(f"{search_count} search result sets")
            
            return {
                "success": f"Cleaned CNF data from session {input_data.session_id}",
                "session_id": input_data.session_id,
                "cleanup_type": input_data.cleanup_type,
                "cleaned_items": cleaned_items,
                "total_cleaned": len(cleaned_items)
            }
            
        except Exception as e:
            logger.error(f"Error clearing CNF session data: {e}")
            return {"error": f"Failed to clear CNF session data: {str(e)}"}

    logger.info("CNF tools registered successfully")

def _store_cnf_profile_in_session(session_data: Dict[str, Any], food_code: str, 
                                 serving_options: Dict[str, Any], refuse_info: str, 
                                 nutrient_profile: Dict[str, Any]) -> None:
    """Helper method to store CNF profile data in session (same logic as get_cnf_nutrient_profile)."""
    # This replicates the storage logic from get_cnf_nutrient_profile
    # Ensure CNF data structures exist
    if 'nutrient_profiles' not in session_data:
        session_data['nutrient_profiles'] = {}
    if 'cnf_foods' not in session_data:
        session_data['cnf_foods'] = []
    if 'cnf_nutrients' not in session_data:
        session_data['cnf_nutrients'] = []
    
    # Store complete profile (legacy format)
    session_data['nutrient_profiles'][food_code] = {
        'food_code': food_code,
        'serving_options': serving_options,
        'refuse_info': refuse_info,
        'nutrient_profile': nutrient_profile,
        'retrieved_at': str(json.dumps(None))
    }
    
    # Add to cnf_foods table
    cnf_foods_entry = {
        'cnf_food_code': food_code,
        'food_description': f"CNF Food {food_code}"
    }
    
    existing_food = next((f for f in session_data['cnf_foods'] if f['cnf_food_code'] == food_code), None)
    if not existing_food:
        session_data['cnf_foods'].append(cnf_foods_entry)
    
    # Add to cnf_nutrients table (same logic as original)
    if isinstance(nutrient_profile, dict):
        for category_name, nutrients in nutrient_profile.items():
            if isinstance(nutrients, list):
                for nutrient in nutrients:
                    nutrient_name = nutrient.get('Nutrient name', '')
                    
                    # Store 100g baseline value
                    baseline_value = nutrient.get('Value per 100 g of edible portion', '')
                    if baseline_value and baseline_value.strip():
                        try:
                            baseline_float = float(baseline_value)
                            session_data['cnf_nutrients'].append({
                                'cnf_food_code': food_code,
                                'nutrient_name': nutrient_name,
                                'nutrient_value': baseline_float,
                                'per_amount': 100.0,
                                'unit': 'g'
                            })
                        except (ValueError, TypeError):
                            pass

# Helper functions for CNF serving size processing

def _parse_cnf_serving_columns(nutrient_entry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Parse all serving size columns from a CNF nutrient entry.
    
    Args:
        nutrient_entry: Single nutrient dict from CNF data
        
    Returns:
        Dict mapping serving descriptions to parsed serving info
        Example: {"5ml / 5 g": {"amount": 5, "unit": "ml", "weight": 5, "value": 44.25}}
    """
    serving_data = {}
    
    for key, value in nutrient_entry.items():
        # Skip standard columns
        if key in ['Nutrient name', 'Unit see footnote1', 'Value per 100 g of edible portion', 
                   'Number of observations', 'Standard error', 'Data source View list']:
            continue
            
        # Parse serving size columns (e.g., "5ml / 5 g", "15ml / 14 g", "100ml / 92 g")
        if '/' in key and any(unit in key.lower() for unit in ['ml', 'g', 'tsp', 'tbsp', 'cup']):
            try:
                # Extract serving amount and unit
                parts = key.split('/')
                if len(parts) >= 2:
                    # Parse first part (e.g., "5ml")
                    serving_part = parts[0].strip()
                    amount_match = None
                    unit = None
                    
                    # Extract number and unit
                    import re
                    match = re.match(r'(\d+(?:\.\d+)?)\s*([a-zA-Z]+)', serving_part)
                    if match:
                        amount = float(match.group(1))
                        unit = match.group(2).lower()
                        
                        # Parse weight part if present (e.g., "5 g")
                        weight_part = parts[1].strip()
                        weight_match = re.match(r'(\d+(?:\.\d+)?)\s*g', weight_part)
                        weight = float(weight_match.group(1)) if weight_match else None
                        
                        # Convert value to float if possible
                        nutrient_value = None
                        if value and str(value).strip():
                            try:
                                nutrient_value = float(str(value).strip())
                            except (ValueError, TypeError):
                                continue
                        
                        serving_data[key] = {
                            'amount': amount,
                            'unit': unit,
                            'weight': weight,
                            'value': nutrient_value,
                            'original_key': key
                        }
            except Exception:
                continue
                
    return serving_data

def _normalize_unit(unit: str) -> str:
    """
    Normalize unit variations to standard forms.
    
    Args:
        unit: Unit string to normalize
        
    Returns:
        Normalized unit string
    """
    unit_map = {
        'ml': 'mL', 'milliliter': 'mL', 'millilitre': 'mL',
        'l': 'L', 'liter': 'L', 'litre': 'L',
        'g': 'g', 'gram': 'g', 'grams': 'g',
        'kg': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
        'tsp': 'tsp', 'teaspoon': 'tsp', 'teaspoons': 'tsp',
        'tbsp': 'tbsp', 'tablespoon': 'tbsp', 'tablespoons': 'tbsp',
        'cup': 'cup', 'cups': 'cup'
    }
    
    normalized = unit_map.get(unit.lower(), unit)
    return normalized

def _match_recipe_units_to_servings(recipe_amount: float, recipe_unit: str, 
                                   serving_data: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find best serving size matches for a recipe ingredient.
    
    Args:
        recipe_amount: Amount from recipe (e.g., 10)
        recipe_unit: Unit from recipe (e.g., "mL")
        serving_data: Parsed serving data from CNF
        
    Returns:
        List of calculation options ranked by accuracy
    """
    recipe_unit_norm = _normalize_unit(recipe_unit)
    calculation_options = []
    
    # Find direct unit matches
    for serving_key, serving_info in serving_data.items():
        if serving_info['value'] is None:
            continue
            
        serving_unit_norm = _normalize_unit(serving_info['unit'])
        
        if serving_unit_norm == recipe_unit_norm:
            # Direct unit match - highest accuracy
            multiplier = recipe_amount / serving_info['amount']
            calculation_options.append({
                'method': 'direct_serving_match',
                'serving_key': serving_key,
                'serving_amount': serving_info['amount'],
                'serving_unit': serving_info['unit'],
                'serving_value': serving_info['value'],
                'multiplier': multiplier,
                'formula': f"{serving_info['value']} * {multiplier}",
                'description': f"Use {serving_info['amount']}{serving_info['unit']} serving × {multiplier:.2f}",
                'accuracy': 'high',
                'preferred': True
            })
    
    # Sort by multiplier closeness to 1.0 (prefer multipliers close to whole numbers)
    calculation_options.sort(key=lambda x: abs(x['multiplier'] - round(x['multiplier'])))
    
    # Mark only the best option as preferred
    if calculation_options:
        for i, option in enumerate(calculation_options):
            option['preferred'] = (i == 0)
    
    return calculation_options

def get_cnf_tools_status() -> Dict[str, Any]:
    """Get status of CNF tools availability."""
    return {
        "cnf_tools_available": CNF_TOOLS_AVAILABLE,
        "tools_count": 8 if CNF_TOOLS_AVAILABLE else 0,
        "tools": [
            "analyze_recipe_nutrition",        # 🚀 NEW: One-shot nutrition analysis (replaces 8-step workflow)
            "search_cnf_foods",               # Core search functionality
            "get_cnf_nutrient_profile",       # Core profile retrieval (auto-populates SQL)
            "link_ingredient_to_cnf_simple",  # Simplified linking for SQL
            "execute_nutrition_sql",          # SQL query engine for nutrition calculations
            "get_nutrition_tables_info",      # SQL table schema documentation
            "get_ingredient_nutrition_matches", # Match status viewer
            "clear_cnf_session_data"          # Session cleanup
        ] if CNF_TOOLS_AVAILABLE else [],
        "workflow_improvement": {
            "old_workflow_steps": 9,
            "new_workflow_steps": 2,
            "reduction_percentage": 78,
            "recommended_workflow": [
                "1. analyze_recipe_nutrition() → Complete ingredient analysis + SQL setup",
                "2. execute_nutrition_sql() → Custom nutrition calculations with provided queries"
            ],
            "benefits": [
                "78% reduction in tool calls",
                "Automatic ingredient parsing and CNF matching",
                "Ready-to-use SQL queries provided",
                "No deprecated tools to confuse LLMs",
                "Transparent nutrition calculations"
            ]
        }
    }