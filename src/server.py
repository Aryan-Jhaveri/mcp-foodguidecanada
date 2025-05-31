from fastmcp import FastMCP
import sys
import os
from typing import List, Dict, Any, Optional

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
src_dir = script_dir

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.api.recipe import RecipeFetcher
    from src.api.search import RecipeSearcher
    from src.models.filters import SearchFilters
    from src.db.queries import register_db_tools
    from src.config import DB_FILE
except ImportError:
    try:
        from api.recipe import RecipeFetcher
        from api.search import RecipeSearcher
        from models.filters import SearchFilters
        from db.queries import register_db_tools
        from config import DB_FILE
    except ImportError as e:
        print(f"Error importing modules: {e}", file=sys.stderr)
        sys.exit(1)

def register_recipe_tools(mcp: FastMCP):
    """Register all recipe-related tools with the MCP server."""
    
    @mcp.tool()
    def search_recipes(
        search_text: str = "", 
        fruits: Optional[List[str]] = None,
        vegetables: Optional[List[str]] = None,
        proteins: Optional[List[str]] = None,
        whole_grains: Optional[List[str]] = None,
        meals: Optional[List[str]] = None,
        appliances: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        max_pages: int = 5
    ) -> List[Dict[str, str]]:
        """
        Search for Canadian recipes from Health Canada's official Food Guide website. This tool searches through thousands of government-verified, nutrition-focused recipes designed to help Canadians eat well according to official dietary guidelines.

        The search covers recipes that emphasize:
        - Vegetables and fruits as the foundation of meals
        - Whole grain foods for sustained energy  
        - Protein foods including plant-based options
        - Culturally diverse Canadian cuisine
        - Family-friendly and accessible cooking methods

        Each recipe returned includes complete nutritional guidance, cooking tips from registered dietitians, and visual instruction steps to ensure cooking success.

        Args:
            search_text: Free-text search across recipe titles, ingredients, and descriptions (e.g., "quick breakfast", "salmon dinner", "vegetarian lunch")
            fruits: Filter by specific fruits (e.g., ["apple", "banana", "berries"]) - use list_filters to see all available options
            vegetables: Filter by specific vegetables (e.g., ["carrot", "broccoli", "spinach"]) - use list_filters to see all available options  
            proteins: Filter by protein sources (e.g., ["chicken", "tofu", "beans", "fish"]) - use list_filters to see all available options
            whole_grains: Filter by grain types (e.g., ["rice", "quinoa", "oats"]) - use list_filters to see all available options
            meals: Filter by meal occasions (e.g., ["breakfast", "lunch", "dinner", "snack"]) - use list_filters to see all available options
            appliances: Filter by cooking equipment needed (e.g., ["oven", "stovetop", "slow_cooker"]) - use list_filters to see all available options
            collections: Filter by special dietary collections (e.g., ["vegetarian", "kid_friendly", "quick_meals"]) - use list_filters to see all available options
            max_pages: Maximum search result pages to process (1-10, default: 5). Each page contains ~12 recipes.

        Returns:
            List of recipe metadata dictionaries containing:
            - title: Recipe name as it appears on Canada's Food Guide
            - url: Direct link to the full recipe on food-guide.canada.ca
            - slug: URL-friendly recipe identifier for referencing
            
        Source: Health Canada's Food Guide - https://food-guide.canada.ca/
        """
        try:
            searcher = RecipeSearcher()
            filters = None
            
            filter_types = [
                (fruits, 'fruits'),
                (vegetables, 'vegetables'), 
                (proteins, 'proteins'),
                (whole_grains, 'whole_grains'),
                (meals, 'meals_and_course'),
                (appliances, 'cooking_appliance')
            ]
            
            if any([fruits, vegetables, proteins, whole_grains, meals, appliances, collections]):
                filters = SearchFilters()
                
                for filter_list, filter_type in filter_types:
                    if filter_list:
                        for value in filter_list:
                            filters.add_filter(filter_type, value)
                
                if collections:
                    for value in collections:
                        filters.add_collection(value)
            
            results = searcher.search_recipes(
                search_text=search_text,
                filters=filters,
                max_pages=max_pages
            )
            
            # Add source attribution to each result
            for result in results:
                if 'url' in result and not result.get('source'):
                    result['source'] = 'Health Canada\'s Food Guide'
                    result['website'] = 'https://food-guide.canada.ca/' ## <---  Update this to slug url + url builder (May 30,2025)
            
            return results
            
        except Exception as e:
            return [{"error": f"Search failed: {str(e)}"}]
    
    @mcp.tool()
    def get_recipe(url: str) -> Dict[str, Any]:
        """
        Retrieve complete recipe details from Health Canada's Food Guide website. This tool extracts comprehensive recipe information from official government sources, providing nutrition-focused recipes developed by registered dietitians and health professionals.

        Each recipe includes:
        - Complete ingredient lists with measurements
        - Step-by-step cooking instructions with visual guides
        - Nutritional benefits and dietary information
        - Preparation and cooking time estimates
        - Serving size recommendations
        - Professional cooking tips and techniques
        - Recipe highlight images showing key preparation steps
        - Food category classifications aligned with Canada's Food Guide
        
        All recipes are designed to support healthy eating according to Canadian dietary guidelines and promote food skills development.

        Args:
            url: Complete URL to a specific recipe on Canada's Food Guide website (must start with https://food-guide.canada.ca/)
            
        Returns:
            Comprehensive recipe dictionary containing:
            - title: Official recipe name
            - slug: URL identifier for the recipe
            - url: Source URL for attribution and reference
            - ingredients: Complete list of ingredients with measurements
            - instructions: Detailed step-by-step cooking directions
            - prep_time: Estimated preparation time
            - cook_time: Estimated cooking time  
            - servings: Number of servings the recipe yields
            - categories: Food Guide category classifications
            - tips: Professional cooking tips and dietary guidance
            - recipe_highlights: Visual instruction steps with images and descriptions
            - image_url: Main recipe photo URL
            - source: "Health Canada's Food Guide" for proper attribution
            - website: "https://food-guide.canada.ca/" for reference

        Source: Health Canada's Food Guide - https://food-guide.canada.ca/ + the recipe slug URL builder
        """
        if not url or not url.startswith('https://food-guide.canada.ca/'):
            return {"error": "Invalid URL. Must be a Canada's Food Guide recipe URL."}
        
        try:
            fetcher = RecipeFetcher()
            recipe = fetcher.fetch_recipe(url)
            
            if not recipe:
                return {"error": "Recipe not found or could not be parsed"}
            
            recipe_data = {
                "title": recipe.title,
                "slug": getattr(recipe, 'slug', ''),
                "url": url,
                "ingredients": recipe.ingredients or [],
                "instructions": recipe.instructions or [],
                "prep_time": getattr(recipe, 'prep_time', ''),
                "cook_time": getattr(recipe, 'cook_time', ''),
                "servings": getattr(recipe, 'servings', None),
                "categories": getattr(recipe, 'categories', []),
                "tips": getattr(recipe, 'tips', []),
                "recipe_highlights": getattr(recipe, 'recipe_highlights', []),
                "image_url": getattr(recipe, 'image_url', ''),
                "source": "Health Canada's Food Guide",
                "website": "https://food-guide.canada.ca/",
                "attribution": "Recipe sourced from Canada's official Food Guide"
            }
            
            return recipe_data
            
        except Exception as e:
            return {"error": f"Failed to fetch recipe: {str(e)}"}
    
    @mcp.tool()
    def list_filters(filter_type: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Discover available search filters for Canada's Food Guide recipes. This tool provides the complete catalog of filter options that can be used with the search_recipes tool to find recipes that match specific dietary needs, cooking methods, meal types, and food categories.

        Filters are organized according to Canada's Food Guide food groups and practical cooking considerations:
        
        Food Categories (aligned with Canada's Food Guide):
        - vegetables: All vegetable types featured in Canadian recipes
        - fruits: Fresh, frozen, and dried fruits used in cooking
        - proteins: Both animal and plant-based protein sources
        - whole_grains: Whole grain options promoted for optimal nutrition
        
        Practical Filters:
        - meal: Meal occasions and course types (breakfast, lunch, dinner, snacks)
        - cooking_appliance: Kitchen equipment needed (accommodates various cooking setups)
        - collections: Special dietary categories and cooking themes
        
        This information helps users discover the full range of recipe options available and construct precise searches that match their dietary preferences, available ingredients, cooking equipment, and meal planning needs.

        Args:
            filter_type: Specific filter category to retrieve (optional). Valid options:
                        - "vegetables" - All vegetable filter options
                        - "fruits" - All fruit filter options  
                        - "proteins" - All protein source filter options
                        - "whole_grains" - All whole grain filter options
                        - "meal" - All meal type and course filter options
                        - "cooking_appliance" - All cooking equipment filter options
                        - "collections" - All special dietary and theme collections
                        If not specified, returns all filter categories.

        Returns:
            Dictionary mapping filter categories to their available values. Each category contains a list of specific filter options that can be used in recipe searches.
            Also includes source attribution for transparency.
            
        Source: Health Canada's Food Guide - https://food-guide.canada.ca/
        """
        try:
            filters = SearchFilters(auto_update=True)
            result = {}
            
            if filter_type:
                if filter_type in ["vegetables", "fruits", "proteins", "whole_grains", "meal", "cooking_appliance"]:
                    result[filter_type] = filters.get_available_filters(filter_type)
                elif filter_type == "collections":
                    result["collections"] = filters.get_available_collections()
                else:
                    return {"error": f"Invalid filter type: {filter_type}"}
            else:
                filter_types = [
                    "vegetables", "fruits", "proteins", "whole_grains", 
                    "meal", "cooking_appliance"
                ]
                
                for ft in filter_types:
                    result[ft] = filters.get_available_filters(ft)
                
                result["collections"] = filters.get_available_collections()
            
            # Add source attribution
            result["source"] = "Health Canada's Food Guide"
            result["website"] = "https://food-guide.canada.ca/"
            result["note"] = "Filter options are dynamically updated from Canada's Food Guide recipe database to ensure current availability."
            
            return result
            
        except Exception as e:
            return {"error": f"Failed to fetch filters: {str(e)}"}

def create_server() -> FastMCP:
    """Create and configure the MCP server with all tools registered."""
    mcp = FastMCP(
        name="FoodGuideSousChef",
        title="Canada's Food Guide Sous Chef",
        description="""
        Official recipe search and retrieval system for Health Canada's Food Guide. 
        
        This MCP server provides comprehensive access to thousands of government-verified, nutrition-focused recipes developed by registered dietitians and health professionals. All recipes align with Canada's official dietary guidelines and promote healthy eating patterns.
        
        Capabilities:
        • Search through Canada's complete Food Guide recipe database with advanced filtering
        • Retrieve detailed recipe information including ingredients, instructions, timing, and nutritional guidance
        • Access professional cooking tips and dietary recommendations
        • Discover available search filters organized by food categories and cooking methods
        • Get visual instruction highlights and recipe photography
        
        All content is sourced from Health Canada's official Food Guide website (https://food-guide.canada.ca/) and includes proper attribution for transparency and reference.
        
        Perfect for meal planning, nutrition education, cooking instruction, and promoting healthy eating according to Canadian dietary guidelines.
        """
    )
    
    try:
        register_recipe_tools(mcp)
        register_db_tools(mcp)
    except Exception as e:
        print(f"ERROR during tool registration: {e}", file=sys.stderr)
        raise
    
    return mcp

if __name__ == "__main__":
    try:
        print(f"Database file location: {os.path.abspath(DB_FILE)}", file=sys.stderr)
        mcp = create_server()
        mcp.run()
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)