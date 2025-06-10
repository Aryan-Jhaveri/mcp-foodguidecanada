"""Math tools for calculating recipe servings, scaling ingredients, and comparing recipes."""
import json
import re
import ast
import operator
import os
import sys
from typing import Dict, Any, List, Optional
from fastmcp import FastMCP

# Handle imports using absolute path resolution
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Add paths to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.models.math_models import (
        SimpleMathInput, ServingSizeInput, IngredientScaleInput, BulkIngredientScaleInput, 
        RecipeComparisonInput, BulkMathInput, BulkMathCalculation
    )
except ImportError:
    try:
        from models.math_models import (
            SimpleMathInput, ServingSizeInput, IngredientScaleInput, BulkIngredientScaleInput, 
            RecipeComparisonInput, BulkMathInput, BulkMathCalculation
        )
    except ImportError as e:
        print(f"Error importing math_models: {e}", file=sys.stderr)
        # Set to None - will cause issues but can't easily fallback for Pydantic models
        SimpleMathInput = None
        ServingSizeInput = None
        IngredientScaleInput = None
        BulkIngredientScaleInput = None
        RecipeComparisonInput = None
        BulkMathInput = None
        BulkMathCalculation = None

def register_math_tools(mcp: FastMCP):
    """Register recipe math and calculation tools with the MCP server."""

    @mcp.tool()
    def simple_math_calculator(math_input: SimpleMathInput) -> Dict[str, Any]:
        """
        Perform simple mathematical calculations with string variables.
        
        !!REMEMBER: ALWAYS USE ONLY THE VALUES FROM THE .DB for the given session, NEVER ASSUME VALUES"
        
        This tool allows you to evaluate mathematical expressions containing variables.
        It supports basic arithmetic operations (+, -, *, /, **, %) and common math functions.
        
        **CRITICAL for CNF nutrition calculations**: This is the ONLY tool to use for 
        calculating nutrition totals. Never manually sum values from JSON data.
        
        Supported operations:
        - Basic arithmetic: +, -, *, /, ** (power), % (modulo)
        - Parentheses for grouping: (expression)
        - Variables: any valid Python identifier (letters, numbers, underscores)
        
        Use this tool when:
        - Calculating EER equations with specific values
        - **CNF nutrition calculations - summing calories, macros across ingredients**
        - **Recipe per-serving calculations - dividing totals by serving count**
        - Scaling recipe quantities
        - Converting units
        - Any mathematical operation with known variables
        
        **CNF Nutrition Examples:**
        - Total calories: "(206 * 565 / 100) + (885 * 10 / 100) + (22 * 450 / 100)"
        - Per serving: expression="total_calories / servings", variables={"total_calories": 1437, "servings": 5}
        - Scaling: expression="original_amount * scale_factor", variables={"original_amount": 100, "scale_factor": 1.5}
        - EER comparison: expression="recipe_calories - eer_requirement", variables={"recipe_calories": 287, "eer_requirement": 2000}
        
        **TEMP_RECIPE_MACROS Calculation Examples:**
        - Conversion factor: expression="recipe_amount / cnf_serving", variables={"recipe_amount": 10.0, "cnf_serving": 5.0}  # = 2.0
        - Scaled calories: expression="cnf_calories * conversion_factor", variables={"cnf_calories": 22.0, "conversion_factor": 2.0}  # = 44.0
        - Recipe total from cache: expression="honey_cals + oil_cals + salmon_cals", variables={"honey_cals": 44.0, "oil_cals": 80.0, "salmon_cals": 200.0}
        
        **General Examples:**
        - EER calculation: "662 - (9.53 * age) + (15.91 * weight) + (539.6 * height)"
        - Unit conversion: "cups * 240" (cups to ml)
        - Percentage: "part / total * 100"
        
        Args:
            math_input: Contains expression string and variables dictionary
            
        Returns:
            Dictionary with calculation result and details
        """
        # Use the extracted helper function for core calculation logic
        return _calculate_single_expression(math_input.expression, math_input.variables)

    @mcp.tool()
    def bulk_math_calculator(bulk_input: BulkMathInput) -> Dict[str, Any]:
        """
        Perform multiple mathematical calculations in a single operation.
        
        !!REMEMBER: ALWAYS USE ONLY THE VALUES FROM THE .DB for the given session, NEVER ASSUME VALUES"
        
        This tool allows you to evaluate multiple mathematical expressions in one call,
        eliminating the need for repeated tool calls when calculating nutrition data,
        recipe scaling, or any batch mathematical operations.
        
        **PERFECT for CNF nutrition calculations**: Instead of calling simple_math_calculator
        multiple times for each ingredient, calculate all ingredient nutrition values at once.
        
        Each calculation includes:
        - Unique ID for easy result identification
        - Mathematical expression with variables
        - Variable dictionary for that specific calculation
        
        Supported operations (same as simple_math_calculator):
        - Basic arithmetic: +, -, *, /, ** (power), % (modulo)
        - Parentheses for grouping: (expression)
        - Variables: any valid Python identifier (letters, numbers, underscores)
        
        **Efficiency Benefits:**
        - Reduces N tool calls to 1 tool call (3x-10x+ performance improvement)
        - Perfect for multi-ingredient nutrition analysis
        - Batch processing of recipe scaling calculations
        - Bulk EER calculations for multiple profiles
        
        **Usage Examples:**
        
        **CNF Nutrition Analysis (Multiple Ingredients):**
        ```
        calculations: [
            {"id": "honey_cals", "expression": "cnf_calories * conversion_factor", 
             "variables": {"cnf_calories": 22, "conversion_factor": 2}},
            {"id": "salmon_cals", "expression": "cnf_calories * conversion_factor",
             "variables": {"cnf_calories": 206, "conversion_factor": 5.65}},
            {"id": "oil_cals", "expression": "cnf_calories * conversion_factor",
             "variables": {"cnf_calories": 885, "conversion_factor": 0.1}}
        ]
        ```
        
        **Recipe Totals and Per-Serving:**
        ```
        calculations: [
            {"id": "total_calories", "expression": "honey + salmon + oil", 
             "variables": {"honey": 44, "salmon": 1164, "oil": 89}},
            {"id": "per_serving", "expression": "total / servings",
             "variables": {"total": 1297, "servings": 4}}
        ]
        ```
        
        **Multiple EER Calculations:**
        ```
        calculations: [
            {"id": "adult_male", "expression": "662 - (9.53 * age) + (15.91 * weight) + (539.6 * height)",
             "variables": {"age": 30, "weight": 75, "height": 1.75}},
            {"id": "adult_female", "expression": "354 - (6.91 * age) + (9.36 * weight) + (726 * height)",
             "variables": {"age": 28, "weight": 65, "height": 1.65}}
        ]
        ```
        
        Args:
            bulk_input: Contains list of calculations, each with id, expression, and variables
            
        Returns:
            Dictionary with:
            - Overall status and summary statistics
            - Individual results keyed by calculation ID
            - Error details for any failed calculations
            - Performance metrics (total calculations processed)
        """
        try:
            calculations = bulk_input.calculations
            results = {}
            errors = {}
            successful_calculations = 0
            total_calculations = len(calculations)
            
            # Process each calculation
            for calc in calculations:
                calc_id = calc.id
                
                # Validate unique IDs
                if calc_id in results or calc_id in errors:
                    errors[calc_id] = {
                        "error": f"Duplicate calculation ID: {calc_id}",
                        "expression": calc.expression
                    }
                    continue
                
                # Perform the calculation using the helper function
                calc_result = _calculate_single_expression(calc.expression, calc.variables)
                
                if calc_result["status"] == "success":
                    results[calc_id] = {
                        "result": calc_result["result"],
                        "expression": calc_result["expression"],
                        "substituted_expression": calc_result["substituted_expression"],
                        "variables_used": calc_result["variables_used"],
                        "calculation_steps": calc_result["calculation_steps"]
                    }
                    successful_calculations += 1
                else:
                    errors[calc_id] = {
                        "error": calc_result["error"],
                        "expression": calc_result["expression"],
                        "variables_provided": calc_result.get("variables_provided", [])
                    }
            
            # Determine overall status
            if successful_calculations == total_calculations:
                overall_status = "success"
            elif successful_calculations > 0:
                overall_status = "partial_success"
            else:
                overall_status = "failure"
            
            return {
                "status": overall_status,
                "total_calculations": total_calculations,
                "successful_calculations": successful_calculations,
                "failed_calculations": total_calculations - successful_calculations,
                "results": results,
                "errors": errors,
                "summary": {
                    "efficiency_gain": f"Processed {total_calculations} calculations in 1 tool call",
                    "success_rate": f"{successful_calculations}/{total_calculations}",
                    "performance": f"{successful_calculations} successful calculations" if successful_calculations > 0 else "No successful calculations"
                }
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "error": f"Bulk calculation failed: {e}",
                "total_calculations": len(bulk_input.calculations) if bulk_input.calculations else 0,
                "successful_calculations": 0,
                "failed_calculations": len(bulk_input.calculations) if bulk_input.calculations else 0,
                "results": {},
                "errors": {}
            }

    @mcp.tool()
    def scale_recipe_servings(serving_input: ServingSizeInput) -> Dict[str, Any]:
        """
        Scale all ingredients in a recipe to match a target number of servings.
        
        This tool calculates new ingredient amounts when you want to make more or fewer servings
        of a recipe. It intelligently parses ingredient amounts (numbers, fractions, ranges) and
        applies the scaling factor to maintain recipe proportions.

        REMEMBER! Always share recipe url, and image_url, and title with users before returning full recipe details. This allows them to see the source and context of the recipe.
        REMEMBER! Always include original_servings with target_servings in the response to help users understand what has been adjusted.
        REMEMBER! Scaled recipes cooking times may vary, so users should check for doneness and adjust as needed.

        The scaling process:
        - Calculates scale factor based on original vs target servings
        - Parses ingredient amounts from text (handles fractions, decimals, ranges)
        - Applies scaling to all measurable ingredients
        - Preserves units and ingredient names
        - Updates the recipe data with scaled amounts
        
        Use this tool when:
        - Cooking for more or fewer people than the original recipe
        - Meal prepping larger batches
        - Adjusting recipes for different household sizes
        - Planning party or event cooking
        - Reducing recipe size for testing
        
        Args:
            serving_input: Contains session_id, recipe_id, and target_servings number.
                          Target servings must be greater than 0.
            
        Returns:
            Dict with scaled recipe data including original and new serving counts,
            scale factor used, updated ingredient list with new amounts, and summary
            of changes made, or error message if recipe not found or scaling fails
        """
        session_id = serving_input.session_id
        recipe_id = serving_input.recipe_id
        target_servings = serving_input.target_servings
        
        try:
            from .schema import get_virtual_session_data
            
            # Get virtual session data
            session = get_virtual_session_data(session_id)
            if not session:
                return {"error": f"Virtual session {session_id} not found"}
            
            # Get original recipe data
            if recipe_id not in session['recipes']:
                return {"error": f"Recipe {recipe_id} not found in session {session_id}"}
            
            recipe_data = session['recipes'][recipe_id]
            original_servings = recipe_data.get('base_servings') or 1
            scale_factor = target_servings / original_servings
            
            # Get ingredients for this recipe
            recipe_ingredients = [
                (ing_id, ing_data) for ing_id, ing_data in session['ingredients'].items()
                if ing_data['recipe_id'] == recipe_id
            ]
            
            # Sort by ingredient order
            recipe_ingredients.sort(key=lambda x: x[1]['ingredient_order'])
            
            scaled_ingredients = []
            scaling_log = []
            
            for ingredient_id, ingredient_data in recipe_ingredients:
                original_text = ingredient_data.get('ingredient_list_org', '')
                ingredient_name = ingredient_data.get('ingredient_name', '')
                parsed_amount = ingredient_data.get('amount')
                parsed_unit = ingredient_data.get('unit')
                
                # Use parsed data if available, otherwise fall back to text parsing
                scaled_amount_value = None
                if parsed_amount is not None and parsed_unit is not None:
                    # Direct calculation using parsed data
                    scaled_amount_value = float(parsed_amount) * scale_factor
                    scaled_text = f"{scaled_amount_value} {parsed_unit} {ingredient_name}"
                    
                    amount_info = {
                        'found_amount': True,
                        'original_amount': f"{parsed_amount} {parsed_unit}",
                        'scaled_amount': f"{scaled_amount_value} {parsed_unit}",
                        'ingredient_base': ingredient_name,
                        'parsing_method': 'parsed_data'
                    }
                    
                    scaling_log.append(f"{parsed_amount} {parsed_unit} → {scaled_amount_value} {parsed_unit}: {ingredient_name}")
                else:
                    # Fall back to text parsing
                    scaled_text, amount_info = _scale_ingredient_amount(original_text, scale_factor)
                    amount_info['parsing_method'] = 'text_parsing'
                    
                    if amount_info['found_amount']:
                        scaling_log.append(f"{amount_info['original_amount']} → {amount_info['scaled_amount']}: {amount_info['ingredient_base']}")
                
                scaled_ingredients.append({
                    'ingredient_id': ingredient_id,
                    'original_text': original_text,
                    'ingredient_name': ingredient_name,
                    'scaled_text': scaled_text,
                    'scale_factor': scale_factor,
                    'amount_info': amount_info,
                    'parsed_amount': parsed_amount,
                    'parsed_unit': parsed_unit,
                    'scaled_amount': scaled_amount_value
                })
            
            return {
                "success": f"Recipe scaled from {original_servings} to {target_servings} servings",
                "recipe_id": recipe_id,
                "recipe_title": recipe_data.get('title', 'Unknown'),
                "original_servings": original_servings,
                "target_servings": target_servings,
                "scale_factor": round(scale_factor, 3),
                "scaled_ingredients": scaled_ingredients,
                "scaling_summary": scaling_log,
                "ingredients_scaled": len([log for log in scaling_log if log])
            }
                
        except Exception as e:
            return {"error": f"Unexpected error scaling recipe: {e}"}

    @mcp.tool()
    def scale_individual_ingredient(ingredient_input: IngredientScaleInput) -> Dict[str, Any]:
        """
        Scale a specific ingredient amount by a custom multiplication factor.
        
        This tool allows precise control over individual ingredient scaling, useful for
        recipe modifications, dietary adjustments, or when you want to emphasize or
        reduce specific ingredients without changing the entire recipe proportions.
        
        The scaling process:
        - Finds the specified ingredient in the recipe
        - Parses the current amount from the ingredient text
        - Applies the custom scale factor
        - Returns both original and scaled versions
        - Preserves units and ingredient descriptions
        
        Use this tool when:
        - Adjusting salt, spice, or seasoning levels
        - Increasing protein or vegetable content
        - Reducing sugar or fat in specific ingredients
        - Customizing recipes for dietary preferences
        - Fine-tuning ingredient ratios based on taste
        
        Args:
            ingredient_input: Contains session_id, recipe_id, ingredient_name (partial match allowed),
                             and scale_factor (e.g., 2.0 for double, 0.5 for half, 1.5 for 50% more)
            
        Returns:
            Dict with ingredient scaling details including original and scaled amounts,
            scale factor applied, ingredient identification info, and formatted results,
            or error message if ingredient not found or scaling fails
        """
        session_id = ingredient_input.session_id
        recipe_id = ingredient_input.recipe_id
        ingredient_name = ingredient_input.ingredient_name.lower()
        scale_factor = ingredient_input.scale_factor
        
        try:
            from .schema import get_virtual_session_data
            
            # Get virtual session data
            session = get_virtual_session_data(session_id)
            if not session:
                return {"error": f"Virtual session {session_id} not found"}
            
            # Find matching ingredient (case-insensitive partial match)
            matching_ingredients = []
            for ing_id, ing_data in session['ingredients'].items():
                if ing_data['recipe_id'] != recipe_id:
                    continue
                    
                # Check both ingredient_name and ingredient_list_org for matches
                search_text = (ing_data.get('ingredient_name') or ing_data.get('ingredient_list_org', '')).lower()
                if ingredient_name in search_text:
                    matching_ingredients.append((ing_id, ing_data))
            
            if not matching_ingredients:
                return {"error": f"No ingredient matching '{ingredient_name}' found in recipe"}
            
            if len(matching_ingredients) > 1:
                matches = [ing_data.get('ingredient_name') or ing_data.get('ingredient_list_org', '') 
                          for _, ing_data in matching_ingredients]
                return {
                    "error": f"Multiple ingredients match '{ingredient_name}': {matches}",
                    "suggestion": "Use a more specific ingredient name"
                }
            
            ingredient_id, ingredient_data = matching_ingredients[0]
            original_text = ingredient_data.get('ingredient_list_org', '')
            ingredient_name = ingredient_data.get('ingredient_name', '')
            parsed_amount = ingredient_data.get('amount')
            parsed_unit = ingredient_data.get('unit')
            
            # Use parsed data if available, otherwise fall back to text parsing
            if parsed_amount is not None and parsed_unit is not None:
                # Direct calculation using parsed data
                scaled_amount_value = float(parsed_amount) * scale_factor
                scaled_text = f"{scaled_amount_value} {parsed_unit} {ingredient_name}"
                
                amount_info = {
                    'found_amount': True,
                    'original_amount': f"{parsed_amount} {parsed_unit}",
                    'scaled_amount': f"{scaled_amount_value} {parsed_unit}",
                    'ingredient_base': ingredient_name,
                    'parsing_method': 'parsed_data'
                }
            else:
                # Fall back to text parsing
                scaled_text, amount_info = _scale_ingredient_amount(original_text, scale_factor)
                amount_info['parsing_method'] = 'text_parsing'
                scaled_amount_value = None
            
            return {
                "success": f"Ingredient scaled by factor {scale_factor}",
                "ingredient_id": ingredient_id,
                "original_ingredient": original_text,
                "ingredient_name": ingredient_name,
                "scaled_ingredient": scaled_text,
                "scale_factor": scale_factor,
                "amount_details": amount_info,
                "scaling_applied": amount_info['found_amount'],
                "parsed_amount": parsed_amount,
                "parsed_unit": parsed_unit,
                "scaled_amount": scaled_amount_value
            }
                
        except Exception as e:
            return {"error": f"Unexpected error scaling ingredient: {e}"}

    @mcp.tool()
    def scale_multiple_ingredients(bulk_input: BulkIngredientScaleInput) -> Dict[str, Any]:
        """
        Scale multiple ingredients with different factors in a single operation.
        
        This tool enables complex recipe modifications by applying different scaling factors
        to different ingredients simultaneously. Useful for recipe development, dietary
        customization, or creating recipe variations.
        
        The scaling process:
        - Matches each ingredient name to recipe ingredients (partial matching)
        - Applies individual scale factors to each matched ingredient
        - Processes all scalings in a single transaction
        - Reports success and failure for each ingredient
        - Maintains ingredient order and relationships
        
        Use this tool when:
        - Creating low-sodium versions (reduce salt, increase herbs)
        - Adjusting macro ratios (increase protein, reduce carbs)
        - Developing recipe variations with multiple changes
        - Customizing recipes for dietary restrictions
        - Batch processing multiple ingredient adjustments
        
        Args:
            bulk_input: Contains session_id, recipe_id, and ingredient_scales dict mapping
                       ingredient names (partial matches allowed) to scale factors
            
        Returns:
            Dict with bulk scaling results including successful scalings, failed matches,
            summary of changes made, and detailed scaling log for each ingredient,
            or error message if recipe not found or bulk operation fails
        """
        session_id = bulk_input.session_id
        recipe_id = bulk_input.recipe_id
        ingredient_scales = bulk_input.ingredient_scales
        
        try:
            from .schema import get_virtual_session_data
            
            # Get virtual session data
            session = get_virtual_session_data(session_id)
            if not session:
                return {"error": f"Virtual session {session_id} not found"}
                
            # Get all recipe ingredients
            recipe_ingredients = [
                (ing_id, ing_data) for ing_id, ing_data in session['ingredients'].items()
                if ing_data['recipe_id'] == recipe_id
            ]
            
            if not recipe_ingredients:
                return {"error": f"No ingredients found for recipe {recipe_id} in session {session_id}"}
            
            scaling_results = []
            successful_scales = 0
            failed_matches = []
            
            for target_name, scale_factor in ingredient_scales.items():
                # Find matching ingredient
                target_lower = target_name.lower()
                matching_ingredients = []
                
                for ing_id, ing_data in recipe_ingredients:
                    search_text = (ing_data.get('ingredient_name') or ing_data.get('ingredient_list_org', '')).lower()
                    if target_lower in search_text:
                        matching_ingredients.append((ing_id, ing_data))
                
                if not matching_ingredients:
                    failed_matches.append(f"No match found for '{target_name}'")
                    continue
                
                if len(matching_ingredients) > 1:
                    matches = [ing_data.get('ingredient_name') or ing_data.get('ingredient_list_org', '') 
                              for _, ing_data in matching_ingredients]
                    failed_matches.append(f"Multiple matches for '{target_name}': {matches}")
                    continue
                
                # Scale the ingredient
                ingredient_id, ingredient_data = matching_ingredients[0]
                original_text = ingredient_data.get('ingredient_list_org', '')
                ingredient_name = ingredient_data.get('ingredient_name', '')
                parsed_amount = ingredient_data.get('amount')
                parsed_unit = ingredient_data.get('unit')
                
                # Use parsed data if available, otherwise fall back to text parsing
                if parsed_amount is not None and parsed_unit is not None:
                    # Direct calculation using parsed data
                    scaled_amount_value = float(parsed_amount) * scale_factor
                    scaled_text = f"{scaled_amount_value} {parsed_unit} {ingredient_name}"
                    
                    amount_info = {
                        'found_amount': True,
                        'original_amount': f"{parsed_amount} {parsed_unit}",
                        'scaled_amount': f"{scaled_amount_value} {parsed_unit}",
                        'ingredient_base': ingredient_name,
                        'parsing_method': 'parsed_data'
                    }
                else:
                    # Fall back to text parsing
                    scaled_text, amount_info = _scale_ingredient_amount(original_text, scale_factor)
                    amount_info['parsing_method'] = 'text_parsing'
                    scaled_amount_value = None
                
                scaling_results.append({
                    'target_name': target_name,
                    'matched_ingredient': ingredient_name or original_text,
                    'scale_factor': scale_factor,
                    'original_amount': amount_info.get('original_amount', 'N/A'),
                    'scaled_amount': amount_info.get('scaled_amount', 'N/A'),
                    'scaled_ingredient': scaled_text,
                    'amount_found': amount_info['found_amount'],
                    'parsed_amount': parsed_amount,
                    'parsed_unit': parsed_unit,
                    'scaled_amount_value': scaled_amount_value,
                    'parsing_method': amount_info.get('parsing_method', 'unknown')
                })
                
                if amount_info['found_amount']:
                    successful_scales += 1
                
                return {
                    "success": f"Bulk scaling completed: {successful_scales} ingredients scaled successfully",
                    "recipe_id": recipe_id,
                    "total_requested": len(ingredient_scales),
                    "successful_scales": successful_scales,
                    "failed_matches": failed_matches,
                    "scaling_results": scaling_results,
                    "summary": {
                        "processed": len(scaling_results),
                        "with_amounts": successful_scales,
                        "failed_matches": len(failed_matches)
                    }
                }
                
        except sqlite3.Error as e:
            return {"error": f"Database error in bulk scaling: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error in bulk scaling: {e}"}

    @mcp.tool()
    def compare_recipe_servings(comparison_input: RecipeComparisonInput) -> Dict[str, Any]:
        """
        Compare multiple recipes by servings, ingredients, or portion analysis.
        
        This tool analyzes multiple recipes side-by-side to help with meal planning,
        recipe selection, and understanding relative recipe sizes and complexity.
        
REMEMBER! Always share recipe url, and image_url, and title with users before returning full recipe details. This allows them to see the source and context of the recipe.

        Comparison types available:
        - 'servings': Compare serving counts and calculate ratios
        - 'ingredients': Compare ingredient counts and complexity
        - 'portions': Analyze per-portion implications and scaling
        
        Use this tool when:
        - Planning meals with consistent serving sizes
        - Choosing between similar recipes based on yield
        - Understanding recipe complexity before cooking
        - Calculating ingredients needed for meal prep
        - Comparing homemade vs store-bought portions
        
        Args:
            comparison_input: Contains session_id, list of recipe_ids to compare,
                             and comparison_type ('servings', 'ingredients', or 'portions')
            
        Returns:
            Dict with comparative analysis including recipe details, serving ratios,
            ingredient complexity comparison, and recommendations for scaling,
            or error message if recipes not found or comparison fails
        """
        session_id = comparison_input.session_id
        recipe_ids = comparison_input.recipe_ids
        comparison_type = comparison_input.comparison_type
        
        try:
            from .schema import get_virtual_session_data
            
            # Get virtual session data
            session = get_virtual_session_data(session_id)
            if not session:
                return {"error": f"Virtual session {session_id} not found"}
                
            recipe_data = []
            
            for recipe_id in recipe_ids:
                # Get recipe basic info
                if recipe_id not in session['recipes']:
                    return {"error": f"Recipe {recipe_id} not found in session {session_id}"}
                
                recipe_info = session['recipes'][recipe_id]
                
                # Count ingredients for this recipe
                ingredient_count = len([
                    ing for ing in session['ingredients'].values()
                    if ing['recipe_id'] == recipe_id
                ])
                
                recipe_data.append({
                    'recipe_id': recipe_id,
                    'title': recipe_info.get('title', 'Unknown'),
                    'base_servings': recipe_info.get('base_servings') or 1,
                    'ingredient_count': ingredient_count
                })
            
            # Perform comparison based on type
            if comparison_type == 'servings':
                return _compare_servings(recipe_data)
            elif comparison_type == 'ingredients':
                return _compare_ingredients(recipe_data)
            elif comparison_type == 'portions':
                return _compare_portions(recipe_data)
            else:
                return {"error": f"Invalid comparison type: {comparison_type}. Use 'servings', 'ingredients', or 'portions'"}
                
        except Exception as e:
            return {"error": f"Unexpected error in recipe comparison: {e}"}


