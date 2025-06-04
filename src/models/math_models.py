from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ServingSizeInput(BaseModel):
    """Input model for serving size calculations"""
    session_id: str = Field(..., description="Session identifier containing the recipe")
    recipe_id: str = Field(..., description="Recipe ID to scale")
    target_servings: int = Field(..., description="Desired number of servings", gt=0)

class IngredientScaleInput(BaseModel):
    """Input model for scaling individual ingredients"""
    session_id: str = Field(..., description="Session identifier containing the recipe")
    recipe_id: str = Field(..., description="Recipe ID containing the ingredient")
    ingredient_name: str = Field(..., description="Name of ingredient to scale")
    scale_factor: float = Field(..., description="Multiplication factor (e.g., 2.0 for double, 0.5 for half)", gt=0)

class BulkIngredientScaleInput(BaseModel):
    """Input model for scaling multiple ingredients at once"""
    session_id: str = Field(..., description="Session identifier containing the recipe")
    recipe_id: str = Field(..., description="Recipe ID containing the ingredients")
    ingredient_scales: Dict[str, float] = Field(..., description="Map of ingredient names to scale factors")

class RecipeComparisonInput(BaseModel):
    """Input model for comparing recipes by servings or ingredients"""
    session_id: str = Field(..., description="Session identifier containing the recipes")
    recipe_ids: List[str] = Field(..., description="List of recipe IDs to compare", min_items=2)
    comparison_type: str = Field("servings", description="Type of comparison: 'servings', 'ingredients', or 'portions'")

# Placeholder models for future nutritional analysis tools
class DRIComparisonInput(BaseModel):
    """
    FUTURE: Input model for comparing recipe nutrition against Dietary Reference Intakes
    This will be used when Canadian Nutrient File (CNF) integration is added
    """
    session_id: str = Field(..., description="Session with recipes to analyze")
    recipe_ids: List[str] = Field(..., description="Recipes to include in nutritional analysis")
    age_group: str = Field(..., description="Age group for DRI comparison (e.g., '19-30', '31-50')")
    gender: str = Field(..., description="Gender for DRI comparison ('male', 'female')")
    daily_intake: bool = Field(True, description="Whether to analyze as part of daily intake")

class NutrientAnalysisInput(BaseModel):
    """
    FUTURE: Input model for detailed nutrient analysis of recipes
    This will be used when Canadian Nutrient File (CNF) integration is added
    """
    session_id: str = Field(..., description="Session with recipes to analyze")
    recipe_ids: List[str] = Field(..., description="Recipes to analyze for nutrients")
    nutrients_of_interest: List[str] = Field(default=[], description="Specific nutrients to focus on (e.g., 'calcium', 'iron')")
    per_serving: bool = Field(True, description="Whether to calculate per serving or total recipe")