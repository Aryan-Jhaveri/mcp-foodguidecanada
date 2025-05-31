import re
import json
import sqlite3
from typing import Dict, Any, Optional, Tuple
from fastmcp import FastMCP
from .connection import get_db_connection
from ..models.db_models import RecipeQueryInput

def register_ingredient_tools(mcp: FastMCP):
    """Register ingredient parsing and management tools with the MCP server."""

    @mcp.tool()
    def parse_and_update_ingredients(query_input: RecipeQueryInput) -> Dict[str, Any]:
        """
        Parse ingredients text to extract amounts, units, and ingredient names, then update the database.
        
        This tool analyzes ingredient text strings and extracts structured data including:
        - Numeric amounts (whole numbers, decimals, fractions, Unicode fractions)
        - Units of measurement (mL, cups, tsp, tbsp, kg, etc.)
        - Clean ingredient names without amounts/units
        - Ingredient categories (section headers like "Quick pickle:")
        
        Use this tool to:
        - Improve recipe scaling accuracy by having structured ingredient data
        - Enable better ingredient analysis and substitution suggestions
        - Prepare ingredient data for nutritional analysis (future CNF integration)
        - Clean up ingredient lists for better display and searching
        
        The parsing handles:
        - Unicode fractions (½, ⅓, ¼, ¾, etc.)
        - Mixed numbers (1½, 2¼)
        - Regular fractions (1/2, 3/4)
        - Metric and imperial units
        - Parenthetical unit conversions "(1 cup)"
        - Ingredient preparation notes ("sliced", "chopped", "optional")
        
        Args:
            query_input: Contains session_id (required) and optional recipe_id (if omitted, 
                        processes all recipes in the session)
            
        Returns:
            Dict with parsing results including total ingredients processed, successfully parsed
            amounts, failed parses, and detailed parsing information for each ingredient
        """
        session_id = query_input.session_id
        recipe_id = query_input.recipe_id
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Check if session exists
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (f"temp_recipe_ingredients_{session_id}",))
                
                if not cursor.fetchone():
                    return {"error": f"Session {session_id} not found"}
                
                # Get ingredients to process
                if recipe_id:
                    cursor.execute(f"""
                        SELECT * FROM temp_recipe_ingredients_{session_id}
                        WHERE recipe_id = ?
                        ORDER BY ingredient_order
                    """, (recipe_id,))
                else:
                    cursor.execute(f"""
                        SELECT * FROM temp_recipe_ingredients_{session_id}
                        ORDER BY recipe_id, ingredient_order
                    """, ())
                
                ingredients = cursor.fetchall()
                if not ingredients:
                    return {"error": f"No ingredients found for parsing"}
                
                parsing_results = []
                updated_count = 0
                failed_count = 0
                
                for ingredient in ingredients:
                    ingredient_text = ingredient['ingredient_name']
                    parsed_data = _parse_ingredient_text(ingredient_text)
                    
                    # Update database with parsed data
                    cursor.execute(f"""
                        UPDATE temp_recipe_ingredients_{session_id}
                        SET amount = ?, unit = ?
                        WHERE ingredient_id = ?
                    """, (
                        parsed_data['amount'], 
                        parsed_data['unit'],
                        ingredient['ingredient_id']
                    ))
                    
                    parsing_results.append({
                        'ingredient_id': ingredient['ingredient_id'],
                        'original_text': ingredient_text,
                        'parsed_amount': parsed_data['amount'],
                        'parsed_unit': parsed_data['unit'],
                        'clean_name': parsed_data['clean_name'],
                        'is_section_header': parsed_data['is_section_header'],
                        'parsing_notes': parsed_data['parsing_notes']
                    })
                    
                    if parsed_data['amount'] is not None:
                        updated_count += 1
                    else:
                        failed_count += 1
                
                conn.commit()
                
                return {
                    "success": f"Processed {len(ingredients)} ingredients",
                    "session_id": session_id,
                    "total_ingredients": len(ingredients),
                    "successfully_parsed": updated_count,
                    "failed_to_parse": failed_count,
                    "parsing_details": parsing_results,
                    "summary": {
                        "ingredients_with_amounts": updated_count,
                        "section_headers": len([r for r in parsing_results if r['is_section_header']]),
                        "parse_success_rate": f"{(updated_count/len(ingredients)*100):.1f}%"
                    }
                }
                
        except sqlite3.Error as e:
            return {"error": f"Database error parsing ingredients: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error parsing ingredients: {e}"}

    @mcp.tool()
    def get_structured_ingredients(query_input: RecipeQueryInput) -> Dict[str, Any]:
        """
        Retrieve ingredients with parsed amounts, units, and clean names.
        
        This tool returns ingredient data in a structured format after parsing, making it
        easy to work with individual components for scaling, substitution, or analysis.
        
        Use this tool to:
        - Get ingredient data ready for precise scaling calculations
        - Analyze ingredient amounts and units across recipes
        - Prepare data for nutritional analysis or shopping lists
        - Review parsing quality and make manual corrections if needed
        
        Args:
            query_input: Contains session_id (required) and optional recipe_id
            
        Returns:
            Dict with structured ingredient data including amounts, units, clean names,
            and parsing metadata for each ingredient
        """
        session_id = query_input.session_id
        recipe_id = query_input.recipe_id
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get ingredients with parsed data
                if recipe_id:
                    cursor.execute(f"""
                        SELECT * FROM temp_recipe_ingredients_{session_id}
                        WHERE recipe_id = ?
                        ORDER BY ingredient_order
                    """, (recipe_id,))
                else:
                    cursor.execute(f"""
                        SELECT ri.*, r.title as recipe_title
                        FROM temp_recipe_ingredients_{session_id} ri
                        JOIN temp_recipes_{session_id} r ON ri.recipe_id = r.recipe_id
                        ORDER BY r.title, ri.ingredient_order
                    """, ())
                
                ingredients = cursor.fetchall()
                if not ingredients:
                    return {"error": f"No ingredients found in session {session_id}"}
                
                structured_ingredients = []
                for ingredient in ingredients:
                    structured_ingredients.append({
                        'ingredient_id': ingredient['ingredient_id'],
                        'recipe_id': ingredient['recipe_id'],
                        'recipe_title': ingredient.get('recipe_title', 'Unknown'),
                        'original_text': ingredient['ingredient_name'],
                        'amount': ingredient['amount'],
                        'unit': ingredient['unit'],
                        'clean_name': _extract_clean_name(ingredient['ingredient_name']),
                        'ingredient_order': ingredient['ingredient_order'],
                        'has_amount': ingredient['amount'] is not None,
                        'is_scalable': ingredient['amount'] is not None and ingredient['amount'] > 0
                    })
                
                return {
                    "session_id": session_id,
                    "ingredients": structured_ingredients,
                    "summary": {
                        "total_ingredients": len(structured_ingredients),
                        "with_amounts": len([i for i in structured_ingredients if i['has_amount']]),
                        "scalable": len([i for i in structured_ingredients if i['is_scalable']]),
                        "section_headers": len([i for i in structured_ingredients if not i['has_amount'] and ':' in i['original_text']])
                    }
                }
                
        except sqlite3.Error as e:
            return {"error": f"Database error retrieving ingredients: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error retrieving ingredients: {e}"}

def _parse_ingredient_text(text: str) -> Dict[str, Any]:
    """
    Parse ingredient text to extract amount, unit, and clean name.
    Uses the improved comprehensive parsing logic.
    
    Args:
        text: Raw ingredient text
        
    Returns:
        Dict with parsed components
    """
    # Import the improved parsing function
    from .math_tools import _parse_ingredient_comprehensive
    
    # Use the comprehensive parser
    result = _parse_ingredient_comprehensive(text)
    
    # Convert to the expected format for ingredient parser
    return {
        'amount': result['amount'],
        'unit': result['unit'],
        'clean_name': result['clean_name'],
        'is_section_header': text.strip().endswith(':'),
        'parsing_notes': result['parsing_notes']
    }

def _extract_clean_name(text: str) -> str:
    """Extract just the ingredient name without amounts or units."""
    parsed = _parse_ingredient_text(text)
    return parsed['clean_name']