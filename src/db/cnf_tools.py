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
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Callable
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

# Import config first to ensure constants are available
try:
    from src.config import CNF_MAX_CONCURRENT, CNF_CACHE_TTL, BULK_OPERATION_TIMEOUT
except ImportError:
    try:
        from config import CNF_MAX_CONCURRENT, CNF_CACHE_TTL, BULK_OPERATION_TIMEOUT
    except ImportError:
        CNF_MAX_CONCURRENT = 3
        CNF_CACHE_TTL = 1800
        BULK_OPERATION_TIMEOUT = 60

try:
    from src.models.cnf_models import (
        CNFSearchInput, CNFProfileInput, CNFMacronutrientsInput, CNFBulkMacronutrientsInput, CNFSearchAndGetInput,
        SQLQueryInput, CNFFoodResult, CNFNutrientProfile, IngredientCNFMatch,
        RecipeNutritionSummary, CNFSessionSummary, IngredientNutritionData,
        AnalyzeRecipeNutritionInput, RecipeNutritionCalculationInput,
        IngredientNutritionBreakdownInput, DailyNutritionComparisonInput,
        RecipeMacrosQueryInput, RecipeMacrosUpdateInput
    )
    from src.api.cnf_api import get_cnf_api_client, CORE_MACRONUTRIENT_IDS, parse_measure_name
    from src.db.schema import get_virtual_session_data, store_recipe_in_virtual_session
    from src.db.sql_engine import VirtualSQLEngine, get_available_tables_info
    from src.db.connection import get_db_connection
    CNF_TOOLS_AVAILABLE = True
except ImportError:
    try:
        from models.cnf_models import (
            CNFSearchInput, CNFProfileInput, CNFMacronutrientsInput, CNFBulkMacronutrientsInput, CNFSearchAndGetInput,
            SQLQueryInput, CNFFoodResult, CNFNutrientProfile, IngredientCNFMatch,
            RecipeNutritionSummary, CNFSessionSummary, IngredientNutritionData,
            AnalyzeRecipeNutritionInput, RecipeNutritionCalculationInput,
            IngredientNutritionBreakdownInput, DailyNutritionComparisonInput
        )
        from api.cnf_api import get_cnf_api_client, CORE_MACRONUTRIENT_IDS, parse_measure_name
        from db.schema import get_virtual_session_data, store_recipe_in_virtual_session
        from db.sql_engine import VirtualSQLEngine, get_available_tables_info
        from db.connection import get_db_connection
        CNF_TOOLS_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: CNF tools not available due to import error: {e}", file=sys.stderr)

# Configure logging with environment-based level control
LOG_LEVEL = os.getenv('FOODGUIDE_LOG_LEVEL', 'ERROR')
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
#logger = logging.getLogger(__name__)

# Global caching
_cnf_cache = {}
_cache_lock = threading.Lock()

class CNFCache:
    """Thread-safe cache for CNF API responses."""
    
    def __init__(self, ttl: int = CNF_CACHE_TTL):
        self.cache = {}
        self.timestamps = {}
        self.ttl = ttl
        self.lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        with self.lock:
            if key in self.cache:
                if time.time() - self.timestamps[key] < self.ttl:
                    return self.cache[key]
                else:
                    # Remove expired entry
                    del self.cache[key]
                    del self.timestamps[key]
            return None
    
    def set(self, key: str, value: Any) -> None:
        """Cache a value with timestamp."""
        with self.lock:
            self.cache[key] = value
            self.timestamps[key] = time.time()
    
    def clear_expired(self) -> None:
        """Remove all expired entries."""
        current_time = time.time()
        with self.lock:
            expired_keys = [
                key for key, timestamp in self.timestamps.items()
                if current_time - timestamp >= self.ttl
            ]
            for key in expired_keys:
                del self.cache[key]
                del self.timestamps[key]

# Global cache instance
_cnf_cache_instance = CNFCache()

def _store_nutrients_in_db(
    cursor,
    session_id: str,
    food_code: str,
    nutrients: List[Dict],
    servings: List[Dict],
    macros_only: bool = True,
) -> int:
    """Shared helper: store nutrient data from the CNF API into SQLite.

    Args:
        cursor: SQLite cursor
        session_id: Session identifier
        food_code: CNF food code
        nutrients: Raw nutrient list from api.get_nutrient_amounts()
        servings: Parsed serving list from api.get_serving_sizes()
        macros_only: If True, only store CORE_MACRONUTRIENT_IDS

    Returns:
        Number of nutrient rows stored.
    """
    count = 0

    for n in nutrients:
        nid = n.get("nutrient_name_id")

        if macros_only and nid not in CORE_MACRONUTRIENT_IDS:
            continue

        value_per_100g = n.get("nutrient_value", 0.0) or 0.0

        # Determine name/unit/symbol — prefer CORE_MACRONUTRIENT_IDS lookup, fall back to API fields
        if nid in CORE_MACRONUTRIENT_IDS:
            info = CORE_MACRONUTRIENT_IDS[nid]
            nutrient_name = info["name"]
            nutrient_symbol = info["unit"]
        else:
            nutrient_name = n.get("nutrient_web_name", "")
            nutrient_symbol = n.get("nutrient_web_unit", "")

        # Store 100g baseline
        cursor.execute("""
            INSERT OR REPLACE INTO temp_cnf_nutrients
            (session_id, cnf_food_code, nutrient_name, nutrient_value,
             per_amount, unit, nutrient_symbol)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, food_code, nutrient_name, value_per_100g, 100.0, 'g', nutrient_symbol))
        count += 1

        # Store per-serving values
        for s in servings:
            factor = s.get("conversion_factor_value", 1.0)
            serving_value = value_per_100g * factor
            amount, unit = parse_measure_name(s.get("measure_name", ""))
            cursor.execute("""
                INSERT OR REPLACE INTO temp_cnf_nutrients
                (session_id, cnf_food_code, nutrient_name, nutrient_value,
                 per_amount, unit, nutrient_symbol)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, food_code, nutrient_name, serving_value, amount, unit, nutrient_symbol))
            count += 1

    return count


def process_single_food_code(
    food_code: str,
    session_id: str,
    preferred_units: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[str, str], None]] = None
) -> Dict[str, Any]:
    """Process a single food code via the CNF API with caching."""
    try:
        if progress_callback:
            progress_callback(food_code, "starting")

        # Check cache first
        cache_key = f"{food_code}_{preferred_units or 'default'}"
        cached_result = _cnf_cache_instance.get(cache_key)

        if cached_result:
            if progress_callback:
                progress_callback(food_code, "cached")
            return {
                "status": "success",
                "food_code": food_code,
                "cached": True,
                "data": cached_result
            }

        api = get_cnf_api_client()

        if progress_callback:
            progress_callback(food_code, "fetching_nutrients")

        nutrients = api.get_nutrient_amounts(food_code)
        servings = api.get_serving_sizes(food_code)
        refuse = api.get_refuse_amount(food_code)
        food_info = api.get_food(food_code)

        if not nutrients:
            return {
                "status": "failed",
                "food_code": food_code,
                "error": "Could not retrieve nutrient data",
                "suggestion": "Verify food code is valid"
            }

        result_data = {
            "nutrients": nutrients,
            "servings": servings,
            "refuse": refuse,
            "food_info": food_info,
        }
        _cnf_cache_instance.set(cache_key, result_data)

        if progress_callback:
            progress_callback(food_code, "completed")

        return {
            "status": "success",
            "food_code": food_code,
            "cached": False,
            "data": result_data
        }

    except Exception as e:
        if progress_callback:
            progress_callback(food_code, f"error: {str(e)}")
        return {
            "status": "failed",
            "food_code": food_code,
            "error": str(e),
            "suggestion": "Check network connection and CNF API availability"
        }

