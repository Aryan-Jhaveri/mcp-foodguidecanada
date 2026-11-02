from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import re

@dataclass
class Recipe:
    title: str # The title of the recipe
    slug: str # A URL-friendly version of the title, typically used in URLs
    url: str # The URL where the recipe can be found
    ingredients: List[str] # A list of ingredients required for the recipe
    instructions: List[str] # Step-by-step instructions for preparing the recipe
    prep_time: Optional[str] = None # Preparation time, e.g., "15 minutes"
    cook_time: Optional[str] = None # Cooking time, e.g., "30 minutes"
    servings: Optional[int] = None # Number of servings the recipe yields
    categories: List[str] = None   # Categories or tags associated with the recipe
    tips: List[str] = None # Additional tips or notes for the recipe
    recipe_highlights: List[dict[str, str]] = None # Highlights of the recipe
    nutrition_info: Optional[dict] = None # <--- NOT USED IN THE CURRENT VERSION
    image_url: Optional[str] = None # URL of the recipe image
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = []
        if self.tips is None:  
            self.tips = []
        if self.recipe_highlights is None:  
            self.recipe_highlights = []