import argparse
import sys
from typing import List
from .api.search import RecipeSearcher
from .api.recipe import RecipeFetcher
from .models.filters import SearchFilters
from .utils.downloader import RecipeDownloader

class FoodGuideCLI:
    def __init__(self):
        self.searcher = RecipeSearcher()
        self.fetcher = RecipeFetcher()
        self.downloader = RecipeDownloader()

    def create_parser(self):
        """Create the argument parser"""
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
        download_parser.add_argument('--print', action='store_true',
                           help='Print recipe data as JSON to console instead of saving to file')
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
        
        return parser

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
                        print(f"✓ Added {display_name} filter: {value}")
                    else:
                        invalid_filters.append((display_name, value))
                        print(f"✗ Warning: Filter '{value}' not found in {display_name}")
        
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
                    print(f"✓ Added collection filter: {collection}")
                else:
                    invalid_filters.append(('collections', collection))
                    print(f"✗ Warning: Collection '{collection}' not found")
        
        # Get search text Join search words into a single string
        search_text = ' '.join(args.search_text) if args.search_text else ''
        
        # Check if we have any valid search criteria
        if not search_text.strip() and not valid_filters_added:
            print("\n❌ Error: No valid search criteria provided!")
            
            if invalid_filters:
                print("\nInvalid filters found:")
                for filter_type, value in invalid_filters:
                    print(f"  • {filter_type}: '{value}'")
                
                print("\n💡 Suggestions:")
                self.show_filter_suggestions(filters, invalid_filters)
            
            print("\nUsage examples:")
            print("  python main.py search apple")
            print("  python main.py search --fruits apple")
            print("  python main.py search \"healthy breakfast\" --meals breakfast")
            print("  python main.py search --fruits apple --vegetables carrot")
            
            sys.exit(1)  # Exit with error code
        
        # Show what we're searching for
        print(f"\n🔍 Searching for: '{search_text}'")
        if valid_filters_added:
            print("📋 Active filters:", filters.get_filters_dict())
        
        # Perform search
        recipes = self.searcher.search_recipes(
            search_text=search_text,
            filters=filters if valid_filters_added else None,
            max_pages=getattr(args, 'max_pages', 35)
        )
        
        # Display results
        if recipes:
            print(f"\n✅ Found {len(recipes)} recipes:")
            for i, recipe in enumerate(recipes, 1):
                print(f"{i}. {recipe['title']}")
                print(f"   URL: {recipe['url']}")
        else:
            print("\n❌ No recipes found.")
            if valid_filters_added or search_text:
                print("💡 Try broadening your search criteria or using different filters.")

    def show_filter_suggestions(self, filters, invalid_filters):
        """Show suggestions for invalid filters"""
        
        # Group invalid filters by type
        invalid_by_type = {}
        for filter_type, value in invalid_filters:
            if filter_type not in invalid_by_type:
                invalid_by_type[filter_type] = []
            invalid_by_type[filter_type].append(value)
        
        for filter_type, invalid_values in invalid_by_type.items():
            print(f"\nAvailable {filter_type}:")
            
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
                    print(f"    • {item}")
                
                if len(available) > 10:
                    print(f"    ... and {len(available) - 10} more")
                
                # Try to suggest similar items
                for invalid_value in invalid_values:
                    suggestions = self.find_similar_items(invalid_value, available)
                    if suggestions:
                        print(f"  💡 Did you mean: {', '.join(suggestions[:3])}?")

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
        """Handle download command - UPDATED to support multiple URLs and print option"""
        if args.url:
            # Ensure args.url is a list of complete URLs, not split characters
            if isinstance(args.url, str):
                # If somehow it's a single string, wrap it in a list
                urls = [args.url]
            else:
                urls = args.url
            
            # Debug: Print what URLs we're processing
            print(f"Debug: Processing URLs: {urls}")
            
            # Download/print multiple recipes
            if args.print:
                print(f"Fetching {len(urls)} recipe(s) for display...")
            else:
                print(f"Downloading {len(urls)} recipe(s)...")
            
            successful_operations = 0
            failed_operations = 0
            
            for i, url in enumerate(urls, 1):
                # Validate URL format before processing
                if not url.startswith(('http://', 'https://')):
                    print(f"❌ Invalid URL format: {url}")
                    failed_operations += 1
                    continue
                    
                print(f"\n[{i}/{len(urls)}] Fetching recipe from: {url}")
                
                try:
                    recipe = self.fetcher.fetch_recipe(url)
                    
                    if recipe:
                        if args.print:
                            # Print to console
                            print(f"\n📄 Recipe Data for: {recipe.title}")
                            print("=" * 50)
                            self.downloader.print_recipe(recipe)
                            print("=" * 50)
                            successful_operations += 1
                        else:
                            # Save to file
                            filepath = self.downloader.save_recipe(recipe, format=args.format)
                            print(f"✅ Saved to: {filepath}")
                            successful_operations += 1
                    else:
                        print(f"❌ Failed to fetch recipe from: {url}")
                        failed_operations += 1
                        
                except Exception as e:
                    print(f"❌ Error processing {url}: {e}")
                    failed_operations += 1
            
            # Summary
            operation_type = "displayed" if args.print else "downloaded"
            print(f"\n📊 Operation Summary:")
            print(f"✅ Successfully {operation_type}: {successful_operations}")
            if failed_operations > 0:
                print(f"❌ Failed: {failed_operations}")
        
        elif args.search:
            # Search and download/print
            results = self.search_command(args)
            
            if results and args.download_all:
                if args.print:
                    print(f"\nFetching {len(results)} recipes for display...")
                else:
                    print(f"\nDownloading {len(results)} recipes...")
                
                successful_operations = 0
                failed_operations = 0
                
                for i, recipe_meta in enumerate(results, 1):
                    print(f"\n[{i}/{len(results)}] Processing: {recipe_meta['title']}")
                    
                    try:
                        recipe = self.fetcher.fetch_recipe(recipe_meta['url'])
                        if recipe:
                            if args.print:
                                # Print to console
                                print(f"\n📄 Recipe Data for: {recipe.title}")
                                print("=" * 50)
                                self.downloader.print_recipe(recipe)
                                print("=" * 50)
                                successful_operations += 1
                            else:
                                # Save to file
                                filepath = self.downloader.save_recipe(recipe, format=args.format)
                                print(f"✅ Saved to: {filepath}")
                                successful_operations += 1
                        else:
                            print(f"❌ Failed to fetch: {recipe_meta['title']}")
                            failed_operations += 1
                    except Exception as e:
                        print(f"❌ Error processing {recipe_meta['title']}: {e}")
                        failed_operations += 1
                
                # Summary
                operation_type = "displayed" if args.print else "downloaded"
                print(f"\n📊 Operation Summary:")
                print(f"✅ Successfully {operation_type}: {successful_operations}")
                if failed_operations > 0:
                    print(f"❌ Failed: {failed_operations}")

    def list_filters_command(self, args):
        """List all available filters."""
        filters = SearchFilters(auto_update=True)
        
        if args.filter_type:
            # Show specific filter type
            available = filters.get_available_filters(args.filter_type)
            if available:
                print(f"\nAvailable {args.filter_type}:")
                for item in sorted(available):
                    print(f"  - {item}")
            else:
                print(f"Unknown filter type: {args.filter_type}")
        else:
            # Show all filter types
            print("\nAvailable filter types:")
            for category in ["vegetables", "fruits", "proteins", "whole grains", 
                            "meal", "cooking appliance"]:
                print(f"\n{category.title()}:")
                items = filters.get_available_filters(category)
                for item in sorted(items[:]):  
                    print(f"  - {item}")
            
            print("\nCollections:")
            for collection in filters.get_available_collections():
                print(f"  - {collection.replace('_', ' ').title()}")

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
        else:
            parser.print_help()

def main():
    """Main entry point"""
    cli = FoodGuideCLI()
    cli.run()

if __name__ == '__main__':
    main()