def _scale_ingredient_amount(ingredient_text: str, scale_factor: float) -> tuple[str, Dict[str, Any]]:
    """
    Helper function to scale ingredient amounts in text with improved parsing priority.
    
    Args:
        ingredient_text: Original ingredient string
        scale_factor: Multiplication factor
        
    Returns:
        Tuple of (scaled_ingredient_text, amount_info_dict)
    """
    # Use the improved parsing function
    parsed_data = _parse_ingredient_comprehensive(ingredient_text)
    
    amount_info = {
        'found_amount': parsed_data['amount'] is not None,
        'original_amount': parsed_data['original_amount_text'],
        'scaled_amount': '',
        'ingredient_base': parsed_data['clean_name']
    }
    
    if parsed_data['amount'] is not None:
        # Scale the amount
        scaled_value = parsed_data['amount'] * scale_factor
        scaled_amount_text = _decimal_to_fraction(scaled_value)
        
        amount_info['scaled_amount'] = scaled_amount_text
        
        # Replace the original amount in the text with the scaled amount
        scaled_text = ingredient_text.replace(parsed_data['original_amount_text'], scaled_amount_text, 1)
    else:
        scaled_text = ingredient_text
        amount_info['scaled_amount'] = ''
    
    return scaled_text, amount_info

def _parse_ingredient_comprehensive(text: str) -> Dict[str, Any]:
    """
    Comprehensive ingredient parsing that handles complex formats correctly.
    Prioritizes main measurements over parenthetical ones.
    
    Args:
        text: Raw ingredient text
        
    Returns:
        Dict with parsed components
    """
    # Check if this is a section header (ends with colon)
    if text.strip().endswith(':'):
        return {
            'amount': None,
            'unit': None,
            'clean_name': text.strip(),
            'original_amount_text': '',
            'parsing_notes': 'Section header'
        }
    
    # Unicode fractions mapping
    unicode_fractions = {
        '½': 0.5, '⅓': 0.333, '⅔': 0.667, '¼': 0.25, '¾': 0.75,
        '⅕': 0.2, '⅖': 0.4, '⅗': 0.6, '⅘': 0.8, '⅙': 0.167,
        '⅚': 0.833, '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875
    }
    
    # Strategy: Try to find the primary amount first, then check parenthetical amounts
    text = text.strip()
    
    # Patterns in order of priority - main measurements before parenthetical ones
    amount_patterns = [
        # Decimal numbers at start (like "250 mL" or "125 mL")
        (r'^(\d+(?:\.\d+)?)\s*', 'decimal'),
        # Mixed numbers with Unicode fractions (like "1½")
        (r'^(\d+)\s*([½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])\s*', 'mixed_unicode'),
        # Regular fractions at start (like "1/2")
        (r'^(\d+)\s*/\s*(\d+)\s*', 'fraction'),
        # Standalone Unicode fractions at start (like "½")
        (r'^([½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])\s*', 'unicode'),
        # Ranges (like "2-3" or "2 to 3")
        (r'^(\d+(?:\.\d+)?)\s*(?:to|\-)\s*(\d+(?:\.\d+)?)\s*', 'range'),
    ]
    
    amount = None
    original_amount_text = ''
    unit = None
    parsing_notes = []
    remaining_text = text
    
    # Try each pattern in priority order
    for pattern, pattern_type in amount_patterns:
        match = re.match(pattern, text)
        if match:
            original_amount_text = match.group(0).strip()
            
            if pattern_type == 'decimal':
                amount = float(match.group(1))
                parsing_notes.append(f"Decimal: {match.group(1)}")
                
            elif pattern_type == 'mixed_unicode':
                whole_part = float(match.group(1))
                fraction_char = match.group(2)
                amount = whole_part + unicode_fractions[fraction_char]
                parsing_notes.append(f"Mixed Unicode: {match.group(1)}{fraction_char}")
                
            elif pattern_type == 'fraction':
                numerator = float(match.group(1))
                denominator = float(match.group(2))
                amount = numerator / denominator
                parsing_notes.append(f"Fraction: {match.group(1)}/{match.group(2)}")
                
            elif pattern_type == 'unicode':
                fraction_char = match.group(1)
                amount = unicode_fractions[fraction_char]
                parsing_notes.append(f"Unicode fraction: {fraction_char}")
                
            elif pattern_type == 'range':
                # For ranges, take the average (could be improved)
                low = float(match.group(1))
                high = float(match.group(2))
                amount = (low + high) / 2
                original_amount_text = f"{match.group(1)}-{match.group(2)}"
                parsing_notes.append(f"Range (using average): {original_amount_text}")
            
            # Remove matched amount from text
            remaining_text = text[match.end():].strip()
            break
    
    # Try to extract unit from remaining text
    if amount is not None:
        # Common units in order of specificity (longer/more specific first)
        units = [
            'package', 'packages', 'pkg', 'tablespoon', 'tablespoons', 'teaspoon', 'teaspoons',
            'can', 'cans', 'jar', 'jars', 'bottle', 'bottles',
            'bunch', 'bunches', 'head', 'heads', 'clove', 'cloves', 'piece', 'pieces',
            'slice', 'slices', 'strip', 'strips', 'sprig', 'sprigs',
            'kilogram', 'kilograms', 'pound', 'pounds', 'ounce', 'ounces',
            'liter', 'liters', 'gram', 'grams', 'tbsp', 'tsp', 'cup', 'cups',
            'kg', 'lb', 'lbs', 'oz', 'mL', 'ml', 'g', 'L'
        ]
        
        # Only treat as unit if it's followed by a space or end of string to avoid "large" matching "L"
        for unit_option in units:
            pattern = rf'\b{re.escape(unit_option.lower())}\b'
            if re.match(pattern, remaining_text.lower()):
                unit = unit_option
                remaining_text = remaining_text[len(unit_option):].strip()
                parsing_notes.append(f"Unit: {unit}")
                break
    
    # Clean up remaining text (remove parenthetical info if needed, extra whitespace)
    clean_name = re.sub(r'\([^)]*\)', '', remaining_text).strip()
    clean_name = re.sub(r'\s+', ' ', clean_name)
    
    return {
        'amount': amount,
        'unit': unit,
        'clean_name': clean_name,
        'original_amount_text': original_amount_text,
        'parsing_notes': '; '.join(parsing_notes) if parsing_notes else 'No amount found'
    }