def register_cnf_tools(mcp: FastMCP, enable_db: bool = True) -> None:
    """Register CNF tools with the FastMCP server.

    Args:
        mcp: The FastMCP server instance.
        enable_db: When True, registers recipe-analysis tools and enables SQLite
                   storage in search tools. When False (HTTP mode), search tools
                   still scrape and return data but skip DB writes, and recipe-analysis
                   tools are not registered.
    """
    if not CNF_TOOLS_AVAILABLE:
        ###logger.warning("CNF tools not available - skipping registration")
        return

    @mcp.tool()
    def search_and_get_cnf_macronutrients(input_data: CNFSearchAndGetInput) -> Dict[str, Any]:
        """
        Search Canadian Nutrient File foods and retrieve core macronutrient data.
        
        This tool searches Health Canada's CNF database for foods matching the provided name
        and returns either complete macronutrient data for single matches or a list of
        options for multiple matches. It focuses on 13 core macronutrients essential for
        basic nutrition analysis while maintaining compatibility with session-based storage.
        
        Use this tool to:
        - Discover CNF foods matching ingredient names from recipes
        - Retrieve core macronutrient data for immediate nutrition analysis
        - Identify available food options when multiple matches exist
        - Prepare data for recipe nutrition calculations
        
        The tool returns different outputs based on search results:
        - Single match: Complete macronutrient data stored in session tables
        - Multiple matches: List of food options with codes for selection
        - No matches: Error message with search suggestions
        
        Args:
            input_data: Contains food_name (search term), session_id (storage identifier),
                       optional preferred_units (serving size filter), and max_results (limit)
            
        Returns:
            Dict with search results, macronutrient data, or error message depending on
            number of matches found
        """
        try:
            api = get_cnf_api_client()

            # Step 1: Search for foods (cached food list — zero network calls after first)
            search_results = api.search_food(input_data.food_name, max_results=input_data.max_results or 10)

            if not search_results:
                return {
                    "message": f"No foods found matching: '{input_data.food_name}'",
                    "search_term": input_data.food_name,
                    "suggestions": [
                        "Try simpler terms (e.g., 'honey' instead of 'liquid honey')",
                        "Check spelling and use common food names",
                        "Search for base ingredients without brands or preparation methods"
                    ]
                }

            # Step 2: If single result, auto-fetch macronutrients
            if len(search_results) == 1:
                selected_food = search_results[0]
                food_code = selected_food['food_code']
                food_description = selected_food['food_name']

                # Fetch nutrient + serving data from API
                nutrients = api.get_nutrient_amounts(food_code)
                servings = api.get_serving_sizes(food_code)
                refuse = api.get_refuse_amount(food_code)

                if not nutrients:
                    return {
                        "error": f"Found food '{food_description}' but failed to get nutrient data",
                        "food_code": food_code,
                        "search_results": search_results
                    }

                # Store in SQL tables
                nutrients_stored = 0
                if enable_db:
                    from .schema import create_temp_nutrition_session, update_session_access_time

                    create_temp_nutrition_session(input_data.session_id)
                    update_session_access_time(input_data.session_id)

                    with get_db_connection() as conn:
                        cursor = conn.cursor()

                        cursor.execute("""
                            INSERT OR REPLACE INTO temp_cnf_foods
                            (session_id, cnf_food_code, food_description, ingredient_name, refuse_flag, refuse_amount)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            input_data.session_id, food_code, food_description,
                            None, bool(refuse), None
                        ))

                        cursor.execute("""
                            DELETE FROM temp_cnf_nutrients
                            WHERE session_id = ? AND cnf_food_code = ?
                        """, (input_data.session_id, food_code))

                        nutrients_stored = _store_nutrients_in_db(
                            cursor, input_data.session_id, food_code,
                            nutrients, servings, macros_only=True
                        )
                        conn.commit()

                return {
                    "success": True,
                    "action": "auto_fetched_macronutrients",
                    "message": f"Found single match and automatically fetched macronutrients",
                    "food_selected": {
                        "food_code": food_code,
                        "food_name": food_description
                    },
                    "macronutrients_stored": nutrients_stored,
                    "serving_options_available": len(servings),
                    "efficiency_stats": {
                        "search_results_count": 1,
                        "macronutrients_stored": nutrients_stored,
                        "tool_calls_saved": "Saved 1-2 tool calls vs separate search + get_macronutrients"
                    },
                    "next_steps": [
                        f"Use get_cnf_macronutrients_only() with ingredient_id to link ingredients to food_code '{food_code}'",
                        "Run nutrition analysis queries with stored macronutrient data",
                        "Calculate recipe totals using sophisticated unit conversion queries"
                    ]
                }

            # Step 3: Multiple results — let LLM choose
            else:
                return {
                    "action": "multiple_results_found",
                    "message": f"Found {len(search_results)} foods matching '{input_data.food_name}' - LLM should select best match",
                    "search_term": input_data.food_name,
                    "search_results": [
                        {
                            "food_code": result['food_code'],
                            "food_name": result['food_name'],
                            "selection_guidance": f"Use get_cnf_macronutrients_only(food_code='{result['food_code']}') to fetch this option"
                        }
                        for result in search_results
                    ],
                    "selection_instructions": [
                        "Review the food options above",
                        "Choose the food_code that best matches your ingredient",
                        "RECOMMENDED: Use bulk_get_cnf_macronutrients(food_codes=['chosen_codes']) for multiple ingredients",
                        "ALTERNATIVE: get_cnf_macronutrients_only(food_code='chosen_code') for single ingredient",
                        "Or try a more specific search term to get fewer results"
                    ],
                    "efficiency_note": f"For maximum efficiency, collect multiple food codes and use bulk_get_cnf_macronutrients()"
                }

        except Exception as e:
            return {"error": f"Error in combined search and macronutrient fetch: {str(e)}"}
    
    @mcp.tool()
    def get_cnf_macronutrients_only(input_data: CNFMacronutrientsInput) -> Dict[str, Any]:
        """
        Retrieve core macronutrients for a specific CNF food code with automatic ingredient linking.
        
        This tool fetches macronutrient data directly from Health Canada's CNF database using
        a known food code and optionally links the data to recipe ingredients for nutrition
        calculations. It stores only 13 essential macronutrients for efficient processing
        while maintaining compatibility with session-based nutrition analysis tools.
        
        **TEMP_RECIPE_MACROS WORKFLOW GUIDANCE:**
        After using this tool, you can populate the temp_recipe_macros table for cached calculations:
        
        1. **Check ingredient data quality first:**
           Query: `SELECT ingredient_id, amount, unit FROM temp_recipe_ingredients WHERE amount IS NULL`
           Fix missing data: `UPDATE temp_recipe_ingredients SET amount = 150, unit = 'g' WHERE ingredient_id = 'salmon_001'`
        
        2. **Review available serving sizes for matching:**
           Query: `SELECT per_amount, unit, nutrient_value FROM temp_cnf_nutrients WHERE cnf_food_code = '4294' AND nutrient_name = 'Energy (kcal)'`
           Example: honey 10.0 mL → CNF options: 5.0 ml (22 kcal), 15.0 ml (65 kcal), 100.0 ml (435 kcal)
        
        3. **Choose best serving match and populate temp_recipe_macros:**
           ```sql
           INSERT INTO temp_recipe_macros (
               session_id, recipe_id, ingredient_id, cnf_food_code, 
               matched_serving_amount, matched_serving_unit, conversion_factor,
               calories_per_recipe_amount, protein_per_recipe_amount, fat_per_recipe_amount, 
               carbs_per_recipe_amount, sodium_per_recipe_amount, fiber_per_recipe_amount
           )
           SELECT 
               'session_id', 'recipe_id', 'honey_001', '4294',
               5.0, 'ml', (10.0 / 5.0),  -- 2.0x conversion factor
               22.0 * (10.0 / 5.0),     -- 44.0 calories for recipe amount
               0.02 * (10.0 / 5.0),     -- scaled protein
               0.0 * (10.0 / 5.0),      -- scaled fat
               5.9 * (10.0 / 5.0),      -- scaled carbs
               0.0 * (10.0 / 5.0),      -- scaled sodium (if available)
               0.0 * (10.0 / 5.0)       -- scaled fiber (if available)
           ```
        
        4. **Calculate recipe totals from cached data:**
           Query: `SELECT SUM(calories_per_recipe_amount) as total_calories FROM temp_recipe_macros WHERE session_id = ? AND recipe_id = ?`
        
        Use this tool to:
        - Fetch macronutrients when you have a specific CNF food code
        - Link CNF data to recipe ingredients for nutrition calculations
        - Store streamlined nutrient data for efficient analysis
        - Prepare data for temp_recipe_macros population workflow
        
        When ingredient_id and recipe_id are provided, the tool automatically updates
        the recipe ingredient with the CNF food code, enabling calculate_recipe_nutrition_summary
        to work correctly. This eliminates the need for separate linking steps.
        
        Args:
            input_data: Contains food_code (CNF identifier), session_id (storage location),
                       optional ingredient_id and recipe_id (for automatic linking),
                       and preferred_units (serving size filter)
            
        Returns:
            Dict with macronutrient data, linking status, and guidance for next steps
        """
        try:
            from .schema import update_session_access_time
            update_session_access_time(input_data.session_id)

            api = get_cnf_api_client()

            # Fetch nutrient + serving data from API
            nutrients = api.get_nutrient_amounts(input_data.food_code)
            servings = api.get_serving_sizes(input_data.food_code)
            refuse = api.get_refuse_amount(input_data.food_code)
            food_info = api.get_food(input_data.food_code)

            if not nutrients:
                return {
                    "error": f"Could not retrieve nutrient data for food code '{input_data.food_code}'",
                    "food_code": input_data.food_code,
                    "suggestion": "Verify the food code is valid - try searching with search_and_get_cnf_macronutrients first"
                }

            food_description = food_info["food_description"] if food_info else f"CNF Food {input_data.food_code}"
            nutrients_stored = 0
            linking_status = "no_linking_requested"

            if enable_db:
                with get_db_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute("""
                        INSERT OR REPLACE INTO temp_cnf_foods
                        (session_id, cnf_food_code, food_description, ingredient_name, refuse_flag, refuse_amount)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        input_data.session_id, input_data.food_code, food_description,
                        None, bool(refuse), None
                    ))

                    cursor.execute("""
                        DELETE FROM temp_cnf_nutrients
                        WHERE session_id = ? AND cnf_food_code = ?
                    """, (input_data.session_id, input_data.food_code))

                    nutrients_stored = _store_nutrients_in_db(
                        cursor, input_data.session_id, input_data.food_code,
                        nutrients, servings, macros_only=True
                    )

                    # Link ingredient if provided
                    if input_data.ingredient_id and input_data.recipe_id:
                        cursor.execute("""
                            UPDATE temp_recipe_ingredients
                            SET cnf_food_code = ?
                            WHERE session_id = ? AND recipe_id = ? AND ingredient_id = ?
                        """, (input_data.food_code, input_data.session_id, input_data.recipe_id, input_data.ingredient_id))

                        rows_updated = cursor.rowcount
                        if rows_updated > 0:
                            linking_status = f"linked_ingredient_{input_data.ingredient_id}"
                        else:
                            linking_status = f"ingredient_not_found_{input_data.ingredient_id}"

                    conn.commit()

            return {
                "success": True,
                "action": "macronutrients_fetched_and_linked",
                "message": f"Successfully fetched {nutrients_stored} core macronutrient records for food code '{input_data.food_code}'",
                "food_code": input_data.food_code,
                "food_description": food_description,
                "session_id": input_data.session_id,
                "macronutrients_stored": nutrients_stored,
                "serving_options_available": len(servings),
                "ingredient_linking": {
                    "status": linking_status,
                    "ingredient_id": input_data.ingredient_id,
                    "recipe_id": input_data.recipe_id,
                    "cnf_food_code": input_data.food_code
                },
                "next_steps": [
                    "calculate_recipe_nutrition_summary() should now work because ingredients are properly linked",
                    "Or continue linking more ingredients before running nutrition calculations"
                ],
                "storage_location": "temp_cnf_foods and temp_cnf_nutrients tables in SQLite"
            }

        except Exception as e:
            return {
                "error": f"Error fetching macronutrients for food code '{input_data.food_code}': {str(e)}",
                "food_code": input_data.food_code,
                "session_id": input_data.session_id,
                "suggestion": "Verify food code is valid and try again, or use search_and_get_cnf_macronutrients() to find correct food code"
            }

    @mcp.tool()
    def bulk_get_cnf_macronutrients(input_data: CNFBulkMacronutrientsInput) -> Dict[str, Any]:
        """
        Process multiple CNF food codes efficiently with automatic ingredient linking for streamlined recipe nutrition analysis.

        This tool retrieves core macronutrient data for up to 20 food codes simultaneously from Health Canada's official Canadian Nutrient File database. It provides massive efficiency gains for multi-ingredient recipes by processing all nutrition data in a single operation while optionally linking each food to specific recipe ingredients automatically.

        The tool fetches 13 essential macronutrients for each food code:
        - Energy (kcal), Protein, Total Fat, Carbohydrate
        - Saturated Fat, Monounsaturated Fat, Polyunsaturated Fat, Trans Fat  
        - Dietary Fiber, Sugars, Sodium, Cholesterol, Energy (kJ)

        Advanced features include automatic ingredient linking when ingredient_mappings are provided, allowing the tool to connect CNF nutrition data directly to recipe ingredients in one operation. This eliminates the need for separate linking steps and enables immediate nutrition calculations.

        Use this tool for:
        - Multi-ingredient recipe nutrition analysis with automatic linking
        - Bulk processing of known CNF food codes for maximum efficiency
        - Recipe preparation workflows where ingredient-CNF relationships are known
        - Large-scale nutrition data preparation with minimal tool call overhead

        Args:
        input_data: Contains food_codes (list of up to 20 CNF identifiers), session_id (data storage location),
                optional preferred_units (serving size preferences), continue_on_error (error handling mode),
                optional ingredient_mappings (food_code to ingredient_id mapping), and optional recipe_id 
                (required for automatic ingredient linking)

        Returns:
        Dict with bulk processing results, success/failure counts for each food, ingredient linking status,
        efficiency metrics, and guidance for next steps in nutrition analysis workflow
        """
        try:
            if enable_db:
                from .schema import update_session_access_time
                update_session_access_time(input_data.session_id)

            total_foods = len(input_data.food_codes)
            successful_foods = []
            failed_foods = []
            total_nutrients_stored = 0
            start_time = time.time()

            # Fetch data concurrently via API
            fetch_results = []
            with ThreadPoolExecutor(max_workers=min(CNF_MAX_CONCURRENT, total_foods)) as executor:
                future_to_food_code = {
                    executor.submit(
                        process_single_food_code,
                        food_code,
                        input_data.session_id,
                        input_data.preferred_units,
                        None
                    ): food_code
                    for food_code in input_data.food_codes
                }

                for future in as_completed(future_to_food_code, timeout=BULK_OPERATION_TIMEOUT):
                    try:
                        result = future.result()
                        fetch_results.append(result)
                    except Exception as e:
                        food_code = future_to_food_code[future]
                        fetch_results.append({
                            "status": "failed",
                            "food_code": food_code,
                            "error": str(e),
                            "suggestion": "Check network connectivity and try again"
                        })
                        if not input_data.continue_on_error:
                            break

            # Process results and store in DB
            for result in fetch_results:
                if result["status"] == "failed":
                    failed_foods.append({
                        "food_code": result["food_code"],
                        "error": result["error"],
                        "suggestion": result.get("suggestion", "Try again")
                    })
                    if not input_data.continue_on_error:
                        break
                    continue

                food_code = result["food_code"]
                result_data = result["data"]
                food_info = result_data.get("food_info")
                food_description = food_info["food_description"] if food_info else f"CNF Food {food_code}"

                successful_foods.append({
                    "food_code": food_code,
                    "food_description": food_description,
                    "nutrients_stored": 0,
                    "serving_options": len(result_data.get("servings", [])),
                    "ingredient_linking": "no_linking_requested"
                })

            # Store in SQLite when DB is available
            if enable_db:
                with get_db_connection() as conn:
                    cursor = conn.cursor()

                    for result in fetch_results:
                        if result["status"] == "failed":
                            continue

                        try:
                            food_code = result["food_code"]
                            result_data = result["data"]
                            raw_nutrients = result_data["nutrients"]
                            raw_servings = result_data["servings"]
                            refuse = result_data.get("refuse")
                            food_info = result_data.get("food_info")
                            food_description = food_info["food_description"] if food_info else f"CNF Food {food_code}"

                            cursor.execute("""
                                INSERT OR REPLACE INTO temp_cnf_foods
                                (session_id, cnf_food_code, food_description, ingredient_name, refuse_flag, refuse_amount)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (input_data.session_id, food_code, food_description, None, bool(refuse), None))

                            cursor.execute("""
                                DELETE FROM temp_cnf_nutrients
                                WHERE session_id = ? AND cnf_food_code = ?
                            """, (input_data.session_id, food_code))

                            nutrients_stored_this_food = _store_nutrients_in_db(
                                cursor, input_data.session_id, food_code,
                                raw_nutrients, raw_servings, macros_only=True
                            )

                            # Link ingredient if mapping provided
                            linking_status = "no_linking_requested"
                            if hasattr(input_data, 'ingredient_mappings') and input_data.ingredient_mappings and input_data.recipe_id:
                                ingredient_id = input_data.ingredient_mappings.get(food_code)
                                if ingredient_id:
                                    cursor.execute("""
                                        UPDATE temp_recipe_ingredients
                                        SET cnf_food_code = ?
                                        WHERE session_id = ? AND recipe_id = ? AND ingredient_id = ?
                                    """, (food_code, input_data.session_id, input_data.recipe_id, ingredient_id))

                                    rows_updated = cursor.rowcount
                                    if rows_updated > 0:
                                        linking_status = f"linked_to_{ingredient_id}"
                                    else:
                                        linking_status = f"ingredient_not_found_{ingredient_id}"

                            for entry in successful_foods:
                                if entry["food_code"] == food_code:
                                    entry["nutrients_stored"] = nutrients_stored_this_food
                                    entry["ingredient_linking"] = linking_status
                                    break
                            total_nutrients_stored += nutrients_stored_this_food

                        except Exception:
                            pass

                    conn.commit()

            # Calculate metrics
            success_rate = (len(successful_foods) / total_foods) * 100 if total_foods > 0 else 0
            avg_nutrients_per_food = total_nutrients_stored / len(successful_foods) if successful_foods else 0
            linked_ingredients = sum(1 for food in successful_foods if food["ingredient_linking"].startswith("linked_to_"))
            linking_requested = bool(hasattr(input_data, 'ingredient_mappings') and input_data.ingredient_mappings and input_data.recipe_id)

            return {
                "success": True,
                "action": "bulk_macronutrients_processed_with_linking" if linking_requested else "bulk_macronutrients_processed",
                "message": f"Processed {len(successful_foods)}/{total_foods} food codes in {time.time() - start_time:.2f}s" + (f" with {linked_ingredients} ingredients linked" if linking_requested else ""),
                "session_id": input_data.session_id,
                "processing_summary": {
                    "total_foods_requested": total_foods,
                    "successful_foods": len(successful_foods),
                    "failed_foods": len(failed_foods),
                    "success_rate_percent": round(success_rate, 1),
                    "total_nutrients_stored": total_nutrients_stored,
                    "avg_nutrients_per_food": round(avg_nutrients_per_food, 1)
                },
                "ingredient_linking": {
                    "linking_requested": linking_requested,
                    "recipe_id": input_data.recipe_id if linking_requested else None,
                    "ingredients_linked": linked_ingredients,
                    "total_mappings_provided": len(input_data.ingredient_mappings) if linking_requested else 0,
                    "linking_success_rate": round((linked_ingredients / len(input_data.ingredient_mappings) * 100), 1) if linking_requested and input_data.ingredient_mappings else 0
                },
                "efficiency_gains": {
                    "tool_calls_saved": f"Processed {total_foods} foods in 1 call vs {total_foods} individual calls",
                    "concurrent_processing": f"Used {min(CNF_MAX_CONCURRENT, total_foods)} concurrent workers",
                    "caching_efficiency": f"Cache hits: {sum(1 for r in fetch_results if r.get('cached', False))}/{total_foods}",
                },
                "successful_foods": successful_foods,
                "failed_foods": failed_foods,
                "next_steps": [
                    "calculate_recipe_nutrition_summary() should now work for linked ingredients" if linking_requested and linked_ingredients > 0 else "Use calculate_recipe_nutrition_summary() for nutrition analysis",
                    "Or link individual foods to recipe ingredients using get_cnf_macronutrients_only() with ingredient_id",
                    "Failed foods can be retried individually if needed"
                ],
                "storage_location": "temp_cnf_foods and temp_cnf_nutrients tables in SQLite"
            }

        except Exception as e:
            return {
                "error": f"Bulk processing error: {str(e)}",
                "session_id": input_data.session_id,
                "food_codes_attempted": input_data.food_codes,
                "suggestion": "Try processing smaller batches or individual food codes"
            }

    @mcp.tool()
    def get_cnf_nutrient_profile(input_data: CNFProfileInput) -> Dict[str, Any]:
        """
        Retrieve complete nutrient profile with all available nutrients for research-grade analysis.
        
        This tool fetches comprehensive nutrient data from Health Canada's CNF database,
        including all vitamins, minerals, fatty acids, and other micronutrients. It stores
        significantly more data than the streamlined macronutrient tools and should be
        used only when detailed micronutrient analysis is specifically required.
        
        Use this tool for:
        - Detailed vitamin and mineral analysis
        - Research-grade nutritional studies
        - Micronutrient deficiency assessment
        - Academic or professional nutrition work requiring complete profiles
        
        For basic recipe nutrition analysis, consider using get_cnf_macronutrients_only
        which provides 13 core nutrients with significantly reduced data complexity.
        This tool processes all available nutrients (146+) and may impact performance.
        
        Args:
            input_data: Contains food_code (CNF identifier), session_id (storage location),
                       and optional preferred_units (serving size preferences)
            
        Returns:
            Dict with complete nutrient profile data and storage confirmation
        """
        try:
            api = get_cnf_api_client()

            # Fetch all nutrients + servings from API
            nutrients = api.get_nutrient_amounts(input_data.food_code)
            servings = api.get_serving_sizes(input_data.food_code)
            refuse = api.get_refuse_amount(input_data.food_code)
            food_info = api.get_food(input_data.food_code)

            if not nutrients:
                return {"error": f"Failed to get nutrient data for food code: {input_data.food_code}"}

            food_description = food_info["food_description"] if food_info else f"CNF Food {input_data.food_code}"
            nutrient_count = 0

            if enable_db:
                from .schema import create_temp_nutrition_session, update_session_access_time

                create_temp_nutrition_session(input_data.session_id)
                update_session_access_time(input_data.session_id)

                with get_db_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute("""
                        INSERT OR REPLACE INTO temp_cnf_foods
                        (session_id, cnf_food_code, food_description, ingredient_name, refuse_flag, refuse_amount)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        input_data.session_id, input_data.food_code, food_description,
                        None, bool(refuse), None
                    ))

                    cursor.execute("""
                        DELETE FROM temp_cnf_nutrients
                        WHERE session_id = ? AND cnf_food_code = ?
                    """, (input_data.session_id, input_data.food_code))

                    # Store ALL nutrients (not just macros)
                    nutrient_count = _store_nutrients_in_db(
                        cursor, input_data.session_id, input_data.food_code,
                        nutrients, servings, macros_only=False
                    )
                    conn.commit()

            # Backward compatibility: store in virtual session for legacy tools
            session_data = get_virtual_session_data(input_data.session_id)
            if session_data is None:
                from src.db.schema import create_virtual_recipe_session
                create_virtual_recipe_session(input_data.session_id)
                session_data = get_virtual_session_data(input_data.session_id)

            if 'nutrient_profiles' not in session_data:
                session_data['nutrient_profiles'] = {}

            session_data['nutrient_profiles'][input_data.food_code] = {
                'food_code': input_data.food_code,
                'food_description': food_description,
                'total_nutrients': len(nutrients),
                'serving_sizes': len(servings),
                'refuse': refuse,
            }

            return {
                "success": True,
                "food_code": input_data.food_code,
                "food_description": food_description,
                "session_id": input_data.session_id,
                "storage_type": "persistent_sqlite",
                "nutrient_records_stored": nutrient_count,
                "total_nutrients_from_api": len(nutrients),
                "serving_options": len(servings),
                "next_step": "Use get_cnf_macronutrients_only() with ingredient_id to link ingredients",
                "data_source": "Health Canada CNF REST API"
            }

        except Exception as e:
            return {"error": f"Failed to get CNF nutrient profile: {str(e)}"}

    # Recipe analysis tools require SQLite for temp table storage
    if not enable_db:
        return

    @mcp.tool()
    def simple_recipe_setup(input_data: AnalyzeRecipeNutritionInput) -> Dict[str, Any]:
        """
        Transfer recipe data to analysis tables with comprehensive ingredient parsing for streamlined nutrition analysis preparation.
        
        This tool prepares complete recipe data for CNF nutrition analysis by transferring stored recipe information from virtual session storage to temporary database tables and automatically parsing ingredient text into structured components. It provides the essential foundation for linking ingredients to CNF foods and calculating detailed nutrition summaries.
        
        The tool performs comprehensive ingredient parsing that handles complex measurement formats including:
        - Unicode fractions (½, ⅓, ¼, ¾, etc.) converted to precise decimal values
        - Mixed numbers (1½, 2¼) with accurate decimal conversion
        - Regular fractions (1/2, 3/4) and measurement ranges (2-3 cups)
        - All standard units (mL, cups, tsp, tbsp, kg, g, lbs, oz)
        - Ingredient preparation notes (sliced, chopped, optional)
        
        Use this tool for:
        - Complete recipe data transfer from session storage to analysis tables
        - Automatic ingredient parsing into structured amount, unit, and name components
        - Foundation preparation for CNF food linking and nutrition calculations
        - Streamlined setup for multi-step recipe nutrition analysis workflows
        
        The processed data includes recipe metadata, fully parsed ingredients with structured amounts/units, and step-by-step instructions, all stored in temporary database tables optimized for nutrition analysis tools.
        
        Args:
            input_data: Contains session_id (source virtual session location) and recipe_id
                       (specific recipe identifier to process and parse)
            
        Returns:
            Dict with setup status, ingredient parsing statistics, structured data counts,
            and comprehensive guidance for next steps in nutrition analysis workflow
        """
        try:
            # Extract parameters from input_data
            session_id = input_data.session_id
            recipe_id = input_data.recipe_id
            
            session_data = get_virtual_session_data(session_id)
            if session_data is None:
                return {"error": f"Session {session_id} not found"}
            
            # Check if recipe exists
            if 'recipes' not in session_data or recipe_id not in session_data['recipes']:
                available_recipes = list(session_data.get('recipes', {}).keys()) if session_data else []
                return {"error": f"Recipe {recipe_id} not found in session. Available recipes: {available_recipes}"}
            
            recipe_data = session_data['recipes'][recipe_id]
            recipe_title = recipe_data.get('title', 'Unknown Recipe')
            
            # Step 1: Setup temp persistent storage
            from .schema import create_temp_nutrition_session, update_session_access_time
            create_temp_nutrition_session(session_id)
            update_session_access_time(session_id)
            
            # Step 2: Transfer recipe data from virtual session to temp SQLite tables
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Transfer recipe metadata
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
                
                # Transfer ingredients from virtual session
                if 'ingredients' in session_data:
                    recipe_ingredients = [
                        ing_data for ing_data in session_data['ingredients'].values() 
                        if ing_data.get('recipe_id') == recipe_id
                    ]
                    
                    for i, ingredient_data in enumerate(recipe_ingredients):
                        if isinstance(ingredient_data, dict):
                            cursor.execute("""
                                INSERT OR REPLACE INTO temp_recipe_ingredients 
                                (session_id, recipe_id, ingredient_id, ingredient_list_org, ingredient_name, 
                                 amount, unit, ingredient_order, cnf_food_code)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                session_id, recipe_id, 
                                ingredient_data.get('ingredient_id', f"ing_{i}_{ingredient_data.get('ingredient_order', i)}"),
                                ingredient_data.get('ingredient_list_org', ''),
                                ingredient_data.get('ingredient_name', ''),
                                ingredient_data.get('amount'),
                                ingredient_data.get('unit'),
                                ingredient_data.get('ingredient_order', i),
                                None  # cnf_food_code will be set manually
                            ))
                
                conn.commit()
            
            # Step 3: ENHANCED - Parse ingredients using comprehensive parser
            from .math_tools import _parse_ingredient_comprehensive
            
            parsed_count = 0
            failed_count = 0
            parsing_details = []
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get all ingredients for parsing
                cursor.execute("""
                    SELECT ingredient_id, ingredient_list_org 
                    FROM temp_recipe_ingredients 
                    WHERE session_id = ? AND recipe_id = ?
                    ORDER BY ingredient_order
                """, (session_id, recipe_id))
                
                ingredients_to_parse = cursor.fetchall()
                
                for ingredient_id, ingredient_text in ingredients_to_parse:
                    if not ingredient_text or not ingredient_text.strip():
                        failed_count += 1
                        continue
                    
                    # Parse the ingredient text using comprehensive parser
                    parsed_data = _parse_ingredient_comprehensive(ingredient_text)
                    
                    # Update the temp table with parsed data
                    cursor.execute("""
                        UPDATE temp_recipe_ingredients 
                        SET ingredient_name = ?, amount = ?, unit = ?
                        WHERE session_id = ? AND ingredient_id = ?
                    """, (
                        parsed_data['clean_name'],
                        parsed_data.get('amount'),
                        parsed_data.get('unit'),
                        session_id,
                        ingredient_id
                    ))
                    
                    parsing_details.append({
                        'ingredient_id': ingredient_id,
                        'original_text': ingredient_text,
                        'parsed_amount': parsed_data.get('amount'),
                        'parsed_unit': parsed_data.get('unit'),
                        'clean_name': parsed_data['clean_name'],
                        'parsing_notes': parsed_data.get('parsing_notes', '')
                    })
                    
                    if parsed_data.get('amount') is not None:
                        parsed_count += 1
                    else:
                        failed_count += 1
                
                # Get final ingredient count
                cursor.execute("""
                    SELECT COUNT(*) FROM temp_recipe_ingredients 
                    WHERE session_id = ? AND recipe_id = ?
                """, (session_id, recipe_id))
                ingredient_count = cursor.fetchone()[0]
                
                conn.commit()
            
            return {
                "success": f"Recipe setup and parsing complete for: {recipe_title}",
                "recipe_id": recipe_id,
                "recipe_title": recipe_title,
                "session_id": session_id,
                "ingredient_count": ingredient_count,
                "parsing_summary": {
                    "total_ingredients": len(ingredients_to_parse),
                    "successfully_parsed": parsed_count,
                    "failed_to_parse": failed_count,
                    "parse_success_rate": f"{(parsed_count/len(ingredients_to_parse)*100):.1f}%" if ingredients_to_parse else "0%",
                    "ingredients_with_amounts": parsed_count,
                    "section_headers_detected": len([p for p in parsing_details if p['parsed_amount'] is None and p['original_text'].strip().endswith(':')])
                },
                "parsing_details": parsing_details[:5],  # Show first 5 for LLM review
                "workflow_status": {
                    "recipe_transfer": "✅ Complete",
                    "ingredient_parsing": f"✅ Complete - {parsed_count}/{len(ingredients_to_parse)} parsed successfully", 
                    "cnf_linking": "⏳ Ready for bulk_get_cnf_macronutrients with ingredient_mappings",
                    "nutrition_analysis": "⏳ Ready after CNF linking"
                },
                "next_steps": [
                    "Use search_and_get_cnf_macronutrients() to find CNF food codes for ingredients",
                    "Use bulk_get_cnf_macronutrients() with ingredient_mappings for efficient linking",
                    "OR use get_cnf_macronutrients_only() with ingredient_id for individual linking",
                    "Then use calculate_recipe_nutrition_summary() for complete nutrition analysis"
                ],
                "storage_location": "temp_recipe_ingredients table with parsed amount, unit, and ingredient_name columns"
            }
            
        except Exception as e:
            ###logger.error(f"Error in simple_recipe_setup: {e}")
            return {"error": f"Failed to setup recipe: {str(e)}"}



    # ========================================
    # 🚀 SIMPLE CALCULATION TOOLS (EER-STYLE)
    # ========================================

    @mcp.tool()
    def calculate_recipe_nutrition_summary(input_data: RecipeNutritionCalculationInput) -> Dict[str, Any]:
        """
        Analyze unit matching for recipe ingredients and populate temp_recipe_macros table.
        
        This tool performs unit matching analysis between recipe ingredients and CNF nutrition data,
        identifying which conversions are possible and which need manual LLM decisions. It populates
        the temp_recipe_macros table with detailed unit matching information for LLM review.
        
        NEW BEHAVIOR (Unit Matching Analysis):
        - Analyzes each ingredient's unit compatibility with available CNF serving sizes
        - Identifies exact matches, possible conversions, and manual decision needs
        - Populates temp_recipe_macros with unit matching status and recommendations
        - Returns analysis summary for LLM to make conversion decisions
        
        Use this tool to:
        - Set up unit matching analysis for recipe nutrition calculations
        - Identify which ingredients need manual conversion decisions
        - Prepare data for LLM-driven nutrition calculations
        - Get transparent view of unit conversion challenges
        
        The tool requires that ingredients have been previously linked to CNF data using
        get_cnf_macronutrients_only or bulk_get_cnf_macronutrients. After running this tool,
        review the temp_recipe_macros table and use simple_math_calculator for final calculations.
        
        Args:
            input_data: Contains session_id (data location) and recipe_id (target recipe identifier)
            
        Returns:
            Dict with unit matching analysis summary and temp_recipe_macros population status
        """
        try:
            # Get recipe details
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get recipe base servings
                cursor.execute("""
                    SELECT title, base_servings FROM temp_recipes 
                    WHERE session_id = ? AND recipe_id = ?
                """, (input_data.session_id, input_data.recipe_id))
                
                recipe_info = cursor.fetchone()
                if not recipe_info:
                    return {"error": f"Recipe {input_data.recipe_id} not found in session {input_data.session_id}"}
                
                recipe_title, base_servings = recipe_info
                base_servings = base_servings or 1
                
                # Get all ingredients (including those without CNF linkage)
                cursor.execute("""
                    SELECT ri.ingredient_id, ri.ingredient_name, ri.amount, ri.unit, ri.cnf_food_code
                    FROM temp_recipe_ingredients ri
                    WHERE ri.session_id = ? AND ri.recipe_id = ?
                    ORDER BY ri.ingredient_order
                """, (input_data.session_id, input_data.recipe_id))
                
                ingredients = cursor.fetchall()
                if not ingredients:
                    return {"error": f"No ingredients found for recipe {input_data.recipe_id}"}
                
                # Clear existing temp_recipe_macros for this recipe
                cursor.execute("""
                    DELETE FROM temp_recipe_macros 
                    WHERE session_id = ? AND recipe_id = ?
                """, (input_data.session_id, input_data.recipe_id))
                
                # Analyze unit matching for each ingredient
                ingredients_analyzed = 0
                manual_decisions_needed = 0
                exact_matches = 0
                conversion_available = 0
                no_cnf_data = 0
                
                for ingredient_id, ingredient_name, amount, unit, cnf_food_code in ingredients:
                    ingredients_analyzed += 1
                    
                    if cnf_food_code:
                        # Get nutrient data for unit matching analysis
                        cursor.execute("""
                            SELECT nutrient_name, nutrient_value, per_amount, unit as cnf_unit
                            FROM temp_cnf_nutrients
                            WHERE session_id = ? AND cnf_food_code = ?
                            AND nutrient_name IN ('Energy (kcal)', 'Protein', 'Total Fat', 'Carbohydrate')
                            ORDER BY nutrient_name, per_amount
                        """, (input_data.session_id, cnf_food_code))
                        
                        nutrients = cursor.fetchall()
                        
                        # Analyze unit matching
                        matching_analysis = _analyze_unit_matching(
                            ingredient_name, amount, unit, nutrients
                        )
                    else:
                        # No CNF data available
                        matching_analysis = {
                            "unit_match_status": 'no_cnf_data',
                            "available_cnf_servings": '[]',
                            "recommended_conversion": f"No CNF data linked for '{ingredient_name}' - needs CNF food code assignment",
                            "confidence_level": 'low'
                        }
                    
                    # Count status types
                    status = matching_analysis["unit_match_status"]
                    if status == 'exact_match':
                        exact_matches += 1
                    elif status == 'conversion_available':
                        conversion_available += 1
                    elif status == 'manual_decision_needed':
                        manual_decisions_needed += 1
                    elif status == 'no_cnf_data':
                        no_cnf_data += 1
                    
                    # Insert into temp_recipe_macros
                    cursor.execute("""
                        INSERT INTO temp_recipe_macros (
                            session_id, recipe_id, ingredient_id, cnf_food_code,
                            recipe_ingredient_name, recipe_amount, recipe_unit,
                            unit_match_status, available_cnf_servings, 
                            recommended_conversion, confidence_level
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        input_data.session_id, input_data.recipe_id, ingredient_id, cnf_food_code,
                        ingredient_name, amount, unit,
                        matching_analysis["unit_match_status"],
                        matching_analysis["available_cnf_servings"],
                        matching_analysis["recommended_conversion"],
                        matching_analysis["confidence_level"]
                    ))
                
                conn.commit()
                
                return {
                    "success": True,
                    "recipe_title": recipe_title,
                    "recipe_id": input_data.recipe_id,
                    "base_servings": base_servings,
                    "unit_matching_complete": True,
                    "ingredients_analyzed": ingredients_analyzed,
                    "analysis_summary": {
                        "exact_matches": exact_matches,
                        "conversion_available": conversion_available,
                        "manual_decisions_needed": manual_decisions_needed,
                        "no_cnf_data": no_cnf_data
                    },
                    "next_steps": [
                        "1. Review temp_recipe_macros table for unit matching status",
                        "2. Make conversion decisions for manual_decision_needed ingredients", 
                        "3. Use simple_math_calculator for nutrition calculations",
                        "4. Update temp_recipe_macros with final calculated values"
                    ],
                    "sql_query_example": f"SELECT * FROM temp_recipe_macros WHERE session_id = '{input_data.session_id}' AND recipe_id = '{input_data.recipe_id}' ORDER BY unit_match_status, recipe_ingredient_name"
                }
                
        except Exception as e:
            return {
                "error": f"Failed to analyze recipe unit matching: {str(e)}",
                "recipe_id": input_data.recipe_id
            }

    @mcp.tool()
    def query_recipe_macros_table(input_data: RecipeMacrosQueryInput) -> Dict[str, Any]:
        """
        Query temp_recipe_macros table with joined CNF nutrition data for recipe calculations.
        
        This tool retrieves recipe ingredients with their matched Canadian Nutrient File data,
        including nutrition values (calories, protein, fat, carbohydrates) for each available 
        serving size. The data enables direct nutrition calculations using bulk_math_calculator
        without requiring database storage of intermediate results.
        
        Returns recipe ingredient details, unit matching status, available CNF serving sizes,
        and complete CNF nutrition values per serving size for each ingredient. Unit matching
        status indicates: exact_match, conversion_available, manual_decision_needed, or no_cnf_data.
        
        Use this tool to:
        - Get ingredient data with CNF nutrition values for each serving size
        - Review unit matching status and available serving options
        - Select appropriate serving sizes for nutrition calculations
        - Obtain complete data for bulk_math_calculator operations
        
        Args:
            input_data: Contains session_id, optional recipe_id filter, optional unit_match_status filter
            
        Returns:
            Dict with ingredient data and CNF nutrition values per serving size
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Build query with optional filters - JOIN with CNF nutrients for complete data
                query = """
                    SELECT DISTINCT
                        rm.recipe_id,
                        rm.ingredient_id,
                        rm.cnf_food_code,
                        rm.recipe_ingredient_name,
                        rm.recipe_amount,
                        rm.recipe_unit,
                        rm.unit_match_status,
                        rm.available_cnf_servings,
                        rm.recommended_conversion,
                        rm.confidence_level,
                        rm.llm_conversion_decision,
                        rm.llm_conversion_factor,
                        rm.llm_reasoning,
                        rm.final_calories,
                        rm.final_protein,
                        rm.final_fat,
                        rm.final_carbs,
                        -- Add CNF nutrition data for each serving size
                        GROUP_CONCAT(
                            CASE WHEN cn.nutrient_name = 'Energy' 
                            THEN cn.nutrient_value || '|' || cn.per_amount || '|' || cn.unit 
                            END
                        ) as cnf_calories_servings,
                        GROUP_CONCAT(
                            CASE WHEN cn.nutrient_name = 'Protein' 
                            THEN cn.nutrient_value || '|' || cn.per_amount || '|' || cn.unit 
                            END
                        ) as cnf_protein_servings,
                        GROUP_CONCAT(
                            CASE WHEN cn.nutrient_name = 'Total Fat' 
                            THEN cn.nutrient_value || '|' || cn.per_amount || '|' || cn.unit 
                            END
                        ) as cnf_fat_servings,
                        GROUP_CONCAT(
                            CASE WHEN cn.nutrient_name = 'Carbohydrate' 
                            THEN cn.nutrient_value || '|' || cn.per_amount || '|' || cn.unit 
                            END
                        ) as cnf_carbs_servings
                    FROM temp_recipe_macros rm
                    LEFT JOIN temp_cnf_nutrients cn ON rm.session_id = cn.session_id 
                        AND rm.cnf_food_code = cn.cnf_food_code
                        AND cn.nutrient_name IN ('Energy', 'Protein', 'Total Fat', 'Carbohydrate')
                    WHERE rm.session_id = ?
                """
                
                params = [input_data.session_id]
                
                if input_data.recipe_id:
                    query += " AND rm.recipe_id = ?"
                    params.append(input_data.recipe_id)
                    
                if input_data.unit_match_status:
                    query += " AND rm.unit_match_status = ?"
                    params.append(input_data.unit_match_status)
                    
                query += """
                    GROUP BY rm.recipe_id, rm.ingredient_id, rm.cnf_food_code, rm.recipe_ingredient_name,
                             rm.recipe_amount, rm.recipe_unit, rm.unit_match_status, rm.available_cnf_servings,
                             rm.recommended_conversion, rm.confidence_level, rm.llm_conversion_decision,
                             rm.llm_conversion_factor, rm.llm_reasoning, rm.final_calories, rm.final_protein,
                             rm.final_fat, rm.final_carbs
                    ORDER BY rm.unit_match_status, rm.recipe_ingredient_name
                """
                
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                if not results:
                    return {
                        "message": f"No recipe macros data found for session {input_data.session_id}",
                        "session_id": input_data.session_id,
                        "recipe_id": input_data.recipe_id,
                        "suggestion": "Run calculate_recipe_nutrition_summary first to populate temp_recipe_macros table"
                    }
                
                # Process results into structured format
                ingredients_data = []
                status_summary = {}
                
                for row in results:
                    # Helper function to parse concatenated nutrition data
                    def parse_nutrition_servings(concat_str):
                        if not concat_str:
                            return []
                        servings = []
                        for item in concat_str.split(','):
                            if item and '|' in item:
                                parts = item.split('|')
                                if len(parts) == 3:
                                    servings.append({
                                        "nutrient_value": float(parts[0]) if parts[0] else 0.0,
                                        "per_amount": float(parts[1]) if parts[1] else 0.0,
                                        "unit": parts[2]
                                    })
                        return servings
                    
                    ingredient_data = {
                        "recipe_id": row[0],
                        "ingredient_id": row[1],
                        "cnf_food_code": row[2],
                        "recipe_ingredient_name": row[3],
                        "recipe_amount": row[4],
                        "recipe_unit": row[5],
                        "unit_match_status": row[6],
                        "available_cnf_servings": json.loads(row[7]) if row[7] else [],
                        "recommended_conversion": row[8],
                        "confidence_level": row[9],
                        "llm_conversion_decision": row[10],
                        "llm_conversion_factor": row[11],
                        "llm_reasoning": row[12],
                        "final_calories": row[13],
                        "final_protein": row[14],
                        "final_fat": row[15],
                        "final_carbs": row[16],
                        # NEW: CNF nutrition data for LLM calculations
                        "cnf_calories_per_serving": parse_nutrition_servings(row[17]),
                        "cnf_protein_per_serving": parse_nutrition_servings(row[18]),
                        "cnf_fat_per_serving": parse_nutrition_servings(row[19]),
                        "cnf_carbs_per_serving": parse_nutrition_servings(row[20])
                    }
                    ingredients_data.append(ingredient_data)
                    
                    # Count status types
                    status = row[6]
                    status_summary[status] = status_summary.get(status, 0) + 1
                
                # Identify ingredients needing LLM attention
                needs_decision = [ing for ing in ingredients_data if ing["unit_match_status"] == "manual_decision_needed"]
                has_decisions = [ing for ing in ingredients_data if ing["llm_conversion_decision"]]
                
                return {
                    "success": True,
                    "session_id": input_data.session_id,
                    "query_filters": {
                        "recipe_id": input_data.recipe_id,
                        "unit_match_status": input_data.unit_match_status
                    },
                    "total_ingredients": len(ingredients_data),
                    "status_summary": status_summary,
                    "needs_llm_decisions": len(needs_decision),
                    "has_llm_decisions": len(has_decisions),
                    "ingredients_data": ingredients_data,
                    "next_steps": [
                        f"Make conversion decisions for {len(needs_decision)} ingredients with manual_decision_needed status" if needs_decision else "All ingredients have unit matching completed",
                        "Use update_recipe_macros_decisions tool to record conversion decisions",
                        "Use simple_math_calculator for final nutrition calculations"
                    ],
                    "ingredients_needing_decisions": [
                        {
                            "ingredient_id": ing["ingredient_id"],
                            "name": ing["recipe_ingredient_name"],
                            "amount_unit": f"{ing['recipe_amount']} {ing['recipe_unit']}" if ing['recipe_amount'] else "unclear amount",
                            "available_servings": ing["available_cnf_servings"],
                            "recommendation": ing["recommended_conversion"]
                        }
                        for ing in needs_decision
                    ]
                }
                
        except Exception as e:
            return {
                "error": f"Failed to query recipe macros: {str(e)}",
                "session_id": input_data.session_id,
                "suggestion": "Check that session exists and calculate_recipe_nutrition_summary has been run"
            }

    @mcp.tool()
    def update_recipe_macros_decisions(input_data: RecipeMacrosUpdateInput) -> Dict[str, Any]:
        """
        Update temp_recipe_macros table with LLM conversion decisions and reasoning.
        
        This tool allows the LLM to record intelligent conversion decisions for ingredients
        that need manual unit conversions (e.g., "4 salmon fillets" -> "565g"). After
        reviewing the temp_recipe_macros table, use this tool to update specific ingredients
        with conversion factors and reasoning.
        
        The tool updates the LLM decision fields in temp_recipe_macros:
        - llm_conversion_decision: Human-readable conversion (e.g., "4 fillets = 565g")
        - llm_conversion_factor: Calculated factor for nutrition math (e.g., 5.65 for 565g/100g)
        - llm_reasoning: LLM's reasoning for the conversion estimate
        
        Use this tool to:
        - Record conversion decisions for manual_decision_needed ingredients
        - Document reasoning for conversion estimates
        - Prepare data for final nutrition calculations with simple_math_calculator
        - Build transparent audit trail of conversion decisions
        
        Args:
            input_data: Contains session_id, ingredient_id, conversion decision, factor, and reasoning
            
        Returns:
            Dict with update status and next steps for nutrition calculations
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # First, verify the ingredient exists and needs a decision
                cursor.execute("""
                    SELECT recipe_ingredient_name, recipe_amount, recipe_unit, unit_match_status, cnf_food_code
                    FROM temp_recipe_macros 
                    WHERE session_id = ? AND ingredient_id = ?
                """, (input_data.session_id, input_data.ingredient_id))
                
                result = cursor.fetchone()
                if not result:
                    return {
                        "error": f"Ingredient {input_data.ingredient_id} not found in session {input_data.session_id}",
                        "session_id": input_data.session_id,
                        "ingredient_id": input_data.ingredient_id,
                        "suggestion": "Use query_recipe_macros_table to see available ingredient IDs"
                    }
                
                ingredient_name, recipe_amount, recipe_unit, unit_status, cnf_food_code = result
                
                # Update the LLM decision fields
                cursor.execute("""
                    UPDATE temp_recipe_macros 
                    SET 
                        llm_conversion_decision = ?,
                        llm_conversion_factor = ?,
                        llm_reasoning = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = ? AND ingredient_id = ?
                """, (
                    input_data.llm_conversion_decision,
                    input_data.llm_conversion_factor,
                    input_data.llm_reasoning,
                    input_data.session_id,
                    input_data.ingredient_id
                ))
                
                if cursor.rowcount == 0:
                    return {
                        "error": f"Failed to update ingredient {input_data.ingredient_id}",
                        "session_id": input_data.session_id,
                        "ingredient_id": input_data.ingredient_id
                    }
                
                conn.commit()
                
                # Check if this was the last ingredient needing decisions
                cursor.execute("""
                    SELECT COUNT(*) FROM temp_recipe_macros 
                    WHERE session_id = ? AND unit_match_status = 'manual_decision_needed' 
                    AND llm_conversion_decision IS NULL
                """, (input_data.session_id,))
                
                remaining_decisions = cursor.fetchone()[0]
                
                return {
                    "success": True,
                    "message": f"Updated conversion decision for ingredient: {ingredient_name}",
                    "session_id": input_data.session_id,
                    "ingredient_id": input_data.ingredient_id,
                    "updated_fields": {
                        "ingredient_name": ingredient_name,
                        "original_amount_unit": f"{recipe_amount} {recipe_unit}" if recipe_amount else "unclear amount",
                        "conversion_decision": input_data.llm_conversion_decision,
                        "conversion_factor": input_data.llm_conversion_factor,
                        "reasoning": input_data.llm_reasoning,
                        "cnf_food_code": cnf_food_code,
                        "unit_match_status": unit_status
                    },
                    "workflow_status": {
                        "remaining_manual_decisions": remaining_decisions,
                        "ready_for_calculations": remaining_decisions == 0
                    },
                    "next_steps": [
                        f"Update {remaining_decisions} more ingredients needing manual decisions" if remaining_decisions > 0 else "All conversion decisions completed",
                        "Use simple_math_calculator to calculate final nutrition values" if remaining_decisions == 0 else "Continue making conversion decisions",
                        "Example calculation: simple_math_calculator(expression='cnf_calories * conversion_factor', variables={'cnf_calories': 206, 'conversion_factor': " + str(input_data.llm_conversion_factor) + "})" if remaining_decisions == 0 else ""
                    ],
                    "calculation_example": {
                        "expression": "cnf_calories * conversion_factor",
                        "variables": {
                            "cnf_calories": "VALUE_FROM_CNF_DATA",  
                            "conversion_factor": input_data.llm_conversion_factor
                        },
                        "description": f"Use this pattern to calculate final nutrition for {ingredient_name}"
                    }
                }
                
        except Exception as e:
            return {
                "error": f"Failed to update conversion decision: {str(e)}",
                "session_id": input_data.session_id,
                "ingredient_id": input_data.ingredient_id,
                "suggestion": "Check that ingredient_id exists and conversion_factor is positive"
            }


