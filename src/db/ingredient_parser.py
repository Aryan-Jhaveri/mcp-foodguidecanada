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
        Parse ingredients text from ingredient_list_org to extract amounts, units, and ingredient names, then update virtual session data.
        
        ⚠️ IMPORTANT: This tool reads from the 'ingredient_list_org' column which contains the original ingredient text,
        and populates the separate 'ingredient_name', 'amount', and 'unit' columns. Always run this tool after 
        storing recipes in a session to enable accurate serving size calculations.
        
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
            from .schema import get_virtual_session_data
            
            # Get virtual session data
            session = get_virtual_session_data(session_id)
            if not session:
                return {"error": f"Virtual session {session_id} not found"}
            
            # Get ingredients to process
            ingredients_to_process = []
            for ingredient_id, ingredient_data in session['ingredients'].items():
                if recipe_id and ingredient_data['recipe_id'] != recipe_id:
                    continue
                ingredients_to_process.append((ingredient_id, ingredient_data))
            
            if not ingredients_to_process:
                return {"error": f"No ingredients found for parsing"}
            
            parsing_results = []
            updated_count = 0
            failed_count = 0
            
            for ingredient_id, ingredient_data in ingredients_to_process:
                # Parse from ingredient_list_org
                ingredient_text = ingredient_data.get('ingredient_list_org', '')
                if not ingredient_text:
                    failed_count += 1
                    continue
                    
                parsed_data = _parse_ingredient_text(ingredient_text)
                
                # Update virtual session data with parsed components
                ingredient_data['ingredient_name'] = parsed_data['clean_name']
                ingredient_data['amount'] = parsed_data['amount']
                ingredient_data['unit'] = parsed_data['unit']
                
                parsing_results.append({
                    'ingredient_id': ingredient_id,
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
            
            return {
                "success": f"Processed {len(ingredients_to_process)} ingredients in virtual session",
                "session_id": session_id,
                "total_ingredients": len(ingredients_to_process),
                "successfully_parsed": updated_count,
                "failed_to_parse": failed_count,
                "parsing_details": parsing_results,
                "summary": {
                    "ingredients_with_amounts": updated_count,
                    "section_headers": len([r for r in parsing_results if r['is_section_header']]),
                    "parse_success_rate": f"{(updated_count/len(ingredients_to_process)*100):.1f}%"
                }
            }
                
        except Exception as e:
            return {"error": f"Unexpected error parsing ingredients: {e}"}

    @mcp.tool()
    def get_structured_ingredients(query_input: RecipeQueryInput) -> Dict[str, Any]:
        """
        Retrieve ingredients with parsed amounts, units, and clean names from virtual session storage.
        
        This tool returns ingredient data in a structured format after parsing, making it
        easy to work with individual components for scaling, substitution, or analysis.
        Shows both the original ingredient_list_org text and the parsed components.
        
        Use this tool to:
        - Get ingredient data ready for precise scaling calculations
        - Analyze ingredient amounts and units across recipes
        - Prepare data for nutritional analysis or shopping lists
        - Review parsing quality and make manual corrections if needed
        - See both original and parsed ingredient information
        
        Args:
            query_input: Contains session_id (required) and optional recipe_id
            
        Returns:
            Dict with structured ingredient data including amounts, units, clean names,
            and parsing metadata for each ingredient
        """
        session_id = query_input.session_id
        recipe_id = query_input.recipe_id
        
        try:
            from .schema import get_virtual_session_data
            
            # Get virtual session data
            session = get_virtual_session_data(session_id)
            if not session:
                return {"error": f"Virtual session {session_id} not found"}
            
            structured_ingredients = []
            
            # Get recipe titles for context
            recipe_titles = {rid: rdata['title'] for rid, rdata in session['recipes'].items()}
            
            for ingredient_id, ingredient_data in session['ingredients'].items():
                if recipe_id and ingredient_data['recipe_id'] != recipe_id:
                    continue
                    
                structured_ingredients.append({
                    'ingredient_id': ingredient_id,
                    'recipe_id': ingredient_data['recipe_id'],
                    'recipe_title': recipe_titles.get(ingredient_data['recipe_id'], 'Unknown'),
                    'original_text': ingredient_data.get('ingredient_list_org', ''),
                    'parsed_ingredient_name': ingredient_data.get('ingredient_name'),
                    'amount': ingredient_data.get('amount'),
                    'unit': ingredient_data.get('unit'),
                    'ingredient_order': ingredient_data['ingredient_order'],
                    'has_amount': ingredient_data.get('amount') is not None,
                    'is_scalable': ingredient_data.get('amount') is not None and float(ingredient_data.get('amount', 0)) > 0
                })
            
            # Sort by recipe and ingredient order
            structured_ingredients.sort(key=lambda x: (x['recipe_title'], x['ingredient_order']))
            
            if not structured_ingredients:
                return {"error": f"No ingredients found in virtual session {session_id}"}
            
            return {
                "session_id": session_id,
                "ingredients": structured_ingredients,
                "summary": {
                    "total_ingredients": len(structured_ingredients),
                    "with_amounts": len([i for i in structured_ingredients if i['has_amount']]),
                    "scalable": len([i for i in structured_ingredients if i['is_scalable']]),
                    "section_headers": len([i for i in structured_ingredients if not i['has_amount'] and ':' in i['original_text']]),
                    "parsed_ingredients": len([i for i in structured_ingredients if i['parsed_ingredient_name']])
                }
            }
                
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