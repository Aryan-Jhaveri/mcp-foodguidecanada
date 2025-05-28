import requests
from bs4 import BeautifulSoup
from typing import List, Optional, Dict
import time
import re
import os
import sys

# Dynamically handle imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Try to import with different methods
try:
    # Try first with src prefix
    from src.models.recipe import Recipe
    from src.models.filters import SearchFilters
    from src.utils.url_builder import FoodGuideURLBuilder
except ImportError:
    try:
        # Next, try with parent directory
        from models.recipe import Recipe
        from models.filters import SearchFilters
        from utils.url_builder import FoodGuideURLBuilder
    except ImportError:
        # As a last resort, modify sys.path and try again
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from models.recipe import Recipe
        from models.filters import SearchFilters
        from utils.url_builder import FoodGuideURLBuilder

class RecipeSearcher:
    def __init__(self, delay_between_requests: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.delay = delay_between_requests
    
    def search_recipes(self, 
                      search_text: str = "",
                      filters: Optional[SearchFilters] = None,
                      max_pages: int = 30) -> List[Dict[str, str]]:
        """
        Search for recipes with optional filters.
        
        Returns:
            List of recipe metadata (title, url, slug)
        """
        filter_dict = filters.get_filters_dict() if filters else None
        search_url = FoodGuideURLBuilder.build_search_url(search_text, filter_dict)
        
        recipes = []
        current_page = 1
        seen_urls = set()
        
        while current_page <= max_pages:
            try:
                print(f"Fetching page {current_page}: {search_url}")
                response = self.session.get(search_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find the view content area
                view_content = soup.find('div', class_='view-content')
                
                if view_content:
                    # Find all recipe containers (they're in views-col divs)
                    recipe_containers = view_content.find_all('div', class_='views-col')
                    
                    for container in recipe_containers:
                        # Extract recipe data from this container
                        recipe_data = self._extract_recipe_from_container(container)
                        
                        if recipe_data and recipe_data['url'] not in seen_urls:
                            seen_urls.add(recipe_data['url'])
                            recipes.append(recipe_data)
                            print(f"Found recipe: {recipe_data['title']}")
                
                # Handle pagination
                next_url = self._get_next_page_url(soup)
                
                if not next_url or current_page >= max_pages:
                    break
                
                search_url = next_url
                current_page += 1
                time.sleep(self.delay)
                
            except Exception as e:
                print(f"Error searching recipes on page {current_page}: {e}")
                import traceback
                traceback.print_exc()
                break
        
        return recipes
    
    def _extract_recipe_from_container(self, container) -> Optional[Dict[str, str]]:
        """Extract recipe data from a views-col container"""
        try:
            # Find the image field which contains the link
            image_field = container.find('div', class_='views-field-field-featured-image')
            if not image_field:
                return None
            
            # Get the link
            link = image_field.find('a', href=True)
            if not link:
                return None
            
            href = link.get('href', '')
            
            # Check if it's a valid recipe URL
            if not re.match(r'^/en/recipes/[^/?]+/?$', href):
                return None
            
            # Find the title field
            title_field = container.find('div', class_='views-field-title')
            if not title_field:
                return None
            
            # Get the title text
            title_element = title_field.find('span', class_='field-content')
            if not title_element:
                return None
            
            title = title_element.get_text(strip=True)
            
            if not title:
                return None
            
            # Extract slug from URL
            slug_match = re.search(r'/en/recipes/([^/?]+)/?$', href)
            if not slug_match:
                return None
            
            slug = slug_match.group(1)
            
            # Build full URL
            full_url = FoodGuideURLBuilder.BASE_URL + href
            
            return {
                'title': title,
                'url': full_url,
                'slug': slug
            }
            
        except Exception as e:
            print(f"Error extracting recipe from container: {e}")
            return None
    
    def _get_next_page_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the URL for the next page of results"""
        # Look for pagination nav
        pagination = soup.find('nav', class_='pager-nav')
        
        if not pagination:
            # Try to find ul with pagination class
            pagination = soup.find('ul', class_='pagination')
        
        if pagination:
            # Look for next page link
            next_link = None
            
            # Try to find link with ›› text
            for link in pagination.find_all('a'):
                link_text = link.get_text(strip=True)
                if '››' in link_text or 'Next page' in link_text:
                    next_link = link
                    break
            
            if next_link:
                href = next_link.get('href', '')
                if href:
                    # Check if it's a query string
                    if href.startswith('?'):
                        # Append to base recipes URL
                        return FoodGuideURLBuilder.BASE_URL + '/en/recipes/' + href
                    elif href.startswith('/'):
                        return FoodGuideURLBuilder.BASE_URL + href
                    else:
                        return href
        
        return None