def _normalize_unit(unit: str) -> str:
    """Normalize unit variations for better matching."""
    if not unit:
        return ""
    
    unit_lower = unit.lower().strip()
    
    # Volume units
    if unit_lower in ['ml', 'millilitre', 'milliliter']:
        return 'ml'
    elif unit_lower in ['tsp', 'teaspoon']:
        return 'tsp'
    elif unit_lower in ['tbsp', 'tablespoon']:
        return 'tbsp'
    elif unit_lower in ['cup', 'cups']:
        return 'cup'
    # Weight units
    elif unit_lower in ['g', 'gram', 'grams']:
        return 'g'
    elif unit_lower in ['kg', 'kilogram', 'kilograms']:
        return 'kg'
    elif unit_lower in ['lb', 'pound', 'pounds']:
        return 'lb'
    elif unit_lower in ['oz', 'ounce', 'ounces']:
        return 'oz'
    
    return unit_lower

def _analyze_unit_matching(ingredient_name: str, amount: float, unit: str, cnf_nutrients: list) -> Dict[str, Any]:
    """
    Analyze unit matching between recipe ingredient and CNF data without doing calculations.
    
    Returns analysis of what conversions are possible and recommendations for LLM decisions.
    """
    try:
        import json
        
        # Normalize recipe unit
        normalized_unit = _normalize_unit(unit) if unit else 'unknown'
        
        # Get available CNF servings
        available_servings = []
        exact_matches = []
        conversion_matches = []
        
        for nutrient_name, nutrient_value, per_amount, cnf_unit in cnf_nutrients:
            if nutrient_name == 'Energy (kcal)':  # Use energy as representative nutrient
                serving_info = {
                    "amount": per_amount,
                    "unit": cnf_unit,
                    "calories_per_serving": nutrient_value
                }
                available_servings.append(serving_info)
                
                cnf_normalized = _normalize_unit(cnf_unit)
                
                # Check for exact matches
                if normalized_unit == cnf_normalized:
                    exact_matches.append(serving_info)
                
                # Check for conversion possibilities
                elif _can_convert_units(normalized_unit, cnf_normalized):
                    conversion_matches.append(serving_info)
        
        # Determine unit match status
        if not cnf_nutrients:
            unit_match_status = 'no_cnf_data'
            confidence_level = 'low'
            recommended_conversion = 'No CNF data available for this ingredient'
        elif exact_matches:
            unit_match_status = 'exact_match'
            confidence_level = 'high'
            best_match = exact_matches[0]
            recommended_conversion = f"Exact match: {amount} {unit} matches CNF serving of {best_match['amount']} {best_match['unit']}"
        elif conversion_matches:
            unit_match_status = 'conversion_available'
            confidence_level = 'medium'
            best_match = conversion_matches[0]
            recommended_conversion = f"Unit conversion: {amount} {unit} can be converted to match CNF serving of {best_match['amount']} {best_match['unit']}"
        elif unit in [None, 'unknown', ''] or amount is None or amount <= 0:
            unit_match_status = 'manual_decision_needed'
            confidence_level = 'low'
            recommended_conversion = f"Manual decision needed: '{ingredient_name}' has unclear amount/unit. Consider estimating reasonable serving size."
        else:
            unit_match_status = 'manual_decision_needed'
            confidence_level = 'low'
            recommended_conversion = f"Manual decision needed: '{amount} {unit}' needs conversion estimate to match available CNF servings"
        
        return {
            "unit_match_status": unit_match_status,
            "available_cnf_servings": json.dumps(available_servings),
            "recommended_conversion": recommended_conversion,
            "confidence_level": confidence_level,
            "exact_matches_found": len(exact_matches),
            "conversion_matches_found": len(conversion_matches)
        }
        
    except Exception as e:
        return {
            "unit_match_status": 'no_match',
            "available_cnf_servings": '[]',
            "recommended_conversion": f"Error analyzing unit matching: {str(e)}",
            "confidence_level": 'low',
            "exact_matches_found": 0,
            "conversion_matches_found": 0
        }

