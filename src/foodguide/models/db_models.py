from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class RecipeInput(BaseModel):
    """Input model for storing recipe data in temporary tables"""
    session_id: str = Field(..., description="Session identifier for temporary storage")
    recipe_data: Dict[str, Any] = Field(..., description="Complete recipe data from API")

class FavoriteInput(BaseModel):
    """Input model for adding/removing favorites"""
    recipe_url: str = Field(..., description="URL of the recipe to favorite")
    recipe_title: Optional[str] = Field(None, description="Title of the recipe")
    user_session: Optional[str] = Field(None, description="User session identifier")
    custom_notes: Optional[str] = Field(None, description="User's custom notes about the recipe")

class SessionInput(BaseModel):
    """Input model for session management"""
    session_id: str = Field(..., description="Session identifier")

class QueryInput(BaseModel):
    """Input model for database queries"""
    sql_query: str = Field(..., description="The SQL query to execute")

class RecipeQueryInput(BaseModel):
    """Input model for querying recipes in a session"""
    session_id: str = Field(..., description="Session identifier")
    recipe_id: Optional[str] = Field(None, description="Specific recipe ID to query")