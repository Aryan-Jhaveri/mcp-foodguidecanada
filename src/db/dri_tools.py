"""
DRI (Dietary Reference Intake) tools for the MCP server.

This module provides tools for:
1. Fetching Health Canada's DRI macronutrient reference values
2. Getting specific macronutrient recommendations by age and gender  
3. Retrieving Acceptable Macronutrient Distribution Ranges (AMDRs)
4. Comparing actual intake against DRI recommendations
5. Accessing amino acid patterns for protein quality evaluation
"""

import json
import os
import sys
from typing import Dict, Any, List, Optional
from fastmcp import FastMCP
from datetime import datetime

# Handle imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Add paths to sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Global flag for whether DRI tools are available
DRI_TOOLS_AVAILABLE = False
SCHEMA_FUNCTIONS_AVAILABLE = False

try:
    from src.models.dri_models import (
        GetMacronutrientDRIInput, GetAMDRInput, CompareIntakeToDRIInput,
        DRIMacronutrientData, DRIError, MacronutrientType, LifeStageCategory
    )
    from src.api.dri import MacronutrientScraper, get_macronutrient_dri_data
    DRI_TOOLS_AVAILABLE = True
except ImportError:
    try:
        from models.dri_models import (
            GetMacronutrientDRIInput, GetAMDRInput, CompareIntakeToDRIInput,
            DRIMacronutrientData, DRIError, MacronutrientType, LifeStageCategory
        )
        from api.dri import MacronutrientScraper, get_macronutrient_dri_data
        DRI_TOOLS_AVAILABLE = True
    except ImportError as e:
        print(f"Error importing DRI modules: {e}", file=sys.stderr)
        DRI_TOOLS_AVAILABLE = False

# Import schema functions for session-aware tools
try:
    from src.db.schema import (
        ensure_dri_session_structure, get_virtual_session_data, get_dri_session_summary
    )
    SCHEMA_FUNCTIONS_AVAILABLE = True
except ImportError:
    try:
        from db.schema import (
            ensure_dri_session_structure, get_virtual_session_data, get_dri_session_summary
        )
        SCHEMA_FUNCTIONS_AVAILABLE = True
    except ImportError as e:
        print(f"Error importing schema functions: {e}", file=sys.stderr)
        SCHEMA_FUNCTIONS_AVAILABLE = False

# Global instance
_dri_scraper = None

def get_dri_scraper():
    """Get or create DRI scraper instance"""
    if not DRI_TOOLS_AVAILABLE:
        return None
    global _dri_scraper
    if _dri_scraper is None:
        _dri_scraper = MacronutrientScraper()
    return _dri_scraper

