from urllib.parse import urlencode, quote
from typing import Dict, List, Optional

class FoodGuideURLBuilder:
    BASE_URL = "https://food-guide.canada.ca"
    RECIPES_PATH = "/en/recipes/"
    
    @classmethod
    def build_search_url(cls, 
                        search_text: str = "", 
                        filters: Optional[Dict[str, List[str]]] = None) -> str:
        """
        Build search URL with optional filters.
        
        Args:
            search_text: Text to search for
            filters: Dictionary of filter types and values
                    e.g., {"fruits": ["43"], "vegetables": ["48"], "collection": ["17"]}
        
        Returns:
            Complete search URL
        """
        params = {
            "search_api_fulltext": search_text,
            "cfg-search": "Search"
        }
        
        # Build filter parameters
        if filters:
            filter_index = 0
            for filter_type, values in filters.items():
                for value in values:
                    param_key = f"f[{filter_index}]"
                    param_value = f"{filter_type}:{value}"
                    params[param_key] = param_value
                    filter_index += 1
        
        query_string = urlencode(params, safe=':[]')
        return f"{cls.BASE_URL}{cls.RECIPES_PATH}?{query_string}"
    
    @classmethod
    def build_recipe_url(cls, recipe_slug: str) -> str:
        """Build URL for a specific recipe."""
        return f"{cls.BASE_URL}{cls.RECIPES_PATH}{recipe_slug}/"