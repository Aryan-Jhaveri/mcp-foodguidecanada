import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional, List, Tuple, Union, Any
import re
import json
import os
import sys
import sqlite3
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

# Dynamically handle imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Add paths for imports
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import database connection after path setup
try:
    from src.db.connection import get_db_connection
except ImportError:
    from db.connection import get_db_connection


class Gender(Enum):
    MALE = "male"
    FEMALE = "female"

class PALCategory(Enum):
    INACTIVE = "inactive"
    LOW_ACTIVE = "low_active" 
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"

class LifeStage(Enum):
    INFANT_0_3_MONTHS = "0_to_3_months"
    INFANT_3_6_MONTHS = "3_to_6_months"
    INFANT_6_12_MONTHS = "6_to_12_months"
    TODDLER_1_3_YEARS = "1_to_3_years"
    CHILD_3_TO_9 = "3_to_9_years"
    CHILD_9_TO_14 = "9_to_14_years"
    ADOLESCENT_14_TO_19 = "14_to_19_years"
    ADULT_19_PLUS = "19_years_plus"


class PregnancyStatus(Enum):
    NOT_PREGNANT = "not_pregnant"
    FIRST_TRIMESTER = "first_trimester"
    SECOND_TRIMESTER = "second_trimester"
    THIRD_TRIMESTER = "third_trimester"

class LactationStatus(Enum):
    NOT_LACTATING = "not_lactating"
    LACTATING_0_6_MONTHS = "lactating_0_6_months"
    LACTATING_7_12_MONTHS = "lactating_7_12_months"

@dataclass
class UserProfile:
    """User profile for EER calculations"""
    age: int
    gender: Gender
    height_cm: float
    weight_kg: float
    pal_category: PALCategory
    pregnancy_status: PregnancyStatus = PregnancyStatus.NOT_PREGNANT
    lactation_status: LactationStatus = LactationStatus.NOT_LACTATING
    bmi: Optional[float] = None
    gestation_weeks: Optional[int] = None
    pre_pregnancy_bmi: Optional[float] = None
    
    def __post_init__(self):
        """Calculate BMI if not provided"""
        if self.bmi is None:
            height_m = self.height_cm / 100
            self.bmi = self.weight_kg / (height_m ** 2)
    
    def get_life_stage(self) -> LifeStage:
        """Determine life stage based on age"""
        if self.age < 0.25:  # 0-3 months (0.25 years = 3 months)
            return LifeStage.INFANT_0_3_MONTHS
        elif self.age < 0.5:  # 3-6 months
            return LifeStage.INFANT_3_6_MONTHS
        elif self.age < 1:  # 6-12 months
            return LifeStage.INFANT_6_12_MONTHS
        elif 1 <= self.age < 3:
            return LifeStage.TODDLER_1_3_YEARS
        elif 3 <= self.age < 9:
            return LifeStage.CHILD_3_TO_9
        elif 9 <= self.age < 14:
            return LifeStage.CHILD_9_TO_14
        elif 14 <= self.age < 19:
            return LifeStage.ADOLESCENT_14_TO_19
        else:
            return LifeStage.ADULT_19_PLUS

