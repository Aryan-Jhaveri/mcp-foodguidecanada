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

def get_profile_manager():
    """Get or create profile manager instance"""
    if not EER_TOOLS_AVAILABLE:
        return None
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = EERProfileManager(use_persistent_storage=False)
    return _profile_manager

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