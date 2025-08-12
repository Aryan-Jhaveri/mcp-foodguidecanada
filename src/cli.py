import argparse
import sys
import sqlite3
import json
import uuid
from typing import List, Dict, Any, Optional
from .api.search import RecipeSearcher
from .api.recipe import RecipeFetcher
from .models.filters import SearchFilters
from .utils.downloader import RecipeDownloader
from .db.connection import get_db_connection
from .db.schema import (
    initialize_database, 
    create_virtual_recipe_session, 
    cleanup_virtual_session, 
    list_active_virtual_sessions,
    store_recipe_in_virtual_session,
    get_virtual_session_recipes
)
from .models.db_models import RecipeInput, FavoriteInput, SessionInput, RecipeQueryInput

## db update


class FoodGuideCLI:
    def __init__(self):
        self.searcher = RecipeSearcher()
        self.fetcher = RecipeFetcher()
        self.downloader = RecipeDownloader()

    # Database management methods
    def initialize_db(self):
        """Initialize the recipe database."""
        result = initialize_database()
        if "success" in result:
            #print(f"✅ {result['success']}")
        else:
            #print(f"❌ {result['error']}")
        return result

    def create_session(self, session_id: str):
        """Create a virtual recipe session."""
        result = create_virtual_recipe_session(session_id)
        if "success" in result:
            #print(f"✅ {result['success']}")
        else:
            #print(f"❌ {result['error']}")
        return result

    def cleanup_session(self, session_id: str):
        """Clean up a virtual recipe session."""
        result = cleanup_virtual_session(session_id)
        if "success" in result:
            #print(f"✅ {result['success']}")
        elif "message" in result:
            #print(f"ℹ️ {result['message']}")
        else:
            #print(f"❌ {result['error']}")
        return result

    def list_sessions(self):
        """List all active virtual sessions."""
        result = list_active_virtual_sessions()
        if "sessions" in result:
            sessions = result["sessions"]
            if sessions:
                #print("📋 Active sessions:")
                for session in sessions:
                    #print(f"  • {session['session_id']}: {session['recipe_count']} recipes")
            else:
                #print("ℹ️ No active sessions found")
        else:
            #print(f"❌ {result['error']}")
        return result

    def store_recipe(self, session_id: str, recipe_url: str):
        """Fetch and store a recipe in a virtual session."""
        #print(f"🔄 Fetching recipe from: {recipe_url}")
        
        # Fetch the recipe
        recipe = self.fetcher.fetch_recipe(recipe_url)
        if not recipe:
            #print("❌ Failed to fetch recipe")
            return {"error": "Failed to fetch recipe"}

        # Convert recipe to dict format
        recipe_data = {
            "title": recipe.title,
            "slug": getattr(recipe, 'slug', ''),
            "url": recipe_url,
            "ingredients": recipe.ingredients or [],
            "instructions": recipe.instructions or [],
            "prep_time": getattr(recipe, 'prep_time', ''),
            "cook_time": getattr(recipe, 'cook_time', ''),
            "servings": getattr(recipe, 'servings', None),
            "categories": getattr(recipe, 'categories', []),
            "tips": getattr(recipe, 'tips', []),
            "recipe_highlights": getattr(recipe, 'recipe_highlights', []),
            "image_url": getattr(recipe, 'image_url', ''),
            "source": "Health Canada's Food Guide",
            "website": "https://food-guide.canada.ca/",
            "attribution": "Recipe sourced from Canada's official Food Guide"
        }

        # Generate recipe ID and store
        recipe_id = str(uuid.uuid4())
        result = store_recipe_in_virtual_session(session_id, recipe_id, recipe_data)
        
        if "success" in result:
            #print(f"✅ {result['success']}")
            #print(f"   Recipe ID: {recipe_id}")
            #print(f"   Title: {result.get('title', 'Unknown')}")
            #print(f"   Ingredients: {result.get('ingredients_count', 0)}")
            #print(f"   Instructions: {result.get('instructions_count', 0)}")
        else:
            #print(f"❌ {result['error']}")
        
        return result

    def get_session_recipes(self, session_id: str, recipe_id: Optional[str] = None):
        """Get recipes from a virtual session."""
        result = get_virtual_session_recipes(session_id, recipe_id)
        
        if "recipes" in result:
            recipes = result["recipes"]
            if recipes:
                #print(f"📋 Found {len(recipes)} recipe(s) in session '{session_id}':")
                for recipe in recipes:
                    #print(f"\n  🍽️ {recipe.get('title', 'Unknown')}")
                    #print(f"     Recipe ID: {recipe.get('recipe_id', 'Unknown')}")
                    #print(f"     Servings: {recipe.get('base_servings', 'Unknown')}")
                    #print(f"     Ingredients: {len(recipe.get('ingredients', []))}")
                    #print(f"     Instructions: {len(recipe.get('instructions', []))}")
            else:
                #print(f"ℹ️ No recipes found in session '{session_id}'")
        else:
            #print(f"❌ {result['error']}")
        
        return result

    def parse_ingredients(self, session_id: str, recipe_id: Optional[str] = None):
        """Parse ingredients in a session to extract amounts, units, and names."""
        from .db.ingredient_parser import _parse_ingredient_text
        from .db.schema import get_virtual_session_data
        
        try:
            # Get virtual session data
            session = get_virtual_session_data(session_id)
            if not session:
                #print(f"❌ Virtual session {session_id} not found")
                return {"error": f"Virtual session {session_id} not found"}
            
            # Get ingredients to process
            ingredients_to_process = []
            for ingredient_id, ingredient_data in session['ingredients'].items():
                if recipe_id and ingredient_data['recipe_id'] != recipe_id:
                    continue
                ingredients_to_process.append((ingredient_id, ingredient_data))
            
            if not ingredients_to_process:
                #print("❌ No ingredients found for parsing")
                return {"error": "No ingredients found for parsing"}
            
            #print(f"🔄 Parsing {len(ingredients_to_process)} ingredients...")
            
            parsing_results = []
            updated_count = 0
            failed_count = 0
            
            for ingredient_id, ingredient_data in ingredients_to_process:
                # Parse from ingredient_list_org
                ingredient_text = ingredient_data.get('ingredient_list_org', '')
                if not ingredient_text:
                    failed_count += 1
                    continue
                    
                parsed_data = _parse_ingredient_text(ingredient_text)
                
                # Update virtual session data with parsed components
                ingredient_data['ingredient_name'] = parsed_data['clean_name']
                ingredient_data['amount'] = parsed_data['amount']
                ingredient_data['unit'] = parsed_data['unit']
                
                parsing_results.append({
                    'ingredient_id': ingredient_id,
                    'original_text': ingredient_text,
                    'parsed_amount': parsed_data['amount'],
                    'parsed_unit': parsed_data['unit'],
                    'clean_name': parsed_data['clean_name'],
                    'is_section_header': parsed_data['is_section_header']
                })
                
                if parsed_data['amount'] is not None:
                    updated_count += 1
                    #print(f"  ✅ {ingredient_text} → {parsed_data['amount']} {parsed_data['unit']} {parsed_data['clean_name']}")
                else:
                    failed_count += 1
                    #print(f"  ⚠️ {ingredient_text} → No amount found")
            
            #print(f"\n📊 Parsing Summary:")
            #print(f"   Total ingredients: {len(ingredients_to_process)}")
            #print(f"   Successfully parsed: {updated_count}")
            #print(f"   Failed to parse: {failed_count}")
            #print(f"   Success rate: {(updated_count/len(ingredients_to_process)*100):.1f}%")
            
            return {
                "success": f"Processed {len(ingredients_to_process)} ingredients",
                "total_ingredients": len(ingredients_to_process),
                "successfully_parsed": updated_count,
                "failed_to_parse": failed_count,
                "parsing_details": parsing_results
            }
                
        except Exception as e:
            #print(f"❌ Error parsing ingredients: {e}")
            return {"error": f"Unexpected error parsing ingredients: {e}"}

    def scale_recipe(self, session_id: str, recipe_id: str, target_servings: int):
        """Scale a recipe to a target number of servings."""
        from .db.math_tools import _scale_ingredient_amount
        from .db.schema import get_virtual_session_data
        
        try:
            # Get virtual session data
            session = get_virtual_session_data(session_id)
            if not session:
                #print(f"❌ Virtual session {session_id} not found")
                return {"error": f"Virtual session {session_id} not found"}
            
            # Get original recipe data
            if recipe_id not in session['recipes']:
                #print(f"❌ Recipe {recipe_id} not found in session")
                return {"error": f"Recipe {recipe_id} not found in session {session_id}"}
            
            recipe_data = session['recipes'][recipe_id]
            original_servings = recipe_data.get('base_servings') or 1
            scale_factor = target_servings / original_servings
            
            #print(f"🔄 Scaling '{recipe_data.get('title', 'Unknown')}' from {original_servings} to {target_servings} servings")
            #print(f"   Scale factor: {scale_factor:.3f}")
            
            # Get ingredients for this recipe
            recipe_ingredients = [
                (ing_id, ing_data) for ing_id, ing_data in session['ingredients'].items()
                if ing_data['recipe_id'] == recipe_id
            ]
            
            # Sort by ingredient order
            recipe_ingredients.sort(key=lambda x: x[1]['ingredient_order'])
            
            scaled_ingredients = []
            scaling_log = []
            
            for ingredient_id, ingredient_data in recipe_ingredients:
                original_text = ingredient_data.get('ingredient_list_org', '')
                ingredient_name = ingredient_data.get('ingredient_name', '')
                parsed_amount = ingredient_data.get('amount')
                parsed_unit = ingredient_data.get('unit')
                
                # Use parsed data if available, otherwise fall back to text parsing
                if parsed_amount is not None and parsed_unit is not None:
                    # Direct calculation using parsed data
                    scaled_amount_value = float(parsed_amount) * scale_factor
                    scaled_text = f"{scaled_amount_value} {parsed_unit} {ingredient_name}"
                    
                    #print(f"  ✅ {parsed_amount} {parsed_unit} → {scaled_amount_value:.2f} {parsed_unit}: {ingredient_name}")
                    scaling_log.append(f"{parsed_amount} {parsed_unit} → {scaled_amount_value:.2f} {parsed_unit}: {ingredient_name}")
                else:
                    # Fall back to text parsing
                    scaled_text, amount_info = _scale_ingredient_amount(original_text, scale_factor)
                    
                    if amount_info['found_amount']:
                        #print(f"  ✅ {amount_info['original_amount']} → {amount_info['scaled_amount']}: {amount_info['ingredient_base']}")
                        scaling_log.append(f"{amount_info['original_amount']} → {amount_info['scaled_amount']}: {amount_info['ingredient_base']}")
                    else:
                        #print(f"  ⚠️ No scaling: {original_text}")
                
                scaled_ingredients.append({
                    'original_text': original_text,
                    'scaled_text': scaled_text,
                    'ingredient_name': ingredient_name
                })
            
            #print(f"\n📊 Scaling Summary:")
            #print(f"   Ingredients processed: {len(recipe_ingredients)}")
            #print(f"   Successfully scaled: {len(scaling_log)}")
            
            return {
                "success": f"Recipe scaled from {original_servings} to {target_servings} servings",
                "recipe_title": recipe_data.get('title', 'Unknown'),
                "scale_factor": scale_factor,
                "scaled_ingredients": scaled_ingredients,
                "scaling_summary": scaling_log
            }
                
        except Exception as e:
            #print(f"❌ Error scaling recipe: {e}")
            return {"error": f"Unexpected error scaling recipe: {e}"}

    # Favorites management methods
    def add_favorite(self, recipe_url: str, recipe_title: str = None, user_session: str = "default", custom_notes: str = None):
        """Add a recipe to favorites."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                favorite_id = str(uuid.uuid4())
                
                cursor.execute("""
                    INSERT OR IGNORE INTO user_favorites 
                    (favorite_id, recipe_url, recipe_title, user_session, custom_notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    favorite_id,
                    recipe_url,
                    recipe_title,
                    user_session,
                    custom_notes
                ))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    #print(f"✅ Recipe added to favorites: {recipe_title or recipe_url}")
                    return {"success": f"Recipe added to favorites: {recipe_title}"}
                else:
                    #print(f"ℹ️ Recipe was already in favorites")
                    return {"message": "Recipe was already in favorites"}
                    
        except sqlite3.Error as e:
            #print(f"❌ SQLite error adding favorite: {e}")
            return {"error": f"SQLite error adding favorite: {e}"}
        except Exception as e:
            #print(f"❌ Unexpected error adding favorite: {e}")
            return {"error": f"Unexpected error adding favorite: {e}"}

    def remove_favorite(self, recipe_url: str, user_session: str = None):
        """Remove a recipe from favorites."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                where_clause = "recipe_url = ?"
                params = [recipe_url]
                
                if user_session:
                    where_clause += " AND user_session = ?"
                    params.append(user_session)
                
                cursor.execute(f"""
                    DELETE FROM user_favorites WHERE {where_clause}
                """, params)
                
                if cursor.rowcount > 0:
                    conn.commit()
                    #print(f"✅ Recipe removed from favorites")
                    return {"success": f"Recipe removed from favorites"}
                else:
                    #print(f"ℹ️ Recipe was not in favorites")
                    return {"message": "Recipe was not in favorites"}
                    
        except sqlite3.Error as e:
            #print(f"❌ SQLite error removing favorite: {e}")
            return {"error": f"SQLite error removing favorite: {e}"}
        except Exception as e:
            #print(f"❌ Unexpected error removing favorite: {e}")
            return {"error": f"Unexpected error removing favorite: {e}"}

    def list_favorites_cmd(self, user_session: str = None):
        """List user's favorite recipes."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                if user_session:
                    cursor.execute("""
                        SELECT * FROM user_favorites 
                        WHERE user_session = ? 
                        ORDER BY added_at DESC
                    """, (user_session,))
                else:
                    cursor.execute("""
                        SELECT * FROM user_favorites 
                        ORDER BY added_at DESC
                    """)
                
                favorites = [dict(row) for row in cursor.fetchall()]
                
                if favorites:
                    #print(f"⭐ Found {len(favorites)} favorite recipe(s):")
                    for i, fav in enumerate(favorites, 1):
                        #print(f"\n{i}. {fav['recipe_title'] or 'Untitled'}")
                        #print(f"   URL: {fav['recipe_url']}")
                        #print(f"   Added: {fav['added_at']}")
                        if fav['custom_notes']:
                            #print(f"   Notes: {fav['custom_notes']}")
                        if fav['user_session']:
                            #print(f"   Session: {fav['user_session']}")
                else:
                    #print("ℹ️ No favorites found")
                
                return {"favorites": favorites}
                
        except sqlite3.Error as e:
            #print(f"❌ SQLite error listing favorites: {e}")
            return {"error": f"SQLite error listing favorites: {e}"}
        except Exception as e:
            #print(f"❌ Unexpected error listing favorites: {e}")
            return {"error": f"Unexpected error listing favorites: {e}"}

    def create_parser(self):
        """Create the argument parser with database commands."""
        parser = argparse.ArgumentParser(description='Search Canada Food Guide recipes')
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Search subcommand
        search_parser = subparsers.add_parser('search', help='Search for recipes')
        
        # Add positional argument for search text
        search_parser.add_argument('search_text', nargs='*', default='', 
                                  help='Text to search for in recipes')
        
        # Add filter arguments
        search_parser.add_argument('--fruits', nargs='*', 
                                  help='Filter by fruits (e.g., apple, banana)')
        search_parser.add_argument('--vegetables', nargs='*',
                                  help='Filter by vegetables (e.g., carrot, broccoli)')
        search_parser.add_argument('--proteins', nargs='*',
                                  help='Filter by proteins (e.g., chicken, tofu)')
        search_parser.add_argument('--whole-grains', dest='whole_grains', nargs='*',
                                  help='Filter by whole grains (e.g., rice, quinoa)')
        search_parser.add_argument('--meals', nargs='*',
                                  help='Filter by meal type (e.g., breakfast, dinner)')
        search_parser.add_argument('--appliances', nargs='*',
                                  help='Filter by cooking appliance (e.g., oven, stovetop)')
        search_parser.add_argument('--collections', nargs='*',
                                  help='Filter by collections (e.g., vegetarian, kid-friendly)')
        
        # Other options
        search_parser.add_argument('--max-pages', type=int, default=5,
                                  help='Maximum pages to search (default: 5)')
        
        # Download command
        download_parser = subparsers.add_parser('download', help='Download recipes')
        download_parser.add_argument('--url', help='Recipe URL to download')
        download_parser.add_argument('--search', help='Search and download')
        download_parser.add_argument('--download-all', action='store_true', 
                                   help='Download all search results')
        download_parser.add_argument('--format', choices=['json', 'md'], 
                                   default='json', help='Output format')
        download_parser.add_argument('--#print', action='store_true',
                           help='#print recipe data as JSON to console instead of saving to file')
        download_parser.add_argument('--fruits', nargs='+', help='Fruit filter IDs')
        download_parser.add_argument('--vegetables', nargs='+', help='Vegetable filter IDs')
        download_parser.add_argument('--collection', help='Collection ID')
        download_parser.add_argument('--max-pages', type=int, default=5, help='Max pages to search')

        # List filters command
        list_filters_parser = subparsers.add_parser('list-filters', help='List available filters')
        list_filters_parser.add_argument('--filter-type', choices=['vegetables', 'fruits', 
                                                                   'proteins', 'whole_grains', 
                                                                   'meal', 'cooking_appliance'], 
                                         help='Filter type to list')
        list_filters_parser.add_argument('--collection', action='store_true',
                                        help='List available collections')
        
        # Database commands
        db_parser = subparsers.add_parser('db', help='Database management commands')
        db_subparsers = db_parser.add_subparsers(dest='db_command', help='Database operations')
        
        # Initialize database
        db_subparsers.add_parser('init', help='Initialize the database')
        
        # Session management
        session_parser = db_subparsers.add_parser('session', help='Session management')
        session_subparsers = session_parser.add_subparsers(dest='session_command', help='Session operations')
        
        create_session_parser = session_subparsers.add_parser('create', help='Create a session')
        create_session_parser.add_argument('session_id', help='Session ID to create')
        
        cleanup_session_parser = session_subparsers.add_parser('cleanup', help='Clean up a session')
        cleanup_session_parser.add_argument('session_id', help='Session ID to clean up')
        
        session_subparsers.add_parser('list', help='List all active sessions')
        
        # Recipe storage
        store_parser = db_subparsers.add_parser('store', help='Store a recipe in session')
        store_parser.add_argument('session_id', help='Session ID')
        store_parser.add_argument('recipe_url', help='Recipe URL to store')
        
        # Get recipes from session
        get_parser = db_subparsers.add_parser('get', help='Get recipes from session')
        get_parser.add_argument('session_id', help='Session ID')
        get_parser.add_argument('--recipe-id', help='Specific recipe ID (optional)')
        
        # Parse ingredients
        parse_parser = db_subparsers.add_parser('parse', help='Parse ingredients in session')
        parse_parser.add_argument('session_id', help='Session ID')
        parse_parser.add_argument('--recipe-id', help='Specific recipe ID (optional)')
        
        # Scale recipe
        scale_parser = db_subparsers.add_parser('scale', help='Scale recipe servings')
        scale_parser.add_argument('session_id', help='Session ID')
        scale_parser.add_argument('recipe_id', help='Recipe ID')
        scale_parser.add_argument('target_servings', type=int, help='Target number of servings')
        
        # Favorites management
        fav_parser = db_subparsers.add_parser('favorites', help='Manage favorites')
        fav_subparsers = fav_parser.add_subparsers(dest='fav_command', help='Favorites operations')
        
        add_fav_parser = fav_subparsers.add_parser('add', help='Add recipe to favorites')
        add_fav_parser.add_argument('recipe_url', help='Recipe URL')
        add_fav_parser.add_argument('--title', help='Recipe title')
        add_fav_parser.add_argument('--session', default='default', help='User session')
        add_fav_parser.add_argument('--notes', help='Custom notes')
        
        remove_fav_parser = fav_subparsers.add_parser('remove', help='Remove recipe from favorites')
        remove_fav_parser.add_argument('recipe_url', help='Recipe URL')
        remove_fav_parser.add_argument('--session', help='User session')
        
        list_fav_parser = fav_subparsers.add_parser('list', help='List favorite recipes')
        list_fav_parser.add_argument('--session', help='Filter by user session')
        
        return parser

    def handle_db_command(self, args):
        """Handle database commands."""
        if args.db_command == 'init':
            self.initialize_db()
        
        elif args.db_command == 'session':
            if args.session_command == 'create':
                self.create_session(args.session_id)
            elif args.session_command == 'cleanup':
                self.cleanup_session(args.session_id)
            elif args.session_command == 'list':
                self.list_sessions()
        
        elif args.db_command == 'store':
            self.store_recipe(args.session_id, args.recipe_url)
        
        elif args.db_command == 'get':
            self.get_session_recipes(args.session_id, getattr(args, 'recipe_id', None))
        
        elif args.db_command == 'parse':
            self.parse_ingredients(args.session_id, getattr(args, 'recipe_id', None))
        
        elif args.db_command == 'scale':
            self.scale_recipe(args.session_id, args.recipe_id, args.target_servings)
        
        elif args.db_command == 'favorites':
            if args.fav_command == 'add':
                self.add_favorite(args.recipe_url, args.title, args.session, args.notes)
            elif args.fav_command == 'remove':
                self.remove_favorite(args.recipe_url, args.session)
            elif args.fav_command == 'list':
                self.list_favorites_cmd(args.session)

    def handle_search_command(self, args):
        """Handle the search command with proper error handling"""
        
        # Initialize filters
        filters = SearchFilters()
        
        # Track validation results
        valid_filters_added = False
        invalid_filters = []
        
        # Helper function to add filters with validation
        def add_filter_with_validation(filter_type, filter_values, display_name):
            nonlocal valid_filters_added
            if filter_values:
                for value in filter_values:
                    filter_id = filters._resolve_filter_id(filter_type, value)
                    if filter_id:
                        filters.add_filter(filter_type, value)
                        valid_filters_added = True
                        #print(f"✓ Added {display_name} filter: {value}")
                    else:
                        invalid_filters.append((display_name, value))
                        #print(f"✗ Warning: Filter '{value}' not found in {display_name}")
        
        # Add filters with validation
        add_filter_with_validation('fruits', args.fruits, 'fruits')
        add_filter_with_validation('vegetables', args.vegetables, 'vegetables')
        add_filter_with_validation('proteins', args.proteins, 'proteins')
        add_filter_with_validation('whole_grains', getattr(args, 'whole_grains', None), 'whole grains')
        add_filter_with_validation('meals_and_course', args.meals, 'meals')
        add_filter_with_validation('cooking_appliance', args.appliances, 'appliances')
        
        # Handle collections separately
        if getattr(args, 'collections', None):
            for collection in args.collections:
                collection_key = filters._normalize_key(collection)
                if collection_key in filters._collections_data:
                    filters.add_collection(collection)
                    valid_filters_added = True
                    #print(f"✓ Added collection filter: {collection}")
                else:
                    invalid_filters.append(('collections', collection))
                    #print(f"✗ Warning: Collection '{collection}' not found")
        
        # Get search text Join search words into a single string
        search_text = ' '.join(args.search_text) if args.search_text else ''
        
        # Check if we have any valid search criteria
        if not search_text.strip() and not valid_filters_added:
            #print("\n❌ Error: No valid search criteria provided!")
            
            if invalid_filters:
                #print("\nInvalid filters found:")
                for filter_type, value in invalid_filters:
                    #print(f"  • {filter_type}: '{value}'")
                
                #print("\n💡 Suggestions:")
                self.show_filter_suggestions(filters, invalid_filters)
            
            #print("\nUsage examples:")
            #print("  python main.py search apple")
            #print("  python main.py search --fruits apple")
            #print("  python main.py search \"healthy breakfast\" --meals breakfast")
            #print("  python main.py search --fruits apple --vegetables carrot")
            
            sys.exit(1)  # Exit with error code
        
        # Show what we're searching for
        #print(f"\n🔍 Searching for: '{search_text}'")
        if valid_filters_added:
            #print("📋 Active filters:", filters.get_filters_dict())
        
        # Perform search
        recipes = self.searcher.search_recipes(
            search_text=search_text,
            filters=filters if valid_filters_added else None,
            max_pages=getattr(args, 'max_pages', 35)
        )
        
        # Display results
        if recipes:
            #print(f"\n✅ Found {len(recipes)} recipes:")
            for i, recipe in enumerate(recipes, 1):
                #print(f"{i}. {recipe['title']}")
                #print(f"   URL: {recipe['url']}")
        else:
            #print("\n❌ No recipes found.")
            if valid_filters_added or search_text:
                #print("💡 Try broadening your search criteria or using different filters.")

    def show_filter_suggestions(self, filters, invalid_filters):
        """Show suggestions for invalid filters"""
        
        # Group invalid filters by type
        invalid_by_type = {}
        for filter_type, value in invalid_filters:
            if filter_type not in invalid_by_type:
                invalid_by_type[filter_type] = []
            invalid_by_type[filter_type].append(value)
        
        for filter_type, invalid_values in invalid_by_type.items():
            #print(f"\nAvailable {filter_type}:")
            
            if filter_type == 'collections':
                available = list(filters._collections_data.keys())
            else:
                # Map display names to internal filter types
                type_mapping = {
                    'fruits': 'Fruits',
                    'vegetables': 'Vegetables', 
                    'proteins': 'Proteins',
                    'whole grains': 'Whole grains',
                    'meals': 'Meal',
                    'appliances': 'Cooking appliance'
                }
                
                internal_type = type_mapping.get(filter_type, filter_type)
                if internal_type in filters._filters_data:
                    available = [f.label for f in filters._filters_data[internal_type].values()]
                else:
                    available = []
            
            if available:
                # Show first 10 options, sorted
                available_sorted = sorted(available)[:10]
                for item in available_sorted:
                    #print(f"    • {item}")
                
                if len(available) > 10:
                    #print(f"    ... and {len(available) - 10} more")
                
                # Try to suggest similar items
                for invalid_value in invalid_values:
                    suggestions = self.find_similar_items(invalid_value, available)
                    if suggestions:
                        #print(f"  💡 Did you mean: {', '.join(suggestions[:3])}?")

    def find_similar_items(self, invalid_value, available_items, max_suggestions=3):
        """Find similar items using simple string matching"""
        invalid_lower = invalid_value.lower()
        suggestions = []
        
        # Look for items that start with the invalid value
        for item in available_items:
            if item.lower().startswith(invalid_lower):
                suggestions.append(item)
        
        # Look for items that contain the invalid value
        if len(suggestions) < max_suggestions:
            for item in available_items:
                if invalid_lower in item.lower() and item not in suggestions:
                    suggestions.append(item)
        
        return suggestions[:max_suggestions]

    def download_command(self, args):
        """Handle download command - UPDATED to support multiple URLs and #print option"""
        if args.url:
            # Ensure args.url is a list of complete URLs, not split characters
            if isinstance(args.url, str):
                # If somehow it's a single string, wrap it in a list
                urls = [args.url]
            else:
                urls = args.url
            
            # Debug: #print what URLs we're processing
            #print(f"Debug: Processing URLs: {urls}")
            
            # Download/#print multiple recipes
            if args.#print:
                #print(f"Fetching {len(urls)} recipe(s) for display...")
            else:
                #print(f"Downloading {len(urls)} recipe(s)...")
            
            successful_operations = 0
            failed_operations = 0
            
            for i, url in enumerate(urls, 1):
                # Validate URL format before processing
                if not url.startswith(('http://', 'https://')):
                    #print(f"❌ Invalid URL format: {url}")
                    failed_operations += 1
                    continue
                    
                #print(f"\n[{i}/{len(urls)}] Fetching recipe from: {url}")
                
                try:
                    recipe = self.fetcher.fetch_recipe(url)
                    
                    if recipe:
                        if args.#print:
                            # #print to console
                            #print(f"\n📄 Recipe Data for: {recipe.title}")
                            #print("=" * 50)
                            self.downloader.#print_recipe(recipe)
                            #print("=" * 50)
                            successful_operations += 1
                        else:
                            # Save to file
                            filepath = self.downloader.save_recipe(recipe, format=args.format)
                            #print(f"✅ Saved to: {filepath}")
                            successful_operations += 1
                    else:
                        #print(f"❌ Failed to fetch recipe from: {url}")
                        failed_operations += 1
                        
                except Exception as e:
                    #print(f"❌ Error processing {url}: {e}")
                    failed_operations += 1
            
            # Summary
            operation_type = "displayed" if args.#print else "downloaded"
            #print(f"\n📊 Operation Summary:")
            #print(f"✅ Successfully {operation_type}: {successful_operations}")
            if failed_operations > 0:
                #print(f"❌ Failed: {failed_operations}")
        
        elif args.search:
            # Search and download/#print
            results = self.search_command(args)
            
            if results and args.download_all:
                if args.#print:
                    #print(f"\nFetching {len(results)} recipes for display...")
                else:
                    #print(f"\nDownloading {len(results)} recipes...")
                
                successful_operations = 0
                failed_operations = 0
                
                for i, recipe_meta in enumerate(results, 1):
                    #print(f"\n[{i}/{len(results)}] Processing: {recipe_meta['title']}")
                    
                    try:
                        recipe = self.fetcher.fetch_recipe(recipe_meta['url'])
                        if recipe:
                            if args.#print:
                                # #print to console
                                #print(f"\n📄 Recipe Data for: {recipe.title}")
                                #print("=" * 50)
                                self.downloader.#print_recipe(recipe)
                                #print("=" * 50)
                                successful_operations += 1
                            else:
                                # Save to file
                                filepath = self.downloader.save_recipe(recipe, format=args.format)
                                #print(f"✅ Saved to: {filepath}")
                                successful_operations += 1
                        else:
                            #print(f"❌ Failed to fetch: {recipe_meta['title']}")
                            failed_operations += 1
                    except Exception as e:
                        #print(f"❌ Error processing {recipe_meta['title']}: {e}")
                        failed_operations += 1
                
                # Summary
                operation_type = "displayed" if args.#print else "downloaded"
                #print(f"\n📊 Operation Summary:")
                #print(f"✅ Successfully {operation_type}: {successful_operations}")
                if failed_operations > 0:
                    #print(f"❌ Failed: {failed_operations}")

    def list_filters_command(self, args):
        """List all available filters."""
        filters = SearchFilters(auto_update=True)
        
        if args.filter_type:
            # Show specific filter type
            available = filters.get_available_filters(args.filter_type)
            if available:
                #print(f"\nAvailable {args.filter_type}:")
                for item in sorted(available):
                    #print(f"  - {item}")
            else:
                #print(f"Unknown filter type: {args.filter_type}")
        else:
            # Show all filter types
            #print("\nAvailable filter types:")
            for category in ["vegetables", "fruits", "proteins", "whole grains", 
                            "meal", "cooking appliance"]:
                #print(f"\n{category.title()}:")
                items = filters.get_available_filters(category)
                for item in sorted(items[:]):  
                    #print(f"  - {item}")
            
            #print("\nCollections:")
            for collection in filters.get_available_collections():
                #print(f"  - {collection.replace('_', ' ').title()}")

    def run(self):
        """Run the CLI application."""
        parser = self.create_parser()
        args = parser.parse_args()
        
        if args.command == 'search':
            self.handle_search_command(args)
        elif args.command == 'download':
            self.download_command(args)
        elif args.command == 'list-filters':
            self.list_filters_command(args)
        elif args.command == 'db':
            self.handle_db_command(args)
        else:
            parser.#print_help()

def main():
    """Main entry point"""
    cli = FoodGuideCLI()
    cli.run()

if __name__ == '__main__':
    main()