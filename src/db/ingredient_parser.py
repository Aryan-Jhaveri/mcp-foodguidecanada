import re
import json
import sqlite3
import os
import sys
from typing import Dict, Any, Optional, Tuple
from fastmcp import FastMCP
from .connection import get_db_connection

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
    from src.models.db_models import RecipeQueryInput
except ImportError:
    try:
        from models.db_models import RecipeQueryInput
    except ImportError as e:
        print(f"Error importing db_models: {e}", file=sys.stderr)
        # This will cause issues but we can't easily fallback for Pydantic models
        RecipeQueryInput = None

def register_ingredient_tools(mcp: FastMCP):
    """Register ingredient parsing and management tools with the MCP server."""

    @mcp.tool()
    def parse_and_update_ingredients(query_input: RecipeQueryInput) -> Dict[str, Any]:
        """
        Parse ingredients text to extract amounts, units, and ingredient names - RUN ONCE PER RECIPE.
        
        **⚡ EFFICIENCY GUIDELINES:**
        - ✅ **RUN ONCE**: Parse all ingredients for a recipe in a single call
        - ❌ **AVOID**: Running this multiple times for the same recipe
        - ✅ **FIRST STEP**: Always run this immediately after storing a recipe
        - ❌ **AVOID**: Manual ingredient parsing - let this tool handle it
        
        **🔧 WHAT THIS TOOL DOES:**
        Converts messy ingredient text like "15 mL liquid honey" into structured data:
        - `amount`: 15.0
        - `unit`: "mL"
        - `ingredient_name`: "liquid honey"
        
        **📊 PARSING CAPABILITIES:**
        - Unicode fractions (½, ⅓, ¼, ¾, etc.) → decimal values
        - Mixed numbers (1½, 2¼) → accurate decimal conversion
        - All measurement units (mL, cups, tsp, tbsp, kg, etc.)
        - Ingredient preparation notes ("sliced", "chopped", "optional")
        
        **🎯 RECOMMENDED WORKFLOW:**
        ```
        1. store_recipe_in_session() ← Store raw recipe data
        2. parse_and_update_ingredients() ← YOU ARE HERE (run once!)
        3. search_cnf_foods() for each ingredient ← Find nutrition data
        4. execute_nutrition_sql() ← Link and calculate
        ```
        
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
                
                # Update virtual session data with parsed components (legacy format)
                ingredient_data['ingredient_name'] = parsed_data['clean_name']
                ingredient_data['amount'] = parsed_data['amount']
                ingredient_data['unit'] = parsed_data['unit']
                
                # UPDATE SQL table structure as well
                if 'recipe_ingredients' in session:
                    # Find and update the corresponding SQL table entry
                    for sql_ingredient in session['recipe_ingredients']:
                        if sql_ingredient['ingredient_id'] == ingredient_id:
                            sql_ingredient['ingredient_name'] = parsed_data['clean_name']
                            sql_ingredient['amount'] = parsed_data['amount']
                            sql_ingredient['unit'] = parsed_data['unit']
                            break
                
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

def parse_ingredients_for_temp_tables(session_id: str, recipe_id: str) -> Dict[str, Any]:
    """
    Parse ingredients and update them in temporary persistent storage tables.
    
    This function parses ingredient text from temp_recipe_ingredients table
    and updates the ingredient_name, amount, and unit fields directly in SQLite.
    
    Args:
        session_id: Session identifier
        recipe_id: Recipe identifier
        
    Returns:
        Dict with parsing results and success status
    """
    try:
        parsed_count = 0
        failed_count = 0
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get ingredients from temp storage
            cursor.execute("""
                SELECT ingredient_id, ingredient_list_org 
                FROM temp_recipe_ingredients 
                WHERE session_id = ? AND recipe_id = ?
                ORDER BY ingredient_order
            """, (session_id, recipe_id))
            
            ingredients = cursor.fetchall()
            
            if not ingredients:
                return {"error": f"No ingredients found for recipe {recipe_id} in session {session_id}"}
            
            for ingredient_row in ingredients:
                ingredient_id = ingredient_row[0]
                ingredient_text = ingredient_row[1]
                
                if not ingredient_text or not ingredient_text.strip():
                    continue
                
                # Parse the ingredient text
                parsed = _parse_ingredient_text(ingredient_text)
                
                # Check if parsing was successful (has valid clean_name)
                if parsed.get('clean_name') and parsed['clean_name'].strip():
                    # Update the temp table with parsed data
                    cursor.execute("""
                        UPDATE temp_recipe_ingredients 
                        SET ingredient_name = ?, amount = ?, unit = ?
                        WHERE session_id = ? AND ingredient_id = ?
                    """, (
                        parsed['clean_name'],
                        parsed.get('amount'),
                        parsed.get('unit'),
                        session_id,
                        ingredient_id
                    ))
                    parsed_count += 1
                else:
                    failed_count += 1
            
            conn.commit()
            
            return {
                "success": f"Parsed ingredients for recipe {recipe_id}",
                "session_id": session_id,
                "recipe_id": recipe_id,
                "total_ingredients": len(ingredients),
                "parsed_count": parsed_count,
                "failed_count": failed_count,
                "storage_type": "persistent_sqlite"
            }
            
    except sqlite3.Error as e:
        return {"error": f"SQLite error parsing ingredients: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error parsing ingredients: {e}"}