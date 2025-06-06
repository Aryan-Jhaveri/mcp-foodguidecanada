import requests
from bs4 import BeautifulSoup
import json
import time
from typing import Optional, List, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NutrientFileScraper:
    """
    A class to scrape food nutrient information from the Canadian Nutrient File website.
    
    This class provides programmatic access to Health Canada's CNF database for
    searching foods and retrieving detailed nutrient profiles. Designed for MCP
    server integration with proper error handling and rate limiting.
    """
    BASE_URL = "https://food-nutrition.canada.ca/cnf-fce"

    def __init__(self, rate_limit: float = 1.0):
        """
        Initializes the scraper with a session object and standard browser headers.
        
        Args:
            rate_limit: Seconds to wait between requests to be respectful of the server
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        self._csrf_token = None
        self.rate_limit = rate_limit
        self._last_request_time = 0

    def _rate_limit_wait(self):
        """Ensure we don't exceed rate limits."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.rate_limit:
            sleep_time = self.rate_limit - time_since_last
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _get_csrf_token(self, soup: BeautifulSoup) -> bool:
        """Helper to find and store CSRF token from a BeautifulSoup object."""
        try:
            csrf_tag = soup.find('input', {'name': '_csrf'})
            if csrf_tag and csrf_tag.has_attr('value'):
                self._csrf_token = csrf_tag['value']
                return True
            return False
        except Exception as e:
            logger.error(f"Error extracting CSRF token: {e}")
            return False

    def search_food(self, food_name: str) -> Optional[List[Dict[str, str]]]:
        """
        Searches for a food by name in the CNF database.
        
        Args:
            food_name: Name of the food to search for (e.g., 'potatoes', 'honey')
            
        Returns:
            List of dictionaries with 'food_code' and 'food_name' keys, or None if error
        """
        if not food_name or not food_name.strip():
            logger.error("Food name cannot be empty")
            return None

        search_page_url = f"{self.BASE_URL}/newSearch"
        
        try:
            self._rate_limit_wait()
            logger.info(f"Searching CNF for: '{food_name}'")
            
            # Get search page to obtain CSRF token
            get_response = self.session.get(search_page_url)
            get_response.raise_for_status()

            soup = BeautifulSoup(get_response.text, 'html.parser')
            if not self._get_csrf_token(soup):
                logger.error("Could not find CSRF token on search page")
                return None

            # Submit search request with DataTables parameters to get all results
            payload = {
                "foodName": food_name.strip(), 
                "foodId": "", 
                "_csrf": self._csrf_token,
                # DataTables parameters to show all results (not just default 10-25)
                "draw": "1",
                "start": "0", 
                "length": "-1",  # -1 means "All" in DataTables dropdown
                "search[value]": "",
                "search[regex]": "false"
            }
            
            self._rate_limit_wait()
            post_response = self.session.post(f"{self.BASE_URL}/doSearch", data=payload)
            post_response.raise_for_status()

            # Parse search results
            results_soup = BeautifulSoup(post_response.text, 'html.parser')
            results = []
            
            for row in results_soup.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) == 2 and cells[0].find('a'):
                    food_code = cells[0].find('a').text.strip()
                    food_name_text = cells[1].text.strip()
                    results.append({
                        "food_code": food_code, 
                        "food_name": food_name_text
                    })
            
            # Update CSRF token for subsequent requests
            self._get_csrf_token(results_soup)
            
            logger.info(f"Found {len(results)} food matches")
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during food search: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during food search: {e}")
            return None

    def get_serving_info(self, food_code: str) -> tuple[Optional[Dict[str, str]], Optional[str]]:
        """
        Retrieves available serving sizes and refuse information for a given food code.
        
        Args:
            food_code: CNF food code (e.g., '4941')
            
        Returns:
            Tuple of (serving_options_dict, refuse_info_string), or (None, None) if error
        """
        if not food_code or not food_code.strip():
            logger.error("Food code cannot be empty")
            return None, None

        serving_page_url = f"{self.BASE_URL}/serving-portion?id={food_code}"
        
        try:
            self._rate_limit_wait()
            logger.info(f"Getting serving info for food code: {food_code}")
            
            response = self.session.get(serving_page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if not self._get_csrf_token(soup):
                logger.error("Could not find CSRF token on serving info page")
                return None, None

            # Extract ALL serving options (including unchecked ones)
            serving_options = {}
            # Look for the fieldset containing serving size options
            fieldset = soup.find('fieldset')
            if fieldset:
                # Find all serving size input checkboxes within the fieldset
                for opt in fieldset.find_all('input', {'name': 'selectedItems'}):
                    if opt.has_attr('value') and opt.has_attr('id'):
                        # Find the associated label using the 'for' attribute
                        label = soup.find('label', {'for': opt['id']})
                        if label:
                            serving_options[opt['value']] = {
                                'description': label.text.strip(),
                                'checked': opt.has_attr('checked'),
                                'value_id': opt['value']
                            }
            
            # Fallback to original method if fieldset approach doesn't work
            if not serving_options:
                for opt in soup.find_all('input', {'name': 'selectedItems'}):
                    if opt.has_attr('value'):
                        label = opt.find_next('label')
                        if label:
                            serving_options[opt['value']] = label.text.strip()

            # Extract refuse information
            refuse_info = "Not found"
            refuse_div = soup.find('div', class_='well well-sm')
            if refuse_div and 'Refuse:' in refuse_div.text:
                refuse_info = ' '.join(refuse_div.text.strip().split())

            logger.info(f"Found {len(serving_options)} serving options")
            return serving_options, refuse_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error getting serving info: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error getting serving info: {e}")
            return None, None

    def get_nutrient_profile(self, food_code: str, serving_options: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Submits the form to generate the nutrient profile and scrapes the resulting table.
        
        Args:
            food_code: CNF food code
            serving_options: Dictionary of serving options from get_serving_info()
            
        Returns:
            Dictionary with nutrient data organized by category, or None if error
        """
        if not food_code or not serving_options:
            logger.error("Food code and serving options are required")
            return None

        report_url = f"{self.BASE_URL}/report-rapport"
        
        # Handle both old format (strings) and new format (dict with metadata)
        serving_keys = []
        for key, value in serving_options.items():
            if isinstance(value, dict):
                # New format with metadata
                serving_keys.append(key)
            else:
                # Old format (string values)
                serving_keys.append(key)
        
        payload = {
            "foodId": food_code,
            "selectedItems": serving_keys,  # Select all available servings
            "_csrf": self._csrf_token
        }

        try:
            self._rate_limit_wait()
            logger.info(f"Getting nutrient profile for food code: {food_code}")
            
            response = self.session.post(report_url, data=payload)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the nutrient report table
            table = soup.find('table', id='nutrReport')
            if not table:
                logger.error("Nutrient report table not found")
                return {"error": "Nutrient report table not found"}

            # Parse the complex nutrient table structure
            headers = []
            thead = table.find('thead')
            if thead:
                headers = [
                    th.text.strip().replace('\n', ' ').replace('\r', '').replace('  ', ' ') 
                    for th in thead.find_all('th')
                ]

            nutrient_data = {}
            current_group = "General"

            # Process table body sections
            for body in table.find_all('tbody'):
                for row in body.find_all('tr'):
                    if 'active' in row.get('class', []):
                        # This is a category header row
                        current_group = row.th.text.strip() if row.th else "Unknown"
                        if current_group not in nutrient_data:
                            nutrient_data[current_group] = []
                    else:
                        # This is a nutrient data row
                        cols = row.find_all(['th', 'td'])
                        if cols:
                            nutrient_entry = {}
                            for i, col in enumerate(cols):
                                if i < len(headers):
                                    nutrient_entry[headers[i]] = col.text.strip()
                            
                            if current_group not in nutrient_data:
                                nutrient_data[current_group] = []
                            nutrient_data[current_group].append(nutrient_entry)

            logger.info(f"Successfully parsed nutrient profile with {len(nutrient_data)} categories")
            return nutrient_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error generating nutrient profile: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating nutrient profile: {e}")
            return None

    def get_complete_food_profile(self, food_code: str) -> Optional[Dict[str, Any]]:
        """
        Convenience method to get complete food information in one call.
        
        Args:
            food_code: CNF food code
            
        Returns:
            Dictionary with serving info and complete nutrient profile, or None if error
        """
        serving_options, refuse_info = self.get_serving_info(food_code)
        
        if not serving_options:
            logger.error(f"Could not get serving info for food code: {food_code}")
            return None
            
        nutrient_profile = self.get_nutrient_profile(food_code, serving_options)
        
        if not nutrient_profile:
            logger.error(f"Could not get nutrient profile for food code: {food_code}")
            return None
            
        return {
            "food_code": food_code,
            "serving_options": serving_options,
            "refuse_info": refuse_info,
            "nutrient_profile": nutrient_profile
        }

    def search_and_get_profile(self, food_name: str, food_index: int = 0) -> Optional[Dict[str, Any]]:
        """
        Convenience method to search for a food and get the complete profile for the first match.
        
        Args:
            food_name: Name of food to search for
            food_index: Index of search result to use (default: 0 for first match)
            
        Returns:
            Complete food profile dictionary, or None if error
        """
        search_results = self.search_food(food_name)
        
        if not search_results or len(search_results) <= food_index:
            logger.error(f"No food found at index {food_index} for search: {food_name}")
            return None
            
        selected_food = search_results[food_index]
        food_code = selected_food['food_code']
        
        logger.info(f"Selected food: {selected_food['food_name']} (Code: {food_code})")
        
        profile = self.get_complete_food_profile(food_code)
        if profile:
            profile['selected_food'] = selected_food
            profile['search_results'] = search_results
            
        return profile