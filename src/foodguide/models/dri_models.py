"""
Pydantic models for DRI (Dietary Reference Intake) macronutrient data.

This module defines data models for Health Canada's DRI macronutrient reference values,
including input validation and output formatting for the MacronutrientScraper.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional, Union
from enum import Enum

class DRIValueType(str, Enum):
    """Types of DRI values."""
    EAR = "ear"  # Estimated Average Requirement
    RDA = "rda"  # Recommended Dietary Allowance  
    AI = "ai"    # Adequate Intake
    UL = "ul"    # Tolerable Upper Intake Level

class MacronutrientType(str, Enum):
    """Types of macronutrients in DRI tables."""
    CARBOHYDRATE = "carbohydrate"
    PROTEIN = "protein"
    TOTAL_FAT = "total_fat"
    LINOLEIC_ACID = "linoleic_acid"
    ALPHA_LINOLENIC_ACID = "alpha_linolenic_acid"
    TOTAL_FIBRE = "total_fibre"
    TOTAL_WATER = "total_water"

class LifeStageCategory(str, Enum):
    """Life stage categories in DRI tables."""
    INFANTS = "infants"
    CHILDREN = "children"
    MALES = "males"
    FEMALES = "females"
    PREGNANCY = "pregnancy"
    LACTATION = "lactation"

class MacronutrientValue(BaseModel):
    """
    Model for a single macronutrient DRI value.
    """
    ear: Optional[float] = Field(None, description="Estimated Average Requirement")
    rda_ai: Optional[float] = Field(None, description="Recommended Dietary Allowance or Adequate Intake")
    ul: Optional[float] = Field(None, description="Tolerable Upper Intake Level")
    is_ai: bool = Field(False, description="True if value is AI, False if RDA")
    unit: str = Field(..., description="Unit of measurement (g/day, g/kg/day, L/day)")
    footnote_refs: List[str] = Field(default=[], description="Footnote reference IDs")
    
    @validator('ear', 'rda_ai', 'ul')
    def validate_positive_values(cls, v):
        """Ensure values are positive if provided."""
        if v is not None and v < 0:
            raise ValueError("DRI values must be non-negative")
        return v

class CarbohydrateValues(BaseModel):
    """Carbohydrate-specific DRI values."""
    ear_g_day: Optional[float] = Field(None, description="EAR in grams per day")
    rda_ai_g_day: Optional[float] = Field(None, description="RDA/AI in grams per day") 
    ul_g_day: Optional[float] = Field(None, description="UL in grams per day")
    is_ai: bool = Field(False, description="Whether RDA/AI value is an AI")

class ProteinValues(BaseModel):
    """Protein-specific DRI values with multiple units."""
    ear_g_kg_day: Optional[float] = Field(None, description="EAR in grams per kg body weight per day")
    rda_ai_g_kg_day: Optional[float] = Field(None, description="RDA/AI in grams per kg body weight per day")
    rda_ai_g_day: Optional[float] = Field(None, description="RDA/AI in grams per day")
    ul_g_day: Optional[float] = Field(None, description="UL in grams per day")
    is_ai: bool = Field(False, description="Whether RDA/AI value is an AI")

class FatValues(BaseModel):
    """Fat-specific DRI values (typically AI only)."""
    ai_g_day: Optional[float] = Field(None, description="AI in grams per day")
    ul_g_day: Optional[float] = Field(None, description="UL in grams per day")
    is_ai: bool = Field(True, description="Fat values are typically AI")

class EssentialFattyAcidValues(BaseModel):
    """Essential fatty acid DRI values (linoleic and α-linolenic)."""
    ai_g_day: Optional[float] = Field(None, description="AI in grams per day")
    ul_g_day: Optional[float] = Field(None, description="UL in grams per day")
    is_ai: bool = Field(True, description="Essential fatty acids are typically AI")

class FibreValues(BaseModel):
    """Fibre-specific DRI values."""
    ai_g_day: Optional[float] = Field(None, description="AI in grams per day")
    ul_g_day: Optional[float] = Field(None, description="UL in grams per day")
    is_ai: bool = Field(True, description="Fibre values are typically AI")

class WaterValues(BaseModel):
    """Water-specific DRI values."""
    ai_litres_day: Optional[float] = Field(None, description="AI in litres per day")
    ul_litres_day: Optional[float] = Field(None, description="UL in litres per day")
    is_ai: bool = Field(True, description="Water values are typically AI")

class MacronutrientSet(BaseModel):
    """Complete set of macronutrient values for an age/gender group."""
    carbohydrate: CarbohydrateValues
    protein: ProteinValues
    total_fat: FatValues
    linoleic_acid: EssentialFattyAcidValues
    alpha_linolenic_acid: EssentialFattyAcidValues
    total_fibre: FibreValues
    total_water: WaterValues

class AgeGroupDRI(BaseModel):
    """DRI values for a specific age and gender group."""
    age_range: str = Field(..., description="Age range (e.g., '19-30 y', '0-6 mo')")
    category: LifeStageCategory = Field(..., description="Life stage category")
    nutrients: MacronutrientSet = Field(..., description="Complete macronutrient values")
    
    @validator('age_range')
    def validate_age_range(cls, v):
        """Validate age range format."""
        if not v or not isinstance(v, str):
            raise ValueError("Age range must be a non-empty string")
        return v.strip()

class AminoAcidPattern(BaseModel):
    """Amino acid pattern for protein quality evaluation."""
    name: str = Field(..., description="Amino acid name")
    mg_per_g_protein: float = Field(..., description="Recommended pattern in mg/g protein")
    
    @validator('mg_per_g_protein')
    def validate_positive_value(cls, v):
        """Ensure amino acid pattern value is positive."""
        if v <= 0:
            raise ValueError("Amino acid pattern must be positive")
        return v

class AMDRRange(BaseModel):
    """Acceptable Macronutrient Distribution Range."""
    min_percent: float = Field(..., description="Minimum percentage of total energy")
    max_percent: float = Field(..., description="Maximum percentage of total energy")
    
    @validator('max_percent')
    def validate_range(cls, v, values):
        """Ensure max is greater than min."""
        if 'min_percent' in values and v <= values['min_percent']:
            raise ValueError("Maximum percentage must be greater than minimum")
        return v

class AMDRSet(BaseModel):
    """Complete set of AMDR values for an age group."""
    carbohydrate_percent: str = Field(..., description="Carbohydrate AMDR as percentage range")
    protein_percent: str = Field(..., description="Protein AMDR as percentage range") 
    fat_percent: str = Field(..., description="Fat AMDR as percentage range")
    n6_pufa_percent: str = Field(..., description="n-6 PUFA AMDR as percentage range")
    n3_pufa_percent: str = Field(..., description="n-3 PUFA AMDR as percentage range")

class AdditionalRecommendations(BaseModel):
    """Additional macronutrient recommendations beyond standard DRI values."""
    saturated_fatty_acids: str = Field(
        "As low as possible while consuming a nutritionally adequate diet",
        description="Saturated fat recommendation"
    )
    trans_fatty_acids: str = Field(
        "As low as possible while consuming a nutritionally adequate diet", 
        description="Trans fat recommendation"
    )
    dietary_cholesterol: str = Field(
        "As low as possible while consuming a nutritionally adequate diet",
        description="Cholesterol recommendation"
    )
    added_sugars: Dict[str, str] = Field(
        default_factory=lambda: {
            "recommendation": "Limit to no more than 25% of total energy",
            "note": "Although there were insufficient data to set a UL for added sugars, this maximal intake level is suggested to prevent the displacement of foods that are major sources of essential micronutrients."
        },
        description="Added sugars recommendation with note"
    )

class DataQuality(BaseModel):
    """Data quality metrics for the scraped DRI data."""
    parsing_timestamp: str = Field(..., description="When the data was parsed")
    total_age_groups_parsed: int = Field(..., description="Number of age groups successfully parsed")
    total_nutrients_parsed: int = Field(..., description="Total number of nutrient values parsed")
    parsing_warnings: List[str] = Field(default=[], description="Any warnings during parsing")

class DRIMacronutrientData(BaseModel):
    """Complete DRI macronutrient data model."""
    status: str = Field(..., description="Status of data retrieval (success/error)")
    source: str = Field("Health Canada DRI Tables", description="Data source")
    url: str = Field(..., description="Source URL")
    last_updated: str = Field(..., description="When data was last updated")
    reference_values: List[AgeGroupDRI] = Field(..., description="Main reference values by age/gender")
    additional_recommendations: AdditionalRecommendations = Field(..., description="Additional recommendations")
    amino_acid_patterns: Dict[str, AminoAcidPattern] = Field(..., description="Amino acid patterns for protein quality")
    amdrs: Dict[str, AMDRSet] = Field(..., description="Acceptable Macronutrient Distribution Ranges")
    footnotes: Dict[str, str] = Field(default_factory=dict, description="Footnotes from tables")
    data_quality: DataQuality = Field(..., description="Data quality metrics")

# Input models for MCP tools

class GetMacronutrientDRIInput(BaseModel):
    """Input for getting specific macronutrient DRI values."""
    age_range: str = Field(..., description="Age range (e.g., '19-30 y')")
    gender: Optional[str] = Field(None, description="Gender category (males/females) or None for general")
    macronutrient: MacronutrientType = Field(..., description="Type of macronutrient")
    force_refresh: bool = Field(False, description="Force refresh from website")

class GetAMDRInput(BaseModel):
    """Input for getting AMDR values."""
    age_range: str = Field(..., description="Age range for AMDR lookup")
    force_refresh: bool = Field(False, description="Force refresh from website")

class CompareIntakeToDRIInput(BaseModel):
    """Input for comparing intake to DRI recommendations."""
    age_range: str = Field(..., description="User's age range")
    gender: Optional[str] = Field(None, description="User's gender category")
    intake_data: Dict[str, float] = Field(..., description="Actual nutrient intake data")
    comparison_type: str = Field("all", description="Type of comparison (all, specific nutrient)")

class DRIError(BaseModel):
    """Error model for DRI operations."""
    error: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Type of error (network_error, parsing_error, etc.)")
    timestamp: str = Field(..., description="When the error occurred")

# Utility functions for parsing AMDR ranges

def parse_amdr_range(range_str: str) -> Optional[AMDRRange]:
    """
    Parse AMDR range string like '45-65%' into AMDRRange object.
    
    Args:
        range_str: String like '45-65%' or '10-35%'
        
    Returns:
        AMDRRange object or None if parsing fails
    """
    try:
        # Remove percentage sign and split on dash
        clean_str = range_str.replace('%', '').strip()
        if '-' in clean_str:
            min_val, max_val = clean_str.split('-')
            return AMDRRange(
                min_percent=float(min_val.strip()),
                max_percent=float(max_val.strip())
            )
    except (ValueError, AttributeError):
        pass
    
    return None

def format_dri_value(value: Optional[float], unit: str, is_ai: bool = False) -> str:
    """
    Format DRI value for display.
    
    Args:
        value: Numeric value
        unit: Unit string
        is_ai: Whether this is an AI value (affects formatting)
        
    Returns:
        Formatted string representation
    """
    if value is None:
        return "ND"
    
    # Format with appropriate precision
    if unit in ['g/day', 'g/kg/day']:
        formatted = f"{value:.1f}"
    else:
        formatted = f"{value:.2f}"
    
    # Add asterisk for AI values
    if is_ai:
        formatted += "*"
    
    return f"{formatted} {unit}"