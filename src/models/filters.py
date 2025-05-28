from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
import os
import requests
from bs4 import BeautifulSoup
import re
from pathlib import Path

@dataclass
class FilterInfo:
    """Information about a single filter option"""
    id: str
    label: str
    type: str
    name: str

class SearchFilters:
    """Represents search filters for recipe queries with auto-update capability."""
    
    # Cache file paths
    CACHE_DIR = Path(__file__).parent.parent.parent / "cache" # location relative to this file
    FILTERS_CACHE_FILE = CACHE_DIR / "filters_cache.json" #file name for cached filters
    CACHE_EXPIRY_DAYS = 7  # Refresh filters weekly 
    
    def __init__(self, auto_update: bool = True):
        '''
        Initialize the SearchFilters object.
        '''
        self.active_filters: Dict[str, List[str]] = {}
        self._filters_data: Dict[str, Dict[str, FilterInfo]] = {}
        self._collections_data: Dict[str, str] = {}
        self._last_updated: Optional[datetime] = None
        
        # Ensure cache directory exists
        self.CACHE_DIR.mkdir(exist_ok=True)
        
        # Load filters (from cache or fetch new)
        if auto_update:
            self.load_filters()
    
    def load_filters(self):
        """Load filters from cache or fetch from website if expired."""
        if self._is_cache_valid():
            self._load_from_cache()
        else:
            self.update_filters_from_website()
    
    def _is_cache_valid(self) -> bool:
        """Check if the cache file exists and is still valid."""
        if not self.FILTERS_CACHE_FILE.exists():
            return False
        
        try:
            with open(self.FILTERS_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            last_updated = datetime.fromisoformat(cache_data.get('last_updated', ''))
            expiry_date = last_updated + timedelta(days=self.CACHE_EXPIRY_DAYS)
            
            return datetime.now() < expiry_date
        except:
            return False
    
    def _load_from_cache(self):
        """Load filters from cache file."""
        try:
            with open(self.FILTERS_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            self._last_updated = datetime.fromisoformat(cache_data['last_updated'])
            
            # Load filters
            for category, items in cache_data['filters'].items():
                self._filters_data[category] = {}
                for item in items:
                    filter_info = FilterInfo(
                        id=item['id'],
                        label=item['label'],
                        type=item['type'],
                        name=item['name']
                    )
                    # Use normalized label as key
                    key = self._normalize_key(item['label'])
                    self._filters_data[category][key] = filter_info
            
            # Load collections
            for collection in cache_data['collections']:
                key = self._normalize_key(collection['name'])
                self._collections_data[key] = collection['id']
                
            print(f"Loaded filters from cache (last updated: {self._last_updated})")
            
        except Exception as e:
            print(f"Error loading from cache: {e}")
            self.update_filters_from_website()
    
    def update_filters_from_website(self):
        """Fetch and update filters from the Canada Food Guide website."""
        print("Updating filters from website...")
        
        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            response = session.get("https://food-guide.canada.ca/en/recipes/")
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract filters
            filters_raw = self._extract_filters(soup)
            collections_raw = self._extract_collections(soup)
            
            # Process and store filters
            self._filters_data = {}
            for category, items in filters_raw.items():
                self._filters_data[category] = {}
                for item in items:
                    filter_info = FilterInfo(
                        id=item['id'],
                        label=item['label'],
                        type=item['type'],
                        name=item['name']
                    )
                    key = self._normalize_key(item['label'])
                    self._filters_data[category][key] = filter_info
            
            # Process and store collections
            self._collections_data = {}
            for collection in collections_raw:
                key = self._normalize_key(collection['name'])
                self._collections_data[key] = collection['id']
            
            self._last_updated = datetime.now()
            
            # Save to cache
            self._save_to_cache(filters_raw, collections_raw)
            
            print(f"Successfully updated filters from website")
            
        except Exception as e:
            print(f"Error updating filters from website: {e}")
            # Fall back to hardcoded defaults if needed
            self._load_defaults()
    
    def _extract_filters(self, soup: BeautifulSoup) -> Dict[str, List[Dict[str, str]]]:
        """Extract all filters from the page."""
        filters = {}
        
        facets_form = soup.find('form', id='facets-form')
        if facets_form:
            details_sections = facets_form.find_all('details')
            
            for section in details_sections:
                summary = section.find('summary')
                if not summary:
                    continue
                
                category = summary.get_text(strip=True)
                filters[category] = []
                
                checkboxes = section.find_all('input', type='checkbox')
                for checkbox in checkboxes:
                    value = checkbox.get('value', '')
                    name = checkbox.get('name', '')
                    
                    label = checkbox.find_parent('label')
                    if label:
                        label_text = label.get_text(strip=True)
                    else:
                        label_text = "Unknown"
                    
                    filter_type = name.split('[')[0] if '[' in name else name
                    
                    filters[category].append({
                        'id': value,
                        'label': label_text,
                        'name': name,
                        'type': filter_type
                    })
        
        return filters
    
    def _extract_collections(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract recipe collections."""
        collections = []
        
        collections_section = soup.find('section', id='block-recipecollections')
        if collections_section:
            collection_links = collections_section.find_all('a', {'data-drupal-facet-item-id': True})
            
            for link in collection_links:
                collection_id = link.get('data-drupal-facet-item-value', '')
                collection_name = link.get_text(strip=True)
                collection_name = re.sub(r'^Filter results by', '', collection_name).strip()
                
                collections.append({
                    'id': collection_id,
                    'name': collection_name,
                    'facet_id': link.get('data-drupal-facet-item-id', ''),
                    'href': link.get('href', '')
                })
        
        return collections
    
    def _save_to_cache(self, filters: Dict[str, List[Dict[str, str]]], collections: List[Dict[str, str]]):
        """Save filters to cache file."""
        cache_data = {
            'last_updated': self._last_updated.isoformat(),
            'filters': filters,
            'collections': collections
        }
        
        with open(self.FILTERS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
    
    def _normalize_key(self, label: str) -> str:
        """Normalize a label to create a consistent key."""
        # Convert to lowercase, replace spaces and special chars with underscores
        key = label.lower()
        key = re.sub(r'[^\w]+', '_', key)
        key = key.strip('_')
        return key
    
    def _load_defaults(self):
        """Load default hardcoded filters as fallback."""
        # This contains the complete filter data from your JSON
        self._filters_data = {
            "Vegetables": self._create_default_vegetables(),
            "Fruits": self._create_default_fruits(),
            "Whole grains": self._create_default_whole_grains(),
            "Proteins": self._create_default_proteins(),
            "Meal": self._create_default_meals(),
            "Cooking appliance": self._create_default_appliances()
        }
        
        self._collections_data = {
            "10_ingredients_or_less": "21",
            "30_minutes_or_less": "7",
            "freezer_friendly": "17",
            "kid_friendly": "16",
            "no_cook": "15",
            "vegetarian": "6"
        }
        
        self._last_updated = datetime.now()
    
    # Helper methods for creating default filters 
    ## These are hardcoded defaults that can be used if the website is down or cache is invalid
    def _create_default_vegetables(self) -> Dict[str, FilterInfo]:
        """Create default vegetable filters."""
        vegetables = {
            "48": "Asparagus", "49": "Avocado", "50": "Bean sprout", 
            "51": "Bell pepper", "52": "Bok choy", "53": "Broccoli",
            "54": "Butternut squash", "55": "Cabbage", "56": "Carrot",
            "57": "Cauliflower", "58": "Celery", "59": "Collard greens",
            "60": "Corn", "61": "Cucumber", "62": "Eggplant",
            "63": "Garlic", "64": "Green beans", "86": "Green onion",
            "65": "Jalapeño chili pepper", "66": "Kale", "67": "Leek",
            "68": "Lettuce", "171": "Mixed vegetables", "69": "Mushroom",
            "70": "Napa cabbage", "71": "Onion", "72": "Parsnip",
            "174": "Peas", "73": "Potato", "74": "Pumpkin puree",
            "84": "Radishes", "75": "Rapini", "76": "Rutabaga",
            "77": "Scallion", "78": "Shallot", "79": "Spinach",
            "80": "Sweet potato", "81": "Swiss chard", "82": "Tomato",
            "85": "Turnip", "182": "Yellow beans", "83": "Zucchini"
        }
        
        result = {}
        for id, label in vegetables.items():
            key = self._normalize_key(label)
            result[key] = FilterInfo(
                id=id,
                label=label,
                type="vegetables",
                name=f"vegetables[{id}]"
            )
        return result
    
    def _create_default_fruits(self) -> Dict[str, FilterInfo]:
        """Create default fruit filters."""
        fruits = {
            "27": "Apple", "43": "Apricots (dried)", "188": "Avocado",
            "28": "Banana", "29": "Blueberries", "30": "Blueberries (dried)",
            "31": "Cantaloupe", "32": "Cranberries (dried)", "195": "Grapes",
            "172": "Lemon", "173": "Lime", "44": "Low bush cranberries",
            "186": "Mango", "33": "Medjool dates", "34": "Mixed berries",
            "35": "Nectarine", "36": "Orange", "37": "Peach",
            "38": "Pear", "39": "Pineapple", "40": "Plum",
            "41": "Raisins", "178": "Raspberries", "42": "Strawberries"
        }
        
        result = {}
        for id, label in fruits.items():
            key = self._normalize_key(label)
            result[key] = FilterInfo(
                id=id,
                label=label,
                type="fruits",
                name=f"fruits[{id}]"
            )
        return result
    
    def _create_default_whole_grains(self) -> Dict[str, FilterInfo]:
        """Create default whole grain filters."""
        whole_grains = {
            "134":"Barley",
            "135":"Bran flakes",
            "136":"Bread (whole grain)",
            "137":"Breadcrumbs",
            "138":"Cornmeal",
            "139":"Couscous",
            "140":"Egg noodles",
            "141":"English muffin",
            "142":"Flaxseed meal",
            "185":"Hominy corn",
            "143":"Kamut puffs",
            "144":"Millet",
            "145":"Oat bran",
            "146":"Oats (large flakes)",
            "147":"Oats (rolled)",
            "148":"Oats (steel cut)",
            "149":"Pasta",
            "150":"Pita",
            "151":"Pumpernickel rye bread",
            "152":"Quinoa",
            "153":"Ramen noodles",
            "154":"Rice (black)",
            "155":"Rice (brown)",
            "156":"Rice (Calrose)",
            "157":"Rice (Jasmine)",
            "158":"Rice (wild)",
            "159":"Rice puffs",
            "160":"Soba noodles (buckwheat)",
            "161":"Sorghum",
            "162":"Tortilla",
            "163":"Vermicelli noodles (brown rice)",
            "164":"Wheat berries",
            "165":"Wheat bran",
            "166":"Wheat germ",
            "167":"Wheat puffs"
        }

        result = {}
        for id, label in whole_grains.items():
            key = self._normalize_key(label)
            result[key] = FilterInfo(
                id=id,
                label=label,
                type="whole_grains",
                name=f"whole_grains[{id}]"
            )
        return result
    
    def _create_default_proteins(self) -> Dict[str, FilterInfo]:
        """Create default protein filters."""
        proteins = {
        "87":"Almond butter",
        "88":"Almonds",
        "89":"Beef",
        "90":"Black beans",
        "91":"Blue cheese",
        "123":"Bocconcini cheese",
        "129":"Cashews",
        "92":"Cheddar cheese",
        "128":"Chia seeds",
        "93":"Chicken",
        "94":"Chickpeas",
        "95":"Clams",
        "96":"Cod",
        "97":"Edamame",
        "98":"Eggs",
        "175":"Egg whites",
        "99":"Feta cheese",
        "133":"Fish",
        "100":"Flank steak",
        "101":"Greek yogurt",
        "127":"Halloumi cheese",
        "187":"Kefir",
        "102":"Kidney beans",
        "103":"Lentils",
        "189":"Lima beans",
        "122":"Milk or plant-based beverage",
        "176":"Miso",
        "104":"Moose",
        "105":"Mozzarella cheese",
        "106":"Parmesan cheese",
        "107":"Peanut butter",
        "108":"Peanut free butter",
        "126":"Peanuts",
        "109":"Pork chops",
        "124":"Pumpkin seeds",
        "110":"Ricotta cheese",
        "111":"Salmon",
        "112":"Sesame seeds",
        "113":"Snapper fillet",
        "190":"Steak",
        "114":"Striploin steak",
        "197":"Sunflower seeds",
        "115":"Swiss cheese",
        "130":"Tahini paste",
        "125":"Tempeh",
        "196":"Tilapia",
        "116":"Tofu",
        "117":"Trout",
        "118":"Tuna",
        "119":"Turkey",
        "121":"Walnuts",
        "120":"Yogurt",
        }

        result = {}
        for id, label in proteins.items():
            key = self._normalize_key(label)
            result[key] = FilterInfo(
                id=id,
                label=label,
                type="proteins",
                name=f"proteins[{id}]"
            )
        return result
    
    def _create_default_meals(self) -> Dict[str, FilterInfo]:
        """Create default meal filters."""
        meals = {
            "45": "Breakfast",
            "46": "Lunch/dinner",
            "47": "Snack"
        }
        
        result = {}
        for id, label in meals.items():
            key = self._normalize_key(label)
            result[key] = FilterInfo(
                id=id,
                label=label,
                type="meals_and_course",
                name=f"meals_and_course[{id}]"
            )
        return result
    
    def _create_default_appliances(self) -> Dict[str, FilterInfo]:
        """Create default cooking appliance filters."""
        appliances = {
            "22": "Blender",
            "23": "Food processor",
            "180": "Grill",
            "26": "Oven",
            "24": "Slow cooker",
            "25": "Stovetop"
        }
        
        result = {}
        for id, label in appliances.items():
            key = self._normalize_key(label)
            result[key] = FilterInfo(
                id=id,
                label=label,
                type="cooking_appliance",
                name=f"cooking_appliance[{id}]"
            )
        return result
    
    # Public methods for using filters
    def add_filter(self, filter_type: str, filter_value: str):
        """Add a filter to the search.
        
        Args:
            filter_type: Type of filter (vegetables, fruits, etc.)
            filter_value: Either the ID or the label of the filter
        """
        # Find the filter ID
        filter_id = self._resolve_filter_id(filter_type, filter_value)
        
        if filter_id:
            if filter_type not in self.active_filters:
                self.active_filters[filter_type] = []
            if filter_id not in self.active_filters[filter_type]:
                self.active_filters[filter_type].append(filter_id)
        else:
            print(f"Warning: Filter '{filter_value}' not found in {filter_type}")
    
    def add_collection(self, collection_name: str):
        """Add a collection filter.
        
        Args:
            collection_name: Name of the collection (e.g., 'vegetarian', 'kid-friendly')
        """
        key = self._normalize_key(collection_name)
        if key in self._collections_data:
            self.add_filter("collection", self._collections_data[key])
        else:
            print(f"Warning: Collection '{collection_name}' not found")
    
    def _resolve_filter_id(self, filter_type: str, filter_value: str) -> Optional[str]:
        """Resolve a filter value to its ID."""
        # If it's already an ID (all digits), return it
        if filter_value.isdigit():
            return filter_value
        
        # Look up by normalized label
        for category, filters in self._filters_data.items():
            if category.lower() == filter_type.lower() or \
               (category == "Meal" and filter_type == "meals_and_course") or \
               (category == "Cooking appliance" and filter_type == "cooking_appliance"):
                key = self._normalize_key(filter_value)
                if key in filters:
                    return filters[key].id
        
        return None
    
    def get_filters_dict(self) -> Dict[str, List[str]]:
        """Return filters in the format expected by URL builder."""
        return self.active_filters
    
    def clear_filters(self):
        """Clear all active filters."""
        self.active_filters = {}
    
    def get_available_filters(self, filter_type: str) -> List[str]:
        """Get list of available filter labels for a given type."""
        for category, filters in self._filters_data.items():
            if category.lower() == filter_type.lower():
                return [f.label for f in filters.values()]
        return []
    
    def get_available_collections(self) -> List[str]:
        """Get list of available collections."""
        return list(self._collections_data.keys())
    
    def force_update(self):
        """Force an update of filters from the website."""
        self.update_filters_from_website()

    def add_filter_safe(self, filter_type: str, filter_value: str) -> bool:
        """
        Add a filter with error handling.
        
        Args:
            filter_type: Type of filter (vegetables, fruits, etc.)
            filter_value: Either the ID or the label of the filter
            
        Returns:
            bool: True if filter was added successfully, False otherwise
        """
        filter_id = self._resolve_filter_id(filter_type, filter_value)
        
        if filter_id:
            if filter_type not in self.active_filters:
                self.active_filters[filter_type] = []
            if filter_id not in self.active_filters[filter_type]:
                self.active_filters[filter_type].append(filter_id)
            return True
        else:
            return False