def _decimal_to_fraction(decimal_value: float) -> str:
    """Convert decimal to common fraction representation, preferring Unicode fractions."""
    # Unicode fractions for better display
    unicode_fractions = {
        0.125: "⅛", 0.25: "¼", 0.333: "⅓", 0.375: "⅜",
        0.5: "½", 0.625: "⅝", 0.667: "⅔", 0.75: "¾", 0.875: "⅞"
    }
    
    # Regular fractions as fallback
    regular_fractions = {
        0.125: "1/8", 0.25: "1/4", 0.33: "1/3", 0.375: "3/8",
        0.5: "1/2", 0.625: "5/8", 0.67: "2/3", 0.75: "3/4", 0.875: "7/8"
    }
    
    # Check if close to a Unicode fraction first
    for frac_decimal, frac_unicode in unicode_fractions.items():
        if abs(decimal_value - frac_decimal) < 0.05:
            return frac_unicode
    
    # Check if close to a regular fraction
    for frac_decimal, frac_str in regular_fractions.items():
        if abs(decimal_value - frac_decimal) < 0.05:
            return frac_str
    
    # Check if close to a whole number + fraction
    whole_part = int(decimal_value)
    fractional_part = decimal_value - whole_part
    
    for frac_decimal, frac_unicode in unicode_fractions.items():
        if abs(fractional_part - frac_decimal) < 0.05:
            if whole_part > 0:
                return f"{whole_part}{frac_unicode}"
            else:
                return frac_unicode
    
    for frac_decimal, frac_str in regular_fractions.items():
        if abs(fractional_part - frac_decimal) < 0.05:
            if whole_part > 0:
                return f"{whole_part} {frac_str}"
            else:
                return frac_str
    
    # Fall back to decimal
    return _format_number(decimal_value)

