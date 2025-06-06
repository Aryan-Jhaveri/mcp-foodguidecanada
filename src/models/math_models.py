from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

# Simple math tool input
class SimpleMathInput(BaseModel):
    """Input model for simple mathematical calculations with variables"""
    expression: str = Field(..., description="Mathematical expression with variables (e.g., '2 * x + 3 * y - 10')")
    variables: Dict[str, float] = Field(..., description="Dictionary of variable names and their values (e.g., {'x': 5, 'y': 2})")

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

# Note: DRI and nutrient analysis functionality is now implemented
# through dedicated modules in src.db.dri_tools and src.db.cnf_tools