def register_dri_tools(mcp: FastMCP):
    """Register DRI macronutrient tools with the MCP server."""
    
    if not DRI_TOOLS_AVAILABLE:
        print("DRI tools not available due to import errors", file=sys.stderr)
        return

    @mcp.tool()
    def get_macronutrient_dri_tables(force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get complete DRI macronutrient reference tables from Health Canada.
        
        REMEMBER! ALWAYS USE THIS TOOL BY DEFULT BEFORE USING get_specific_macronutrient_dri!!

        This tool fetches comprehensive macronutrient DRI data directly from Health Canada's
        official DRI tables website. It provides structured access to all reference values
        including EAR, RDA, AI, and UL values for macronutrients across all age groups.
        
        The data includes:
        - Reference values for carbohydrate, protein, fat, essential fatty acids, fibre, water
        - Additional recommendations for saturated fats, trans fats, cholesterol, added sugars  
        - Amino acid patterns for protein quality evaluation (PDCAAS)
        - Acceptable Macronutrient Distribution Ranges (AMDRs) by age group
        - Complete footnotes and explanatory notes from official tables
        
        Use this tool when:
        - Setting up comprehensive nutrition analysis systems
        - Building meal planning applications with DRI compliance
        - Research requiring official Health Canada reference values
        - Developing nutrition education materials
        - Creating nutrition assessment tools
        
        Data is cached for 24 hours to minimize website requests while ensuring access
        to current official Health Canada recommendations.
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh data from website
            
        Returns:
            Complete DRI macronutrient data structure with:
            - status: "success" or "error"
            - reference_values: List of age/gender-specific macronutrient values
            - additional_recommendations: Special recommendations (saturated fats, etc.)
            - amino_acid_patterns: Essential amino acid patterns for protein quality
            - amdrs: Acceptable Macronutrient Distribution Ranges
            - footnotes: Complete footnotes from Health Canada tables
            - data_quality: Parsing metrics and validation information
            
        CRITICAL: This tool provides reference data only. For ALL calculations use simple_math_calculator:
        - Adequacy assessment: simple_math_calculator(expression="(intake/rda)*100", variables={"intake": actual, "rda": from_this_tool})
        - AMDR compliance: simple_math_calculator(expression="(protein_cals/total_cals)*100", variables={"protein_cals": value, "total_cals": total})
        - Deficit calculations: simple_math_calculator(expression="rda - intake", variables={"rda": from_this_tool, "intake": actual})
        """
        try:
            scraper = get_dri_scraper()
            if scraper is None:
                return {
                    "status": "error",
                    "error": "DRI scraper not available",
                    "error_type": "initialization_error"
                }
            
            return scraper.fetch_macronutrient_data(force_refresh=force_refresh)
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to fetch DRI macronutrient data: {str(e)}",
                "error_type": "scraping_error"
            }

    @mcp.tool()
    def get_specific_macronutrient_dri(input_data: GetMacronutrientDRIInput) -> Dict[str, Any]:
        """
        Get DRI values for a specific macronutrient, age group, and gender.
        
        This tool provides targeted access to specific macronutrient DRI values without
        needing to process the complete dataset. Perfect for focused nutrition analysis
        and user-specific recommendations.
        
        Supported macronutrients:
        - carbohydrate: Digestible carbohydrate values
        - protein: Protein values in g/kg/day and g/day
        - total_fat: Total fat adequate intake values
        - linoleic_acid: Essential n-6 fatty acid values  
        - alpha_linolenic_acid: Essential n-3 fatty acid values
        - total_fibre: Dietary fibre adequate intake values
        - total_water: Total water adequate intake values
        
        Use this tool when:
        - Calculating specific nutrient needs for individuals
        - Building personalized nutrition recommendations
        - Comparing single nutrient intakes against DRI values
        - Creating targeted dietary guidance
        
        Args:
            input_data: Contains:
                - age_range: Age range (e.g., "19-30 y", "4-8 y")
                - gender: Gender category ("males", "females") or None for general
                - macronutrient: Type of macronutrient to retrieve
                - force_refresh: Whether to bypass cache
        
        Returns:
            Specific macronutrient DRI data including EAR, RDA/AI, UL values
            with units and footnote references, or error message if not found
            
        CRITICAL: This tool provides reference values only. For ALL calculations use simple_math_calculator:
        - Adequacy percentage: simple_math_calculator(expression="(intake/rda)*100", variables={"intake": actual, "rda": from_this_tool})
        - Deficit/surplus: simple_math_calculator(expression="intake - rda", variables={"intake": actual, "rda": from_this_tool})
        - UL assessment: simple_math_calculator(expression="(intake/ul)*100", variables={"intake": actual, "ul": from_this_tool})
        """
        try:
            # Get complete DRI data
            scraper = get_dri_scraper()
            if scraper is None:
                return {
                    "status": "error", 
                    "error": "DRI scraper not available"
                }
            
            dri_data = scraper.fetch_macronutrient_data(force_refresh=input_data.force_refresh)
            
            if dri_data["status"] != "success":
                return dri_data
            
            # Find matching age group and gender
            target_nutrient = input_data.macronutrient.value
            target_age = input_data.age_range
            target_gender = input_data.gender
            
            matching_groups = []
            scraper = get_dri_scraper()
            for group in dri_data["reference_values"]:
                # Use flexible age matching from scraper
                age_match = scraper._flexible_age_match(target_age, group["age_range"])
                gender_match = (target_gender is None or 
                              target_gender.lower() in group.get("category", "").lower())
                
                if age_match and gender_match:
                    matching_groups.append(group)
            
            if not matching_groups:
                return {
                    "status": "error",
                    "error": f"No DRI data found for age '{target_age}' and gender '{target_gender}'",
                    "available_age_ranges": list(set(g["age_range"] for g in dri_data["reference_values"])),
                    "available_categories": list(set(g["category"] for g in dri_data["reference_values"]))
                }
            
            # Extract nutrient data
            result = {
                "status": "success",
                "macronutrient": target_nutrient,
                "age_range": target_age,
                "gender": target_gender,
                "values": [],
                "source": dri_data["source"],
                "url": dri_data["url"]
            }
            
            for group in matching_groups:
                nutrient_data = group["nutrients"].get(target_nutrient, {})
                if nutrient_data:
                    result["values"].append({
                        "category": group["category"],
                        "nutrient_values": nutrient_data
                    })
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get specific macronutrient DRI: {str(e)}"
            }

    @mcp.tool()
    def get_amdrs(input_data: GetAMDRInput) -> Dict[str, Any]:
        """
        Get Acceptable Macronutrient Distribution Ranges (AMDRs) for an age group.
        
        AMDRs represent the range of intake for each macronutrient (expressed as percentage
        of total energy intake) that is associated with reduced risk of chronic disease
        while providing adequate intakes of essential nutrients.
        
        AMDR ranges provided:
        - Total Carbohydrate: Percentage of total energy
        - Total Protein: Percentage of total energy  
        - Total Fat: Percentage of total energy
        - n-6 polyunsaturated fatty acids (linoleic acid): Percentage of total energy
        - n-3 polyunsaturated fatty acids (α-linolenic acid): Percentage of total energy
        
        Age groups available:
        - 1-3 years: Early childhood ranges
        - 4-18 years: School age through adolescence  
        - 19 years and over: Adult ranges (includes pregnancy and lactation)
        
        Use this tool when:
        - Evaluating overall dietary pattern quality
        - Planning balanced meal compositions
        - Assessing macronutrient distribution in diets
        - Creating nutrition education materials about balanced eating
        - Developing dietary guidelines and recommendations
        
        Args:
            input_data: Contains:
                - age_range: Age range for AMDR lookup (e.g., "1-3 years", "19 years and over")
                - force_refresh: Whether to bypass cache and fetch fresh data
        
        Returns:
            AMDR data with percentage ranges for all macronutrients, or error if age range not found
            
        CRITICAL: This tool provides AMDR ranges only. For ALL calculations use simple_math_calculator:
        - AMDR compliance: simple_math_calculator(expression="(nutrient_cals/total_cals)*100", variables={"nutrient_cals": calculated, "total_cals": total})
        - Energy distribution: simple_math_calculator(expression="(protein_grams * 4)", variables={"protein_grams": intake})
        - Range assessment: simple_math_calculator(expression="amdr_percent - actual_percent", variables={"amdr_percent": from_tool, "actual_percent": calculated})
        """
        try:
            # Get complete DRI data
            scraper = get_dri_scraper()
            if scraper is None:
                return {
                    "status": "error",
                    "error": "DRI scraper not available"
                }
            
            dri_data = scraper.fetch_macronutrient_data(force_refresh=input_data.force_refresh)
            
            if dri_data["status"] != "success":
                return dri_data
            
            # Find matching AMDR data using flexible matching
            amdrs = dri_data.get("amdrs", {})
            target_age = input_data.age_range
            
            # Try direct match first
            if target_age in amdrs:
                matched_key = target_age
            else:
                # Use flexible age matching to handle Unicode characters
                scraper = get_dri_scraper()
                matched_key = None
                for amdr_key in amdrs.keys():
                    if scraper._flexible_age_match(target_age, amdr_key):
                        matched_key = amdr_key
                        break
            
            if matched_key:
                return {
                    "status": "success",
                    "age_range": target_age,
                    "matched_key": matched_key,  # Show what key actually matched
                    "amdrs": amdrs[matched_key],
                    "source": dri_data["source"],
                    "url": dri_data["url"],
                    "note": "AMDRs represent percentage of total energy intake associated with reduced chronic disease risk"
                }
            else:
                return {
                    "status": "error",
                    "error": f"No AMDR data found for age range '{target_age}'",
                    "available_age_ranges": list(amdrs.keys()),
                    "tip": "Try using exact formatting from available_age_ranges, including any special characters"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get AMDR data: {str(e)}"
            }

    @mcp.tool()
    def get_amino_acid_patterns() -> Dict[str, Any]:
        """
        Get amino acid patterns for protein quality evaluation using PDCAAS method.
        
        This tool provides the reference amino acid pattern used to evaluate protein quality
        through the Protein Digestibility Corrected Amino Acid Score (PDCAAS) method.
        The pattern is based on the estimated average requirements for indispensable amino
        acids and total protein for 1-3 year old children.
        
        Essential amino acids included:
        - Histidine: 18 mg/g protein
        - Isoleucine: 25 mg/g protein  
        - Leucine: 55 mg/g protein
        - Lysine: 51 mg/g protein
        - Methionine + Cysteine: 25 mg/g protein
        - Phenylalanine + Tyrosine: 47 mg/g protein
        - Threonine: 27 mg/g protein
        - Tryptophan: 7 mg/g protein
        - Valine: 32 mg/g protein
        
        Use this tool when:
        - Evaluating protein quality in foods and diets
        - Calculating Protein Digestibility Corrected Amino Acid Scores (PDCAAS)
        - Developing protein complementation strategies
        - Assessing adequacy of vegetarian and vegan diets
        - Creating nutrition analysis applications
        - Research involving protein quality assessment
        
        Returns:
            Complete amino acid pattern data with reference values in mg/g protein,
            along with methodology notes and source information
            
        CRITICAL: This tool provides amino acid patterns only. For ALL calculations use simple_math_calculator:
        - PDCAAS calculation: simple_math_calculator(expression="(food_amino/reference_amino)*100", variables={"food_amino": analyzed, "reference_amino": from_this_tool})
        - Protein quality: simple_math_calculator(expression="min_score * digestibility", variables={"min_score": lowest_amino_score, "digestibility": coefficient})
        - Amino acid adequacy: simple_math_calculator(expression="(intake/pattern)*protein_grams", variables={"intake": actual, "pattern": from_tool, "protein_grams": total})
        """
        try:
            # Get complete DRI data
            scraper = get_dri_scraper()
            if scraper is None:
                return {
                    "status": "error",
                    "error": "DRI scraper not available"
                }
            
            dri_data = scraper.fetch_macronutrient_data()
            
            if dri_data["status"] != "success":
                return dri_data
            
            amino_acid_data = dri_data.get("amino_acid_patterns", {})
            
            if amino_acid_data:
                return {
                    "status": "success",
                    "amino_acid_patterns": amino_acid_data,
                    "source": dri_data["source"],
                    "url": dri_data["url"],
                    "methodology": "Based on estimated average requirements for 1-3 year olds",
                    "application": "Use for Protein Digestibility Corrected Amino Acid Score (PDCAAS) calculations"
                }
            else:
                return {
                    "status": "error",
                    "error": "No amino acid pattern data found in DRI tables"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get amino acid patterns: {str(e)}"
            }

    @mcp.tool()
    def compare_intake_to_dri(input_data: CompareIntakeToDRIInput) -> Dict[str, Any]:
        """
        Compare actual macronutrient intake against DRI recommendations.
        
        This tool evaluates how an individual's actual nutrient intake compares to Health
        Canada's DRI recommendations, providing percentage adequacy and recommendations
        for dietary adjustments.
        
        Comparison metrics calculated:
        - Percentage of EAR (Estimated Average Requirement) met
        - Percentage of RDA/AI (Recommended Dietary Allowance/Adequate Intake) met  
        - Assessment against UL (Tolerable Upper Intake Level) if applicable
        - AMDR compliance for macronutrient distribution
        - Risk assessment for inadequate or excessive intake
        
        Use this tool when:
        - Conducting personalized nutrition assessments
        - Providing dietary counseling and recommendations
        - Evaluating dietary adequacy for individuals
        - Creating nutrition improvement plans
        - Research involving dietary intake analysis
        
        Args:
            input_data: Contains:
                - age_range: Individual's age range for DRI lookup
                - gender: Individual's gender category  
                - intake_data: Dict of actual nutrient intakes (nutrient_name: amount)
                - comparison_type: "all" for complete analysis or specific nutrient name
        
        Returns:
            Comprehensive comparison analysis with adequacy percentages, risk assessments,
            and specific recommendations for dietary improvements
            
        CRITICAL: This tool provides structured data for analysis. For ALL calculations use simple_math_calculator:
        - Adequacy percentages: simple_math_calculator(expression="(intake/rda)*100", variables=from_this_tool)
        - Deficit assessment: simple_math_calculator(expression="rda - intake", variables=from_this_tool)
        - UL risk evaluation: simple_math_calculator(expression="(intake/ul)*100", variables=from_this_tool)
        - Multiple nutrient analysis: Use simple_math_calculator for each nutrient separately
        """
        try:
            # Get DRI data for the specified age/gender
            scraper = get_dri_scraper()
            if scraper is None:
                return {
                    "status": "error",
                    "error": "DRI scraper not available"
                }
            
            dri_data = scraper.fetch_macronutrient_data()
            
            if dri_data["status"] != "success":
                return dri_data
            
            # Find matching DRI values
            target_age = input_data.age_range
            target_gender = input_data.gender
            intake_data = input_data.intake_data
            
            matching_dri = None
            scraper = get_dri_scraper()
            for group in dri_data["reference_values"]:
                # Use flexible age matching from scraper
                age_match = scraper._flexible_age_match(target_age, group["age_range"])
                gender_match = (target_gender is None or 
                              target_gender.lower() in group.get("category", "").lower())
                
                if age_match and gender_match:
                    matching_dri = group
                    break
            
            if not matching_dri:
                return {
                    "status": "error",
                    "error": f"No DRI data found for age '{target_age}' and gender '{target_gender}'"
                }
            
            # Perform comparisons
            comparisons = {}
            recommendations = []
            
            for nutrient_name, intake_amount in intake_data.items():
                if nutrient_name in matching_dri["nutrients"]:
                    dri_values = matching_dri["nutrients"][nutrient_name]
                    comparison = _compare_single_nutrient(
                        nutrient_name, intake_amount, dri_values
                    )
                    comparisons[nutrient_name] = comparison
                    
                    # Generate recommendations
                    if comparison.get("adequacy_status") == "inadequate":
                        recommendations.append(f"Increase {nutrient_name} intake")
                    elif comparison.get("adequacy_status") == "excessive":
                        recommendations.append(f"Consider reducing {nutrient_name} intake")
            
            return {
                "status": "success",
                "age_range": target_age,
                "gender": target_gender,
                "comparisons": comparisons,
                "recommendations": recommendations,
                "source": dri_data["source"],
                "url": dri_data["url"]
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "error": f"Failed to compare intake to DRI: {str(e)}"
            }

def _compare_single_nutrient(nutrient_name: str, intake_amount: float, dri_values: Dict[str, Any]) -> Dict[str, Any]:
    """Helper function to compare single nutrient intake against DRI values."""
    comparison = {
        "nutrient": nutrient_name,
        "intake_amount": intake_amount,
        "dri_values": dri_values
    }
    
    # Check against EAR if available
    if dri_values.get("ear_g_day") or dri_values.get("ear_g_kg_day"):
        ear_value = dri_values.get("ear_g_day") or dri_values.get("ear_g_kg_day")
        if ear_value:
            comparison["ear_adequacy_percent"] = (intake_amount / ear_value) * 100
            if comparison["ear_adequacy_percent"] < 50:
                comparison["adequacy_status"] = "very_inadequate"
            elif comparison["ear_adequacy_percent"] < 100:
                comparison["adequacy_status"] = "possibly_inadequate"
            else:
                comparison["adequacy_status"] = "adequate"
    
    # Check against RDA/AI
    rda_ai_key = None
    for key in ["rda_ai_g_day", "ai_g_day", "rda_ai_g_kg_day"]:
        if dri_values.get(key):
            rda_ai_key = key
            break
    
    if rda_ai_key:
        rda_ai_value = dri_values[rda_ai_key]
        comparison["rda_ai_adequacy_percent"] = (intake_amount / rda_ai_value) * 100
        comparison["meets_rda_ai"] = comparison["rda_ai_adequacy_percent"] >= 100
    
    # Check against UL if available
    ul_key = None
    for key in ["ul_g_day", "ul_litres_day"]:
        if dri_values.get(key):
            ul_key = key
            break
    
    if ul_key:
        ul_value = dri_values[ul_key] 
        comparison["ul_percent"] = (intake_amount / ul_value) * 100
        if comparison["ul_percent"] > 100:
            comparison["adequacy_status"] = "excessive"
            comparison["exceeds_ul"] = True
    
    return comparison

# Session-aware DRI tools for enhanced LLM workflow integration (outside the main register function)

def register_session_dri_tools(mcp: FastMCP):
    """Register session-aware DRI tools with the MCP server."""
    
    if not DRI_TOOLS_AVAILABLE or not SCHEMA_FUNCTIONS_AVAILABLE:
        print("Session DRI tools not available due to import errors", file=sys.stderr)
        return

    @mcp.tool()
    def store_dri_tables_in_session(session_id: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Cache complete DRI macronutrient tables in virtual session storage.
        
        This tool fetches and stores comprehensive DRI data in the specified virtual session,
        enabling efficient access to DRI values throughout the session without repeated
        website requests. Perfect for workflows involving multiple DRI lookups and calculations.
        
        WORKFLOW INTEGRATION: Use this tool first in any comprehensive nutrition analysis
        session to cache DRI data once, then use session-based lookup tools for specific values.
        
        Benefits of session storage:
        - Single fetch operation for entire session workflow
        - Consistent data across all DRI operations in session  
        - Reduced website requests and improved performance
        - Enables complex multi-step nutrition analysis workflows
        - Data persists for entire session duration
        
        Use this tool when:
        - Starting comprehensive nutrition analysis sessions
        - Planning to perform multiple DRI lookups or comparisons
        - Building meal planning workflows with DRI compliance checks
        - Creating educational nutrition analysis demonstrations
        - Developing nutrition assessment applications
        
        Args:
            session_id: Virtual session identifier for DRI data storage
            force_refresh: If True, bypass cache and fetch fresh data from Health Canada
            
        Returns:
            Dict with storage confirmation, data summary, and session details
        """
        try:
            # Use imported schema functions
            # Ensure session exists with DRI structures
            if not ensure_dri_session_structure(session_id):
                return {
                    "status": "error",
                    "error": "Failed to create or access DRI session structure"
                }
            
            # Fetch DRI data
            scraper = get_dri_scraper()
            if scraper is None:
                return {
                    "status": "error",
                    "error": "DRI scraper not available"
                }
            
            dri_data = scraper.fetch_macronutrient_data(force_refresh=force_refresh)
            
            if dri_data["status"] != "success":
                return dri_data
            
            # Store in session
            session_data = get_virtual_session_data(session_id)
            if session_data is None:
                return {
                    "status": "error",
                    "error": f"Session {session_id} not accessible"
                }
            
            # Store complete DRI dataset with timestamp
            table_key = f"complete_dri_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            session_data['dri_reference_tables'][table_key] = {
                "stored_at": datetime.now().isoformat(),
                "data": dri_data,
                "force_refresh_used": force_refresh
            }
            
            return {
                "status": "success",
                "message": f"DRI tables cached in session {session_id}",
                "session_id": session_id,
                "table_key": table_key,
                "data_summary": {
                    "total_age_groups": len(dri_data.get("reference_values", [])),
                    "amino_acid_patterns": len(dri_data.get("amino_acid_patterns", {})),
                    "amdr_age_groups": len(dri_data.get("amdrs", {})),
                    "last_updated": dri_data.get("last_updated"),
                    "source": dri_data.get("source")
                },
                "next_steps": [
                    "Use get_dri_lookup_from_session for specific nutrient values",
                    "Use store_dri_user_profile_in_session to store user demographics",
                    "Use calculate_dri_adequacy_in_session for intake assessments"
                ]
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to store DRI tables in session: {str(e)}"
            }

    @mcp.tool()
    def get_dri_lookup_from_session(session_id: str, age_range: str, gender: Optional[str], macronutrient: str) -> Dict[str, Any]:
        """
        Retrieve specific DRI values from session-cached data.
        
        This tool provides fast access to DRI values from data already stored in the virtual
        session, eliminating the need for repeated website requests. Perfect for building
        complex nutrition analysis workflows with multiple DRI lookups.
        
        MATH TOOL INTEGRATION: This tool provides DRI reference values for comparison.
        ALWAYS use simple_math_calculator for any calculations involving these values:
        - Adequacy percentages: simple_math_calculator(expression="(intake/rda)*100", variables={"intake": actual, "rda": dri_value})
        - Deficit calculations: simple_math_calculator(expression="rda - intake", variables={"rda": dri_value, "intake": actual})
        - AMDR compliance: simple_math_calculator(expression="(nutrient_cals/total_cals)*100", variables={"nutrient_cals": value, "total_cals": total})
        
        Prerequisites: Must run store_dri_tables_in_session first to populate session data.
        
        Supported macronutrients:
        - carbohydrate, protein, total_fat, linoleic_acid, alpha_linolenic_acid, total_fibre, total_water
        
        Use this tool when:
        - Looking up specific DRI values during nutrition analysis
        - Building personalized nutrition recommendations
        - Comparing individual nutrients against reference values
        - Creating nutrition education content with official values
        
        Args:
            session_id: Virtual session containing cached DRI data
            age_range: Target age range (e.g., "19-30 y", "4-8 y")
            gender: Target gender ("males", "females") or None for general
            macronutrient: Nutrient type to retrieve values for
            
        Returns:
            Dict with specific DRI values (EAR, RDA/AI, UL) and math tool formulas
        """
        try:
            # Use imported schema functions
            
            session_data = get_virtual_session_data(session_id)
            if session_data is None:
                return {
                    "status": "error",
                    "error": f"Session {session_id} not found"
                }
            
            # Find cached DRI data
            dri_tables = session_data.get('dri_reference_tables', {})
            if not dri_tables:
                return {
                    "status": "error",
                    "error": f"No DRI tables found in session {session_id}. Run store_dri_tables_in_session first.",
                    "suggested_action": "store_dri_tables_in_session"
                }
            
            # Get most recent DRI data
            latest_key = max(dri_tables.keys()) if dri_tables else None
            if not latest_key:
                return {
                    "status": "error",
                    "error": "No valid DRI data found in session"
                }
            
            dri_data = dri_tables[latest_key]["data"]
            
            # Use flexible age matching for lookups
            scraper = get_dri_scraper()
            matching_groups = []
            for group in dri_data["reference_values"]:
                age_match = scraper._flexible_age_match(age_range, group["age_range"])
                gender_match = (gender is None or 
                              gender.lower() in group.get("category", "").lower())
                
                if age_match and gender_match:
                    matching_groups.append(group)
            
            if not matching_groups:
                return {
                    "status": "error",
                    "error": f"No DRI data found for age '{age_range}' and gender '{gender}'",
                    "available_age_ranges": list(set(g["age_range"] for g in dri_data["reference_values"])),
                    "session_id": session_id
                }
            
            # Extract nutrient data and create math formulas
            result = {
                "status": "success",
                "session_id": session_id,
                "macronutrient": macronutrient,
                "age_range": age_range,
                "gender": gender,
                "values": [],
                "math_tool_formulas": {},
                "data_source": f"Session-cached from {dri_data.get('source', 'Health Canada')}"
            }
            
            for group in matching_groups:
                nutrient_data = group["nutrients"].get(macronutrient, {})
                if nutrient_data:
                    values_entry = {
                        "category": group["category"],
                        "nutrient_values": nutrient_data
                    }
                    result["values"].append(values_entry)
                    
                    # Create math tool formulas for common calculations
                    formulas = {}
                    for value_type, value in nutrient_data.items():
                        if value is not None and value_type.endswith(('_day', '_kg_day', '_litres_day')):
                            base_name = value_type.replace('_g_day', '').replace('_g_kg_day', '').replace('_litres_day', '')
                            
                            if 'rda' in value_type or 'ai' in value_type:
                                formulas[f"{base_name}_adequacy_percent"] = {
                                    "expression": "(intake/reference)*100",
                                    "variables": {"reference": value},
                                    "description": f"Calculate adequacy percentage for {macronutrient}"
                                }
                                formulas[f"{base_name}_deficit"] = {
                                    "expression": "reference - intake",
                                    "variables": {"reference": value},
                                    "description": f"Calculate deficit below {value_type} for {macronutrient}"
                                }
            
            result["math_tool_formulas"] = formulas
            
            # Store lookup in session for tracking
            lookup_key = f"{age_range}_{gender}_{macronutrient}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            session_data['dri_lookups'][lookup_key] = {
                "lookup_at": datetime.now().isoformat(),
                "query": {"age_range": age_range, "gender": gender, "macronutrient": macronutrient},
                "result": result
            }
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get DRI lookup from session: {str(e)}"
            }

    @mcp.tool()
    def calculate_dri_from_eer(session_id: str, profile_name: str, eer_energy_kcal: float, age_range: str) -> Dict[str, Any]:
        """
        Calculate specific macronutrient targets based on EER energy requirements and AMDR ranges.
        
        This tool integrates EER (Energy Requirement) calculations with DRI macronutrient 
        distribution recommendations to provide personalized daily macronutrient targets in grams.
        Perfect for complete meal planning workflows that start with energy needs.
        
        CRITICAL WORKFLOW INTEGRATION: This tool provides structured data for calculations.
        ALWAYS use simple_math_calculator for ALL arithmetic operations:
        - Carb grams: simple_math_calculator(expression="(kcal * percent) / 4", variables=from_this_tool)
        - Protein grams: simple_math_calculator(expression="(kcal * percent) / 4", variables=from_this_tool)  
        - Fat grams: simple_math_calculator(expression="(kcal * percent) / 9", variables=from_this_tool)
        - Range validation: simple_math_calculator(expression="actual_percent - target_percent", variables=from_this_tool)
        
        Integration workflow:
        1. Calculate EER using get_eer_equations + simple_math_calculator
        2. Store user profile with store_dri_user_profile_in_session
        3. Use this tool to convert energy to macronutrient targets
        4. Use targets for meal planning and recipe analysis
        
        Calculation approach:
        - Uses AMDR ranges to distribute total energy across macronutrients
        - Provides minimum and maximum gram targets for each macronutrient
        - Includes mid-range targets for practical meal planning
        - Accounts for different caloric densities (carb/protein: 4 kcal/g, fat: 9 kcal/g)
        
        Use this tool when:
        - Converting EER energy requirements to practical macronutrient goals
        - Creating personalized meal planning targets
        - Building comprehensive nutrition analysis workflows
        - Developing nutrition counseling applications
        - Educational demonstrations of energy-to-macro conversion
        
        Args:
            session_id: Virtual session with cached DRI data and user profile
            profile_name: Stored user profile name for demographic reference
            eer_energy_kcal: Total daily energy requirement in kilocalories (from EER calculations)
            age_range: Age range for AMDR lookup (e.g., "19 years and over", "1-3 years")
            
        Returns:
            Dict with macronutrient targets in grams and structured formulas for simple_math_calculator
        """
        try:
            # Use imported schema functions
            
            session_data = get_virtual_session_data(session_id)
            if session_data is None:
                return {
                    "status": "error",
                    "error": f"Session {session_id} not found"
                }
            
            # Verify user profile exists
            dri_profiles = session_data.get('dri_user_profiles', {})
            user_profile = None
            
            for profile in dri_profiles.values():
                if profile["profile_name"] == profile_name:
                    user_profile = profile
                    break
            
            if not user_profile:
                return {
                    "status": "error",
                    "error": f"User profile '{profile_name}' not found in session {session_id}",
                    "suggested_action": "store_dri_user_profile_in_session"
                }
            
            # Get cached DRI data
            dri_tables = session_data.get('dri_reference_tables', {})
            if not dri_tables:
                return {
                    "status": "error",
                    "error": "No DRI tables found in session. Run store_dri_tables_in_session first.",
                    "suggested_action": "store_dri_tables_in_session"
                }
            
            # Get most recent DRI data and find AMDR values
            latest_key = max(dri_tables.keys())
            dri_data = dri_tables[latest_key]["data"]
            amdrs = dri_data.get("amdrs", {})
            
            if age_range not in amdrs:
                return {
                    "status": "error",
                    "error": f"No AMDR data found for age range '{age_range}'",
                    "available_age_ranges": list(amdrs.keys())
                }
            
            amdr_data = amdrs[age_range]
            
            # Prepare calculation data structure (NO calculations here!)
            calculation_data = {
                "status": "success",
                "session_id": session_id,
                "profile_name": profile_name,
                "eer_energy_kcal": eer_energy_kcal,
                "age_range": age_range,
                "amdr_ranges": amdr_data,
                "macronutrient_formulas": {},
                "calculation_constants": {
                    "carbohydrate_kcal_per_gram": 4,
                    "protein_kcal_per_gram": 4,
                    "fat_kcal_per_gram": 9
                },
                "calculated_at": datetime.now().isoformat()
            }
            
            # Create formulas for simple_math_calculator (NO calculations performed!)
            macros = ["carbohydrate", "protein", "fat"]
            amdr_keys = ["carbohydrate_percent", "protein_percent", "fat_percent"]
            kcal_per_gram = [4, 4, 9]
            
            for macro, amdr_key, kcal_density in zip(macros, amdr_keys, kcal_per_gram):
                amdr_range = amdr_data.get(amdr_key, "")
                
                # Extract min/max percentages from range string (e.g., "45-65%")
                if '-' in amdr_range and '%' in amdr_range:
                    range_clean = amdr_range.replace('%', '').strip()
                    min_percent, max_percent = range_clean.split('-')
                    min_percent = float(min_percent.strip()) / 100  # Convert to decimal
                    max_percent = float(max_percent.strip()) / 100
                    mid_percent = (min_percent + max_percent) / 2
                    
                    # Create formulas for grams calculation
                    calculation_data["macronutrient_formulas"][macro] = {
                        "min_grams": {
                            "expression": "(energy * min_percent) / kcal_per_gram",
                            "variables": {
                                "energy": eer_energy_kcal,
                                "min_percent": min_percent,
                                "kcal_per_gram": kcal_density
                            },
                            "description": f"Minimum {macro} grams per day (AMDR lower bound)"
                        },
                        "max_grams": {
                            "expression": "(energy * max_percent) / kcal_per_gram",
                            "variables": {
                                "energy": eer_energy_kcal,
                                "max_percent": max_percent,
                                "kcal_per_gram": kcal_density
                            },
                            "description": f"Maximum {macro} grams per day (AMDR upper bound)"
                        },
                        "target_grams": {
                            "expression": "(energy * mid_percent) / kcal_per_gram",
                            "variables": {
                                "energy": eer_energy_kcal,
                                "mid_percent": mid_percent,
                                "kcal_per_gram": kcal_density
                            },
                            "description": f"Target {macro} grams per day (AMDR midpoint)"
                        },
                        "amdr_range_text": amdr_range,
                        "amdr_min_percent": min_percent * 100,
                        "amdr_max_percent": max_percent * 100,
                        "kcal_per_gram": kcal_density
                    }
            
            # Store calculation in session
            calc_key = f"{profile_name}_eer_dri_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            session_data['dri_macro_calculations'][calc_key] = calculation_data
            
            return calculation_data
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to calculate DRI from EER: {str(e)}"
            }

    @mcp.tool()
    def list_session_dri_analysis(session_id: str) -> Dict[str, Any]:
        """
        View all DRI calculations and analysis stored in a virtual session.
        
        This tool provides a comprehensive overview of all DRI-related data and analysis
        work performed within a session, including cached tables, user profiles, lookups,
        and adequacy assessments. Perfect for managing complex nutrition analysis workflows.
        
        Session data overview includes:
        - Cached DRI reference tables with timestamps
        - Stored user profiles with demographics
        - Individual nutrient lookups performed
        - Complete adequacy assessments conducted
        - Macro calculation results (if any)
        - Session activity summary and workflow guidance
        
        Use this tool when:
        - Reviewing completed DRI analysis work in a session
        - Planning next steps in nutrition assessment workflows
        - Debugging session data or workflow issues
        - Managing multiple user profiles or analyses
        - Preparing session data for reporting or export
        
        Args:
            session_id: Virtual session to analyze
            
        Returns:
            Dict with comprehensive session DRI data overview and activity summary
        """
        try:
            # Use imported schema functions
            
            session_data = get_virtual_session_data(session_id)
            if session_data is None:
                return {
                    "status": "error",
                    "error": f"Session {session_id} not found"
                }
            
            # Get basic DRI session summary
            summary = get_dri_session_summary(session_id)
            
            # Detailed breakdown of session contents
            result = {
                "status": "success",
                "session_id": session_id,
                "summary": summary,
                "detailed_contents": {}
            }
            
            # DRI reference tables
            dri_tables = session_data.get('dri_reference_tables', {})
            result["detailed_contents"]["dri_reference_tables"] = []
            for key, table_data in dri_tables.items():
                result["detailed_contents"]["dri_reference_tables"].append({
                    "table_key": key,
                    "stored_at": table_data.get("stored_at"),
                    "force_refresh_used": table_data.get("force_refresh_used"),
                    "age_groups_count": len(table_data.get("data", {}).get("reference_values", [])),
                    "source": table_data.get("data", {}).get("source")
                })
            
            # User profiles
            dri_profiles = session_data.get('dri_user_profiles', {})
            result["detailed_contents"]["user_profiles"] = []
            for key, profile_data in dri_profiles.items():
                result["detailed_contents"]["user_profiles"].append({
                    "profile_key": key,
                    "profile_name": profile_data.get("profile_name"),
                    "age_range": profile_data.get("age_range"),
                    "gender": profile_data.get("gender"),
                    "created_at": profile_data.get("created_at"),
                    "has_additional_info": bool(profile_data.get("additional_info"))
                })
            
            # DRI lookups
            dri_lookups = session_data.get('dri_lookups', {})
            result["detailed_contents"]["dri_lookups"] = []
            for key, lookup_data in dri_lookups.items():
                result["detailed_contents"]["dri_lookups"].append({
                    "lookup_key": key,
                    "lookup_at": lookup_data.get("lookup_at"),
                    "query": lookup_data.get("query"),
                    "results_found": lookup_data.get("result", {}).get("status") == "success"
                })
            
            # DRI comparisons/adequacy assessments
            dri_comparisons = session_data.get('dri_comparisons', {})
            result["detailed_contents"]["adequacy_assessments"] = []
            for key, comparison_data in dri_comparisons.items():
                assessment_info = {
                    "assessment_key": key,
                    "calculated_at": comparison_data.get("calculated_at"),
                    "profile_name": comparison_data.get("profile_name"),
                    "nutrients_assessed": len(comparison_data.get("nutrient_assessments", {})),
                    "intake_nutrients": list(comparison_data.get("intake_data", {}).keys())
                }
                
                # Add summary if available
                if "assessment_summary" in comparison_data:
                    assessment_info["summary"] = comparison_data["assessment_summary"]
                
                result["detailed_contents"]["adequacy_assessments"].append(assessment_info)
            
            # Macro calculations
            macro_calcs = session_data.get('dri_macro_calculations', {})
            result["detailed_contents"]["macro_calculations"] = []
            for key, calc_data in macro_calcs.items():
                calc_info = {
                    "calculation_key": key,
                    "calculation_type": calc_data.get("calculation_type", "eer_to_dri_macros"),
                    "created_at": calc_data.get("created_at"),
                    "profile_name": calc_data.get("profile_name"),
                    "eer_energy_kcal": calc_data.get("eer_energy_kcal"),
                    "age_range": calc_data.get("age_range"),
                    "has_formulas": "macronutrient_formulas" in calc_data
                }
                result["detailed_contents"]["macro_calculations"].append(calc_info)
            
            # Workflow suggestions
            workflow_suggestions = []
            if not dri_tables:
                workflow_suggestions.append("Run store_dri_tables_in_session to cache DRI reference data")
            if not dri_profiles:
                workflow_suggestions.append("Run store_dri_user_profile_in_session to create user demographics")
            if dri_tables and dri_profiles and not dri_comparisons and not macro_calcs:
                workflow_suggestions.append("Run calculate_dri_adequacy_in_session or calculate_dri_from_eer for analysis")
            if not workflow_suggestions:
                workflow_suggestions.append("Session is well-populated with DRI analysis data")
            
            result["workflow_suggestions"] = workflow_suggestions
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to list session DRI analysis: {str(e)}"
            }