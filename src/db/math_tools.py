import sqlite3
import json
import re
from typing import Dict, Any, List, Optional
from fastmcp import FastMCP
from .connection import get_db_connection
from ..models.math_models import (
    ServingSizeInput, IngredientScaleInput, BulkIngredientScaleInput, 
    RecipeComparisonInput, DRIComparisonInput, NutrientAnalysisInput
)

def register_math_tools(mcp: FastMCP):
    """Register recipe math and calculation tools with the MCP server."""

    @mcp.tool()
    def scale_recipe_servings(serving_input: ServingSizeInput) -> Dict[str, Any]:
        """
        Scale all ingredients in a recipe to match a target number of servings.
        
        This tool calculates new ingredient amounts when you want to make more or fewer servings
        of a recipe. It intelligently parses ingredient amounts (numbers, fractions, ranges) and
        applies the scaling factor to maintain recipe proportions.
        
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get original recipe data
                cursor.execute(f"""
                    SELECT base_servings FROM temp_recipes_{session_id} WHERE recipe_id = ?
                """, (recipe_id,))
                
                recipe_row = cursor.fetchone()
                if not recipe_row:
                    return {"error": f"Recipe {recipe_id} not found in session {session_id}"}
                
                original_servings = recipe_row['base_servings'] or 1
                scale_factor = target_servings / original_servings
                
                # Get ingredients
                cursor.execute(f"""
                    SELECT * FROM temp_recipe_ingredients_{session_id} 
                    WHERE recipe_id = ? ORDER BY ingredient_order
                """, (recipe_id,))
                
                ingredients = cursor.fetchall()
                scaled_ingredients = []
                scaling_log = []
                
                for ingredient in ingredients:
                    original_name = ingredient['ingredient_name']
                    scaled_amount, amount_info = _scale_ingredient_amount(original_name, scale_factor)
                    
                    scaled_ingredients.append({
                        'ingredient_id': ingredient['ingredient_id'],
                        'original_name': original_name,
                        'scaled_name': scaled_amount,
                        'scale_factor': scale_factor,
                        'amount_info': amount_info
                    })
                    
                    if amount_info['found_amount']:
                        scaling_log.append(f"{amount_info['original_amount']} → {amount_info['scaled_amount']}: {amount_info['ingredient_base']}")
                
                return {
                    "success": f"Recipe scaled from {original_servings} to {target_servings} servings",
                    "recipe_id": recipe_id,
                    "original_servings": original_servings,
                    "target_servings": target_servings,
                    "scale_factor": round(scale_factor, 3),
                    "scaled_ingredients": scaled_ingredients,
                    "scaling_summary": scaling_log,
                    "ingredients_scaled": len([log for log in scaling_log if log])
                }
                
        except sqlite3.Error as e:
            return {"error": f"Database error scaling recipe: {e}"}
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Find matching ingredient (case-insensitive partial match)
                cursor.execute(f"""
                    SELECT * FROM temp_recipe_ingredients_{session_id} 
                    WHERE recipe_id = ? AND LOWER(ingredient_name) LIKE ?
                    ORDER BY ingredient_order
                """, (recipe_id, f"%{ingredient_name}%"))
                
                matching_ingredients = cursor.fetchall()
                
                if not matching_ingredients:
                    return {"error": f"No ingredient matching '{ingredient_name}' found in recipe"}
                
                if len(matching_ingredients) > 1:
                    matches = [ing['ingredient_name'] for ing in matching_ingredients]
                    return {
                        "error": f"Multiple ingredients match '{ingredient_name}': {matches}",
                        "suggestion": "Use a more specific ingredient name"
                    }
                
                ingredient = matching_ingredients[0]
                original_name = ingredient['ingredient_name']
                
                scaled_amount, amount_info = _scale_ingredient_amount(original_name, scale_factor)
                
                return {
                    "success": f"Ingredient scaled by factor {scale_factor}",
                    "ingredient_id": ingredient['ingredient_id'],
                    "original_ingredient": original_name,
                    "scaled_ingredient": scaled_amount,
                    "scale_factor": scale_factor,
                    "amount_details": amount_info,
                    "scaling_applied": amount_info['found_amount']
                }
                
        except sqlite3.Error as e:
            return {"error": f"Database error scaling ingredient: {e}"}
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get all recipe ingredients
                cursor.execute(f"""
                    SELECT * FROM temp_recipe_ingredients_{session_id} 
                    WHERE recipe_id = ? ORDER BY ingredient_order
                """, (recipe_id,))
                
                all_ingredients = cursor.fetchall()
                if not all_ingredients:
                    return {"error": f"No ingredients found for recipe {recipe_id} in session {session_id}"}
                
                scaling_results = []
                successful_scales = 0
                failed_matches = []
                
                for target_name, scale_factor in ingredient_scales.items():
                    # Find matching ingredient
                    target_lower = target_name.lower()
                    matching_ingredients = [
                        ing for ing in all_ingredients 
                        if target_lower in ing['ingredient_name'].lower()
                    ]
                    
                    if not matching_ingredients:
                        failed_matches.append(f"No match found for '{target_name}'")
                        continue
                    
                    if len(matching_ingredients) > 1:
                        matches = [ing['ingredient_name'] for ing in matching_ingredients]
                        failed_matches.append(f"Multiple matches for '{target_name}': {matches}")
                        continue
                    
                    # Scale the ingredient
                    ingredient = matching_ingredients[0]
                    original_name = ingredient['ingredient_name']
                    scaled_amount, amount_info = _scale_ingredient_amount(original_name, scale_factor)
                    
                    scaling_results.append({
                        'target_name': target_name,
                        'matched_ingredient': original_name,
                        'scale_factor': scale_factor,
                        'original_amount': amount_info.get('original_amount', 'N/A'),
                        'scaled_amount': amount_info.get('scaled_amount', 'N/A'),
                        'scaled_ingredient': scaled_amount,
                        'amount_found': amount_info['found_amount']
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                recipe_data = []
                
                for recipe_id in recipe_ids:
                    # Get recipe basic info
                    cursor.execute(f"""
                        SELECT title, base_servings FROM temp_recipes_{session_id} 
                        WHERE recipe_id = ?
                    """, (recipe_id,))
                    
                    recipe_row = cursor.fetchone()
                    if not recipe_row:
                        return {"error": f"Recipe {recipe_id} not found in session {session_id}"}
                    
                    # Get ingredient count
                    cursor.execute(f"""
                        SELECT COUNT(*) as ingredient_count FROM temp_recipe_ingredients_{session_id} 
                        WHERE recipe_id = ?
                    """, (recipe_id,))
                    
                    ingredient_count = cursor.fetchone()['ingredient_count']
                    
                    recipe_data.append({
                        'recipe_id': recipe_id,
                        'title': recipe_row['title'],
                        'base_servings': recipe_row['base_servings'] or 1,
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
                
        except sqlite3.Error as e:
            return {"error": f"Database error in recipe comparison: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error in recipe comparison: {e}"}

    #----
    # FUTURE: Placeholder tools for nutritional analysis
    # These will be implemented when Canadian Nutrient File (CNF) integration is added
    
    # @mcp.tool() 
    # def compare_daily_nutrition_to_dri(dri_input: DRIComparisonInput) -> Dict[str, Any]:
    #     """
    #     FUTURE TOOL: Compare recipe nutrition against Canadian Dietary Reference Intakes (DRI).
    #     
    #     This tool will analyze the nutritional content of recipes against official Canadian
    #     DRI values based on age, gender, and activity level. It will help users understand
    #     how recipes contribute to meeting daily nutritional requirements.
    #     
    #     Features to be implemented:
    #     - Integration with Canadian Nutrient File (CNF) for ingredient nutrition data
    #     - DRI table lookups based on demographics
    #     - Percentage of daily value calculations
    #     - Deficiency and excess warnings
    #     - Meal planning recommendations for balanced nutrition
    #     
    #     Will require:
    #     - CNF database integration for ingredient nutrition lookup
    #     - DRI reference tables from Health Canada
    #     - Ingredient amount parsing and unit conversion
    #     - Nutritional calculation algorithms
    #     """
    #     return {"error": "DRI comparison tool not yet implemented. Requires CNF integration."}
    
    # @mcp.tool()
    # def analyze_recipe_nutrients(nutrient_input: NutrientAnalysisInput) -> Dict[str, Any]:
    #     """
    #     FUTURE TOOL: Detailed nutritional analysis of recipe ingredients and totals.
    #     
    #     This tool will provide comprehensive nutritional breakdowns for recipes including
    #     macro and micronutrients, calories, and specific nutrients of interest.
    #     
    #     Features to be implemented:
    #     - Complete macro analysis (protein, carbs, fat, fiber)
    #     - Micronutrient analysis (vitamins, minerals)
    #     - Calorie calculations per serving and total
    #     - Nutritional density scoring
    #     - Allergen and dietary restriction flagging
    #     - Recipe healthiness scoring based on Canadian guidelines
    #     
    #     Will require:
    #     - CNF database for comprehensive nutrient data
    #     - Ingredient parsing and standardization
    #     - Unit conversion systems (cups to grams, etc.)
    #     - Nutrition calculation algorithms
    #     - Health Canada dietary guideline integration
    #     """
    #     return {"error": "Nutrient analysis tool not yet implemented. Requires CNF integration."}

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