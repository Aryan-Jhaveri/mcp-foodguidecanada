from fastmcp import FastMCP
import sys  # Import sys to print to stderr
import os  # Import os for path manipulation

# Add the project root directory to the Python path to ensure imports work
# when running the script directly
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
src_dir = script_dir  # The src directory itself

# Add both src directory and project root to the path
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
    print(f"--> Added {src_dir} to Python path", file=sys.stderr)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"--> Added {project_root} to Python path", file=sys.stderr)

# Import the necessary components - use absolute imports with src prefix
try:
    # Try first with absolute imports
    from src.api.recipe import RecipeFetcher
    from src.api.search import RecipeSearcher
    from src.models.filters import SearchFilters
    from typing import List, Dict, Any, Optional
    print("--> Imported modules using absolute imports with src prefix", file=sys.stderr)
except ImportError:
    try:
        # If that fails, try with absolute imports without src prefix
        from api.recipe import RecipeFetcher
        from api.search import RecipeSearcher
        from models.filters import SearchFilters
        from typing import List, Dict, Any, Optional
        print("--> Imported modules using absolute imports without src prefix", file=sys.stderr)
    except ImportError as e:
        print(f"--> Error importing modules: {e}", file=sys.stderr)
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
        Search for recipes on Canada's Food Guide website.
        
        Args:
            search_text: Text to search for in recipes
            fruits: Filter by fruits (e.g., apple, banana)
            vegetables: Filter by vegetables (e.g., carrot, broccoli)
            proteins: Filter by proteins (e.g., chicken, tofu)
            whole_grains: Filter by whole grains (e.g., rice, quinoa)
            meals: Filter by meal type (e.g., breakfast, dinner)
            appliances: Filter by cooking appliance (e.g., oven, stovetop)
            collections: Filter by collections (e.g., vegetarian, kid-friendly)
            max_pages: Maximum pages to search (default: 5)
        
        Returns:
            List of recipe metadata with title, URL, and slug
        """
        print(f"Searching for recipes with text: '{search_text}'")
        
        searcher = RecipeSearcher()
        filters = None
        
        # Setup filters if any are provided
        if any([fruits, vegetables, proteins, whole_grains, meals, appliances, collections]):
            filters = SearchFilters()
            
            # Process each filter type
            if fruits:
                for value in fruits:
                    filters.add_filter('fruits', value)
                    print(f"Added fruit filter: {value}")
            
            if vegetables:
                for value in vegetables:
                    filters.add_filter('vegetables', value)
                    print(f"Added vegetable filter: {value}")
            
            if proteins:
                for value in proteins:
                    filters.add_filter('proteins', value)
                    print(f"Added protein filter: {value}")
            
            if whole_grains:
                for value in whole_grains:
                    filters.add_filter('whole_grains', value)
                    print(f"Added whole grain filter: {value}")
            
            if meals:
                for value in meals:
                    filters.add_filter('meals_and_course', value)
                    print(f"Added meal filter: {value}")
            
            if appliances:
                for value in appliances:
                    filters.add_filter('cooking_appliance', value)
                    print(f"Added appliance filter: {value}")
            
            # Process collections separately
            if collections:
                for value in collections:
                    filters.add_collection(value)
                    print(f"Added collection filter: {value}")
        
        # Perform search
        results = searcher.search_recipes(
            search_text=search_text,
            filters=filters,
            max_pages=max_pages
        )
        
        print(f"Found {len(results)} matching recipes")
        return results
    
    @mcp.tool()
    def get_recipe(url: str) -> Dict[str, Any]:
        """
        Fetch detailed recipe information from a URL.
        
        Args:
            url: The full URL to the recipe on Canada's Food Guide website
        
        Returns:
            Detailed recipe information including ingredients, instructions, etc.
        """
        print(f"Fetching recipe from URL: {url}")
        
        fetcher = RecipeFetcher()
        recipe = fetcher.fetch_recipe(url)
        
        if not recipe:
            print(f"Failed to fetch recipe from URL: {url}")
            return {"error": "Recipe not found or could not be parsed"}
        
        print(f"Successfully fetched recipe: {recipe.title}")
        
        # Convert recipe to dict for JSON serialization
        recipe_dict = recipe.__dict__
        
        return recipe_dict
    
    @mcp.tool()
    def list_filters(filter_type: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Get available filters for searching recipes.
        
        Args:
            filter_type: Optional specific filter type to retrieve
                        (vegetables, fruits, proteins, whole_grains, meal, cooking_appliance)
        
        Returns:
            Dictionary of filter types and their available values
        """
        filters = SearchFilters(auto_update=True)
        result = {}
        
        if filter_type:
            print(f"Fetching available filters for type: {filter_type}")
            # Return specific filter type
            result[filter_type] = filters.get_available_filters(filter_type)
        else:
            print("Fetching all available filter types")
            # Return all filter types
            filter_types = [
                "vegetables", "fruits", "proteins", "whole_grains", 
                "meal", "cooking_appliance"
            ]
            
            for ft in filter_types:
                result[ft] = filters.get_available_filters(ft)
            
            # Also include collections
            result["collections"] = filters.get_available_collections()
        
        return result

def create_server():
    """Create and configure the MCP server with all tools registered."""
    print("--> Creating Canada's Food Guide MCP server...", file=sys.stderr)
    
    # Create the FastMCP app with metadata
    mcp = FastMCP(
        name="FoodGuideSousChef",
        title="Canada's Food Guide Sous Chef",
        description="A FastMCP server for searching and retrieving recipes from Canada's Food Guide."
    )
    
    # Register all tools
    try:
        print("--> Registering recipe tools...", file=sys.stderr)
        register_recipe_tools(mcp)
        print("--> Tool registration complete.", file=sys.stderr)
        
    except Exception as e:
        print(f"--> ERROR during tool registration: {e}", file=sys.stderr)
        raise
    
    return mcp

# This part runs when the script is executed directly
if __name__ == "__main__":
    try:
        print("--> Initializing Canada's Food Guide MCP Server...", file=sys.stderr)
        
        # Create the server
        mcp = create_server()
        
        # This print goes to stdout
        print("Starting Canada's Food Guide Sous Chef MCP Server...")
        
        # Run the server
        mcp.run()
        
    except Exception as e:
        # Catch any unexpected exceptions
        print(f"--> UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
    
    finally:
        print("--> Server execution finished.", file=sys.stderr)