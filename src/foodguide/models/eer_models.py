"""
Pydantic models for EER (Estimated Energy Requirement) calculations and user profiles.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from enum import Enum

class GenderEnum(str, Enum):
    """Gender options for EER calculations"""
    MALE = "male"
    FEMALE = "female"

class PALCategoryEnum(str, Enum):
    """Physical Activity Level categories"""
    INACTIVE = "inactive"
    LOW_ACTIVE = "low_active"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"

class PregnancyStatusEnum(str, Enum):
    """Pregnancy status options"""
    NOT_PREGNANT = "not_pregnant"
    FIRST_TRIMESTER = "first_trimester"
    SECOND_TRIMESTER = "second_trimester"
    THIRD_TRIMESTER = "third_trimester"

class LactationStatusEnum(str, Enum):
    """Lactation status options"""
    NOT_LACTATING = "not_lactating"
    LACTATING_0_6_MONTHS = "lactating_0_6_months"
    LACTATING_7_12_MONTHS = "lactating_7_12_months"

class CreateUserProfileInput(BaseModel):
    """Input model for creating a user profile for EER calculations"""
    profile_id: str = Field(..., description="Unique identifier for the user profile")
    age: int = Field(..., description="Age in years", ge=1, le=120)
    gender: GenderEnum = Field(..., description="Gender (male or female)")
    height_cm: float = Field(..., description="Height in centimeters", ge=50, le=250)
    weight_kg: float = Field(..., description="Weight in kilograms", ge=10, le=300)
    pal_category: PALCategoryEnum = Field(..., description="Physical Activity Level category")
    pregnancy_status: PregnancyStatusEnum = Field(
        PregnancyStatusEnum.NOT_PREGNANT, 
        description="Pregnancy status (for females only)"
    )
    lactation_status: LactationStatusEnum = Field(
        LactationStatusEnum.NOT_LACTATING,
        description="Lactation status (for females only)"
    )
    gestation_weeks: Optional[int] = Field(
        None,
        description="Gestation weeks (required for 2nd and 3rd trimester pregnancy calculations)",
        ge=1, le=42
    )
    pre_pregnancy_bmi: Optional[float] = Field(
        None,
        description="Pre-pregnancy BMI (required for pregnancy calculations to determine weight category)",
        ge=10, le=50
    )
    use_persistent_storage: bool = Field(
        False, 
        description="Whether to store profile persistently or in virtual session"
    )

    @validator('pregnancy_status')
    def validate_pregnancy_status(cls, v, values):
        """Validate pregnancy status is only set for females"""
        if 'gender' in values and values['gender'] == GenderEnum.MALE:
            if v != PregnancyStatusEnum.NOT_PREGNANT:
                raise ValueError("Pregnancy status can only be set for females")
        return v

    @validator('lactation_status')
    def validate_lactation_status(cls, v, values):
        """Validate lactation status is only set for females"""
        if 'gender' in values and values['gender'] == GenderEnum.MALE:
            if v != LactationStatusEnum.NOT_LACTATING:
                raise ValueError("Lactation status can only be set for females")
        return v

    @validator('gestation_weeks')
    def validate_gestation_weeks(cls, v, values):
        """Validate gestation weeks are provided for 2nd and 3rd trimester pregnancy"""
        if 'pregnancy_status' in values:
            pregnancy_status = values['pregnancy_status']
            if pregnancy_status in [PregnancyStatusEnum.SECOND_TRIMESTER, PregnancyStatusEnum.THIRD_TRIMESTER]:
                if v is None:
                    raise ValueError("Gestation weeks are required for 2nd and 3rd trimester pregnancy calculations")
                if pregnancy_status == PregnancyStatusEnum.SECOND_TRIMESTER and (v < 14 or v > 27):
                    raise ValueError("Second trimester is typically weeks 14-27")
                if pregnancy_status == PregnancyStatusEnum.THIRD_TRIMESTER and (v < 28 or v > 42):
                    raise ValueError("Third trimester is typically weeks 28-42")
        return v

    @validator('pre_pregnancy_bmi')
    def validate_pre_pregnancy_bmi(cls, v, values):
        """Validate pre-pregnancy BMI for pregnancy calculations"""
        if 'pregnancy_status' in values:
            pregnancy_status = values['pregnancy_status']
            if pregnancy_status in [PregnancyStatusEnum.SECOND_TRIMESTER, PregnancyStatusEnum.THIRD_TRIMESTER]:
                if v is None:
                    raise ValueError("Pre-pregnancy BMI is required for pregnancy EER calculations to determine weight category")
        return v

class CalculateEERInput(BaseModel):
    """Input model for calculating EER from existing profile"""
    profile_id: str = Field(..., description="User profile ID to use for calculation")

class GetProfileInput(BaseModel):
    """Input model for retrieving a user profile"""
    profile_id: str = Field(..., description="User profile ID to retrieve")

class DeleteProfileInput(BaseModel):
    """Input model for deleting a user profile"""
    profile_id: str = Field(..., description="User profile ID to delete")

class GetPALDescriptionsInput(BaseModel):
    """Input model for getting PAL category descriptions"""
    pass  # No input required

# Output models

class EERCalculationResult(BaseModel):
    """Result model for EER calculations"""
    eer_kcal: float = Field(..., description="Estimated Energy Requirement in kilocalories per day")
    equation_used: str = Field(..., description="Identifier of the EER equation used")
    pa_coefficient: float = Field(..., description="Physical Activity coefficient used")
    life_stage: str = Field(..., description="Life stage category")
    gender: str = Field(..., description="Gender")
    age: int = Field(..., description="Age in years")
    weight_kg: float = Field(..., description="Weight in kilograms")
    height_cm: float = Field(..., description="Height in centimeters")
    bmi: float = Field(..., description="Body Mass Index")
    pal_category: str = Field(..., description="Physical Activity Level category")
    pregnancy_status: str = Field(..., description="Pregnancy status")
    lactation_status: str = Field(..., description="Lactation status")
    calculation_notes: Optional[str] = Field(None, description="Additional notes about the calculation")

class UserProfileResult(BaseModel):
    """Result model for user profile operations"""
    profile_id: str = Field(..., description="User profile identifier")
    age: int = Field(..., description="Age in years")
    gender: str = Field(..., description="Gender")
    height_cm: float = Field(..., description="Height in centimeters")
    weight_kg: float = Field(..., description="Weight in kilograms")
    bmi: float = Field(..., description="Body Mass Index")
    pal_category: str = Field(..., description="Physical Activity Level category")
    pregnancy_status: str = Field(..., description="Pregnancy status")
    lactation_status: str = Field(..., description="Lactation status")
    storage_type: str = Field(..., description="Storage type (virtual or persistent)")
    created_at: Optional[str] = Field(None, description="Creation timestamp")

class PALDescriptionResult(BaseModel):
    """Result model for PAL category descriptions"""
    pal_categories: Dict[str, Dict[str, Any]] = Field(
        ..., 
        description="Dictionary of PAL categories with descriptions and examples"
    )

class ProfileListResult(BaseModel):
    """Result model for listing user profiles"""
    profiles: List[str] = Field(..., description="List of available profile IDs")
    total_count: int = Field(..., description="Total number of profiles")
    storage_type: str = Field(..., description="Storage type (virtual or persistent)")

class EERError(BaseModel):
    """Error model for EER operations"""
    error: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code for programmatic handling")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")