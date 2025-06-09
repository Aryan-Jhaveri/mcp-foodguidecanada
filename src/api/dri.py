"""
DRI (Dietary Reference Intake) MacronutrientScraper for Health Canada data.

This module provides comprehensive scraping and parsing of Health Canada's
official DRI tables for macronutrients including:
- Reference values for carbohydrate, protein, fat, essential fatty acids, fibre, water
- Additional macronutrient recommendations (saturated fats, trans fats, cholesterol, added sugars)
- Amino acid recommended patterns for protein quality evaluation
- Acceptable Macronutrient Distribution Ranges (AMDRs)
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional, List, Tuple, Union, Any
import re
import json
import os
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass
import time

# Dynamically handle imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Add paths for imports
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

class MacronutrientScraper:
    """
    Scraper for Health Canada's DRI macronutrient reference values.
    
    This class fetches and parses comprehensive macronutrient data from Health Canada's
    official DRI tables, providing structured JSON output for nutrition analysis.
    """
    
    def __init__(self, cache_duration_hours: int = 24, rate_limit: float = 1.5):
        """
        Initialize the MacronutrientScraper.
        
        Args:
            cache_duration_hours: How long to cache scraped data (default 24 hours)
            rate_limit: Seconds to wait between requests (default 1.5)
        """
        self.base_url = "https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/reference-values-macronutrients.html"
        self.cache_duration = timedelta(hours=cache_duration_hours)
        self.session = requests.Session()
        self.rate_limit = rate_limit
        self._last_request_time = 0
        
        # Simple user agent like successful EER scraper
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; CanadaFoodGuide-MCP/2.0)'
        })
        
        # Cache file setup
        self.cache_dir = os.path.join(project_root, 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, 'dri_macronutrients.json')
    
    def _rate_limit_wait(self):
        """Ensure we don't exceed rate limits like CNF scraper."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.rate_limit:
            sleep_time = self.rate_limit - time_since_last
            time.sleep(sleep_time)
        self._last_request_time = time.time()
        
    def fetch_macronutrient_data(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Main method to fetch and parse all macronutrient data from Health Canada DRI tables.
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh data
            
        Returns:
            Dict containing all parsed macronutrient data in structured format
        """
        try:
            # Check cache first unless force refresh
            if not force_refresh and self._is_cache_valid():
                cached_data = self._load_cache()
                if cached_data:
                    return cached_data
            
            # Fetch fresh data from website - simplified like EER scraper
            print("Fetching fresh DRI macronutrient data from Health Canada...")
            self._rate_limit_wait()
            
            response = self.session.get(self.base_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Parse all sections
            result = {
                "status": "success",
                "source": "Health Canada DRI Tables",
                "url": self.base_url,
                "last_updated": datetime.now().isoformat(),
                "reference_values": self._parse_main_reference_table(soup),
                "additional_recommendations": self._parse_additional_recommendations(soup),
                "amino_acid_patterns": self._parse_amino_acid_patterns(soup),
                "amdrs": self._parse_amdrs(soup),
                "footnotes": self._parse_footnotes(soup),
                "data_quality": {
                    "parsing_timestamp": datetime.now().isoformat(),
                    "total_age_groups_parsed": 0,  # Will be calculated
                    "total_nutrients_parsed": 0,   # Will be calculated
                    "parsing_warnings": []
                }
            }
            
            # Calculate data quality metrics
            result["data_quality"]["total_age_groups_parsed"] = len(result["reference_values"])
            result["data_quality"]["total_nutrients_parsed"] = sum(
                len(age_group.get("nutrients", {})) for age_group in result["reference_values"]
            )
            
            # Add detailed validation metrics
            validation_results = self._validate_parsed_values(result)
            result["data_quality"].update(validation_results)
            
            # Save to cache
            self._save_cache(result)
            
            return result
            
        except requests.RequestException as e:
            return {
                "status": "error",
                "error": f"Network error fetching DRI data from Health Canada: {str(e)}",
                "error_type": "network_error"
            }
        except Exception as e:
            return {
                "status": "error", 
                "error": f"Error parsing DRI data: {str(e)}",
                "error_type": "parsing_error"
            }
    
    def _parse_main_reference_table(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Parse the main Table 1 with macronutrient reference values.
        
        This table contains EAR, RDA/AI, and UL values for:
        - Carbohydrate (Digestible)
        - Total Protein 
        - Total Fat
        - Linoleic Acid (n-6)
        - α-linolenic Acid (n-3)
        - Total Fibre
        - Total Water
        
        Args:
            soup: BeautifulSoup object of the webpage
            
        Returns:
            List of dictionaries containing parsed reference values by age group
        """
        reference_values = []
        warnings = []
        
        try:
            # Find the main reference table (Table 1)
            table = soup.find('table', {'id': 'tbl1'})
            if not table:
                warnings.append("Main reference table (tbl1) not found")
                return reference_values
            
            # Parse table headers to understand column structure
            headers = self._parse_table_headers(table)
            
            # Find all data rows (excluding header rows)
            tbody = table.find('tbody')
            if not tbody:
                warnings.append("Table body not found in main reference table")
                return reference_values
            
            rows = tbody.find_all('tr')
            current_category = None
            
            for row in rows:
                # Check if this is a category header row (Infants, Children, Males, etc.)
                category_header = row.find('th', {'class': 'bg-info'})
                if category_header:
                    current_category = self._normalize_text(category_header.get_text(strip=True))
                    continue
                
                # Parse data row
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 18:  # Main table has 18 columns
                    age_group_data = self._parse_reference_row(cells, headers, current_category)
                    if age_group_data:
                        reference_values.append(age_group_data)
            
        except Exception as e:
            warnings.append(f"Error parsing main reference table: {str(e)}")
        
        return reference_values
    
    def _parse_table_headers(self, table) -> Dict[str, int]:
        """Parse table headers to map nutrient names to column indices."""
        headers = {}
        header_rows = table.find('thead').find_all('tr')
        
        # The table has complex multi-row headers, need to parse carefully
        if len(header_rows) >= 2:
            # Second row contains the actual column headers
            header_cells = header_rows[1].find_all('th')
            for i, cell in enumerate(header_cells):
                header_text = cell.get_text(strip=True)
                headers[header_text] = i
        
        return headers
    
    def _parse_reference_row(self, cells, headers: Dict[str, int], category: str) -> Optional[Dict[str, Any]]:
        """Parse a single data row from the reference table."""
        try:
            if len(cells) < 18:
                return None
                
            age_range = cells[0].get_text(strip=True)
            age_range = self._normalize_text(age_range)
            if not age_range:
                return None
            
            # Extract values for each nutrient
            nutrients = {}
            
            # Carbohydrate (columns 1-3: EAR, RDA/AI, UL)
            nutrients['carbohydrate'] = {
                'ear_g_day': self._parse_numeric_value(cells[1]),
                'rda_ai_g_day': self._parse_numeric_value(cells[2]),
                'ul_g_day': self._parse_numeric_value(cells[3]),
                'is_ai': self._check_if_ai(cells[2])
            }
            
            # Protein (columns 4-7: EAR g/kg/day, RDA/AI g/kg/day, RDA/AI g/day, UL g/day)
            nutrients['protein'] = {
                'ear_g_kg_day': self._parse_numeric_value(cells[4]),
                'rda_ai_g_kg_day': self._parse_numeric_value(cells[5]),
                'rda_ai_g_day': self._parse_numeric_value(cells[6]),
                'ul_g_day': self._parse_numeric_value(cells[7]),
                'is_ai': self._check_if_ai(cells[5])
            }
            
            # Total Fat (columns 8-9: AI g/day, UL g/day)
            nutrients['total_fat'] = {
                'ai_g_day': self._parse_numeric_value(cells[8]),
                'ul_g_day': self._parse_numeric_value(cells[9]),
                'is_ai': True  # Fat is always AI
            }
            
            # Linoleic Acid (columns 10-11: AI g/day, UL g/day)
            nutrients['linoleic_acid'] = {
                'ai_g_day': self._parse_numeric_value(cells[10]),
                'ul_g_day': self._parse_numeric_value(cells[11]),
                'is_ai': True
            }
            
            # α-linolenic Acid (columns 12-13: AI g/day, UL g/day)
            nutrients['alpha_linolenic_acid'] = {
                'ai_g_day': self._parse_numeric_value(cells[12]),
                'ul_g_day': self._parse_numeric_value(cells[13]),
                'is_ai': True
            }
            
            # Total Fibre (columns 14-15: AI g/day, UL g/day)
            nutrients['total_fibre'] = {
                'ai_g_day': self._parse_numeric_value(cells[14]),
                'ul_g_day': self._parse_numeric_value(cells[15]),
                'is_ai': True
            }
            
            # Total Water (columns 16-17: AI Litres/day, UL Litres/day)
            nutrients['total_water'] = {
                'ai_litres_day': self._parse_numeric_value(cells[16]),
                'ul_litres_day': self._parse_numeric_value(cells[17]),
                'is_ai': True
            }
            
            return {
                'age_range': age_range,
                'category': category,
                'nutrients': nutrients
            }
            
        except Exception as e:
            return None
    
    def _parse_numeric_value(self, cell) -> Optional[float]:
        """Parse numeric value from table cell, handling special cases."""
        if not cell:
            return None
            
        text = cell.get_text(strip=True)
        
        # Normalize non-breaking spaces and other Unicode whitespace
        text = self._normalize_text(text)
        
        # Handle special cases
        if text in ['ND', 'nd', '', '—', '-', 'n/a', 'N/A']:
            return None
        
        # Remove footnote references (superscript numbers/symbols)
        # Use regex to remove <sup> tags and their content
        clean_text = re.sub(r'<sup[^>]*>.*?</sup>', '', str(cell))
        clean_text = BeautifulSoup(clean_text, 'html.parser').get_text(strip=True)
        clean_text = self._normalize_text(clean_text)
        
        # Extract numeric value
        try:
            # Handle bold formatting (RDA values)
            if cell.find('strong'):
                clean_text = cell.find('strong').get_text(strip=True)
                clean_text = self._normalize_text(clean_text)
            
            # Remove any remaining non-numeric characters except decimal point
            numeric_text = re.sub(r'[^\d.]', '', clean_text)
            
            if numeric_text:
                return float(numeric_text)
                
        except (ValueError, AttributeError):
            pass
            
        return None
    
    def _check_if_ai(self, cell) -> bool:
        """Check if a value is an AI (has asterisk) vs RDA."""
        if not cell:
            return False
        
        cell_html = str(cell)
        # Look for asterisk in footnote references
        return '*' in cell_html or 'fn*' in cell_html
    
    def _parse_additional_recommendations(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        Parse additional macronutrient recommendations section.
        
        This includes recommendations for:
        - Saturated fatty acids
        - Trans fatty acids  
        - Dietary cholesterol
        - Added sugars
        """
        recommendations = {}
        
        try:
            # Look for the details section with additional recommendations
            details_section = soup.find('details', {'id': 'a1'})
            if details_section:
                # Find the list items
                list_items = details_section.find_all('li')
                
                for item in list_items:
                    text = item.get_text(strip=True)
                    
                    if 'Saturated fatty acids' in text:
                        recommendations['saturated_fatty_acids'] = "As low as possible while consuming a nutritionally adequate diet"
                    elif 'Trans fatty acids' in text:
                        recommendations['trans_fatty_acids'] = "As low as possible while consuming a nutritionally adequate diet"
                    elif 'Dietary cholesterol' in text:
                        recommendations['dietary_cholesterol'] = "As low as possible while consuming a nutritionally adequate diet"
                    elif 'Added sugars' in text:
                        recommendations['added_sugars'] = {
                            "recommendation": "Limit to no more than 25% of total energy",
                            "note": "Although there were insufficient data to set a UL for added sugars, this maximal intake level is suggested to prevent the displacement of foods that are major sources of essential micronutrients."
                        }
        
        except Exception as e:
            recommendations['parsing_error'] = f"Error parsing additional recommendations: {str(e)}"
        
        return recommendations
    
    def _parse_amino_acid_patterns(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Parse the amino acid recommended patterns table.
        
        Returns patterns for essential amino acids in mg/g protein.
        """
        amino_acids = {}
        
        try:
            # Find the amino acid table
            tables = soup.find_all('table', {'class': 'table table-bordered'})
            
            for table in tables:
                # Look for table with amino acid headers
                if table.find('th', string=re.compile(r'Amino acid', re.I)):
                    tbody = table.find('tbody')
                    if tbody:
                        rows = tbody.find_all('tr')
                        
                        for row in rows:
                            cells = row.find_all('td')
                            if len(cells) >= 2:
                                amino_acid = cells[0].get_text(strip=True)
                                pattern_value = self._parse_numeric_value(cells[1])
                                
                                if amino_acid and pattern_value is not None:
                                    amino_acids[amino_acid.lower().replace(' + ', '_').replace(' ', '_')] = {
                                        'name': amino_acid,
                                        'mg_per_g_protein': pattern_value
                                    }
                    
                    # Get the footer note about reference pattern
                    tfoot = table.find('tfoot')
                    if tfoot:
                        amino_acids['reference_note'] = tfoot.get_text(strip=True)
                    
                    break
        
        except Exception as e:
            amino_acids['parsing_error'] = f"Error parsing amino acid patterns: {str(e)}"
        
        return amino_acids
    
    def _parse_amdrs(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Parse the Acceptable Macronutrient Distribution Ranges (AMDRs) table.
        """
        amdrs = {}
        
        try:
            # Find the AMDRs table (Table 2)
            table = soup.find('table', {'id': 'tbl2'})
            if not table:
                # Fallback: look for table with AMDR in caption
                tables = soup.find_all('table')
                for t in tables:
                    caption = t.find('caption')
                    if caption and 'AMDR' in caption.get_text():
                        table = t
                        break
            
            if table:
                tbody = table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 6:
                            age_group = cells[0].get_text(strip=True)
                            
                            amdrs[age_group] = {
                                'carbohydrate_percent': cells[1].get_text(strip=True),
                                'protein_percent': cells[2].get_text(strip=True),
                                'fat_percent': cells[3].get_text(strip=True),
                                'n6_pufa_percent': cells[4].get_text(strip=True),
                                'n3_pufa_percent': cells[5].get_text(strip=True)
                            }
        
        except Exception as e:
            amdrs['parsing_error'] = f"Error parsing AMDRs: {str(e)}"
        
        return amdrs
    
    def _parse_footnotes(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Parse footnotes from the tables."""
        footnotes = {}
        
        try:
            # Look for footnote sections
            footnote_sections = soup.find_all('aside', {'class': 'wb-fnote'})
            
            for section in footnote_sections:
                dl = section.find('dl')
                if dl:
                    terms = dl.find_all('dt')
                    definitions = dl.find_all('dd')
                    
                    for term, definition in zip(terms, definitions):
                        footnote_id = term.get('id', '')
                        footnote_text = definition.get_text(strip=True)
                        
                        if footnote_id and footnote_text:
                            footnotes[footnote_id] = footnote_text
        
        except Exception as e:
            footnotes['parsing_error'] = f"Error parsing footnotes: {str(e)}"
        
        return footnotes
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text by handling non-breaking spaces and other Unicode characters."""
        if not text:
            return text
        
        # Replace non-breaking spaces (\u00a0 or \xa0) with regular spaces
        text = text.replace('\u00a0', ' ').replace('\xa0', ' ')
        
        # Replace other Unicode whitespace characters
        text = re.sub(r'\s+', ' ', text)  # Normalize all whitespace to single spaces
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def _flexible_age_match(self, target_age: str, available_age: str) -> bool:
        """Perform flexible matching of age ranges to handle text variations."""
        # Normalize both age strings
        target_norm = self._normalize_text(target_age).lower()
        available_norm = self._normalize_text(available_age).lower()
        
        # Direct match
        if target_norm == available_norm:
            return True
        
        # Try various normalization approaches
        variations = [
            # Remove extra spaces around hyphens
            (re.sub(r'\s*-\s*', '-', target_norm), re.sub(r'\s*-\s*', '-', available_norm)),
            # Standardize year abbreviations
            (re.sub(r'\byears?\b', 'y', target_norm), re.sub(r'\byears?\b', 'y', available_norm)),
            (re.sub(r'\bmonths?\b', 'mo', target_norm), re.sub(r'\bmonths?\b', 'mo', available_norm)),
            # Remove all spaces
            (re.sub(r'\s+', '', target_norm), re.sub(r'\s+', '', available_norm))
        ]
        
        for target_var, available_var in variations:
            if target_var == available_var:
                return True
        
        return False
    
    def _validate_parsed_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parsed DRI values and add quality metrics."""
        validation_results = {
            "total_values_parsed": 0,
            "valid_numeric_values": 0,
            "missing_values": 0,
            "validation_warnings": []
        }
        
        # Validate reference values
        for age_group in data.get("reference_values", []):
            for nutrient_name, nutrient_data in age_group.get("nutrients", {}).items():
                for value_type, value in nutrient_data.items():
                    if value_type.endswith(('_day', '_kg_day', '_litres_day')):
                        validation_results["total_values_parsed"] += 1
                        
                        if value is None:
                            validation_results["missing_values"] += 1
                        elif isinstance(value, (int, float)) and value >= 0:
                            validation_results["valid_numeric_values"] += 1
                        else:
                            validation_results["validation_warnings"].append(
                                f"Invalid value for {nutrient_name}.{value_type}: {value}"
                            )
        
        # Calculate validation percentage
        if validation_results["total_values_parsed"] > 0:
            validation_results["validation_success_rate"] = (
                validation_results["valid_numeric_values"] / 
                validation_results["total_values_parsed"]
            ) * 100
        else:
            validation_results["validation_success_rate"] = 0
        
        return validation_results
    
    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if not os.path.exists(self.cache_file):
            return False
        
        file_time = datetime.fromtimestamp(os.path.getmtime(self.cache_file))
        return datetime.now() - file_time < self.cache_duration
    
    def _load_cache(self) -> Optional[Dict[str, Any]]:
        """Load data from cache file."""
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    
    def _save_cache(self, data: Dict[str, Any]) -> None:
        """Save data to cache file."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")


def get_macronutrient_dri_data(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Convenience function to get DRI macronutrient data.
    
    Args:
        force_refresh: If True, bypass cache and fetch fresh data
        
    Returns:
        Dictionary containing all DRI macronutrient data
    """
    scraper = MacronutrientScraper()
    return scraper.fetch_macronutrient_data(force_refresh=force_refresh)


# Example usage and testing
if __name__ == "__main__":
    scraper = MacronutrientScraper()
    result = scraper.fetch_macronutrient_data()
    
    if result["status"] == "success":
        print("Successfully scraped DRI macronutrient data!")
        print(f"Found {len(result['reference_values'])} age groups")
        print(f"Parsed {len(result['amino_acid_patterns'])} amino acids")
        print(f"Found {len(result['amdrs'])} AMDR age groups")
    else:
        print(f"Error: {result['error']}")