def _can_convert_units(recipe_unit: str, cnf_unit: str) -> bool:
    """Check if unit conversion is possible between recipe and CNF units."""
    # Volume conversions
    volume_units = {'tsp', 'tbsp', 'cup', 'ml', 'l', 'fl oz'}
    weight_units = {'g', 'kg', 'lb', 'oz'}
    
    recipe_is_volume = recipe_unit in volume_units
    recipe_is_weight = recipe_unit in weight_units
    cnf_is_volume = cnf_unit in volume_units
    cnf_is_weight = cnf_unit in weight_units
    
    # Same category conversions
    if recipe_is_volume and cnf_is_volume:
        return True
    if recipe_is_weight and cnf_is_weight:
        return True
    
    # Cross-category approximations (liquids only)
    if recipe_is_volume and cnf_is_weight and cnf_unit == 'g':
        return True
    if recipe_is_weight and cnf_is_volume and cnf_unit == 'ml':
        return True
    
    return False

    
# Helper functions for direct SQLite CNF population

def populate_cnf_food_in_sqlite(session_id: str, food_code: str, food_description: str, 
                               ingredient_name: str = None, refuse_info: str = None) -> bool:
    """
    Helper function to populate CNF food data directly in SQLite.
    
    Args:
        session_id: Session identifier
        food_code: CNF food code
        food_description: Food description
        ingredient_name: Optional ingredient name this CNF food is linked to
        refuse_info: Optional refuse information
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from .schema import create_temp_nutrition_session, update_session_access_time
        
        # Ensure session exists
        create_temp_nutrition_session(session_id)
        update_session_access_time(session_id)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO temp_cnf_foods 
                (session_id, cnf_food_code, food_description, ingredient_name, refuse_flag, refuse_amount)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                food_code,
                food_description,
                ingredient_name,
                bool(refuse_info),
                None
            ))
            conn.commit()
            return True
    except Exception:
        return False

def populate_cnf_nutrient_in_sqlite(session_id: str, food_code: str, nutrient_name: str, 
                                   nutrient_value: float, per_amount: float, unit: str,
                                   nutrient_symbol: str = '') -> bool:
    """
    Helper function to populate individual CNF nutrient data directly in SQLite.
    
    Args:
        session_id: Session identifier
        food_code: CNF food code
        nutrient_name: Name of the nutrient
        nutrient_value: Nutrient value
        per_amount: Amount this value represents
        unit: Unit of measurement
        nutrient_symbol: Optional nutrient symbol
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO temp_cnf_nutrients 
                (session_id, cnf_food_code, nutrient_name, nutrient_value, 
                 per_amount, unit, nutrient_symbol)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, food_code, nutrient_name, nutrient_value,
                per_amount, unit, nutrient_symbol
            ))
            conn.commit()
            return True
    except Exception:
        return False

