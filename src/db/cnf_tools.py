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
        CNFSearchInput, CNFProfileInput, IngredientMatchInput,
        NutritionCalculationInput, CNFCleanupInput,
        CNFFoodResult, CNFNutrientProfile, IngredientCNFMatch,
        RecipeNutritionSummary, CNFSessionSummary
    )
    from src.api.cnf import NutrientFileScraper
    from src.db.schema import get_virtual_session_data, store_recipe_in_virtual_session
    CNF_TOOLS_AVAILABLE = True
except ImportError:
    try:
        from models.cnf_models import (
            CNFSearchInput, CNFProfileInput, IngredientMatchInput,
            NutritionCalculationInput, CNFCleanupInput,
            CNFFoodResult, CNFNutrientProfile, IngredientCNFMatch,
            RecipeNutritionSummary, CNFSessionSummary
        )
        from api.cnf import NutrientFileScraper
        from db.schema import get_virtual_session_data, store_recipe_in_virtual_session
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
        
        **Complete CNF Workflow (use math tools for calculations):**
        1. search_cnf_foods → find appropriate food codes
        2. get_cnf_nutrient_profile → retrieve nutrition data  
        3. link_ingredient_to_cnf → connect to recipe ingredients
        4. calculate_recipe_nutrition → prepare calculation formulas
        5. simple_math_calculator → calculate totals using provided formulas
        6. simple_math_calculator → calculate per-serving values
        
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
        
        **Math Tool Workflow After Getting Profile:**
        1. Extract specific nutrient values from the nutrient_profile
        2. Use simple_math_calculator to convert amounts: "(calories_per_100g * ingredient_amount / 100)"
        3. Use simple_math_calculator to sum multiple ingredients
        4. Use simple_math_calculator for per-serving calculations
        
        **Example Values Extraction:**
        - Calories: nutrient_profile['Proximates'][find 'Energy (kcal)']['Value per 100 g of edible portion']
        - Protein: nutrient_profile['Proximates'][find 'Protein']['Value per 100 g of edible portion']
        - Fat: nutrient_profile['Proximates'][find 'Total Fat']['Value per 100 g of edible portion']
        
        **Enhanced serving size handling**: Now captures ALL available serving options,
        including volume measures (ml, tsp, tbsp) and weight conversions for liquid foods.
        
        Use this tool when:
        - Getting detailed nutrition data for a matched ingredient
        - Preparing data for math tool calculations
        - Exploring nutritional content of specific CNF foods
        - Building ingredient-nutrition databases
        
        Next steps after getting profile:
        1. Use link_ingredient_to_cnf to connect this food to recipe ingredients
        2. Use calculate_recipe_nutrition to prepare calculation formulas
        3. Use simple_math_calculator with the provided formulas for totals
        4. Compare results with EER calculations using simple_math_calculator
        
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
            
            # Store complete profile
            session_data['nutrient_profiles'][input_data.food_code] = {
                'food_code': input_data.food_code,
                'serving_options': serving_options,
                'refuse_info': refuse_info,
                'nutrient_profile': nutrient_profile,
                'retrieved_at': str(json.dumps(None))  # Will be set by JSON serialization
            }
            
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
    def link_ingredient_to_cnf(input_data: IngredientMatchInput) -> Dict[str, Any]:
        """
        Link a recipe ingredient to a specific CNF food for nutrition analysis.
        
        This tool creates a connection between a recipe ingredient and a CNF food code,
        enabling nutrition calculations for recipes. The link includes confidence scoring
        and serving conversion information for accurate nutrition calculations.
        
        Use this tool when:
        - Connecting parsed recipe ingredients to CNF foods
        - Building ingredient-to-nutrition mappings for recipes
        - Preparing recipes for complete nutrition analysis
        - Creating ingredient databases for repeated use
        
        After linking ingredients to CNF foods, use calculate_recipe_nutrition to get
        complete nutritional summaries for recipes.
        
        Args:
            input_data: IngredientMatchInput with session_id, ingredient_id, cnf_food_code
            
        Returns:
            Dict confirming the ingredient-CNF link creation with match details
        """
        try:
            session_data = get_virtual_session_data(input_data.session_id)
            if session_data is None:
                return {"error": f"Session {input_data.session_id} not found"}
            
            # Check if ingredient exists
            if 'ingredients' not in session_data or input_data.ingredient_id not in session_data['ingredients']:
                return {"error": f"Ingredient {input_data.ingredient_id} not found in session"}
            
            # Check if CNF profile exists in session
            if 'nutrient_profiles' not in session_data or input_data.cnf_food_code not in session_data['nutrient_profiles']:
                return {"error": f"CNF food code {input_data.cnf_food_code} not found in session. Get nutrient profile first."}
            
            # Ensure match data structure exists
            if 'ingredient_cnf_matches' not in session_data:
                session_data['ingredient_cnf_matches'] = {}
            
            # Get ingredient and CNF data
            ingredient_data = session_data['ingredients'][input_data.ingredient_id]
            cnf_data = session_data['nutrient_profiles'][input_data.cnf_food_code]
            
            # Create the match
            match_data = {
                'ingredient_id': input_data.ingredient_id,
                'cnf_food_code': input_data.cnf_food_code,
                'cnf_food_name': 'Unknown',  # Would need additional lookup
                'confidence_score': input_data.confidence_score,
                'ingredient_name': ingredient_data.get('ingredient_name', ''),
                'ingredient_text': ingredient_data.get('ingredient_list_org', ''),
                'serving_conversion': {},  # Could be enhanced with unit conversions
                'created_at': str(json.dumps(None))  # JSON serialization will handle
            }
            
            session_data['ingredient_cnf_matches'][input_data.ingredient_id] = match_data
            
            return {
                "success": f"Linked ingredient {input_data.ingredient_id} to CNF food {input_data.cnf_food_code}",
                "ingredient_id": input_data.ingredient_id,
                "ingredient_name": ingredient_data.get('ingredient_name', ''),
                "cnf_food_code": input_data.cnf_food_code,
                "confidence_score": input_data.confidence_score,
                "session_id": input_data.session_id
            }
            
        except Exception as e:
            logger.error(f"Error linking ingredient to CNF: {e}")
            return {"error": f"Failed to link ingredient to CNF: {str(e)}"}

    @mcp.tool()
    def calculate_recipe_nutrition(input_data: NutritionCalculationInput) -> Dict[str, Any]:
        """
        Prepare nutrition data with optimized CNF serving size matching - DO NOT manually calculate totals.
        
        CRITICAL: This tool now intelligently matches recipe units to CNF serving sizes for maximum accuracy.
        DO NOT manually parse JSON or sum values - use math tools for all calculations!
        
        **NEW: Enhanced Serving Size Matching**
        - Automatically finds CNF serving sizes that match recipe ingredient units
        - Example: 10mL oil uses "5mL serving × 2" instead of "100g conversion"
        - Provides serving_size_analysis showing accuracy improvements
        - Falls back to 100g baseline when no serving matches are found
        
        REQUIRED WORKFLOW after using this tool:
        1. Review serving_size_analysis to see accuracy improvements
        2. Use simple_math_calculator with the optimized calculation_formulas 
        3. Calculate per-serving values using simple_math_calculator
        4. The formulas now use CNF serving sizes when recipe units match
        
        Example usage with serving size optimization:
        ```
        # Step 1: Get optimized nutrition data (this tool)
        nutrition_data = calculate_recipe_nutrition(session_id="session1", recipe_id="recipe1")
        
        # Step 2: Review serving size matching success
        print(f"Serving match rate: {nutrition_data['serving_size_analysis']['serving_match_percentage']}%")
        
        # Step 3: Calculate totals using optimized formulas
        total_calories = simple_math_calculator(
            expression=nutrition_data["calculation_formulas"]["total_calories"], 
            variables={}
        )
        
        # Step 4: Calculate per-serving
        per_serving = simple_math_calculator(
            expression="total_calories / servings", 
            variables={"total_calories": total_calories["result"], "servings": nutrition_data["base_servings"]}
        )
        ```
        
        **Serving Size Matching Benefits:**
        - More accurate calculations using CNF serving-specific values
        - Reduces unit conversion errors
        - Matches recipe measurements (mL, tsp, tbsp) to CNF serving columns
        - Provides transparency about calculation methods used
        
        This tool extracts nutrition values from CNF profiles, matches serving sizes to recipe units,
        and prepares optimized calculation formulas for the math tools. It does NOT perform final calculations.
        
        Use this tool when:
        - Preparing recipe nutrition data for accurate calculation
        - Getting detailed serving size matching analysis
        - Setting up optimized data for math tool calculations
        - Comparing calculation accuracy between serving-based vs 100g methods
        
        Args:
            input_data: NutritionCalculationInput with session_id, recipe_id
            
        Returns:
            Dict with optimized nutrition data, serving size analysis, calculation formulas,
            coverage information, and instructions to use simple_math_calculator
        """
        try:
            session_data = get_virtual_session_data(input_data.session_id)
            if session_data is None:
                return {"error": f"Session {input_data.session_id} not found"}
            
            # Check if recipe exists
            if 'recipes' not in session_data or input_data.recipe_id not in session_data['recipes']:
                return {"error": f"Recipe {input_data.recipe_id} not found in session"}
            
            recipe_data = session_data['recipes'][input_data.recipe_id]
            base_servings = recipe_data.get('base_servings', 1)
            
            # Get all ingredients for this recipe
            recipe_ingredients = [
                ing for ing in session_data.get('ingredients', {}).values()
                if ing.get('recipe_id') == input_data.recipe_id
            ]
            
            if not recipe_ingredients:
                return {"error": f"No ingredients found for recipe {input_data.recipe_id}"}
            
            # Get CNF matches
            matches = session_data.get('ingredient_cnf_matches', {})
            nutrient_profiles = session_data.get('nutrient_profiles', {})
            
            # Prepare nutrition data for math tools (DO NOT calculate here)
            nutrition_data = []
            calorie_terms = []
            protein_terms = []
            fat_terms = []
            carb_terms = []
            matched_count = 0
            
            for ingredient in recipe_ingredients:
                ingredient_id = ingredient['ingredient_id']
                ingredient_name = ingredient.get('ingredient_name', 'Unknown')
                ingredient_amount = ingredient.get('amount', 0) or 0
                
                if ingredient_id in matches and matches[ingredient_id]['cnf_food_code'] in nutrient_profiles:
                    matched_count += 1
                    cnf_code = matches[ingredient_id]['cnf_food_code']
                    profile = nutrient_profiles[cnf_code]
                    nutrient_data = profile.get('nutrient_profile', {})
                    
                    # Extract nutrition values and serving size options (prepare for math tools, don't calculate)
                    ingredient_nutrition = {
                        'ingredient_name': ingredient_name,
                        'amount': ingredient_amount,
                        'unit': ingredient.get('unit', ''),
                        'cnf_code': cnf_code,
                        'calories_per_100g': 0,
                        'protein_per_100g': 0,
                        'fat_per_100g': 0,
                        'carbs_per_100g': 0,
                        'calculation_options': {
                            'calories': [],
                            'protein': [],
                            'fat': [],
                            'carbohydrates': []
                        }
                    }
                    
                    # Extract values from Proximates category with serving size analysis
                    if 'Proximates' in nutrient_data:
                        for nutrient in nutrient_data['Proximates']:
                            nutrient_name = nutrient.get('Nutrient name', '').lower()
                            
                            # Parse all serving size columns for this nutrient
                            serving_data = _parse_cnf_serving_columns(nutrient)
                            
                            try:
                                # Get 100g baseline value
                                baseline_value = float(nutrient.get('Value per 100 g of edible portion', 0))
                                
                                if 'energy (kcal)' in nutrient_name:
                                    ingredient_nutrition['calories_per_100g'] = baseline_value
                                    
                                    # Find serving size matches for calories
                                    if ingredient_amount and ingredient.get('unit'):
                                        serving_options = _match_recipe_units_to_servings(
                                            ingredient_amount, ingredient.get('unit'), serving_data
                                        )
                                        ingredient_nutrition['calculation_options']['calories'] = serving_options
                                    
                                    # Add fallback 100g calculation
                                    fallback_formula = f"({baseline_value} * {ingredient_amount} / 100)"
                                    if not ingredient_nutrition['calculation_options']['calories']:
                                        # No serving matches found - use 100g baseline
                                        calorie_terms.append(fallback_formula)
                                    else:
                                        # Use best serving match
                                        best_option = ingredient_nutrition['calculation_options']['calories'][0]
                                        calorie_terms.append(best_option['formula'])
                                
                                elif 'protein' in nutrient_name:
                                    ingredient_nutrition['protein_per_100g'] = baseline_value
                                    
                                    # Find serving size matches for protein
                                    if ingredient_amount and ingredient.get('unit'):
                                        serving_options = _match_recipe_units_to_servings(
                                            ingredient_amount, ingredient.get('unit'), serving_data
                                        )
                                        ingredient_nutrition['calculation_options']['protein'] = serving_options
                                    
                                    # Add to formula
                                    fallback_formula = f"({baseline_value} * {ingredient_amount} / 100)"
                                    if not ingredient_nutrition['calculation_options']['protein']:
                                        protein_terms.append(fallback_formula)
                                    else:
                                        best_option = ingredient_nutrition['calculation_options']['protein'][0]
                                        protein_terms.append(best_option['formula'])
                                
                                elif 'total fat' in nutrient_name:
                                    ingredient_nutrition['fat_per_100g'] = baseline_value
                                    
                                    # Find serving size matches for fat
                                    if ingredient_amount and ingredient.get('unit'):
                                        serving_options = _match_recipe_units_to_servings(
                                            ingredient_amount, ingredient.get('unit'), serving_data
                                        )
                                        ingredient_nutrition['calculation_options']['fat'] = serving_options
                                    
                                    # Add to formula
                                    fallback_formula = f"({baseline_value} * {ingredient_amount} / 100)"
                                    if not ingredient_nutrition['calculation_options']['fat']:
                                        fat_terms.append(fallback_formula)
                                    else:
                                        best_option = ingredient_nutrition['calculation_options']['fat'][0]
                                        fat_terms.append(best_option['formula'])
                                
                                elif 'carbohydrate' in nutrient_name:
                                    ingredient_nutrition['carbs_per_100g'] = baseline_value
                                    
                                    # Find serving size matches for carbohydrates
                                    if ingredient_amount and ingredient.get('unit'):
                                        serving_options = _match_recipe_units_to_servings(
                                            ingredient_amount, ingredient.get('unit'), serving_data
                                        )
                                        ingredient_nutrition['calculation_options']['carbohydrates'] = serving_options
                                    
                                    # Add to formula
                                    fallback_formula = f"({baseline_value} * {ingredient_amount} / 100)"
                                    if not ingredient_nutrition['calculation_options']['carbohydrates']:
                                        carb_terms.append(fallback_formula)
                                    else:
                                        best_option = ingredient_nutrition['calculation_options']['carbohydrates'][0]
                                        carb_terms.append(best_option['formula'])
                                        
                            except (ValueError, TypeError):
                                continue
                    
                    nutrition_data.append(ingredient_nutrition)
            
            # Calculate coverage
            coverage_percentage = (matched_count / len(recipe_ingredients)) * 100
            
            # Prepare calculation formulas for math tools
            calories_formula = " + ".join(calorie_terms) if calorie_terms else "0"
            protein_formula = " + ".join(protein_terms) if protein_terms else "0"
            fat_formula = " + ".join(fat_terms) if fat_terms else "0"
            carbs_formula = " + ".join(carb_terms) if carb_terms else "0"
            
            # Analyze serving size matching success
            serving_matches_found = 0
            total_nutrients_analyzed = 0
            serving_size_summary = []
            
            for ingredient in nutrition_data:
                for nutrient_type, options in ingredient['calculation_options'].items():
                    total_nutrients_analyzed += 1
                    if options and options[0].get('preferred'):
                        serving_matches_found += 1
                        serving_size_summary.append({
                            'ingredient': ingredient['ingredient_name'],
                            'nutrient': nutrient_type,
                            'recipe_amount': f"{ingredient['amount']} {ingredient['unit']}",
                            'cnf_serving_used': options[0]['description'],
                            'accuracy': options[0]['accuracy']
                        })
            
            serving_match_percentage = (serving_matches_found / total_nutrients_analyzed * 100) if total_nutrients_analyzed > 0 else 0
            
            return {
                "instruction": "Use simple_math_calculator to calculate nutrition totals - formulas optimized with CNF serving sizes",
                "recipe_id": input_data.recipe_id,
                "recipe_title": recipe_data.get('title', 'Unknown'),
                "base_servings": base_servings,
                "nutrition_data": nutrition_data,
                "calculation_formulas": {
                    "total_calories": calories_formula,
                    "total_protein": protein_formula,
                    "total_fat": fat_formula,
                    "total_carbohydrates": carbs_formula
                },
                "serving_size_analysis": {
                    "serving_matches_found": serving_matches_found,
                    "total_nutrients_analyzed": total_nutrients_analyzed,
                    "serving_match_percentage": round(serving_match_percentage, 1),
                    "serving_size_summary": serving_size_summary,
                    "accuracy_note": "Higher percentages indicate more accurate calculations using CNF serving sizes"
                },
                "math_tool_examples": {
                    "calculate_total_calories": f"simple_math_calculator(expression='{calories_formula}', variables={{}})",
                    "calculate_per_serving": f"simple_math_calculator(expression='total_calories / {base_servings}', variables={{'total_calories': result_from_above}})"
                },
                "coverage_info": {
                    "matched_ingredients": matched_count,
                    "total_ingredients": len(recipe_ingredients),
                    "coverage_percentage": round(coverage_percentage, 1),
                    "unmatched_ingredients": len(recipe_ingredients) - matched_count
                },
                "calculation_accuracy": {
                    "method_used": "serving_size_optimized" if serving_match_percentage > 50 else "mixed_methods",
                    "accuracy_level": "high" if serving_match_percentage > 75 else "medium" if serving_match_percentage > 25 else "baseline",
                    "improvement": f"Using CNF serving sizes improved accuracy for {serving_match_percentage:.1f}% of nutrients"
                },
                "session_id": input_data.session_id,
                "next_steps": [
                    "1. Use simple_math_calculator with the optimized calculation_formulas",
                    "2. Review serving_size_analysis to understand accuracy improvements", 
                    "3. Calculate per-serving values by dividing totals by base_servings",
                    "4. Compare with EER values using simple_math_calculator",
                    "5. The formulas now use CNF serving sizes when recipe units match"
                ]
            }
            
        except Exception as e:
            logger.error(f"Error preparing recipe nutrition data: {e}")
            return {"error": f"Failed to prepare recipe nutrition data: {str(e)}"}

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
        "tools_count": 6 if CNF_TOOLS_AVAILABLE else 0,
        "tools": [
            "search_cnf_foods",
            "get_cnf_nutrient_profile", 
            "link_ingredient_to_cnf",
            "calculate_recipe_nutrition",
            "get_ingredient_nutrition_matches",
            "clear_cnf_session_data"
        ] if CNF_TOOLS_AVAILABLE else []
    }