def _format_number(value: float) -> str:
    """Format number for display, removing unnecessary decimals."""
    if value == int(value):
        return str(int(value))
    else:
        return f"{value:.2f}".rstrip('0').rstrip('.')

def _compare_servings(recipe_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare recipes by serving sizes."""
    max_servings = max(recipe['base_servings'] for recipe in recipe_data)
    min_servings = min(recipe['base_servings'] for recipe in recipe_data)
    
    comparison_results = []
    for recipe in recipe_data:
        servings = recipe['base_servings']
        comparison_results.append({
            'recipe_id': recipe['recipe_id'],
            'title': recipe['title'],
            'servings': servings,
            'ratio_to_largest': round(servings / max_servings, 2),
            'ratio_to_smallest': round(servings / min_servings, 2),
            'scale_to_match_largest': round(max_servings / servings, 2)
        })
    
    return {
        "comparison_type": "servings",
        "recipes_compared": len(recipe_data),
        "serving_range": {"min": min_servings, "max": max_servings},
        "comparison_results": comparison_results,
        "recommendations": {
            "largest_recipe": max(recipe_data, key=lambda x: x['base_servings'])['title'],
            "smallest_recipe": min(recipe_data, key=lambda x: x['base_servings'])['title'],
            "average_servings": round(sum(r['base_servings'] for r in recipe_data) / len(recipe_data), 1)
        }
    }

def _compare_ingredients(recipe_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare recipes by ingredient complexity."""
    max_ingredients = max(recipe['ingredient_count'] for recipe in recipe_data)
    min_ingredients = min(recipe['ingredient_count'] for recipe in recipe_data)
    
    comparison_results = []
    for recipe in recipe_data:
        ingredient_count = recipe['ingredient_count']
        complexity = "Simple" if ingredient_count <= 5 else "Moderate" if ingredient_count <= 10 else "Complex"
        
        comparison_results.append({
            'recipe_id': recipe['recipe_id'],
            'title': recipe['title'],
            'ingredient_count': ingredient_count,
            'complexity_level': complexity,
            'ingredients_per_serving': round(ingredient_count / recipe['base_servings'], 1)
        })
    
    return {
        "comparison_type": "ingredients",
        "recipes_compared": len(recipe_data),
        "ingredient_range": {"min": min_ingredients, "max": max_ingredients},
        "comparison_results": comparison_results,
        "complexity_summary": {
            "most_complex": max(recipe_data, key=lambda x: x['ingredient_count'])['title'],
            "simplest": min(recipe_data, key=lambda x: x['ingredient_count'])['title'],
            "average_ingredients": round(sum(r['ingredient_count'] for r in recipe_data) / len(recipe_data), 1)
        }
    }

def _compare_portions(recipe_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare recipes by portion analysis."""
    comparison_results = []
    
    for recipe in recipe_data:
        servings = recipe['base_servings']
        ingredient_count = recipe['ingredient_count']
        
        comparison_results.append({
            'recipe_id': recipe['recipe_id'],
            'title': recipe['title'],
            'servings': servings,
            'ingredient_count': ingredient_count,
            'ingredients_per_serving': round(ingredient_count / servings, 1),
            'portion_complexity': "Light" if ingredient_count / servings < 1.5 else "Balanced" if ingredient_count / servings < 2.5 else "Rich"
        })
    
    return {
        "comparison_type": "portions",
        "recipes_compared": len(recipe_data),
        "comparison_results": comparison_results,
        "portion_analysis": {
            "lightest_portions": min(comparison_results, key=lambda x: x['ingredients_per_serving'])['title'],
            "richest_portions": max(comparison_results, key=lambda x: x['ingredients_per_serving'])['title'],
            "average_ingredients_per_serving": round(sum(r['ingredients_per_serving'] for r in comparison_results) / len(comparison_results), 1)
        }
    }

def _is_safe_expression(expression: str) -> bool:
    """
    Check if a mathematical expression is safe to evaluate.
    
    Args:
        expression: Mathematical expression string
        
    Returns:
        True if expression is safe, False otherwise
    """
    # List of allowed characters and patterns
    allowed_chars = set('0123456789+-*/.()%** abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_')
    
    # Check if expression only contains allowed characters
    if not all(c in allowed_chars for c in expression):
        return False
    
    # Check for dangerous keywords/functions
    dangerous_keywords = [
        'import', 'exec', 'eval', 'open', 'file', 'input', 'raw_input',
        'compile', '__', 'getattr', 'setattr', 'delattr', 'globals', 'locals',
        'vars', 'dir', 'help', 'exit', 'quit', 'reload', 'execfile'
    ]
    
    expression_lower = expression.lower()
    for keyword in dangerous_keywords:
        if keyword in expression_lower:
            return False
    
    return True

def _calculate_single_expression(expression: str, variables: Dict[str, float]) -> Dict[str, Any]:
    """
    Core calculation logic extracted for reuse by both single and bulk calculators.
    
    Args:
        expression: Mathematical expression string
        variables: Dictionary of variable names and values
        
    Returns:
        Dictionary with calculation result and details
    """
    try:
        # Validate expression - only allow safe mathematical operations
        if not _is_safe_expression(expression):
            return {
                "status": "error",
                "error": "Expression contains unsafe operations. Only basic math operations are allowed.",
                "expression": expression
            }
        
        # Replace variables in expression
        substituted_expression = expression
        for var_name, var_value in variables.items():
            # Use word boundaries to avoid partial replacements
            substituted_expression = re.sub(rf'\b{re.escape(var_name)}\b', str(var_value), substituted_expression)
        
        # Check if all variables were substituted
        remaining_vars = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', substituted_expression)
        if remaining_vars:
            return {
                "status": "error", 
                "error": f"Undefined variables in expression: {remaining_vars}",
                "expression": expression,
                "variables_provided": list(variables.keys())
            }
        
        # Evaluate the expression safely
        result = _safe_eval(substituted_expression)
        
        return {
            "status": "success",
            "result": round(result, 6),
            "expression": expression,
            "substituted_expression": substituted_expression,
            "variables_used": variables,
            "calculation_steps": {
                "original": expression,
                "substituted": substituted_expression,
                "result": result
            }
        }
        
    except ZeroDivisionError:
        return {
            "status": "error",
            "error": "Division by zero",
            "expression": expression
        }
    except ValueError as e:
        return {
            "status": "error",
            "error": f"Invalid mathematical expression: {e}",
            "expression": expression
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Calculation failed: {e}",
            "expression": expression
        }

def _safe_eval(expression: str) -> float:
    """
    Safely evaluate a mathematical expression using ast.
    
    Args:
        expression: Mathematical expression string (should be pre-validated)
        
    Returns:
        Result of the mathematical expression
        
    Raises:
        ValueError: If expression is invalid
    """
    # Allowed operators and functions
    allowed_operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub, 
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    def eval_node(node):
        if isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        elif isinstance(node, ast.Num):  # Python < 3.8
            return node.n
        elif isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)
            op = allowed_operators.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operation: {type(node.op)}")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = eval_node(node.operand)
            op = allowed_operators.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported unary operation: {type(node.op)}")
            return op(operand)
        else:
            raise ValueError(f"Unsupported node type: {type(node)}")
    
    try:
        # Parse the expression into an AST
        tree = ast.parse(expression, mode='eval')
        
        # Evaluate the AST safely
        result = eval_node(tree.body)
        
        return float(result)
        
    except (SyntaxError, ValueError) as e:
        raise ValueError(f"Invalid expression: {e}")
    except ZeroDivisionError:
        raise ZeroDivisionError("Division by zero")
    except Exception as e:
        raise ValueError(f"Evaluation error: {e}")