def clear_cnf_data_from_sqlite(session_id: str, food_code: str = None) -> Dict[str, Any]:
    """
    Helper function to clear CNF data from SQLite tables.
    
    Args:
        session_id: Session identifier
        food_code: Optional specific food code to clear (clears all if None)
        
    Returns:
        Dict with cleanup results
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if food_code:
                # Clear specific food
                cursor.execute("DELETE FROM temp_cnf_nutrients WHERE session_id = ? AND cnf_food_code = ?", 
                              (session_id, food_code))
                cursor.execute("DELETE FROM temp_cnf_foods WHERE session_id = ? AND cnf_food_code = ?", 
                              (session_id, food_code))
            else:
                # Clear all CNF data for session
                cursor.execute("DELETE FROM temp_cnf_nutrients WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM temp_cnf_foods WHERE session_id = ?", (session_id,))
            
            deleted_nutrients = cursor.rowcount
            conn.commit()
            
            return {
                "success": f"Cleared CNF data from SQLite for session {session_id}",
                "food_code": food_code or "all",
                "records_deleted": deleted_nutrients
            }
    except Exception as e:
        return {"error": f"Failed to clear CNF data: {str(e)}"}

def get_cnf_tools_status() -> Dict[str, Any]:
    """Get status of CNF tools availability."""
    return {
        "cnf_tools_available": CNF_TOOLS_AVAILABLE,
        "data_source": "Health Canada CNF REST API (food-nutrition.canada.ca)",
        "tools_count": 8 if CNF_TOOLS_AVAILABLE else 0,
        "tools": [
            "search_and_get_cnf_macronutrients",
            "get_cnf_macronutrients_only",
            "bulk_get_cnf_macronutrients",
            "get_cnf_nutrient_profile",
            "simple_recipe_setup",
            "calculate_recipe_nutrition_summary",
            "query_recipe_macros_table",
            "update_recipe_macros_decisions",
        ] if CNF_TOOLS_AVAILABLE else [],
    }