class EERCalculator:
    """
    Estimated Energy Requirement calculator using Health Canada DRI equations.
    
    Fetches specific equations from:
    https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/equations-estimate-energy-requirement.html
    """
    
    def __init__(self):
        self.base_url = "https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; CanadaFoodGuide-MCP/2.0)'
        })
    
    def get_specific_eer_equations(self, equation_type: str = "all", pal_category: str = "all") -> Dict[str, Any]:
        """
        Get specific EER equations from Health Canada DRI tables in JSON format.
        
        Args:
            equation_type: Type of equation ("adult", "child", "pregnancy", "lactation", "all")
            pal_category: PAL category ("inactive", "low_active", "active", "very_active", "all")
        
        Returns:
            Dictionary with equations in JSON format
        """
        url = f"{self.base_url}/equations-estimate-energy-requirement.html"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Parse equations from the fetched HTML
            equations = self._parse_equations_from_html(soup)
            
            # Filter based on requested type and PAL category
            filtered_equations = {}
            
            for eq_id, eq_data in equations.items():
                if equation_type != "all" and equation_type not in eq_id:
                    continue
                if pal_category != "all" and pal_category not in eq_id:
                    continue
                filtered_equations[eq_id] = eq_data
            
            return {
                "status": "success",
                "equation_type": equation_type,
                "pal_category": pal_category,
                "equations": filtered_equations,
                "source": "Health Canada DRI Tables",
                "url": url,
                "total_equations_found": len(equations),
                "filtered_equations_count": len(filtered_equations)
            }
            
        except requests.RequestException as e:
            return {
                "status": "error", 
                "error": f"Failed to fetch DRI equations: {e}",
                "equations": {}
            }
    
    def _parse_equations_from_html(self, soup: BeautifulSoup) -> Dict[str, Dict[str, Any]]:
        """
        Parse EER equations from fetched HTML content.
        
        Args:
            soup: BeautifulSoup object of the DRI equations page
        
        Returns:
            Dictionary of parsed equations in JSON format
        """
        equations = {}
        
        # Find all h2 headers to identify sections
        sections = soup.find_all('h2')
        
        for section in sections:
            section_title = section.get_text().strip()
            
            # Determine section type from title (normalize whitespace)
            normalized_title = ' '.join(section_title.split())
            
            if 'Adults' in normalized_title and '19 years and older' in normalized_title:
                section_type = 'adult'
            elif 'Children' in normalized_title and '0 to 3 years' in normalized_title:
                section_type = 'child_0_3'
            elif 'Children' in normalized_title and 'adolescents' in normalized_title and '3 to 18 years' in normalized_title:
                section_type = 'child_adolescent'
            elif 'Pregnancy' in normalized_title:
                section_type = 'pregnancy'
            elif 'Breastfeeding' in normalized_title:
                section_type = 'lactation'
            else:
                continue
            
            # Find the next details element after this h2
            next_element = section.find_next_sibling()
            while next_element:
                if next_element.name == 'details':
                    # Parse equations from this details section
                    parsed_eqs = self._parse_details_section(next_element, section_type, section_title)
                    equations.update(parsed_eqs)
                elif next_element.name == 'h2':
                    # Hit the next section, stop
                    break
                next_element = next_element.find_next_sibling()
        
        return equations
    
    def _parse_details_section(self, details: BeautifulSoup, section_type: str, section_title: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse equations from a details section.
        
        Args:
            details: BeautifulSoup details element
            section_type: Type of section (adult, child, etc.)
            section_title: Title of the parent section
        
        Returns:
            Dictionary of equations from this section
        """
        equations = {}
        
        # Get subsection info from summary
        summary = details.find('summary')
        subsection_info = summary.get_text().strip() if summary else ""
        
        # Check if gender is in the summary (e.g., "Males", "Females")
        current_gender = None
        if 'Male' in subsection_info and 'Female' not in subsection_info:
            current_gender = 'male'
        elif 'Female' in subsection_info:
            current_gender = 'female'
        
        # Find all paragraphs in this details section
        paragraphs = details.find_all('p')
        
        current_pal = None
        
        for p in paragraphs:
            p_text = p.get_text().strip()
            
            # Check for gender headers
            if p_text in ['Males', 'Females'] or p_text.startswith('Males') or p_text.startswith('Females'):
                current_gender = 'male' if 'Male' in p_text else 'female'
                continue
            
            # Check for PAL category headers
            if 'PA CAT' in p_text:
                if 'Inactive' in p_text:
                    current_pal = 'inactive'
                elif 'Low active' in p_text:
                    current_pal = 'low_active'
                elif 'Very active' in p_text:
                    current_pal = 'very_active'
                elif 'Active' in p_text:
                    current_pal = 'active'
                continue
            
            # Look for EER equations
            if 'EER =' in p_text:
                equation_id = self._generate_equation_id(section_type, subsection_info, current_gender, current_pal)
                
                equation_data = {
                    "equation": p_text,
                    "population": section_title,
                    "gender": current_gender,
                    "pal_category": current_pal
                }
                
                # Add subsection info for special cases (BMI category, age group)
                if subsection_info:
                    equation_data["subsection"] = subsection_info
                
                # Try to extract coefficients
                coefficients = self._extract_coefficients_from_equation(p_text)
                if coefficients:
                    equation_data["coefficients"] = coefficients
                
                equations[equation_id] = equation_data
        
        return equations
    
    def _generate_equation_id(self, section_type: str, subsection_info: str, gender: str, pal: str) -> str:
        """Generate a unique ID for an equation."""
        parts = [section_type]
        
        # Add subsection info if relevant
        if subsection_info:
            if 'underweight' in subsection_info.lower():
                parts.append('underweight')
            elif 'normal' in subsection_info.lower():
                parts.append('normal')
            elif 'overweight' in subsection_info.lower():
                parts.append('overweight')
            elif 'obese' in subsection_info.lower():
                parts.append('obese')
            elif '0 to 6 months' in subsection_info:
                parts.append('0_6_months')
            elif '7 to 12 months' in subsection_info:
                parts.append('7_12_months')
            elif 'less than 19' in subsection_info:
                parts.append('under19')
        
        if gender:
            parts.append(gender)
        if pal:
            parts.append(pal)
        
        return '_'.join(parts)
    
    def _extract_coefficients_from_equation(self, equation_text: str) -> Optional[Dict[str, float]]:
        """
        Extract numerical coefficients from EER equation text.
        
        Args:
            equation_text: Text containing the EER equation
        
        Returns:
            Dictionary of coefficients or None if parsing fails
        """
        # Clean up equation text
        text = equation_text.replace('EER =', '').replace('×', '*').replace('[y]', '').replace('[cm]', '').replace('[kg]', '').replace('[weeks]', '')
        
        coefficients = {}
        
        # Extract base coefficient (first number)
        base_match = re.search(r'^[\s]*([+-]?\d+(?:,\d{3})*(?:\.\d+)?)', text.strip())
        if base_match:
            coefficients['base'] = float(base_match.group(1).replace(',', ''))
        
        # Extract age coefficient
        age_match = re.search(r'([+-]?)\s*\(\s*([\d.,]+)\s*\*\s*age', text)
        if age_match:
            sign = -1 if age_match.group(1) == '-' else 1
            value = float(age_match.group(2).replace(',', ''))
            coefficients['age'] = sign * value
        
        # Extract height coefficient
        height_match = re.search(r'([+-]?)\s*\(\s*([\d.,]+)\s*\*\s*height', text)
        if height_match:
            sign = 1 if height_match.group(1) != '-' else -1
            value = float(height_match.group(2).replace(',', ''))
            coefficients['height'] = sign * value
        
        # Extract weight coefficient
        weight_match = re.search(r'([+-]?)\s*\(\s*([\d.,]+)\s*\*\s*weight', text)
        if weight_match:
            sign = 1 if weight_match.group(1) != '-' else -1
            value = float(weight_match.group(2).replace(',', ''))
            coefficients['weight'] = sign * value
        
        # Extract gestation coefficient (for pregnancy equations)
        gestation_match = re.search(r'([+-]?)\s*\(\s*([\d.,]+)\s*\*\s*gestation', text)
        if gestation_match:
            sign = 1 if gestation_match.group(1) != '-' else -1
            value = float(gestation_match.group(2).replace(',', ''))
            coefficients['gestation'] = sign * value
        
        # Extract additional constants (like + 300, + 540 - 140)
        const_matches = re.findall(r'([+-])\s*(\d+)(?!\s*\*)', text)
        if const_matches:
            total_const = 0
            for sign, value in const_matches:
                if sign == '+':
                    total_const += int(value)
                else:
                    total_const -= int(value)
            if total_const != 0:
                coefficients['additional_constant'] = total_const
        
        return coefficients if coefficients else None
    
class EERProfileManager:
    """
    Manager for user profiles used in EER calculations.
    Supports both virtual (session-based) and persistent storage.
    """
    
    def __init__(self, use_persistent_storage: bool = False):
        self.use_persistent_storage = use_persistent_storage
        self.virtual_profiles: Dict[str, UserProfile] = {}
        
    def create_profile(self, 
                      profile_id: str,
                      age: int,
                      gender: str,
                      height_cm: float,
                      weight_kg: float,
                      pal_category: str,
                      pregnancy_status: str = "not_pregnant",
                      lactation_status: str = "not_lactating") -> UserProfile:
        """
        Create a new user profile for EER calculations.
        
        Args:
            profile_id: Unique identifier for the profile
            age: Age in years
            gender: "male" or "female"
            height_cm: Height in centimeters
            weight_kg: Weight in kilograms
            pal_category: Physical activity level category
            pregnancy_status: Pregnancy status (for females)
            lactation_status: Lactation status (for females)
            
        Returns:
            Created UserProfile object
        """
        profile = UserProfile(
            age=age,
            gender=Gender(gender.lower()),
            height_cm=height_cm,
            weight_kg=weight_kg,
            pal_category=PALCategory(pal_category.lower()),
            pregnancy_status=PregnancyStatus(pregnancy_status.lower()),
            lactation_status=LactationStatus(lactation_status.lower())
        )
        
        if self.use_persistent_storage:
            # Store profile in database
            self._save_profile_to_database(profile_id, profile)
        else:
            self.virtual_profiles[profile_id] = profile
        
        return profile
    
    def get_profile(self, profile_id: str) -> Optional[UserProfile]:
        """
        Retrieve a user profile by ID.
        
        Args:
            profile_id: Profile identifier
            
        Returns:
            UserProfile if found, None otherwise
        """
        if self.use_persistent_storage:
            # Retrieve profile from database
            return self._load_profile_from_database(profile_id)
        else:
            return self.virtual_profiles.get(profile_id)
    
    def list_profiles(self) -> List[str]:
        """
        List all available profile IDs.
        
        Returns:
            List of profile identifiers
        """
        if self.use_persistent_storage:
            # List profiles from database
            return self._list_profiles_from_database()
        else:
            return list(self.virtual_profiles.keys())
    
    def delete_profile(self, profile_id: str) -> bool:
        """
        Delete a user profile.
        
        Args:
            profile_id: Profile identifier
            
        Returns:
            True if deleted, False if not found
        """
        if self.use_persistent_storage:
            # Delete profile from database
            return self._delete_profile_from_database(profile_id)
        else:
            if profile_id in self.virtual_profiles:
                del self.virtual_profiles[profile_id]
                return True
            return False
    
    def _save_profile_to_database(self, profile_id: str, profile: 'UserProfile') -> None:
        """Save a user profile to the database."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO user_profiles (
                        profile_id, age, gender, height_cm, weight_kg, pal_category,
                        pregnancy_status, lactation_status, gestation_weeks, pre_pregnancy_bmi
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    profile_id,
                    profile.age,
                    profile.gender.value,
                    profile.height_cm,
                    profile.weight_kg,
                    profile.pal_category.value,
                    profile.pregnancy_status.value,
                    profile.lactation_status.value,
                    getattr(profile, 'gestation_weeks', None),
                    getattr(profile, 'pre_pregnancy_bmi', None)
                ))
                conn.commit()
        except sqlite3.Error as e:
            raise Exception(f"Database error saving profile: {e}")
    
    def _load_profile_from_database(self, profile_id: str) -> Optional['UserProfile']:
        """Load a user profile from the database."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT age, gender, height_cm, weight_kg, pal_category,
                           pregnancy_status, lactation_status, gestation_weeks, pre_pregnancy_bmi
                    FROM user_profiles WHERE profile_id = ?
                """, (profile_id,))
                
                row = cursor.fetchone()
                if row is None:
                    return None
                
                age, gender, height_cm, weight_kg, pal_category, pregnancy_status, lactation_status, gestation_weeks, pre_pregnancy_bmi = row
                
                profile = UserProfile(
                    age=age,
                    gender=Gender(gender),
                    height_cm=height_cm,
                    weight_kg=weight_kg,
                    pal_category=PALCategory(pal_category),
                    pregnancy_status=PregnancyStatus(pregnancy_status),
                    lactation_status=LactationStatus(lactation_status)
                )
                
                # Add optional fields if they exist
                if gestation_weeks is not None:
                    setattr(profile, 'gestation_weeks', gestation_weeks)
                if pre_pregnancy_bmi is not None:
                    setattr(profile, 'pre_pregnancy_bmi', pre_pregnancy_bmi)
                    
                return profile
                
        except sqlite3.Error as e:
            raise Exception(f"Database error loading profile: {e}")
    
    def _list_profiles_from_database(self) -> List[str]:
        """List all profile IDs from the database."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT profile_id FROM user_profiles ORDER BY created_at DESC")
                rows = cursor.fetchall()
                return [row[0] for row in rows]
        except sqlite3.Error as e:
            raise Exception(f"Database error listing profiles: {e}")
    
    def _delete_profile_from_database(self, profile_id: str) -> bool:
        """Delete a profile from the database."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM user_profiles WHERE profile_id = ?", (profile_id,))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            raise Exception(f"Database error deleting profile: {e}")

def get_pal_activity_descriptions() -> Dict[str, Dict[str, str]]:
    """
    Get descriptions of Physical Activity Level categories with examples.
    
    Returns:
        Dictionary with PAL categories and their descriptions
    """
    return {
        "inactive": {
            "description": "Sedentary lifestyle",
            "examples": [
                "Typical daily living activities only",
                "Sitting most of the day",
                "Little to no structured exercise"
            ]
        },
        "low_active": {
            "description": "Low active lifestyle", 
            "examples": [
                "Daily living activities plus 30-60 minutes of moderate activity",
                "Walking 2.5-5 km per day",
                "Light exercise 3-4 times per week"
            ]
        },
        "active": {
            "description": "Active lifestyle",
            "examples": [
                "Daily living activities plus 60+ minutes of moderate activity", 
                "Walking 7.5-10 km per day",
                "Regular structured exercise 4-5 times per week"
            ]
        },
        "very_active": {
            "description": "Very active lifestyle",
            "examples": [
                "Daily living activities plus 60+ minutes of moderate to vigorous activity",
                "Walking 12.5+ km per day", 
                "Intensive training or physical work"
            ]
        }
    }