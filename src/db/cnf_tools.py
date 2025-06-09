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

try:
    from src.models.cnf_models import (
        CNFSearchInput, CNFProfileInput, CNFMacronutrientsInput, CNFBulkMacronutrientsInput, CNFSearchAndGetInput,
        SQLQueryInput, CNFFoodResult, CNFNutrientProfile, IngredientCNFMatch,
        RecipeNutritionSummary, CNFSessionSummary, IngredientNutritionData,
        AnalyzeRecipeNutritionInput, RecipeNutritionCalculationInput,
        IngredientNutritionBreakdownInput, DailyNutritionComparisonInput
    )
    from src.api.cnf import NutrientFileScraper, CORE_MACRONUTRIENTS
    from src.db.schema import get_virtual_session_data, store_recipe_in_virtual_session
    from src.db.sql_engine import VirtualSQLEngine, get_available_tables_info
    from src.db.connection import get_db_connection
    from src.config import CNF_RATE_LIMIT, CNF_MAX_CONCURRENT, CNF_CACHE_TTL, BULK_OPERATION_TIMEOUT, PROGRESS_REPORT_INTERVAL
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
        from api.cnf import NutrientFileScraper, CORE_MACRONUTRIENTS
        from db.schema import get_virtual_session_data, store_recipe_in_virtual_session
        from db.sql_engine import VirtualSQLEngine, get_available_tables_info
        from db.connection import get_db_connection
        from config import CNF_RATE_LIMIT, CNF_MAX_CONCURRENT, CNF_CACHE_TTL, BULK_OPERATION_TIMEOUT, PROGRESS_REPORT_INTERVAL
        CNF_TOOLS_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: CNF tools not available due to import error: {e}", file=sys.stderr)

# Configure logging
logging.basicConfig(level=logging.INFO)
#logger = logging.getLogger(__name__)

# Global CNF scraper instance and caching
_cnf_scraper = None
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

def get_cnf_scraper() -> NutrientFileScraper:
    """Get or create the global CNF scraper instance with optimized rate limiting."""
    global _cnf_scraper
    if _cnf_scraper is None:
        _cnf_scraper = NutrientFileScraper(rate_limit=CNF_RATE_LIMIT)
    return _cnf_scraper

