from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import re

@dataclass
class Recipe:
    title: str
    slug: str
    url: str
    ingredients: List[str]
    instructions: List[str]
    prep_time: Optional[str] = None
    cook_time: Optional[str] = None
    servings: Optional[int] = None
    categories: List[str] = None
    tips: List[str] = None
    recipe_highlights: List[dict[str, str]] = None
    nutrition_info: Optional[dict] = None
    image_url: Optional[str] = None
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = []
        if self.tips is None:  
            self.tips = []
        if self.recipe_highlights is None:  
            self.recipe_highlights = []