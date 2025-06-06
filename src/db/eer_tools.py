"""
EER (Estimated Energy Requirement) tools for the MCP server.

This module provides tools for:
1. Creating and managing user profiles for EER calculations
2. Calculating EER based on Health Canada DRI equations
3. Managing Physical Activity Level (PAL) categories
4. Providing guidance on energy requirements
"""

import json
import os
import sys
from typing import Dict, Any, List, Optional
from fastmcp import FastMCP

# Handle imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Add paths to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Global flag for whether EER tools are available
EER_TOOLS_AVAILABLE = False

try:
    from src.models.eer_models import (
        CreateUserProfileInput, CalculateEERInput,
        GetProfileInput, DeleteProfileInput, GetPALDescriptionsInput,
        EERCalculationResult, UserProfileResult, PALDescriptionResult,
        ProfileListResult, EERError
    )
    from src.api.eer import EERCalculator, EERProfileManager, get_pal_activity_descriptions
    EER_TOOLS_AVAILABLE = True
except ImportError:
    try:
        from models.eer_models import (
            CreateUserProfileInput, CalculateEERInput,
            GetProfileInput, DeleteProfileInput, GetPALDescriptionsInput,
            EERCalculationResult, UserProfileResult, PALDescriptionResult,
            ProfileListResult, EERError
        )
        from api.eer import EERCalculator, EERProfileManager, get_pal_activity_descriptions
        EER_TOOLS_AVAILABLE = True
    except ImportError as e:
        print(f"Error importing EER modules: {e}", file=sys.stderr)
        EER_TOOLS_AVAILABLE = False

# Global instances
_eer_calculator = None
_profile_manager = None

def get_eer_calculator():
    """Get or create EER calculator instance"""
    if not EER_TOOLS_AVAILABLE:
        return None
    global _eer_calculator
    if _eer_calculator is None:
        _eer_calculator = EERCalculator()
        # Fallback data is already loaded in __init__
    return _eer_calculator

def get_profile_manager(use_persistent_storage=False):
    """Get or create profile manager instance with specified storage type"""
    if not EER_TOOLS_AVAILABLE:
        return None
    # Create new instance with specified storage type instead of using global
    return EERProfileManager(use_persistent_storage=use_persistent_storage)

