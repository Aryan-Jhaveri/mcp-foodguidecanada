"""
Pydantic models for CNF (Canadian Nutrient File) data validation and processing.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from datetime import datetime

class CNFSearchInput(BaseModel):
    """Input model for CNF food search operations"""
    food_name: str = Field(..., description="Name of food to search for in CNF database")
    session_id: str = Field(..., description="Session ID for storing search results")
    max_results: Optional[int] = Field(default=None, description="Maximum number of search results to return (None = all results, which is now the default)")
    
    @validator('food_name')
    def validate_food_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Food name cannot be empty')
        return v.strip()
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()

class CNFFoodResult(BaseModel):
    """Model for a single CNF food search result"""
    food_code: str = Field(..., description="CNF food code identifier")
    food_name: str = Field(..., description="Full descriptive name of the food")
    
    @validator('food_code')
    def validate_food_code(cls, v):
        if not v or not v.strip():
            raise ValueError('Food code cannot be empty')
        return v.strip()

class CNFSearchResult(BaseModel):
    """Model for complete CNF search results"""
    search_term: str = Field(..., description="Original search term used")
    results: List[CNFFoodResult] = Field(..., description="List of matching foods found")
    session_id: str = Field(..., description="Session where results are stored")
    search_timestamp: datetime = Field(default_factory=datetime.now, description="When search was performed")

class CNFNutrientEntry(BaseModel):
    """Model for a single nutrient entry from CNF"""
    nutrient_name: str = Field(..., description="Name of the nutrient")
    unit: str = Field(..., description="Unit of measurement")
    value_per_100g: str = Field(..., description="Nutrient value per 100g edible portion")
    observations: Optional[str] = Field(default="", description="Number of observations")
    standard_error: Optional[str] = Field(default="", description="Standard error value")
    data_source: Optional[str] = Field(default="", description="Data source information")
    serving_values: Dict[str, str] = Field(default_factory=dict, description="Values for different serving sizes")

class CNFNutrientProfile(BaseModel):
    """Model for complete CNF nutrient profile"""
    food_code: str = Field(..., description="CNF food code")
    food_name: str = Field(..., description="Food name")
    serving_options: Dict[str, str] = Field(..., description="Available serving size options")
    refuse_info: str = Field(..., description="Food refuse information")
    nutrient_categories: Dict[str, List[CNFNutrientEntry]] = Field(..., description="Nutrients organized by category")
    profile_timestamp: datetime = Field(default_factory=datetime.now, description="When profile was retrieved")

class CNFProfileInput(BaseModel):
    """Input model for getting CNF nutrient profiles"""
    food_code: str = Field(..., description="CNF food code to get profile for")
    session_id: str = Field(..., description="Session ID for storing profile data")
    
    @validator('food_code')
    def validate_food_code(cls, v):
        if not v or not v.strip():
            raise ValueError('Food code cannot be empty')
        return v.strip()

class CNFSearchAndGetInput(BaseModel):
    """Input model for combined search and macronutrient fetching (LLM-optimized efficiency)"""
    food_name: str = Field(..., description="Name of food to search for in CNF database")
    session_id: str = Field(..., description="Session ID for storing search and macronutrient data")
    preferred_units: Optional[List[str]] = Field(
        default=["100g", "ml", "tsp", "tbsp"], 
        description="Preferred serving units to include (e.g. ['5ml', '15ml', '100g'])"
    )
    max_results: Optional[int] = Field(default=None, description="Maximum number of search results to return for LLM selection (None = all results)")
    
    @validator('food_name')
    def validate_food_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Food name cannot be empty')
        return v.strip()
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('preferred_units')
    def validate_preferred_units(cls, v):
        if v is not None and len(v) == 0:
            # If empty list provided, use default units
            return ["100g", "ml", "tsp", "tbsp"]
        return v

class CNFMacronutrientsInput(BaseModel):
    """Input model for streamlined macronutrient-only fetching (LLM-optimized)"""
    food_code: str = Field(..., description="CNF food code to get macronutrients for")
    session_id: str = Field(..., description="Session ID for storing macronutrient data")
    preferred_units: Optional[List[str]] = Field(
        default=["100g", "ml", "tsp", "tbsp"], 
        description="Preferred serving units to include (e.g. ['5ml', '15ml', '100g'])"
    )
    ingredient_id: Optional[str] = Field(
        default=None, 
        description="Optional: ingredient_id to link this CNF food to a specific recipe ingredient"
    )
    recipe_id: Optional[str] = Field(
        default=None, 
        description="Optional: recipe_id to link this CNF food to (required if ingredient_id provided)"
    )
    
    @validator('food_code')
    def validate_food_code(cls, v):
        if not v or not v.strip():
            raise ValueError('Food code cannot be empty')
        return v.strip()
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('preferred_units')
    def validate_preferred_units(cls, v):
        if v is not None and len(v) == 0:
            # If empty list provided, use default units
            return ["100g", "ml", "tsp", "tbsp"]
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "food_code": "4294",
                "session_id": "nutrition_analysis", 
                "preferred_units": ["5ml", "15ml", "100g"]
            }
        }

class CNFBulkMacronutrientsInput(BaseModel):
    """Input model for bulk macronutrient fetching (multiple food codes at once)"""
    food_codes: List[str] = Field(..., description="List of CNF food codes to fetch macronutrients for", min_items=1, max_items=20)
    session_id: str = Field(..., description="Session ID for storing bulk macronutrient data")
    preferred_units: Optional[List[str]] = Field(
        default=["100g", "ml", "tsp", "tbsp"], 
        description="Preferred serving units to include for all foods (e.g. ['5ml', '15ml', '100g'])"
    )
    continue_on_error: bool = Field(
        default=True, 
        description="Whether to continue processing other food codes if one fails"
    )
    ingredient_mappings: Optional[Dict[str, str]] = Field(
        default=None, 
        description="Optional mapping of food_code to ingredient_id for automatic linking (e.g. {'3183': 'salmon_001', '4294': 'honey_001'})"
    )
    recipe_id: Optional[str] = Field(
        default=None, 
        description="Recipe ID for linking ingredients (required if ingredient_mappings provided)"
    )
    
    @validator('food_codes')
    def validate_food_codes(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one food code is required')
        
        # Remove empty codes and strip whitespace
        cleaned_codes = [code.strip() for code in v if code and code.strip()]
        
        if len(cleaned_codes) == 0:
            raise ValueError('At least one valid food code is required')
        
        if len(cleaned_codes) > 20:
            raise ValueError('Maximum 20 food codes allowed per bulk request')
            
        return cleaned_codes
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('preferred_units')
    def validate_preferred_units(cls, v):
        if v is not None and len(v) == 0:
            # If empty list provided, use default units
            return ["100g", "ml", "tsp", "tbsp"]
        return v
    
    @validator('recipe_id')
    def validate_recipe_id_with_mappings(cls, v, values):
        ingredient_mappings = values.get('ingredient_mappings')
        if ingredient_mappings and not v:
            raise ValueError('recipe_id is required when ingredient_mappings is provided')
        if v and not v.strip():
            raise ValueError('recipe_id cannot be empty string')
        return v.strip() if v else None
    
    @validator('ingredient_mappings')
    def validate_ingredient_mappings(cls, v):
        if v is not None and len(v) == 0:
            # If empty dict provided, set to None
            return None
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "food_codes": ["4294", "3183", "5067"],
                "session_id": "bulk_nutrition_analysis", 
                "preferred_units": ["5ml", "15ml", "100g"],
                "continue_on_error": True,
                "ingredient_mappings": {"4294": "ingredient_001", "3183": "ingredient_002", "5067": "ingredient_003"},
                "recipe_id": "recipe_001"
            }
        }

class RecipeNutritionCalculationInput(BaseModel):
    """Input model for simple recipe nutrition calculations (EER-style approach)"""
    session_id: str = Field(..., description="Session ID containing recipe and CNF data")
    recipe_id: str = Field(..., description="Recipe ID to calculate nutrition for")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('recipe_id')
    def validate_recipe_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Recipe ID cannot be empty')
        return v.strip()
    
    class Config:
        schema_extra = {
            "example": {
                "session_id": "nutrition_analysis",
                "recipe_id": "honey_salmon"
            }
        }

class IngredientNutritionBreakdownInput(BaseModel):
    """Input model for per-ingredient nutrition breakdown"""
    session_id: str = Field(..., description="Session ID containing recipe and CNF data")
    recipe_id: str = Field(..., description="Recipe ID to analyze")
    include_per_serving: bool = Field(default=True, description="Include per-serving calculations")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    class Config:
        schema_extra = {
            "example": {
                "session_id": "nutrition_analysis",
                "recipe_id": "honey_salmon",
                "include_per_serving": True
            }
        }

class DailyNutritionComparisonInput(BaseModel):
    """Input model for comparing recipe nutrition to daily requirements"""
    session_id: str = Field(..., description="Session ID containing recipe and CNF data")
    recipe_id: str = Field(..., description="Recipe ID to compare")
    servings: int = Field(default=1, description="Number of servings to analyze")
    target_calories: Optional[int] = Field(default=2000, description="Target daily calories for comparison")
    
    @validator('servings')
    def validate_servings(cls, v):
        if v <= 0:
            raise ValueError('Servings must be greater than 0')
        return v
    
    @validator('target_calories')
    def validate_target_calories(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Target calories must be greater than 0')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "session_id": "nutrition_analysis",
                "recipe_id": "honey_salmon",
                "servings": 1,
                "target_calories": 2000
            }
        }

class IngredientCNFMatch(BaseModel):
    """Model for linking recipe ingredients to CNF foods"""
    ingredient_id: str = Field(..., description="Recipe ingredient identifier")
    cnf_food_code: str = Field(..., description="Matched CNF food code")
    cnf_food_name: str = Field(..., description="Matched CNF food name")
    confidence_score: float = Field(default=1.0, description="Confidence in the match (0.0-1.0)")
    serving_conversion: Dict[str, Any] = Field(default_factory=dict, description="Conversion between recipe and CNF servings")
    match_timestamp: datetime = Field(default_factory=datetime.now, description="When match was created")

class IngredientMatchInput(BaseModel):
    """Input model for creating ingredient-CNF matches"""
    session_id: str = Field(..., description="Session containing the ingredient")
    ingredient_id: str = Field(..., description="Ingredient ID from recipe session")
    cnf_food_code: str = Field(..., description="CNF food code to link to")
    confidence_score: Optional[float] = Field(default=1.0, description="Confidence in match quality")
    
    @validator('confidence_score')
    def validate_confidence_score(cls, v):
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError('Confidence score must be between 0.0 and 1.0')
        return v

class IngredientNutritionData(BaseModel):
    """Model for individual ingredient nutrition calculation data"""
    ingredient_name: str = Field(..., description="Name of the ingredient")
    amount: float = Field(..., description="Amount of ingredient in recipe")
    unit: Optional[str] = Field(default="", description="Unit of measurement")
    cnf_code: str = Field(..., description="CNF food code used")
    calculation_method: str = Field(..., description="Method used for calculation (serving_match, 100g_baseline)")
    serving_match_info: Optional[str] = Field(default="", description="Details about serving size matching")
    calories: float = Field(..., description="Calculated calories for this ingredient")
    protein: float = Field(..., description="Calculated protein (g) for this ingredient")
    fat: float = Field(..., description="Calculated fat (g) for this ingredient")
    carbohydrates: float = Field(..., description="Calculated carbohydrates (g) for this ingredient")

class RecipeNutritionSummary(BaseModel):
    """Model for aggregated nutrition data for a recipe with calculated totals"""
    recipe_id: str = Field(..., description="Recipe identifier")
    recipe_title: str = Field(..., description="Recipe title")
    session_id: str = Field(..., description="Session containing the recipe")
    base_servings: int = Field(..., description="Number of servings recipe makes")
    
    # Total nutrition values (calculated directly, not formulas)
    total_calories: float = Field(..., description="Total calories for entire recipe")
    total_protein: float = Field(..., description="Total protein (g) for entire recipe")
    total_fat: float = Field(..., description="Total fat (g) for entire recipe")
    total_carbohydrates: float = Field(..., description="Total carbohydrates (g) for entire recipe")
    
    # Per-serving nutrition values
    calories_per_serving: float = Field(..., description="Calories per serving")
    protein_per_serving: float = Field(..., description="Protein (g) per serving")
    fat_per_serving: float = Field(..., description="Fat (g) per serving")
    carbohydrates_per_serving: float = Field(..., description="Carbohydrates (g) per serving")
    
    # Ingredient details
    ingredient_nutrition: List[IngredientNutritionData] = Field(default_factory=list, description="Nutrition breakdown by ingredient")
    
    # Coverage and accuracy information
    matched_ingredients_count: int = Field(..., description="Number of ingredients with CNF matches")
    total_ingredients_count: int = Field(..., description="Total number of ingredients in recipe")
    coverage_percentage: float = Field(..., description="Percentage of ingredients with nutrition data")
    
    # Serving size matching analysis
    serving_matches_found: int = Field(default=0, description="Number of nutrients calculated using CNF serving sizes")
    total_nutrients_analyzed: int = Field(default=0, description="Total nutrients analyzed across all ingredients")
    serving_match_percentage: float = Field(default=0.0, description="Percentage of nutrients using CNF serving matches")
    calculation_accuracy: str = Field(default="baseline", description="Overall calculation accuracy level")
    
    # Metadata
    calculation_timestamp: datetime = Field(default_factory=datetime.now, description="When nutrition was calculated")
    calculation_method: str = Field(default="serving_size_optimized", description="Method used for calculations")

class NutritionCalculationInput(BaseModel):
    """Input model for calculating recipe nutrition"""
    session_id: str = Field(..., description="Session containing recipe and CNF data")
    recipe_id: str = Field(..., description="Recipe to calculate nutrition for")
    include_micronutrients: Optional[bool] = Field(default=False, description="Whether to include detailed micronutrient data")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('recipe_id')
    def validate_recipe_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Recipe ID cannot be empty')
        return v.strip()

class NutritionSummaryInput(BaseModel):
    """Input model for retrieving calculated nutrition summaries"""
    session_id: str = Field(..., description="Session containing nutrition data")
    recipe_id: Optional[str] = Field(default=None, description="Specific recipe to get summary for (None = all recipes)")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('recipe_id')
    def validate_recipe_id(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Recipe ID cannot be empty string')
        return v.strip() if v else None

class SQLQueryInput(BaseModel):
    """Input model for executing SQL queries on virtual nutrition tables"""
    session_id: str = Field(..., description="Session containing virtual table data")
    query: str = Field(..., description="SQL query to execute on virtual tables")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('query')
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError('SQL query cannot be empty')
        # Basic SQL injection prevention - allow UPDATE/INSERT for manual ingredient linking
        dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE']
        query_upper = v.upper()
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                raise ValueError(f'Query contains prohibited keyword: {keyword}')
        
        # Additional safety for UPDATE/INSERT: require temp_ tables and session_id
        if query_upper.startswith('UPDATE') or query_upper.startswith('INSERT'):
            if 'temp_' not in v:
                raise ValueError('UPDATE/INSERT operations are only allowed on temp_ tables')
            # Note: session_id validation is handled in the execute_nutrition_sql function
        
        return v.strip()

class CNFSessionSummary(BaseModel):
    """Model for CNF session status and contents"""
    session_id: str = Field(..., description="Session identifier")
    nutrient_profiles_count: int = Field(..., description="Number of CNF profiles stored")
    ingredient_matches_count: int = Field(..., description="Number of ingredient-CNF matches")
    nutrition_summaries_count: int = Field(..., description="Number of calculated nutrition summaries")
    created_at: Optional[datetime] = Field(default=None, description="When session was created")
    last_updated: datetime = Field(default_factory=datetime.now, description="Last activity timestamp")

class CNFCleanupInput(BaseModel):
    """Input model for CNF session cleanup operations"""
    session_id: str = Field(..., description="Session to clean up CNF data for")
    cleanup_type: str = Field(default="all", description="Type of cleanup: 'profiles', 'matches', 'summaries', or 'all'")
    
    @validator('cleanup_type')
    def validate_cleanup_type(cls, v):
        valid_types = {'profiles', 'matches', 'summaries', 'all'}
        if v not in valid_types:
            raise ValueError(f'Cleanup type must be one of: {valid_types}')
        return v

class AnalyzeRecipeNutritionInput(BaseModel):
    """Input model for one-shot recipe nutrition analysis"""
    session_id: str = Field(..., description="Session containing the recipe data")
    recipe_id: str = Field(..., description="Recipe to analyze for nutrition")
    auto_link_major_ingredients: bool = Field(default=True, description="Whether to automatically link obvious ingredient matches")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('recipe_id')
    def validate_recipe_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Recipe ID cannot be empty')
        return v.strip()

class RecipeMacrosQueryInput(BaseModel):
    """Input model for querying temp_recipe_macros table"""
    session_id: str = Field(..., description="Session containing the recipe macros data")
    recipe_id: Optional[str] = Field(default=None, description="Optional specific recipe to filter (None = all recipes in session)")
    unit_match_status: Optional[str] = Field(default=None, description="Optional filter by unit match status (exact_match, conversion_available, manual_decision_needed, no_match, no_cnf_data)")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('unit_match_status')
    def validate_unit_match_status(cls, v):
        if v is not None:
            valid_statuses = ['exact_match', 'conversion_available', 'manual_decision_needed', 'no_match', 'no_cnf_data']
            if v not in valid_statuses:
                raise ValueError(f'Unit match status must be one of: {valid_statuses}')
        return v

class RecipeMacrosUpdateInput(BaseModel):
    """Input model for updating temp_recipe_macros with LLM conversion decisions"""
    session_id: str = Field(..., description="Session containing the recipe macros data")
    ingredient_id: str = Field(..., description="Ingredient ID to update")
    llm_conversion_decision: str = Field(..., description="LLM's conversion decision (e.g., '4 fillets = 565g')")
    llm_conversion_factor: float = Field(..., description="Calculated conversion factor (e.g., 5.65 for 565g/100g)")
    llm_reasoning: str = Field(..., description="LLM's reasoning for the conversion decision")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()
    
    @validator('ingredient_id')
    def validate_ingredient_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Ingredient ID cannot be empty')
        return v.strip()
    
    @validator('llm_conversion_factor')
    def validate_conversion_factor(cls, v):
        if v <= 0:
            raise ValueError('Conversion factor must be positive')
        return v