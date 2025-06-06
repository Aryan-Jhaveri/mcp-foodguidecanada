import requests
from bs4 import BeautifulSoup
from typing import Optional, List
import json
import re
import os
import sys
from fastmcp import FastMCP
from typing import List, Dict, Any, Optional

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
src_dir = script_dir

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.api.search import RecipeSearcher
    from src.models.filters import SearchFilters
    from src.db.queries import register_db_tools
    from src.config import DB_FILE
    from src.utils.url_builder import FoodGuideURLBuilder
except ImportError:
    try:
        from api.search import RecipeSearcher
        from models.filters import SearchFilters
        from db.queries import register_db_tools
        from config import DB_FILE
        from utils.url_builder import FoodGuideURLBuilder
    except ImportError as e:
        print(f"Error importing modules: {e}", file=sys.stderr)
        sys.exit(1)

try:
    # Try first with src prefix
    from src.models.recipe import Recipe
    from src.utils.url_builder import FoodGuideURLBuilder
except ImportError:
    try:
        # Next, try with parent directory
        from models.recipe import Recipe
        from utils.url_builder import FoodGuideURLBuilder
    except ImportError:
        # As a last resort, modify sys.path and try again
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from models.recipe import Recipe
        from utils.url_builder import FoodGuideURLBuilder

class RecipeFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_recipe(self, recipe_url: str) -> Optional[Recipe]:
        """Fetch and parse a single recipe."""
        try:
            print(f"Fetching recipe from: {recipe_url}")
            response = self.session.get(recipe_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract recipe data
            title = self._extract_title(soup)
            ingredients = self._extract_ingredients(soup)
            instructions = self._extract_instructions(soup)
            categories = self.extract_categories(soup)
            tips = self._extract_tips(soup)
            recipe_highlights = self._extract_recipe_highlights(soup)  # Add this line
            
            # Extract metadata
            prep_time = self._extract_time(soup, 'prep')
            cook_time = self._extract_time(soup, 'cook')
            servings = self._extract_servings(soup)
            image_url = self._extract_image(soup)
            
            # Extract slug from URL
            slug = recipe_url.rstrip('/').split('/')[-1]
            
            return Recipe(
                title=title,
                slug=slug,
                url=recipe_url,
                ingredients=ingredients,
                instructions=instructions,
                prep_time=prep_time,
                cook_time=cook_time,
                servings=servings,
                categories=categories,
                tips=tips,
                recipe_highlights=recipe_highlights,  # Add this line
                image_url=image_url
            )
            
        except Exception as e:
            print(f"Error fetching recipe: {e}")
            return None
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract recipe title."""
        # Try different title selectors
        title_element = (
            soup.find('h1', class_='page-header__title') or
            soup.find('h1', id='wb-cont') or
            soup.find('h1', class_='gc-thickline') or
            soup.find('h1')
        )
        return title_element.get_text(strip=True) if title_element else "Unknown Recipe"
    
    def _extract_ingredients(self, soup: BeautifulSoup) -> List[str]:
        """
        Extract ingredients list, prioritizing a specific div class for Canada Food Guide patterns.
        This version extracts all textual content within the target div.
        """
        ingredients = []

        # 1. Prioritize the specific div class for ingredients
        ingredients_div = soup.find('div', class_='field--name-field-ingredients')

        if ingredients_div:
            # Iterate through all direct children divisions and extract their text
            for child in ingredients_div.children:
                text = child.get_text(strip=True) if hasattr(child, 'get_text') else str(child).strip()
                if text and text not in ingredients: # Avoid duplicates if an element contains redundant text
                    # to keep lines from within <ul> separately, need to specifically look for <li> tags within any <ul> child
                    if child.name == 'ul' or child.name == 'ol':
                        for li in child.find_all('li'):
                            li_text = li.get_text(strip=True)
                            if li_text and li_text not in ingredients:
                                ingredients.append(li_text)
                    elif text: # Add non-list direct text content
                        ingredients.append(text)
            if ingredients:
                return ingredients
    
    def _extract_instructions(self, soup: BeautifulSoup) -> List[str]:
        """Extract cooking instructions."""
        instructions = []
        
        # Look for instructions/directions section
        instructions_heading = soup.find(['h2', 'h3'], text=re.compile(r'Instructions|Directions|Method', re.I))
        
        if instructions_heading:
            # Get the container with the instructions
            instructions_container = instructions_heading.find_next_sibling(['ol', 'ul'])
            if not instructions_container:
                parent = instructions_heading.parent
                if parent:
                    instructions_container = parent.find(['ol', 'ul'])
            
            if instructions_container:
                for li in instructions_container.find_all('li'):
                    text = li.get_text(strip=True)
                    if text:
                        instructions.append(text)
        
        # Alternative: Look for numbered lists
        if not instructions:
            for ol in soup.find_all('ol'):
                items = ol.find_all('li')
                if 2 < len(items) < 20:  # Reasonable number of steps
                    temp_instructions = []
                    for li in items:
                        text = li.get_text(strip=True)
                        if text and len(text) > 20:  # Instructions are usually longer
                            temp_instructions.append(text)
                    
                    if len(temp_instructions) > len(instructions):
                        instructions = temp_instructions
        
        return instructions
    
    def _extract_time(self, soup: BeautifulSoup, time_type: str) -> Optional[str]:
        """
        Extract prep or cook time, prioritizing a specific div structure.
        time_type should be 'Prep' or 'Cook'.
        """
        # 1. Prioritize extraction from the specific div structure
        # Find all 'div' elements that have 'class="item col-xs-4"'
        time_containers = soup.find_all('div', class_='item col-xs-4')

        for container in time_containers:
            # Within each container, find the div with class="title"
            title_div = container.find('div', class_='title')
            if title_div:
                title_text = title_div.get_text(strip=True)
                # Check if the title matches the desired time type (e.g., "Prep time" or "Cook time")
                if time_type.lower() in title_text.lower():
                    # The actual time value is in the next sibling div
                    time_value_div = title_div.find_next_sibling('div')
                    if time_value_div:
                        time = time_value_div.get_text(strip=True)
                        # Basic validation to ensure it looks like a time string
                        if re.search(r'\d+.*(?:min|hour)', time, re.I):
                            return time
        
        # 2. Fallback to general time extraction (your original logic)
        time_patterns = [
            re.compile(f'{time_type}.*time.*:.*?(\\d+.*(?:min|hour))', re.I),
            re.compile(f'{time_type}.*:.*?(\\d+.*(?:min|hour))', re.I),
        ]
        
        # Search in common time display areas
        for element in soup.find_all(['p', 'span', 'div', 'li']):
            text = element.get_text(strip=True)
            for pattern in time_patterns:
                match = pattern.search(text)
                if match:
                    return match.group(1)
        
        return None
    
    def _extract_servings(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract number of servings."""
        # Look for servings information
        servings_patterns = [
            re.compile(r'(?:serves?|servings?|yield[s]?).*?(\d+)', re.I),
            re.compile(r'(\d+).*(?:servings?|portions?)', re.I),
        ]
        
        for element in soup.find_all(['p', 'span', 'div', 'li']):
            text = element.get_text(strip=True)
            for pattern in servings_patterns:
                match = pattern.search(text)
                if match:
                    try:
                        return int(match.group(1))
                    except:
                        pass
        
        return None
    
    def _extract_image(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract recipe image URL."""
        
        # First, look for featured image wrapper (most likely to be the main recipe image)
        featured_wrapper = soup.find('div', class_='featured-image-wrapper')
        if featured_wrapper:
            img = featured_wrapper.find('img')
            if img:
                src = img.get('src', '')
                if src:
                    if not src.startswith('http'):
                        src = FoodGuideURLBuilder.BASE_URL + src
                    return src
        
        # Look for images that are clearly from the Canada Food Guide site
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and 'food-guide.canada.ca' in src:
                # Skip small images (likely icons, logos, buttons)
                if not any(skip in src.lower() for skip in ['icon', 'logo', 'button', 'nav']):
                    # Prefer images with 'styles' in path (these are usually processed/sized images)
                    if 'styles' in src:
                        return src
        
        # Look for images with Canada Food Guide domain (second pass without styles requirement)
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and 'food-guide.canada.ca' in src:
                if not any(skip in src.lower() for skip in ['icon', 'logo', 'button', 'nav']):
                    return src
        
        # Look for images with recipe-related classes or attributes
        image_selectors = [
            {'class': re.compile('recipe.*image', re.I)},
            {'class': re.compile('food.*image', re.I)},
            {'class': re.compile('featured.*image', re.I)},
            {'class': re.compile('hero.*image', re.I)},
            {'alt': re.compile('recipe', re.I)},
        ]
        
        for selector in image_selectors:
            image_element = soup.find('img', selector)
            if image_element:
                src = image_element.get('src', '')
                if src:
                    if not src.startswith('http'):
                        src = FoodGuideURLBuilder.BASE_URL + src
                    return src
        
        # Look for images in common container classes
        container_selectors = [
            'div.container img',
            'div.image-container img',
            'div.recipe-image img',
            'div.hero-image img',
            'article img',
            'main img'
        ]
        
        for selector in container_selectors:
            img = soup.select_one(selector)
            if img:
                src = img.get('src', '')
                if src and not any(skip in src.lower() for skip in ['icon', 'logo', 'button', 'nav']):
                    if not src.startswith('http'):
                        src = FoodGuideURLBuilder.BASE_URL + src
                    return src
        
        # Final fallback: Look for the first substantial image
        for img in soup.find_all('img'):
            src = img.get('src', '')
            # Skip small images (likely icons)
            if src and not any(skip in src.lower() for skip in ['icon', 'logo', 'button', 'nav', 'sprite']):
                # Check if the image seems substantial (has some indicators of being a main image)
                if any(indicator in src.lower() for indicator in ['recipe', 'food', 'hero', 'main', 'featured']) or \
                len(src) > 50:  # Longer URLs often indicate processed images
                    if not src.startswith('http'):
                        src = FoodGuideURLBuilder.BASE_URL + src
                    return src
        
        return None
    
    def extract_categories(self, soup: BeautifulSoup) -> List[str]:
        """
        Extracts a list of categories from the specific HTML structure.
        Looks for divs with class 'field--name-name' inside the 'collection-name' divs.
        """
        category_divs = soup.select('div.collection-name > div.field--name-name.field--type-string.field--label-hidden.field--item')
        return [div.get_text(strip=True) for div in category_divs]
    
    def _extract_tips(self, soup: BeautifulSoup) -> List[str]:
        """Extract cooking tips from the recipe page."""
        tips = []
        
        # Look for the tips section with the specific class
        tips_div = soup.find('div', class_='field--name-field-cooking-tips')
        
        if tips_div:
            # Find the field item container
            field_item = tips_div.find('div', class_='field--item')
            
            if field_item:
                # Extract all paragraph elements
                paragraphs = field_item.find_all('p')
                for p in paragraphs:
                    tip_text = p.get_text(strip=True)
                    if tip_text:
                        tips.append(tip_text)
        
        # Alternative: Look for any section with "Tips" heading
        if not tips:
            tips_heading = soup.find(['h2', 'h3', 'h4'], text=re.compile(r'Tips?', re.I))
            if tips_heading:
                # Look for content after the heading
                current = tips_heading.find_next_sibling()
                while current and current.name in ['p', 'ul', 'ol', 'div']:
                    if current.name == 'p':
                        tip_text = current.get_text(strip=True)
                        if tip_text:
                            tips.append(tip_text)
                    elif current.name in ['ul', 'ol']:
                        for li in current.find_all('li'):
                            tip_text = li.get_text(strip=True)
                            if tip_text:
                                tips.append(tip_text)
                    elif current.name == 'div' and 'field--item' in current.get('class', []):
                        for p in current.find_all('p'):
                            tip_text = p.get_text(strip=True)
                            if tip_text:
                                tips.append(tip_text)
                        break
                    
                    current = current.find_next_sibling()
        
        return tips
    
    def _extract_recipe_highlights(self, soup: BeautifulSoup) -> List[dict[str, str]]:
        """Extract recipe highlights slides from the recipe page."""
        highlights = []
        
        # Look for the recipe highlights section
        highlights_section = soup.find('section', class_=re.compile(r'.*instruction-steps.*'))
        
        if not highlights_section:
            # Alternative: look for section with "Recipe highlights" heading
            highlights_heading = soup.find(['h2', 'h3'], text=re.compile(r'Recipe highlights', re.I))
            if highlights_heading:
                highlights_section = highlights_heading.find_parent('section')
        
        # Also try to find slides directly if no specific section is found
        if not highlights_section:
            highlights_section = soup
        
        if highlights_section:
            # Look for slides in multiple possible structures
            slide_selectors = [
                'div.slick__slide',           # Original selector
                'div.slide__content',         # New structure from your HTML
                'div[class*="slide"]'         # Any div with "slide" in class name
            ]
            
            slides = []
            for selector in slide_selectors:
                found_slides = highlights_section.select(selector)
                if found_slides:
                    slides = found_slides
                    break
            
            for slide in slides:
                highlight = {}
                
                # Extract slide count - look in multiple possible locations
                slide_count_div = slide.find('div', class_='slide-count')
                if slide_count_div:
                    # Get the slide count text
                    slide_count_text = slide_count_div.get_text(strip=True)
                    # Extract just the number from patterns like "1 of 2" or "Slide 1 of 2"
                    count_match = re.search(r'(\d+)', slide_count_text)
                    if count_match:
                        highlight['slide_count'] = count_match.group(1)
                    else:
                        highlight['slide_count'] = slide_count_text.replace('Slide', '').strip()
                
                # Extract caption text - look in multiple possible locations
                caption_selectors = [
                    'div.caption-text p',
                    'div.slide__description p',
                    'div.field-content p',
                    'p'  # fallback to any p tag in the slide
                ]
                
                caption_text = None
                for caption_selector in caption_selectors:
                    caption_element = slide.select_one(caption_selector)
                    if caption_element:
                        caption_text = caption_element.get_text(strip=True)
                        if caption_text and len(caption_text) > 10:  # Ensure it's substantial text
                            break
                
                if caption_text:
                    highlight['caption_text'] = caption_text
                
                # Extract image URL - look for multiple possible image structures
                img_selectors = [
                    'img.media__element',                    # Your HTML structure
                    'img.b-lazy',                           # Alternative class from your HTML
                    'img.img-responsive',                   # Another class from your HTML
                    'div.slide__media img',                 # Images within slide media container
                    'div.media img',                        # Images within media container
                    'img'                                   # Fallback to any img tag
                ]
                
                img_element = None
                for img_selector in img_selectors:
                    img_element = slide.select_one(img_selector)
                    if img_element:
                        # First try to get the actual image URL from data attributes (for lazy loading)
                        src = self._get_actual_image_src(img_element)
                        
                        # Skip placeholder images and obvious non-content images
                        if src and not any(skip in src.lower() for skip in ['icon', 'logo', 'button', 'nav', 'data:image', 'svg+xml']):
                            break
                        img_element = None  # Reset if this image was skipped
                
                if img_element:
                    src = self._get_actual_image_src(img_element)
                    if src and not any(skip in src.lower() for skip in ['data:image', 'svg+xml']):
                        # Build full URL if it's relative
                        if not src.startswith('http'):
                            # FoodGuideURLBuilder is already imported at the top of the file
                            src = FoodGuideURLBuilder.BASE_URL + src
                        highlight['image_url'] = src
                
                # Add highlight if we have meaningful content
                # Require either caption OR image (not both) since some slides might only have one
                if 'caption_text' in highlight or 'image_url' in highlight:
                    # Add slide count if we don't have it but can infer from position
                    if 'slide_count' not in highlight:
                        highlight['slide_count'] = str(len(highlights) + 1)
                    highlights.append(highlight)
        
        return highlights

    def _get_actual_image_src(self, img_element) -> Optional[str]:
        """
        Extract the actual image source from an img element, handling lazy loading.
        Checks data attributes first, then falls back to src.
        """
        # Common lazy loading attributes in order of preference
        lazy_attrs = [
            'data-src',
            'data-lazy-src', 
            'data-original',
            'data-srcset',
            'srcset',
            'src'
        ]
        
        for attr in lazy_attrs:
            value = img_element.get(attr, '')
            if value:
                # For srcset, take the first URL (before any spaces or commas)
                if attr in ['srcset', 'data-srcset']:
                    # srcset format: "url1 1x, url2 2x" or "url1 100w, url2 200w"  
                    first_url = value.split(',')[0].split(' ')[0].strip()
                    if first_url and not any(skip in first_url.lower() for skip in ['data:image', 'svg+xml']):
                        return first_url
                else:
                    # Regular src/data-src attribute
                    if not any(skip in value.lower() for skip in ['data:image', 'svg+xml']):
                        return value
        
        
        return None
    
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
    ) -> List[dict[str, str]]:
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
                    # Use proper URL builder instead of hardcoded URL
                    result['website'] = FoodGuideURLBuilder.BASE_URL
            
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

