import os
import json
import requests
from pathlib import Path
from typing import List, Optional
import sys

# Dynamically handle imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(parent_dir)

# Try to import with different methods
try:
    # Try first with src prefix
    from src.models.recipe import Recipe
except ImportError:
    try:
        # Next, try with parent directory
        from models.recipe import Recipe
    except ImportError:
        # As a last resort, modify sys.path and try again
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from models.recipe import Recipe

class RecipeDownloader:
    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        self.recipes_dir = self.output_dir / "recipes"
        self.images_dir = self.output_dir / "images"
        self.recipes_dir.mkdir(exist_ok=True)
        self.images_dir.mkdir(exist_ok=True)
    
    def save_recipe(self, recipe: Recipe, format: str = "json") -> str:
        """Save recipe to file."""
        filename = f"{recipe.slug}.{format}"
        filepath = self.recipes_dir / filename
        
        if format == "json":
            self._save_as_json(recipe, filepath)
        elif format == "md":
            self._save_as_markdown(recipe, filepath)
        
        # Download image if available
        if recipe.image_url:
            self._download_image(recipe.image_url, recipe.slug)
        
        return str(filepath)
    
    def print_recipe(self, recipe: Recipe) -> None:
        """Print recipe data as formatted JSON to console."""
        recipe_dict = {
            'title': recipe.title,
            'slug': recipe.slug,
            'url': recipe.url,
            'ingredients': recipe.ingredients,
            'instructions': recipe.instructions,
            'prep_time': recipe.prep_time,
            'cook_time': recipe.cook_time,
            'servings': recipe.servings,
            'categories': recipe.categories,
            'tips': recipe.tips,
            'recipe_highlights': recipe.recipe_highlights,
            'image_url': recipe.image_url
        }
        
        # Print formatted JSON
        print(json.dumps(recipe_dict, indent=2, ensure_ascii=False))
    
    def _save_as_json(self, recipe: Recipe, filepath: Path):
        """Save recipe as JSON."""
        recipe_dict = {
            'title': recipe.title,
            'slug': recipe.slug,
            'url': recipe.url,
            'ingredients': recipe.ingredients,
            'instructions': recipe.instructions,
            'prep_time': recipe.prep_time,
            'cook_time': recipe.cook_time,
            'servings': recipe.servings,
            'categories': recipe.categories,
            'tips': recipe.tips,
            'recipe_highlights': recipe.recipe_highlights,
            'image_url': recipe.image_url
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(recipe_dict, f, indent=2, ensure_ascii=False)

    def _save_as_markdown(self, recipe: Recipe, filepath: Path):
        """Save recipe as Markdown."""
        content = f"# {recipe.title}\n\n"
        
        if recipe.prep_time or recipe.cook_time:
            content += "## Time\n"
            if recipe.prep_time:
                content += f"- Prep: {recipe.prep_time}\n"
            if recipe.cook_time:
                content += f"- Cook: {recipe.cook_time}\n"
            content += "\n"
        
        if recipe.servings:
            content += f"**Servings:** {recipe.servings}\n\n"
        
        content += "## Ingredients\n"
        for ingredient in recipe.ingredients:
            content += f"- {ingredient}\n"
        
        content += "\n## Instructions\n"
        for i, instruction in enumerate(recipe.instructions, 1):
            content += f"{i}. {instruction}\n"
        
        # Add recipe highlights section
        if recipe.recipe_highlights:
            content += "\n## Recipe Highlights\n"
            for i, highlight in enumerate(recipe.recipe_highlights, 1):
                slide_count = highlight.get('slide_count', f'{i}')
                caption = highlight.get('caption_text', '')
                image_url = highlight.get('image_url', '')
                
                content += f"\n### Step {slide_count}\n"
                content += f"**{caption}**\n\n"
                if image_url:
                    content += f"![Step {slide_count}]({image_url})\n\n"
        
        # Add tips section
        if recipe.tips:
            content += "\n## Tips\n"
            for tip in recipe.tips:
                content += f"- {tip}\n"
        
        content += f"\n---\n*Source: [{recipe.url}]({recipe.url})*"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def _download_image(self, image_url: str, slug: str) -> Optional[str]:
        """Download recipe image."""
        try:
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            
            # Get file extension from URL or content-type
            ext = image_url.split('.')[-1].split('?')[0]
            if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                ext = 'jpg'
            
            filename = f"{slug}.{ext}"
            filepath = self.images_dir / filename
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return str(filepath)
        except Exception as e:
            print(f"Error downloading image: {e}")
            return None