def process_single_food_code(
    food_code: str, 
    session_id: str, 
    preferred_units: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[str, str], None]] = None
) -> Dict[str, Any]:
    """
    Process a single food code with caching and error handling.
    
    Args:
        food_code: CNF food code to process
        session_id: Session identifier
        preferred_units: Preferred serving units
        progress_callback: Optional callback for progress updates
        
    Returns:
        Dict with processing result including success/failure status
    """
    try:
        if progress_callback:
            progress_callback(food_code, "starting")
            
        # Check cache first
        cache_key = f"{food_code}_{preferred_units or 'default'}"
        cached_result = _cnf_cache_instance.get(cache_key)
        
        if cached_result:
            #logger.debug(f"Using cached data for food code {food_code}")
            if progress_callback:
                progress_callback(food_code, "cached")
            return {
                "status": "success",
                "food_code": food_code,
                "cached": True,
                "data": cached_result
            }
        
        scraper = get_cnf_scraper()
        
        if progress_callback:
            progress_callback(food_code, "fetching_serving_info")
            
        # Step 1: Get serving info
        serving_options, refuse_info = scraper.get_serving_info(food_code)
        
        if not serving_options:
            return {
                "status": "failed",
                "food_code": food_code,
                "error": "Could not retrieve serving information",
                "suggestion": "Verify food code is valid"
            }
        
        if progress_callback:
            progress_callback(food_code, "fetching_nutrients")
            
        # Step 2: Get nutrient profile
        nutrient_profile = scraper.get_nutrient_profile(
            food_code=food_code,
            serving_options=serving_options,
            nutrient_filter="macronutrients",
            preferred_units=preferred_units
        )
        
        if not nutrient_profile or nutrient_profile.get('error'):
            return {
                "status": "failed",
                "food_code": food_code,
                "error": "Could not retrieve nutrient profile",
                "suggestion": "Food code may be invalid or CNF website temporarily unavailable"
            }
        
        # Cache the successful result
        result_data = {
            "serving_options": serving_options,
            "refuse_info": refuse_info,
            "nutrient_profile": nutrient_profile
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
        #logger.error(f"Error processing food code {food_code}: {e}")
        if progress_callback:
            progress_callback(food_code, f"error: {str(e)}")
        return {
            "status": "failed",
            "food_code": food_code,
            "error": str(e),
            "suggestion": "Check network connection and CNF website availability"
        }

def register_cnf_tools(mcp: FastMCP) -> None:
    """Register all CNF tools with the FastMCP server."""
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
            scraper = get_cnf_scraper()
            
            # Step 1: Search for foods
            search_results = scraper.search_food(input_data.food_name)
            
            if search_results is None:
                return {"error": f"Failed to search for food: {input_data.food_name}"}
            
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
            
            # Limit results for LLM efficiency
            if input_data.max_results and len(search_results) > input_data.max_results:
                search_results = search_results[:input_data.max_results]
            
            # Step 2: If single result, auto-fetch macronutrients
            if len(search_results) == 1:
                selected_food = search_results[0]
                food_code = selected_food['food_code']
                
                # Get serving information
                serving_options, refuse_info = scraper.get_serving_info(food_code)
                
                if serving_options is None:
                    return {
                        "error": f"Found food '{selected_food['food_name']}' but failed to get serving info",
                        "food_code": food_code,
                        "search_results": search_results
                    }
                
                # Get macronutrient profile (filtered)
                nutrient_profile = scraper.get_nutrient_profile(
                    food_code, 
                    serving_options,
                    nutrient_filter="macronutrients",
                    preferred_units=input_data.preferred_units
                )
                
                if nutrient_profile is None:
                    return {
                        "error": f"Found food '{selected_food['food_name']}' but failed to get macronutrient profile",
                        "food_code": food_code,
                        "search_results": search_results
                    }
                
                # Store in SQL tables (same logic as get_cnf_macronutrients_only)
                from .schema import create_temp_nutrition_session, update_session_access_time
                
                create_temp_nutrition_session(input_data.session_id)
                update_session_access_time(input_data.session_id)
                
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get food description from first nutrient category
                    food_description = selected_food['food_name']
                    for category_data in nutrient_profile.values():
                        if category_data and len(category_data) > 0:
                            food_description = selected_food['food_name']
                            break
                    
                    # Insert/update CNF food entry
                    cursor.execute("""
                        INSERT OR REPLACE INTO temp_cnf_foods 
                        (session_id, food_code, food_description, food_group, food_source, refuse_flag, refuse_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        input_data.session_id,
                        food_code,
                        food_description,
                        "Unknown",  # Could be enhanced to extract from profile
                        "CNF Database",
                        False,
                        0.0
                    ))
                    
                    # Store macronutrients in temp_cnf_nutrients table
                    nutrients_stored = 0
                    
                    for category_name, category_data in nutrient_profile.items():
                        if not category_data:
                            continue
                            
                        for nutrient_entry in category_data:
                            if not nutrient_entry:
                                continue
                                
                            nutrient_name = nutrient_entry.get('Nutrient name', '')
                            
                            # Only store core macronutrients for efficiency
                            if nutrient_name in CORE_MACRONUTRIENTS:
                                cursor.execute("""
                                    INSERT OR REPLACE INTO temp_cnf_nutrients
                                    (session_id, food_code, nutrient_name, nutrient_symbol, nutrient_unit, 
                                     nutrient_value, standard_error, number_observations, serving_values)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    input_data.session_id,
                                    food_code,
                                    nutrient_name,
                                    nutrient_entry.get('Nutrient symbol', ''),
                                    nutrient_entry.get('Unit', ''),
                                    nutrient_entry.get('100 g edible portion', ''),
                                    nutrient_entry.get('Standard Error', ''),
                                    nutrient_entry.get('Number of Observations', ''),
                                    json.dumps({k: v for k, v in nutrient_entry.items() 
                                               if k not in ['Nutrient name', 'Nutrient symbol', 'Unit', 
                                                          '100 g edible portion', 'Standard Error', 'Number of Observations']})
                                ))
                                nutrients_stored += 1
                    
                    conn.commit()
                
                return {
                    "success": True,
                    "action": "auto_fetched_macronutrients",
                    "message": f"✅ Found single match and automatically fetched macronutrients",
                    "food_selected": {
                        "food_code": food_code,
                        "food_name": selected_food['food_name']
                    },
                    "macronutrients_stored": nutrients_stored,
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
            
            # Step 3: Multiple results - let LLM choose
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
            
            # Update session access time
            update_session_access_time(input_data.session_id)
            
            scraper = get_cnf_scraper()
            
            # Step 1: Get serving info for the food code
            serving_options, refuse_info = scraper.get_serving_info(input_data.food_code)
            
            if not serving_options:
                return {
                    "error": f"Could not retrieve serving information for food code '{input_data.food_code}'",
                    "food_code": input_data.food_code,
                    "suggestion": "Verify the food code is valid - try searching with search_and_get_cnf_macronutrients first"
                }
            
            # Step 2: Get nutrient profile with macronutrients filter
            nutrient_profile = scraper.get_nutrient_profile(
                food_code=input_data.food_code,
                serving_options=serving_options,
                nutrient_filter="macronutrients",  # Apply 91% data reduction filter
                preferred_units=input_data.preferred_units
            )
            
            if not nutrient_profile or nutrient_profile.get('error'):
                return {
                    "error": f"Could not retrieve nutrient profile for food code '{input_data.food_code}'",
                    "food_code": input_data.food_code,
                    "serving_options_found": len(serving_options) if serving_options else 0,
                    "suggestion": "Food code may be invalid or CNF website may be temporarily unavailable"
                }
            
            # Step 3: Store macronutrients in SQLite temp tables WITH CORRECT SCHEMA
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Extract food description from profile data
                food_description = f"CNF Food {input_data.food_code}"
                if isinstance(nutrient_profile, dict):
                    for category_name, nutrients in nutrient_profile.items():
                        if isinstance(nutrients, list) and nutrients:
                            first_nutrient = nutrients[0]
                            if isinstance(first_nutrient, dict):
                                for key, value in first_nutrient.items():
                                    if 'food' in key.lower() and isinstance(value, str) and len(value) > 10:
                                        food_description = value[:100]
                                        break
                                break
                
                # Insert/update CNF food entry with CORRECT column names
                cursor.execute("""
                    INSERT OR REPLACE INTO temp_cnf_foods 
                    (session_id, cnf_food_code, food_description, ingredient_name, refuse_flag, refuse_amount)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    input_data.session_id,
                    input_data.food_code,
                    food_description,
                    None,  # ingredient_name - to be populated when linking ingredients
                    bool(refuse_info),
                    None  # refuse_amount
                ))
                
                # Clear existing nutrients for this food code (in case of re-fetch)
                cursor.execute("""
                    DELETE FROM temp_cnf_nutrients 
                    WHERE session_id = ? AND cnf_food_code = ?
                """, (input_data.session_id, input_data.food_code))
                
                # Store macronutrients with CORRECT schema (matching get_cnf_nutrient_profile logic)
                nutrients_stored = 0
                
                if isinstance(nutrient_profile, dict):
                    for category_name, nutrients in nutrient_profile.items():
                        if isinstance(nutrients, list):
                            for nutrient_idx, nutrient in enumerate(nutrients):
                                if not isinstance(nutrient, dict):
                                    continue
                                
                                nutrient_name = nutrient.get('Nutrient name', '').strip()
                                if not nutrient_name:
                                    continue
                                
                                # Store 100g baseline value
                                baseline_value = None
                                for key in ['Value per 100 g of edible portion', 'Per 100 g', '100g', 'Value/100g']:
                                    if key in nutrient:
                                        baseline_value = nutrient[key]
                                        break
                                
                                if baseline_value and str(baseline_value).strip():
                                    try:
                                        # Clean the value
                                        clean_value = str(baseline_value).strip()
                                        if clean_value.lower() in ['trace', 'tr', '']:
                                            baseline_float = 0.0
                                        elif clean_value.startswith('<'):
                                            baseline_float = 0.0
                                        else:
                                            import re
                                            numeric_value = re.sub(r'[^\d\.\-]', '', clean_value)
                                            baseline_float = float(numeric_value) if numeric_value else 0.0
                                        
                                        cursor.execute("""
                                            INSERT OR REPLACE INTO temp_cnf_nutrients 
                                            (session_id, cnf_food_code, nutrient_name, nutrient_value, 
                                             per_amount, unit, nutrient_symbol)
                                            VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """, (
                                            input_data.session_id,
                                            input_data.food_code,
                                            nutrient_name,
                                            baseline_float,
                                            100.0,
                                            'g',
                                            nutrient.get('Unit see footnote1', '') or ''
                                        ))
                                        nutrients_stored += 1
                                    except (ValueError, TypeError):
                                        continue
                                
                                # Store serving size values - COPIED FROM get_cnf_nutrient_profile
                                for key, value in nutrient.items():
                                    # Look for serving size columns (e.g., "5ml / 5 g", "15ml / 14 g") 
                                    # More robust serving size detection
                                    if ('/' in key and any(unit in key.lower() for unit in ['ml', 'g', 'tsp', 'tbsp', 'cup', 'oz'])) or \
                                       (any(unit in key.lower() for unit in ['ml', 'tsp', 'tbsp', 'cup', 'oz']) and any(char.isdigit() for char in key)):
                                        
                                        if value and str(value).strip() and str(value).strip() != '':
                                            try:
                                                # Clean and parse serving value
                                                clean_serving_value = str(value).strip()
                                                if clean_serving_value.lower() in ['trace', 'tr']:
                                                    serving_value = 0.0
                                                elif clean_serving_value.startswith('<'):
                                                    serving_value = 0.0
                                                else:
                                                    import re
                                                    numeric_serving = re.sub(r'[^\d\.\-]', '', clean_serving_value)
                                                    serving_value = float(numeric_serving) if numeric_serving else 0.0
                                                
                                                # Extract serving amount and unit from key
                                                import re
                                                # Try to match patterns like "5ml", "15ml", "1 tsp", "1/2 cup", etc.
                                                match = re.search(r'(\d+(?:\.\d+)?|\d+/\d+)\s*([a-zA-Z]+)', key)
                                                if match:
                                                    serving_amount_str = match.group(1)
                                                    serving_unit = match.group(2).lower()
                                                    
                                                    # Handle fractions in serving amounts
                                                    if '/' in serving_amount_str:
                                                        parts = serving_amount_str.split('/')
                                                        serving_amount = float(parts[0]) / float(parts[1])
                                                    else:
                                                        serving_amount = float(serving_amount_str)
                                                    
                                                    cursor.execute("""
                                                        INSERT OR REPLACE INTO temp_cnf_nutrients 
                                                        (session_id, cnf_food_code, nutrient_name, nutrient_value, 
                                                         per_amount, unit, nutrient_symbol)
                                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                                    """, (
                                                        input_data.session_id,
                                                        input_data.food_code,
                                                        nutrient_name,
                                                        serving_value,
                                                        serving_amount,
                                                        serving_unit or '',
                                                        nutrient.get('Unit see footnote1', '') or ''
                                                    ))
                                                    nutrients_stored += 1
                                            except (ValueError, TypeError) as e:
                                                # Skip serving values that can't be parsed
                                                continue
                
                # Step 4: CRITICAL FIX - Link ingredient if provided
                linking_status = "no_linking_requested"
                if input_data.ingredient_id and input_data.recipe_id:
                    # Update the cnf_food_code in temp_recipe_ingredients
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
            
            # Step 5: Return success with linking confirmation
            return {
                "success": True,
                "action": "macronutrients_fetched_and_linked",
                "message": f"✅ Successfully fetched {nutrients_stored} core macronutrients for food code '{input_data.food_code}'",
                "food_code": input_data.food_code,
                "food_description": food_description,
                "session_id": input_data.session_id,
                "macronutrients_stored": nutrients_stored,
                "serving_options_available": len(serving_options),
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
            from .schema import update_session_access_time
            
            # Update session access time
            update_session_access_time(input_data.session_id)
            
            # Initialize tracking variables
            total_foods = len(input_data.food_codes)
            successful_foods = []
            failed_foods = []
            total_nutrients_stored = 0
            
            # Setup progress tracking
            progress_data = {"completed": 0, "total": total_foods, "current": None}
            start_time = time.time()
            
            def progress_callback(food_code: str, status: str):
                """Progress callback for concurrent processing."""
                if status == "completed":
                    progress_data["completed"] += 1
                progress_data["current"] = f"{food_code}: {status}"
                elapsed = time.time() - start_time
                if elapsed > PROGRESS_REPORT_INTERVAL:
                    raise
                    #logger.info(f"Bulk CNF Progress: {progress_data['completed']}/{progress_data['total']} completed. Current: {progress_data['current']}")
                    
            # Process food codes concurrently
            #logger.info(f"Starting concurrent processing of {total_foods} food codes with max {CNF_MAX_CONCURRENT} workers")
            
            fetch_results = []
            with ThreadPoolExecutor(max_workers=min(CNF_MAX_CONCURRENT, total_foods)) as executor:
                # Submit all tasks
                future_to_food_code = {
                    executor.submit(
                        process_single_food_code, 
                        food_code, 
                        input_data.session_id, 
                        input_data.preferred_units,
                        progress_callback
                    ): food_code 
                    for food_code in input_data.food_codes
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_food_code, timeout=BULK_OPERATION_TIMEOUT):
                    try:
                        result = future.result()
                        fetch_results.append(result)
                    except Exception as e:
                        food_code = future_to_food_code[future]
                        #logger.error(f"Failed to process food code {food_code}: {e}")
                        fetch_results.append({
                            "status": "failed",
                            "food_code": food_code,
                            "error": str(e),
                            "suggestion": "Check network connectivity and try again"
                        })
                        if not input_data.continue_on_error:
                            break
            
            #logger.info(f"Concurrent fetching completed in {time.time() - start_time:.2f} seconds")
            
            # Now process results and store in database
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                for result in fetch_results:
                    if result["status"] == "failed":
                        failed_foods.append({
                            "food_code": result["food_code"],
                            "error": result["error"],
                            "suggestion": result["suggestion"]
                        })
                        if not input_data.continue_on_error:
                            break
                        continue
                    
                    try:
                        food_code = result["food_code"]
                        result_data = result["data"]
                        serving_options = result_data["serving_options"]
                        refuse_info = result_data["refuse_info"]
                        nutrient_profile = result_data["nutrient_profile"]
                        
                        # Step 3: Store this food's data in SQLite
                        food_description = f"CNF Food {food_code}"
                        
                        # Extract food description from the correct data structure
                        description_data = nutrient_profile
                        if isinstance(nutrient_profile, dict) and "nutrient_data" in nutrient_profile:
                            description_data = nutrient_profile["nutrient_data"]
                        
                        if isinstance(description_data, dict):
                            for category_name, nutrients in description_data.items():
                                if isinstance(nutrients, list) and nutrients:
                                    first_nutrient = nutrients[0]
                                    if isinstance(first_nutrient, dict):
                                        for key, value in first_nutrient.items():
                                            if 'food' in key.lower() and isinstance(value, str) and len(value) > 10:
                                                food_description = value[:100]
                                                break
                                        break
                        
                        # Insert/update CNF food entry
                        cursor.execute("""
                            INSERT OR REPLACE INTO temp_cnf_foods 
                            (session_id, cnf_food_code, food_description, ingredient_name, refuse_flag, refuse_amount)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            input_data.session_id,
                            food_code,
                            food_description,
                            None,
                            bool(refuse_info),
                            None
                        ))
                        
                        # Clear existing nutrients for this food code
                        cursor.execute("""
                            DELETE FROM temp_cnf_nutrients 
                            WHERE session_id = ? AND cnf_food_code = ?
                        """, (input_data.session_id, food_code))
                        
                        nutrients_stored_this_food = 0
                        
                        # Extract the actual nutrient data from the response structure
                        actual_nutrient_data = nutrient_profile
                        if isinstance(nutrient_profile, dict) and "nutrient_data" in nutrient_profile:
                            actual_nutrient_data = nutrient_profile["nutrient_data"]
                        
                        if isinstance(actual_nutrient_data, dict):
                            for category_name, nutrients in actual_nutrient_data.items():
                                if isinstance(nutrients, list):
                                    for nutrient_idx, nutrient in enumerate(nutrients):
                                        if not isinstance(nutrient, dict):
                                            continue
                                        
                                        nutrient_name = nutrient.get('Nutrient name', '').strip()
                                        if not nutrient_name:
                                            continue
                                        
                                        # More resilient: checks multiple possible keys for the nutrient value
                                        baseline_value = None
                                        for key in ['Value per 100 g of edible portion', 'Per 100 g', '100g', 'Value/100g']:
                                            if key in nutrient:
                                                baseline_value = nutrient[key]
                                                break
                                        
                                        if baseline_value and str(baseline_value).strip():
                                            try:
                                                # More resilient: handles 'trace', '<' values, and other non-numeric strings
                                                clean_value = str(baseline_value).strip()
                                                if clean_value.lower() in ['trace', 'tr', '']:
                                                    baseline_float = 0.0
                                                elif clean_value.startswith('<'):
                                                    baseline_float = 0.0
                                                else:
                                                    import re
                                                    numeric_value = re.sub(r'[^\d\.\-]', '', clean_value)
                                                    baseline_float = float(numeric_value) if numeric_value else 0.0
                                                
                                                cursor.execute("""
                                                    INSERT OR REPLACE INTO temp_cnf_nutrients 
                                                    (session_id, cnf_food_code, nutrient_name, nutrient_value, 
                                                    per_amount, unit, nutrient_symbol)
                                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                                """, (
                                                    input_data.session_id,
                                                    food_code,  # Use the loop variable 'food_code'
                                                    nutrient_name,
                                                    baseline_float,
                                                    100.0,
                                                    'g',
                                                    nutrient.get('Unit see footnote1', '') or ''
                                                ))
                                                nutrients_stored_this_food += 1
                                            except (ValueError, TypeError):
                                                continue
                                        
                                        # Store serving size values - COPIED FROM get_cnf_nutrient_profile
                                        for key, value in nutrient.items():
                                            # Look for serving size columns (e.g., "5ml / 5 g", "15ml / 14 g") 
                                            # More robust serving size detection
                                            if ('/' in key and any(unit in key.lower() for unit in ['ml', 'g', 'tsp', 'tbsp', 'cup', 'oz'])) or \
                                               (any(unit in key.lower() for unit in ['ml', 'tsp', 'tbsp', 'cup', 'oz']) and any(char.isdigit() for char in key)):
                                                
                                                if value and str(value).strip() and str(value).strip() != '':
                                                    try:
                                                        # Clean and parse serving value
                                                        clean_serving_value = str(value).strip()
                                                        if clean_serving_value.lower() in ['trace', 'tr']:
                                                            serving_value = 0.0
                                                        elif clean_serving_value.startswith('<'):
                                                            serving_value = 0.0
                                                        else:
                                                            import re
                                                            numeric_serving = re.sub(r'[^\d\.\-]', '', clean_serving_value)
                                                            serving_value = float(numeric_serving) if numeric_serving else 0.0
                                                        
                                                        # Extract serving amount and unit from key
                                                        import re
                                                        # Try to match patterns like "5ml", "15ml", "1 tsp", "1/2 cup", etc.
                                                        match = re.search(r'(\d+(?:\.\d+)?|\d+/\d+)\s*([a-zA-Z]+)', key)
                                                        if match:
                                                            serving_amount_str = match.group(1)
                                                            serving_unit = match.group(2).lower()
                                                            
                                                            # Handle fractions in serving amounts
                                                            if '/' in serving_amount_str:
                                                                parts = serving_amount_str.split('/')
                                                                serving_amount = float(parts[0]) / float(parts[1])
                                                            else:
                                                                serving_amount = float(serving_amount_str)
                                                            
                                                            cursor.execute("""
                                                                INSERT OR REPLACE INTO temp_cnf_nutrients 
                                                                (session_id, cnf_food_code, nutrient_name, nutrient_value, 
                                                                 per_amount, unit, nutrient_symbol)
                                                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                                            """, (
                                                                input_data.session_id,
                                                                food_code,  # Use the loop variable 'food_code'
                                                                nutrient_name,
                                                                serving_value,
                                                                serving_amount,
                                                                serving_unit or '',
                                                                nutrient.get('Unit see footnote1', '') or ''
                                                            ))
                                                            nutrients_stored_this_food += 1
                                                    except (ValueError, TypeError) as e:
                                                        # Skip serving values that can't be parsed
                                                        continue
                        
                        # Step 4: ENHANCED - Link ingredient if mapping provided
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
                        
                        # Record success
                        successful_foods.append({
                            "food_code": food_code,
                            "food_description": food_description,
                            "nutrients_stored": nutrients_stored_this_food,
                            "serving_options": len(serving_options),
                            "ingredient_linking": linking_status
                        })
                        total_nutrients_stored += nutrients_stored_this_food
                        
                    except Exception as e:
                        #logger.error(f"Database storage error for food code {food_code}: {e}")
                        failed_foods.append({
                            "food_code": food_code,
                            "error": f"Database storage error: {str(e)}",
                            "suggestion": "Check database connectivity and try again"
                        })
                        if not input_data.continue_on_error:
                            break
                
                conn.commit()
                
            # Calculate efficiency metrics
            success_rate = (len(successful_foods) / total_foods) * 100 if total_foods > 0 else 0
            avg_nutrients_per_food = total_nutrients_stored / len(successful_foods) if successful_foods else 0
            
            # Calculate ingredient linking statistics
            linked_ingredients = sum(1 for food in successful_foods if food["ingredient_linking"].startswith("linked_to_"))
            linking_requested = bool(hasattr(input_data, 'ingredient_mappings') and input_data.ingredient_mappings and input_data.recipe_id)
            
            return {
                "success": True,
                "action": "bulk_macronutrients_processed_with_linking" if linking_requested else "bulk_macronutrients_processed",
                "message": f"✅ Concurrently processed {len(successful_foods)}/{total_foods} food codes successfully in {time.time() - start_time:.2f}s" + (f" with {linked_ingredients} ingredients linked" if linking_requested else ""),
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
                    "efficiency_improvement": f"{max(0, total_foods - 1)} fewer tool calls ({round((total_foods - 1) / total_foods * 100, 1)}% reduction)" if total_foods > 1 else "No efficiency gain for single food",
                    "concurrent_processing": f"Used {min(CNF_MAX_CONCURRENT, total_foods)} concurrent workers with {CNF_RATE_LIMIT}s rate limiting",
                    "performance_improvement": f"Concurrent processing vs sequential (estimated {total_foods * CNF_RATE_LIMIT:.1f}s sequential time)",
                    "caching_efficiency": f"Cache hits: {sum(1 for r in fetch_results if r.get('cached', False))}/{total_foods}",
                    "linking_efficiency": f"Linked {linked_ingredients} ingredients automatically vs separate linking steps" if linking_requested else "No ingredient linking requested"
                },
                "successful_foods": successful_foods,
                "failed_foods": failed_foods,
                "next_steps": [
                    "calculate_recipe_nutrition_summary() should now work for linked ingredients" if linking_requested and linked_ingredients > 0 else "Use calculate_recipe_nutrition_summary() for nutrition analysis",
                    "Continue linking remaining ingredients if needed" if linking_requested and linked_ingredients < (len(input_data.ingredient_mappings) if linking_requested else 0) else "Or link individual foods to recipe ingredients using get_cnf_macronutrients_only() with ingredient_id",
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
            scraper = get_cnf_scraper()
            
            # Get serving information first
            serving_options, refuse_info = scraper.get_serving_info(input_data.food_code)
            
            if serving_options is None:
                return {"error": f"Failed to get serving info for food code: {input_data.food_code}"}
            
            # Get complete nutrient profile
            nutrient_profile = scraper.get_nutrient_profile(input_data.food_code, serving_options)
            
            if nutrient_profile is None:
                return {"error": f"Failed to get nutrient profile for food code: {input_data.food_code}"}
            
            # REVOLUTIONARY CHANGE: Store directly in persistent SQLite tables
            from .schema import create_temp_nutrition_session, update_session_access_time
            
            # Ensure temp session exists
            create_temp_nutrition_session(input_data.session_id)
            update_session_access_time(input_data.session_id)
            
            # MIGRATION FIX: Update table schema to handle multiple serving sizes
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Check if we need to migrate the table schema
                cursor.execute("PRAGMA table_info(temp_cnf_nutrients)")
                columns = cursor.fetchall()
                primary_key_columns = []
                
                # Find if the table has the old primary key structure
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='temp_cnf_nutrients'")
                table_sql = cursor.fetchone()
                
                if table_sql and 'PRIMARY KEY (session_id, cnf_food_code, nutrient_name)' in table_sql[0]:
                    # Drop and recreate with correct primary key
                    cursor.execute("DROP TABLE IF EXISTS temp_cnf_nutrients")
                    cursor.execute("""
                        CREATE TABLE temp_cnf_nutrients (
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
                            PRIMARY KEY (session_id, cnf_food_code, nutrient_name, per_amount, unit),
                            FOREIGN KEY (session_id, cnf_food_code) REFERENCES temp_cnf_foods(session_id, cnf_food_code)
                        )
                    """)
                    
                    # Recreate index
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_temp_cnf_nutrients_food_code ON temp_cnf_nutrients(session_id, cnf_food_code)")
                    
                    conn.commit()
            
            # Extract food description from profile
            food_description = f"CNF Food {input_data.food_code}"
            if isinstance(nutrient_profile, dict):
                # Try to extract a better description from profile data
                for category_name, nutrients in nutrient_profile.items():
                    if isinstance(nutrients, list) and nutrients:
                        first_nutrient = nutrients[0]
                        if isinstance(first_nutrient, dict):
                            # Look for food name in the nutrient data
                            for key, value in first_nutrient.items():
                                if 'food' in key.lower() and isinstance(value, str) and len(value) > 10:
                                    food_description = value[:100]  # Truncate to reasonable length
                                    break
                            break
            
            # Populate persistent SQLite tables
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Insert/update CNF food entry
                cursor.execute("""
                    INSERT OR REPLACE INTO temp_cnf_foods 
                    (session_id, cnf_food_code, food_description, ingredient_name, refuse_flag, refuse_amount)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    input_data.session_id,
                    input_data.food_code,
                    food_description,
                    None,  # ingredient_name - to be populated when linking ingredients
                    bool(refuse_info),
                    None  # TODO: Parse refuse amount from refuse_info if needed
                ))
                
                # Clear existing nutrients for this food code (in case of re-fetch)
                cursor.execute("""
                    DELETE FROM temp_cnf_nutrients 
                    WHERE session_id = ? AND cnf_food_code = ?
                """, (input_data.session_id, input_data.food_code))
                
                # Extract and store nutrient data in persistent SQLite
                nutrient_count = 0
                errors_encountered = []
                
                if isinstance(nutrient_profile, dict):
                    for category_name, nutrients in nutrient_profile.items():
                        if isinstance(nutrients, list):
                            for nutrient_idx, nutrient in enumerate(nutrients):
                                if not isinstance(nutrient, dict):
                                    continue
                                
                                nutrient_name = nutrient.get('Nutrient name', '').strip()
                                if not nutrient_name:
                                    continue
                                
                                # Store 100g baseline value - KEY FIX: Handle various possible column names
                                baseline_value = None
                                for key in ['Value per 100 g of edible portion', 'Per 100 g', '100g', 'Value/100g']:
                                    if key in nutrient:
                                        baseline_value = nutrient[key]
                                        break
                                
                                if baseline_value and str(baseline_value).strip() and str(baseline_value).strip() != '':
                                    try:
                                        # Clean the value - remove any non-numeric characters except decimal point
                                        clean_value = str(baseline_value).strip()
                                        # Handle cases like "trace", "0", "<0.1", etc.
                                        if clean_value.lower() in ['trace', 'tr', '']:
                                            baseline_float = 0.0
                                        elif clean_value.startswith('<'):
                                            baseline_float = 0.0  # Treat "less than" values as 0
                                        else:
                                            # Remove any non-numeric characters except decimal point and negative sign
                                            import re
                                            numeric_value = re.sub(r'[^\d\.\-]', '', clean_value)
                                            baseline_float = float(numeric_value) if numeric_value else 0.0
                                        
                                        cursor.execute("""
                                            INSERT OR REPLACE INTO temp_cnf_nutrients 
                                            (session_id, cnf_food_code, nutrient_name, nutrient_value, 
                                             per_amount, unit, nutrient_symbol)
                                            VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """, (
                                            input_data.session_id,
                                            input_data.food_code,
                                            nutrient_name,
                                            baseline_float,
                                            100.0,
                                            'g',
                                            nutrient.get('Unit see footnote1', '') or ''
                                        ))
                                        nutrient_count += 1
                                    except (ValueError, TypeError) as e:
                                        error_msg = f"Failed to parse 100g value for {nutrient_name}: {baseline_value} -> {str(e)}"
                                        errors_encountered.append(error_msg)
                                
                                # Store serving size values - IMPROVED PARSING
                                for key, value in nutrient.items():
                                    # Look for serving size columns (e.g., "5ml / 5 g", "15ml / 14 g") 
                                    # FIXED: More robust serving size detection
                                    if ('/' in key and any(unit in key.lower() for unit in ['ml', 'g', 'tsp', 'tbsp', 'cup', 'oz'])) or \
                                       (any(unit in key.lower() for unit in ['ml', 'tsp', 'tbsp', 'cup', 'oz']) and any(char.isdigit() for char in key)):
                                        
                                        if value and str(value).strip() and str(value).strip() != '':
                                            try:
                                                # Clean and parse serving value
                                                clean_serving_value = str(value).strip()
                                                if clean_serving_value.lower() in ['trace', 'tr']:
                                                    serving_value = 0.0
                                                elif clean_serving_value.startswith('<'):
                                                    serving_value = 0.0
                                                else:
                                                    import re
                                                    numeric_serving = re.sub(r'[^\d\.\-]', '', clean_serving_value)
                                                    serving_value = float(numeric_serving) if numeric_serving else 0.0
                                                
                                                # IMPROVED: Extract serving amount and unit from key
                                                import re
                                                # Try to match patterns like "5ml", "15ml", "1 tsp", "1/2 cup", etc.
                                                match = re.search(r'(\d+(?:\.\d+)?|\d+/\d+)\s*([a-zA-Z]+)', key)
                                                if match:
                                                    serving_amount_str = match.group(1)
                                                    serving_unit = match.group(2).lower()
                                                    
                                                    # Handle fractions in serving amounts
                                                    if '/' in serving_amount_str:
                                                        parts = serving_amount_str.split('/')
                                                        serving_amount = float(parts[0]) / float(parts[1])
                                                    else:
                                                        serving_amount = float(serving_amount_str)
                                                    
                                                    cursor.execute("""
                                                        INSERT OR REPLACE INTO temp_cnf_nutrients 
                                                        (session_id, cnf_food_code, nutrient_name, nutrient_value, 
                                                         per_amount, unit, nutrient_symbol)
                                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                                    """, (
                                                        input_data.session_id,
                                                        input_data.food_code,
                                                        nutrient_name,
                                                        serving_value,
                                                        serving_amount,
                                                        serving_unit or '',
                                                        nutrient.get('Unit see footnote1', '') or ''
                                                    ))
                                                    nutrient_count += 1
                                            except (ValueError, TypeError) as e:
                                                error_msg = f"Failed to parse serving value for {nutrient_name} ({key}): {value} -> {str(e)}"
                                                errors_encountered.append(error_msg)
                
                conn.commit()
            
            # BACKWARD COMPATIBILITY: Also store in virtual session for legacy tools
            session_data = get_virtual_session_data(input_data.session_id)
            if session_data is None:
                from src.db.schema import create_virtual_recipe_session
                create_virtual_recipe_session(input_data.session_id)
                session_data = get_virtual_session_data(input_data.session_id)
            
            # Store legacy format
            if 'nutrient_profiles' not in session_data:
                session_data['nutrient_profiles'] = {}
            
            session_data['nutrient_profiles'][input_data.food_code] = {
                'food_code': input_data.food_code,
                'serving_options': serving_options,
                'refuse_info': refuse_info,
                'nutrient_profile': nutrient_profile,
                'retrieved_at': str(json.dumps(None))
            }
            
            return {
                "success": f"✅ FIXED: CNF data stored in persistent SQLite tables",
                "food_code": input_data.food_code,
                "food_description": food_description,
                "session_id": input_data.session_id,
                "storage_type": "persistent_sqlite",
                "nutrient_records_stored": nutrient_count,
                "serving_options": len(serving_options) if serving_options else 0,
                "nutrient_categories": list(nutrient_profile.keys()) if isinstance(nutrient_profile, dict) else [],
                "parsing_errors": len(errors_encountered),
                "debug_info": {
                    "profile_type": str(type(nutrient_profile)),
                    "category_count": len(nutrient_profile) if isinstance(nutrient_profile, dict) else 0,
                    "first_few_errors": errors_encountered[:3] if errors_encountered else []
                },
                "next_step": "Use get_cnf_macronutrients_only() with ingredient_id to link ingredients",
                "workflow_status": "✅ Ready for nutrition analysis" if nutrient_count > 0 else "❌ No nutrients stored - check debug info"
            }
            
        except Exception as e:
            ###logger.error(f"Error getting CNF nutrient profile: {e}")
            return {"error": f"Failed to get CNF nutrient profile: {str(e)}"}

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
        "tools_count": 7 if CNF_TOOLS_AVAILABLE else 0,
        "tools": [
            "simple_recipe_setup",            # 🛠️ Manual recipe setup (reliable)
            "search_cnf_foods",               # Core search functionality
            "get_cnf_nutrient_profile",       # Core profile retrieval (NOW: auto-populates SQLite)
            "link_ingredient_to_cnf_simple",  # Simplified linking for SQL
            "get_nutrition_tables_info",      # SQL table schema documentation
            "get_ingredient_nutrition_matches" # Match status viewer
        ] if CNF_TOOLS_AVAILABLE else [],
        "architecture_improvement": {
            "issue_fixed": "CNF linking failures due to dual virtual/persistent architecture",
            "solution_implemented": "Full SQLite architecture - CNF data goes directly to persistent tables",
            "benefits": [
                "✅ CNF data and ingredient updates use SAME SQLite tables",
                "✅ No more virtual/persistent sync issues",
                "✅ Transparent, debuggable nutrition analysis",
                "✅ Single source of truth for all data"
            ],
        }
    }