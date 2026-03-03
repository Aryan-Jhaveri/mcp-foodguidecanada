"""
MCP Resources for static/semi-static reference data.

Resources expose read-only reference data that LLM clients can use as context
without making tool calls. This is ideal for DRI tables, EER equations, and
PAL categories — data that rarely changes and is useful as grounding context.

Resources are always available regardless of transport mode (stdio or HTTP).
"""

import json
import os
import sys
from typing import Dict, Any
from fastmcp import FastMCP

# Path setup
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)

if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Import data managers
try:
    from src.data_manager import get_dri_data_manager, get_eer_data_manager
except ImportError:
    from data_manager import get_dri_data_manager, get_eer_data_manager


def register_resources(mcp: FastMCP):
    """Register all MCP resources with the server."""

    @mcp.resource("dri://macronutrient-tables", mime_type="application/json")
    def dri_macronutrient_tables() -> str:
        """
        Complete DRI macronutrient reference tables from Health Canada.

        Contains reference values (EAR, RDA/AI, UL) for carbohydrate, protein,
        fat, essential fatty acids, fibre, and water across all age groups and
        life stages (infants through elderly, pregnancy, lactation).

        Source: Health Canada Dietary Reference Intakes Tables
        """
        manager = get_dri_data_manager()
        data = manager.get_dri_data()
        return json.dumps(data.get("reference_values", []), indent=2)

    @mcp.resource("dri://amdrs", mime_type="application/json")
    def dri_amdrs() -> str:
        """
        Acceptable Macronutrient Distribution Ranges (AMDRs) from Health Canada.

        Provides recommended percentage ranges for carbohydrate, protein, fat,
        n-6 PUFA, and n-3 PUFA intake as a percentage of total energy, by age group.
        """
        manager = get_dri_data_manager()
        data = manager.get_dri_data()
        return json.dumps(data.get("amdrs", {}), indent=2)

    @mcp.resource("dri://amino-acid-patterns", mime_type="application/json")
    def dri_amino_acid_patterns() -> str:
        """
        Essential amino acid scoring patterns for protein quality evaluation (PDCAAS).

        Reference pattern based on estimated average requirements for 1-3 year olds.
        Used for Protein Digestibility Corrected Amino Acid Score calculations.
        """
        manager = get_dri_data_manager()
        data = manager.get_dri_data()
        return json.dumps(data.get("amino_acid_patterns", {}), indent=2)

    @mcp.resource("dri://additional-recommendations", mime_type="application/json")
    def dri_additional_recommendations() -> str:
        """
        Additional macronutrient recommendations from Health Canada.

        Includes guidance on saturated fatty acids, trans fatty acids,
        dietary cholesterol, and added sugars.
        """
        manager = get_dri_data_manager()
        data = manager.get_dri_data()
        return json.dumps(data.get("additional_recommendations", {}), indent=2)

    @mcp.resource("eer://equations", mime_type="application/json")
    def eer_equations() -> str:
        """
        Health Canada EER (Estimated Energy Requirement) equations.

        Complete set of EER equations with extracted coefficients for:
        - Infants/toddlers (0-3 years)
        - Children/adolescents (3-18 years)
        - Adults (19+ years)
        - Pregnancy (2nd/3rd trimester)
        - Lactation (breastfeeding)

        Each equation includes intercept, age, height, and weight coefficients.
        Variables: age (years), height (cm), weight (kg).
        """
        manager = get_eer_data_manager()
        data = manager.get_eer_data()
        return json.dumps(data.get("equations", {}), indent=2)

    @mcp.resource("eer://pal-categories", mime_type="application/json")
    def eer_pal_categories() -> str:
        """
        Physical Activity Level (PAL) category descriptions and examples.

        Four categories: inactive, low_active, active, very_active.
        Includes practical examples and PAL range definitions by age group.
        """
        manager = get_eer_data_manager()
        data = manager.get_eer_data()
        result = {
            "pal_descriptions": data.get("pal_descriptions", {}),
            "pal_category_definitions": data.get("pal_category_definitions", {})
        }
        return json.dumps(result, indent=2)

    @mcp.resource("dri://footnotes", mime_type="application/json")
    def dri_footnotes() -> str:
        """
        Footnotes and explanatory notes from Health Canada DRI tables.

        Important context for interpreting DRI values, including notes on
        UL limitations, vegetarian protein, fibre definitions, and pregnancy.
        """
        manager = get_dri_data_manager()
        data = manager.get_dri_data()
        return json.dumps(data.get("footnotes", {}), indent=2)