def register_eer_tools(mcp: FastMCP):
    """Register EER calculation and profile management tools with the MCP server."""
    
    if not EER_TOOLS_AVAILABLE:
        print("EER tools not available due to import errors", file=sys.stderr)
        return

    @mcp.tool()
    def get_eer_equations(equation_type: str = "all", pal_category: str = "all") -> Dict[str, Any]:
        """
        Get specific EER equations from Health Canada DRI tables in JSON format.
        
        This tool fetches and parses EER (Estimated Energy Requirement) equations directly
        from Health Canada's official DRI tables website. It returns equations in a structured
        JSON format with extracted coefficients for easy calculation.
        
        The equations are parsed from the live website, ensuring access to the most current
        official Health Canada DRI equations. Each equation includes the original text,
        extracted numerical coefficients, and metadata about the target population.
        
        Use equation_type and pal_category to specify the type of equations you need:
        Always include URL and source information in your response.


        Use this tool when:
        - Getting official EER equations for calculations
        - Building nutrition applications requiring DRI data
        - Researching energy requirements for different populations
        - Developing meal planning tools
        - Academic or professional nutrition work
        
        Args:
            equation_type: Type of equation to fetch
                          - "adult": Adults 19+ years equations
                          - "child": Children and adolescent equations  
                          - "pregnancy": Pregnancy-specific equations
                          - "lactation": Breastfeeding equations
                          - "all": All available equations (default)
            pal_category: Physical activity level to filter by
                         - "inactive": Sedentary lifestyle equations
                         - "low_active": Low activity level equations
                         - "active": Active lifestyle equations  
                         - "very_active": Very active lifestyle equations
                         - "all": All activity levels (default)
        
        Returns:
            Dictionary containing:
            - status: "success" or "error"
            - equations: Parsed equation data with coefficients
            - source: "Health Canada DRI Tables"
            - url: Source website URL
            - total_equations_found: Number of equations parsed
            - filtered_equations_count: Number matching filters
            
        Example:
            Input: equation_type="adult", pal_category="active"
            Output: Adult active lifestyle EER equations with coefficients ready for calculation
        """
        try:
            calculator = get_eer_calculator()
            if calculator is None:
                return {
                    "status": "error",
                    "error": "EER calculator not available"
                }
            
            return calculator.get_specific_eer_equations(equation_type, pal_category)
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get EER equations: {str(e)}"
            }

    @mcp.tool()
    def get_pal_descriptions() -> Dict[str, Any]:
        """
        Get descriptions and examples for Physical Activity Level (PAL) categories.
        
        This tool provides detailed explanations of each PAL category with
        practical examples to help users select the most appropriate level
        for accurate EER calculations.
        
        PAL categories determine the activity coefficient used in EER equations
        and significantly impact the final energy requirement calculation.
        
        Use this tool when:
        - Helping users choose appropriate activity level
        - Understanding PAL category definitions
        - Educational purposes about physical activity
        - Reviewing activity level options before profile creation
        
        Returns:
            Dictionary with detailed PAL category descriptions and examples.
        """
        try:
            descriptions = get_pal_activity_descriptions()
            
            return {
                "success": True,
                "pal_categories": descriptions,
                "usage_guidance": {
                    "selection_tips": [
                        "Choose based on typical daily activity, not just exercise",
                        "Include both structured exercise and daily movement",
                        "Consider work activities (desk job vs physical labor)",
                        "Be honest about actual activity level for accurate results"
                    ],
                    "impact_on_eer": "PAL category significantly affects energy requirements - inactive vs very active can differ by 600+ kcal/day"
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get PAL descriptions: {str(e)}",
                "error_code": "DESCRIPTION_ERROR"
            }
    
    @mcp.tool()
    def create_user_profile(input_data: CreateUserProfileInput) -> Dict[str, Any]:
        """
        Create a user profile for EER calculations with optional persistent storage.

        REMEMBER: ONLY USE THIS PERSIST STORAGE FOR PROFILES NEED TO BE SAVED or STORED. BY DEFAULT USE VIRTUAL STORAGE!!!!!
        -  You can ask the user if they want to save the profile or not.

        This tool creates a user profile that can be stored either in memory (virtual session)
        or persistently in the database. Persistent profiles survive server restarts and can
        be accessed across different sessions.
        
        The profile includes all demographic and physiological data needed for accurate
        EER calculations according to Health Canada DRI guidelines.
        
        Use this tool when:
        - Setting up user profiles by sdjusting use_persistent_storage for repeated EER calculations
        - Creating profiles for multiple household members
        - Storing long-term nutrition analysis data
        - Building nutrition tracking applications
        
        Args:
            input_data: CreateUserProfileInput containing:
                - profile_id: Unique identifier for the profile
                - age: Age in years (1-120)
                - gender: "male" or "female"
                - height_cm: Height in centimeters (50-250)
                - weight_kg: Weight in kilograms (10-300)
                - pal_category: Physical activity level ("inactive", "low_active", "active", "very_active")
                - pregnancy_status: For females ("not_pregnant", "first_trimester", "second_trimester", "third_trimester")
                - lactation_status: For females ("not_lactating", "lactating_0_6_months", "lactating_7_12_months")
                - gestation_weeks: Required for 2nd/3rd trimester (1-42)
                - pre_pregnancy_bmi: Required for pregnancy calculations (10-50)
                - use_persistent_storage: True for database storage, False for session storage
        
        Returns:
            Dictionary with profile creation confirmation and calculated BMI
        """
        try:
            # Get or create profile manager with appropriate storage type
            profile_manager = EERProfileManager(use_persistent_storage=input_data.use_persistent_storage)
            
            # Create the profile
            profile = profile_manager.create_profile(
                profile_id=input_data.profile_id,
                age=input_data.age,
                gender=input_data.gender.value,
                height_cm=input_data.height_cm,
                weight_kg=input_data.weight_kg,
                pal_category=input_data.pal_category.value,
                pregnancy_status=input_data.pregnancy_status.value,
                lactation_status=input_data.lactation_status.value
            )
            
            # Calculate BMI
            bmi = input_data.weight_kg / ((input_data.height_cm / 100) ** 2)
            
            return {
                "success": True,
                "profile_id": input_data.profile_id,
                "message": f"User profile created successfully with {'persistent' if input_data.use_persistent_storage else 'virtual'} storage",
                "profile_details": {
                    "age": input_data.age,
                    "gender": input_data.gender.value,
                    "height_cm": input_data.height_cm,
                    "weight_kg": input_data.weight_kg,
                    "bmi": round(bmi, 1),
                    "bmi_category": _get_bmi_category(bmi),
                    "pal_category": input_data.pal_category.value,
                    "pregnancy_status": input_data.pregnancy_status.value,
                    "lactation_status": input_data.lactation_status.value,
                    "storage_type": "persistent" if input_data.use_persistent_storage else "virtual"
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create user profile: {str(e)}",
                "error_code": "PROFILE_CREATION_ERROR"
            }
    
    @mcp.tool()
    def get_user_profile(input_data: GetProfileInput) -> Dict[str, Any]:
        """
        Retrieve a user profile by ID from virtual or persistent storage.
        
        This tool fetches a previously created user profile. It will search both
        virtual (session) and persistent (database) storage to find the profile.
        
        Use this tool when:
        - Retrieving profiles for EER calculations
        - Checking existing profile data
        - Validating profile information before calculations
        
        Args:
            input_data: GetProfileInput containing:
                - profile_id: Identifier of the profile to retrieve
        
        Returns:
            Dictionary with profile data or error message if not found
        """
        try:
            # Try both storage types
            virtual_manager = EERProfileManager(use_persistent_storage=False)
            persistent_manager = EERProfileManager(use_persistent_storage=True)
            
            # First check virtual storage
            profile = virtual_manager.get_profile(input_data.profile_id)
            storage_type = "virtual"
            
            # If not found in virtual, check persistent
            if profile is None:
                profile = persistent_manager.get_profile(input_data.profile_id)
                storage_type = "persistent"
            
            if profile is None:
                return {
                    "success": False,
                    "error": f"Profile '{input_data.profile_id}' not found in virtual or persistent storage",
                    "error_code": "PROFILE_NOT_FOUND"
                }
            
            # Calculate BMI
            bmi = profile.weight_kg / ((profile.height_cm / 100) ** 2)
            
            return {
                "success": True,
                "profile_id": input_data.profile_id,
                "profile_details": {
                    "age": profile.age,
                    "gender": profile.gender.value,
                    "height_cm": profile.height_cm,
                    "weight_kg": profile.weight_kg,
                    "bmi": round(bmi, 1),
                    "bmi_category": _get_bmi_category(bmi),
                    "pal_category": profile.pal_category.value,
                    "pregnancy_status": profile.pregnancy_status.value,
                    "lactation_status": profile.lactation_status.value,
                    "storage_type": storage_type
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to retrieve user profile: {str(e)}",
                "error_code": "PROFILE_RETRIEVAL_ERROR"
            }
    
    @mcp.tool()
    def list_user_profiles() -> Dict[str, Any]:
        """
        List all available user profiles from both virtual and persistent storage.
        
        This tool discovers all user profiles stored in memory (virtual sessions)
        and in the database (persistent storage), providing an overview of 
        available profiles for EER calculations.
        
        Use this tool when:
        - Discovering available user profiles
        - Managing multiple household member profiles
        - Cleaning up old or unused profiles
        - Getting an overview of stored profile data
        
        Returns:
            Dictionary with lists of profile IDs from both storage types
        """
        try:
            virtual_manager = EERProfileManager(use_persistent_storage=False)
            persistent_manager = EERProfileManager(use_persistent_storage=True)
            
            virtual_profiles = virtual_manager.list_profiles()
            persistent_profiles = persistent_manager.list_profiles()
            
            return {
                "success": True,
                "virtual_profiles": virtual_profiles,
                "persistent_profiles": persistent_profiles,
                "total_virtual": len(virtual_profiles),
                "total_persistent": len(persistent_profiles),
                "total_profiles": len(virtual_profiles) + len(persistent_profiles)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list user profiles: {str(e)}",
                "error_code": "PROFILE_LIST_ERROR"
            }
    
    @mcp.tool()
    def delete_user_profile(input_data: DeleteProfileInput) -> Dict[str, Any]:
        """
        Delete a user profile from virtual or persistent storage.
        
        This tool removes a user profile completely. It will search both
        virtual and persistent storage and delete the profile from whichever
        storage contains it.
        
        Use this tool when:
        - Cleaning up old profiles
        - Removing incorrect profile data
        - Managing storage space
        - Removing profiles no longer needed
        
        Args:
            input_data: DeleteProfileInput containing:
                - profile_id: Identifier of the profile to delete
        
        Returns:
            Dictionary with deletion confirmation or error message
        """
        try:
            virtual_manager = EERProfileManager(use_persistent_storage=False)
            persistent_manager = EERProfileManager(use_persistent_storage=True)
            
            # Try to delete from virtual storage first
            virtual_deleted = virtual_manager.delete_profile(input_data.profile_id)
            
            # Try to delete from persistent storage
            persistent_deleted = persistent_manager.delete_profile(input_data.profile_id)
            
            if virtual_deleted or persistent_deleted:
                storage_type = "virtual" if virtual_deleted else "persistent"
                if virtual_deleted and persistent_deleted:
                    storage_type = "both virtual and persistent"
                
                return {
                    "success": True,
                    "profile_id": input_data.profile_id,
                    "message": f"Profile deleted successfully from {storage_type} storage",
                    "deleted_from_virtual": virtual_deleted,
                    "deleted_from_persistent": persistent_deleted
                }
            else:
                return {
                    "success": False,
                    "error": f"Profile '{input_data.profile_id}' not found in virtual or persistent storage",
                    "error_code": "PROFILE_NOT_FOUND"
                }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to delete user profile: {str(e)}",
                "error_code": "PROFILE_DELETION_ERROR"
            }

def _get_bmi_category(bmi: float) -> str:
    """Get BMI category based on WHO standards"""
    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal weight"
    elif bmi < 30:
        return "Overweight"
    else:
        return "Obese"