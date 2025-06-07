# CLAUDE.md - Canada's Food Guide MCP Server

## Project Overview

This is an MCP (Model Context Protocol) server that provides access to Canada's Food Guide recipes through web scraping. The server offers three main tools for recipe discovery and retrieval from Health Canada's official Food Guide website.

## Current Architecture (v2.0)

### Core Components
- **FastMCP Server** (`src/server.py`): Main MCP server with recipe and database tools
- **Recipe Search** (`src/api/search.py`): Web scraping for recipe discovery
- **Recipe Fetcher** (`src/api/recipe.py`): Detailed recipe extraction
- **Filter System** (`src/models/filters.py`): Dynamic filter management
- **Virtual Session System** (`src/db/schema.py`): In-memory storage for temporary recipe data
- **Persistent Storage** (`src/db/`): SQLite database for user favorites only

### Available Tools

#### Recipe Tools
1. `search_recipes` - Search with filters for ingredients, meal types, appliances, collections
2. `get_recipe` - Fetch complete recipe details from URL
3. `list_filters` - Discover available search filter options

#### Session Management Tools
4. `initialize_database` - Set up persistent database (favorites only)
5. `store_recipe_in_session` - Store fetched recipes in virtual memory session
6. `get_session_recipes` - Retrieve recipes from virtual session storage
7. `create_virtual_recipe_session` - Create in-memory session for recipe analysis
8. `cleanup_virtual_session` - Remove virtual session data from memory
9. `list_active_virtual_sessions` - View active virtual recipe sessions

#### Favorites Management Tools (Persistent)
10. `add_to_favorites` - Add recipes to persistent SQLite favorites
11. `remove_from_favorites` - Remove recipes from persistent favorites
12. `list_favorites` - View user's favorite recipes

#### Ingredient Parsing Tools
13. `parse_and_update_ingredients` - Parse ingredient_list_org to extract amounts, units, names
14. `get_structured_ingredients` - View parsed ingredient data with amounts and units

#### Math & Calculation Tools (Now Using Parsed Data!)
15. `scale_recipe_servings` - Scale all ingredients using parsed amounts/units
16. `scale_individual_ingredient` - Scale specific ingredient using parsed data
17. `scale_multiple_ingredients` - Bulk scale multiple ingredients with parsed data
18. `compare_recipe_servings` - Compare recipes by servings, ingredients, or portions
19. `simple_math_calculator` - Perform arithmetic calculations with string variables

#### EER (Energy Requirement) Tools  
20. `get_eer_equations` - Fetch EER equations from Health Canada DRI tables in JSON format
21. `get_pal_descriptions` - Get Physical Activity Level category descriptions
22. Profile management tools: `create_user_profile`, `get_user_profile`, `list_user_profiles`, `delete_user_profile`

#### CNF (Canadian Nutrient File) Tools ✅ REVOLUTIONIZED!
23. `analyze_recipe_nutrition` - 🚀 **NEW!** One-shot nutrition analysis (replaces 8-step workflow!)
24. `search_cnf_foods` - Search Health Canada's CNF database for foods by name
25. `get_cnf_nutrient_profile` - Get complete nutrient profile and populate SQL tables  
26. `link_ingredient_to_cnf_simple` - Simplified ingredient-CNF linking for SQL
27. `execute_nutrition_sql` - Direct SQL queries on nutrition virtual tables with ready-to-use templates
28. `get_nutrition_tables_info` - SQL table schema and example queries
29. `get_ingredient_nutrition_matches` - View all ingredient-CNF linkages in a session
30. `clear_cnf_session_data` - Clean up CNF data from virtual sessions


#### DRI (Dietary Reference Intake) Tools ✅ ENHANCED!
33. `get_macronutrient_dri_tables` - Get complete DRI macronutrient tables from Health Canada
34. `get_specific_macronutrient_dri` - Get specific macronutrient DRI values by age/gender
35. `get_amdrs` - Get Acceptable Macronutrient Distribution Ranges by age group
36. `get_amino_acid_patterns` - Get amino acid patterns for protein quality evaluation (PDCAAS)
37. `compare_intake_to_dri` - Compare actual intake against DRI recommendations

#### Session-Aware DRI Tools ✅ NEW!
38. `store_dri_tables_in_session` - Cache complete DRI tables in virtual session storage
39. `get_dri_lookup_from_session` - Retrieve specific DRI values from session-cached data
40. `store_dri_user_profile_in_session` - Store user demographics for repeated DRI analysis
41. `calculate_dri_adequacy_in_session` - Calculate and store adequacy assessments
42. `calculate_dri_from_eer` - Convert EER energy requirements to macronutrient targets
43. `list_session_dri_analysis` - View all DRI calculations and analysis in session

## Development Context

### Current Status
- ✅ **Working MCP server** for recipe search and retrieval
- ✅ **Web scraping-based approach** using BeautifulSoup4  
- ✅ **Caching system** for filter data
- ✅ **Virtual session system** - In-memory storage prevents database bloat
- ✅ **Persistent favorites** - SQLite database for user bookmarks only
- ✅ **Ingredient parsing system** - Extracts amounts, units, and names from recipe text
- ✅ **Math tools working properly** - Scaling uses parsed ingredient data
- ✅ **Recipe comparison and analysis** capabilities
- ✅ **EER equations integration** - Live fetching from Health Canada DRI tables
- ✅ **Simple math calculator** - Safe arithmetic evaluation with variables
- ✅ **CNF integration** - Canadian Nutrient File food search and nutrition analysis

### Key Architectural Improvements (v2.0)
- **Virtual Sessions**: Temporary recipe data stored in memory, auto-cleaned
- **Dual Data Structure**: `ingredient_list_org` (original) + parsed components (`ingredient_name`, `amount`, `unit`)  
- **Smart Math Tools**: Use parsed data when available, fall back to text parsing
- **No Database Bloat**: Only user favorites persist in SQLite
- **Proper Workflow**: Store → Parse → Calculate sequence working correctly

### Known Limitations  
- Dependent on Canada's Food Guide website structure
- No nutritional analysis (planned for CNF integration)
- Performance bottlenecks from web scraping  
- Math calculations should be verified (ingredient parsing has limitations)

## Planned Evolution (v2.0)

Based on IMPLEMENTATIONS.md, v2.0 aims to transform this into a comprehensive nutrition platform:

### Database Integration
- SQLite/PostgreSQL for recipe storage and analysis
- Canadian Nutrient File (CNF) integration for ingredient nutrition data
- Dietary Reference Intake (DRI) tables for nutritional comparison
- User session management for favorites and meal planning

### Enhanced Functionality
- **Nutritional Analysis**: Calculate calories, nutrients per serving
- **Serving Size Math**: Dynamic recipe scaling tools
- **Meal Planning**: Daily nutrition tracking and DRI comparison
- **User Favorites**: Recipe bookmarking and custom notes
- **Export Features**: .ics calendar files for meal prep scheduling

### Proposed Database Schema
The IMPLEMENTATIONS.md includes a comprehensive ERD with:
- `RECIPES` table for core recipe data
- `RECIPE_INGREDIENTS` with CNF food code linking
- `CNF_FOODS` and `CNF_NUTRIENTS` for nutritional data
- `DRI_VALUES` for dietary reference comparisons
- `MEAL_PLANS` and user customization tables

## Recommended LLM Workflow (v2.0)

### Complete Recipe Analysis Workflow
```
1. Search for recipes: search_recipes
2. Fetch recipe details: get_recipe  
3. Store in virtual session: store_recipe_in_session
4. Parse ingredients: parse_and_update_ingredients (CRITICAL STEP!)
5. Check parsed data: get_structured_ingredients
6. Use math tools: scale_recipe_servings, scale_individual_ingredient, etc.
7. Save favorites: add_to_favorites (if desired)
8. Clean up: cleanup_virtual_session (when done)
```

### EER Calculation Workflow 
```
1. Get EER equations: get_eer_equations(equation_type="adult", pal_category="active")
2. Use simple math calculator: simple_math_calculator(expression="753.07 - (10.83 * age) + (6.50 * height) + (14.10 * weight)", variables={"age": 30, "height": 180, "weight": 75})
3. Or create user profile: create_user_profile (for repeated calculations)
4. Compare with recipe calories for meal planning
```

### CNF Nutrition Analysis Workflow ✅ ENHANCED WITH SOPHISTICATED UNIT CONVERSION!

#### 🛠️ RELIABLE MANUAL WORKFLOW (RECOMMENDED):
```
⚡ TRANSPARENT, RELIABLE, AND ACCURATE UNIT CONVERSION!

🚨 MAJOR UPDATE: Now includes sophisticated unit conversion logic!
No more naive ÷100 calculations - proper unit matching and conversion factors.

OPTIMIZED MANUAL WORKFLOW (5-6 tool calls):
1. simple_recipe_setup() ✅ → Transfer recipe data and parse ingredients
2. execute_nutrition_sql(CHECK query) ✅ → View all ingredients with amounts/units
3. search_cnf_foods() per ingredient ✅ → Find CNF food codes
4. get_cnf_nutrient_profile() per food ✅ → Store nutrition data with serving options
5. execute_nutrition_sql(BULK UPDATE) ✅ → Link multiple ingredients efficiently
6. execute_nutrition_sql(SOPHISTICATED SELECT) ✅ → Calculate with proper unit conversion

NEW BENEFITS:
- 🔍 Full transparency: see exactly what's happening at each step
- 🛡️ Reliable: no complex auto-matching to break down
- 🎯 Accurate: sophisticated unit conversion (tsp→ml, g→kg, etc.)
- 🐛 Debuggable: verify unit conversions and calculations independently
- ⚡ Efficient: bulk operations reduce tool calls

Unit Conversion Features:
- Exact unit matching (ml→ml, g→g) gets highest priority
- Volume conversions (tsp→ml, cup→ml) with proper conversion factors
- Weight conversions (kg→g, lb→g, oz→g) with accurate multipliers  
- Cross-conversions (ml↔g for liquids) with density approximations
- Fallback to per-100g baseline only when necessary
```

#### 📋 ENHANCED WORKFLOW EXAMPLE:
```
STEP-BY-STEP EXAMPLE FOR "HONEY SALMON ASPARAGUS" RECIPE:

1. Setup Recipe Data:
   simple_recipe_setup(session_id="nutrition", recipe_id="honey_salmon")
   
2. Check Ingredients with Units:
   execute_nutrition_sql(session_id="nutrition", query="SELECT ingredient_id, ingredient_name, amount, unit, cnf_food_code FROM temp_recipe_ingredients WHERE session_id = 'nutrition'")
   
3. Search CNF Foods (strategic, not every ingredient):
   search_cnf_foods(session_id="nutrition", food_name="salmon")  → Find food_code "3183"
   search_cnf_foods(session_id="nutrition", food_name="honey")   → Find food_code "4294"
   search_cnf_foods(session_id="nutrition", food_name="soy sauce") → Find food_code "3416"
   
4. Get Nutrient Profiles (auto-stores multiple serving sizes):
   get_cnf_nutrient_profile(session_id="nutrition", food_code="3183")  ← Stores g, ml options
   get_cnf_nutrient_profile(session_id="nutrition", food_code="4294")  ← Stores tsp, ml options
   get_cnf_nutrient_profile(session_id="nutrition", food_code="3416")  ← Stores ml, tbsp options
   
5. Bulk Link Ingredients (EFFICIENT - Single Query):
   execute_nutrition_sql(session_id="nutrition", query="UPDATE temp_recipe_ingredients SET cnf_food_code = CASE WHEN ingredient_name LIKE '%salmon%' THEN '3183' WHEN ingredient_name LIKE '%honey%' THEN '4294' WHEN ingredient_name LIKE '%soy sauce%' THEN '3416' ELSE cnf_food_code END WHERE session_id = 'nutrition'")
   
6. 🚨 CRITICAL: Calculate with SOPHISTICATED Unit Conversion:
   execute_nutrition_sql(session_id="nutrition", query=SOPHISTICATED_UNIT_CONVERSION_TEMPLATE)
   ✅ Proper: tsp honey × 5ml/tsp ÷ 100ml = accurate honey calories
   ✅ Proper: g salmon ÷ 100g = accurate salmon calories  
   ❌ Wrong: ALL ingredients ÷ 100 (ignores units completely!)

RESULT: Accurate nutrition analysis with proper unit conversion!
```

#### 🎯 CRITICAL UNIT CONVERSION GUIDANCE:
```
🚨 ALWAYS USE SOPHISTICATED UNIT CONVERSION TEMPLATE!

❌ NEVER USE: Simple (ri.amount/100)*cn.nutrient_value
   ↳ This ignores units completely and gives wrong results!

✅ ALWAYS USE: Sophisticated unit conversion template from execute_nutrition_sql
   ↳ Handles tsp→ml, cup→ml, kg→g, lb→g with proper conversion factors
   ↳ Prioritizes exact matches, then conversions, then fallbacks
   ↳ Transparent calculation method for every ingredient

CONVERSION EXAMPLES:
- 15 mL honey: exact match to CNF 15mL serving = perfect accuracy
- 2 tsp honey: converts 2×5mL=10mL, then matches to CNF serving = good accuracy  
- 200g salmon: exact match to CNF 100g serving with 2x multiplier = perfect accuracy
- Wrong way: honey ÷ 100, salmon ÷ 100 = both wrong because units ignored!
```

### DRI Macronutrient Analysis Workflow ✅ ENHANCED!
```
SESSION-BASED APPROACH (RECOMMENDED):
1. Cache DRI data: store_dri_tables_in_session(session_id="nutrition_analysis")
2. Store user profile: store_dri_user_profile_in_session(session_id="nutrition_analysis", profile_name="user1", age_range="19-30 y", gender="males")
3. Quick lookups: get_dri_lookup_from_session(session_id="nutrition_analysis", age_range="19-30 y", gender="males", macronutrient="protein")
4. Adequacy analysis: calculate_dri_adequacy_in_session(session_id="nutrition_analysis", profile_name="user1", intake_data={"protein": 80, "carbohydrate": 250})
5. Calculate values: simple_math_calculator(expression="(intake/rda)*100", variables=from_adequacy_tool)
6. Session overview: list_session_dri_analysis(session_id="nutrition_analysis")

DIRECT APPROACH (SIMPLE QUERIES):
1. Get complete DRI data: get_macronutrient_dri_tables() - fetches all Health Canada DRI macronutrient tables
2. Get specific recommendations: get_specific_macronutrient_dri(age_range="19-30 y", gender="males", macronutrient="protein")
3. Check AMDR compliance: get_amdrs(age_range="19 years and over") - get acceptable distribution ranges
4. Compare actual intake: compare_intake_to_dri(age_range="19-30 y", gender="males", intake_data={"carbohydrate": 250, "protein": 80})
5. Calculate adequacy: simple_math_calculator(expression="(intake/rda)*100", variables={"intake": 80, "rda": 56})

EER → DRI INTEGRATION WORKFLOW ✅ NEW!:
1. Calculate EER: get_eer_equations(equation_type="adult", pal_category="active") + simple_math_calculator
2. Store user profile: store_dri_user_profile_in_session(with demographics)
3. Convert to macros: calculate_dri_from_eer(session_id="nutrition_analysis", profile_name="user1", eer_energy_kcal=2000, age_range="19 years and over")
4. Calculate macro targets: simple_math_calculator(expression="(energy * percent) / kcal_per_gram", variables=from_eer_tool)
5. Use targets for meal planning and recipe evaluation

COMPREHENSIVE DRI FEATURES:
- Complete macronutrient DRI tables (EAR, RDA, AI, UL) for all age groups
- Additional recommendations for saturated fats, trans fats, cholesterol, added sugars
- AMDR ranges for balanced macronutrient distribution assessment
- Amino acid patterns for protein quality evaluation using PDCAAS method
- Intake adequacy assessment with risk evaluation (inadequate/adequate/excessive)
- Session-based workflows for complex multi-step nutrition analysis
- EER integration for energy-based macronutrient target calculation
- Flexible age matching and enhanced data quality validation
```

### Key Points for LLMs ⚡ ENHANCED MANUAL WORKFLOW WITH SOPHISTICATED UNIT CONVERSION

#### 🚨 CRITICAL: SOPHISTICATED UNIT CONVERSION REQUIRED!
- **NEVER USE**: Simple `(ri.amount/100)*cn.nutrient_value` - this ignores units completely!
- **ALWAYS USE**: Sophisticated unit conversion templates from `execute_nutrition_sql` tool
- **UNIT CONVERSION FEATURES**: tsp→ml, cup→ml, kg→g, lb→g with proper conversion factors
- **PRIORITY SYSTEM**: Exact matches > Unit conversions > Weight/volume fallbacks > Per-100g baseline

#### 🛠️ ENHANCED APPROACH: MANUAL CONTROL + SOPHISTICATED CALCULATIONS
- **REMOVED**: analyze_recipe_nutrition() auto-matching (unreliable)
- **ADDED**: simple_recipe_setup() + manual CNF linking (reliable)
- **ENHANCED**: Sophisticated unit conversion templates (accurate)
- **RESULT**: Full transparency, control, and accuracy over nutrition analysis

#### 🎯 PREFERRED WORKFLOW (RELIABLE + ACCURATE):
```
1. simple_recipe_setup(session_id, recipe_id) → Transfer data + parse ingredients with units
2. execute_nutrition_sql(CHECK query) → View ingredients with amounts/units needing CNF linking
3. search_cnf_foods() → Find appropriate CNF food codes strategically
4. get_cnf_nutrient_profile() → Auto-populate SQL nutrition tables with serving options
5. execute_nutrition_sql(BULK UPDATE) → Efficiently link multiple ingredients to CNF foods
6. execute_nutrition_sql(SOPHISTICATED SELECT) → Calculate nutrition with proper unit conversion
```

#### 🔧 ENHANCED MANUAL LINKING + CALCULATION APPROACH:
- **execute_nutrition_sql() with sophisticated templates** - Proper unit conversion calculations
- **Bulk UPDATE operations** - Efficient ingredient-CNF linking
- **get_cnf_nutrient_profile()** - Auto-populates SQL tables with multiple serving sizes
- **search_cnf_foods()** - Strategic CNF food discovery  
- **Unit conversion verification** - Debug queries to check conversion methods
- **Full transparency** - See every step including unit conversion logic

#### ❌ TOOLS REMOVED DUE TO RELIABILITY ISSUES:
- **analyze_recipe_nutrition** - Removed (unreliable auto-matching)
- **link_ingredient_to_cnf** - Use execute_nutrition_sql(UPDATE) instead
- **Complex auto-matching workflows** - Use manual approach instead

#### 🏗️ TECHNICAL DETAILS:
- **Temp SQLite tables** - temp_recipe_ingredients, temp_cnf_foods, temp_cnf_nutrients, temp_recipes
- **Sophisticated unit conversion** - Unit normalization, conversion factors, priority ranking
- **Manual UPDATE queries** - Direct control over ingredient-CNF linking with bulk operations
- **Transparent calculations** - All nutrition logic AND unit conversion visible in SQL queries
- **Session-scoped safety** - All operations restricted to session data
- **No auto-parsing failures** - Manual verification at each step including unit conversions
- **Ready SQL templates** - Comprehensive templates with sophisticated unit conversion logic
- **Conversion verification** - Debug templates to verify unit conversion methods
- **Multiple serving sizes** - CNF profiles include tsp, ml, g, and other serving options

#### 🌟 SYSTEM FEATURES:
- **EER equations are live** - Health Canada DRI website integration
- **CNF nutrition data is live** - Health Canada CNF database integration  
- **DRI macronutrient data is live** - Health Canada DRI tables with 24hr caching
- **Virtual sessions** - No database bloat, data auto-expires
- **Favorites are persistent** - Stored in SQLite, survive server restarts
- **Complete nutrition analysis possible** - Recipe → CNF → SQL → EER → DRI → Analysis

## Development Commands

### Testing
```bash
# No specific test framework identified - manual testing via MCP calls
# Test workflow: store_recipe_in_session → parse_and_update_ingredients → scale_recipe_servings
```

### Linting/Type Checking
```bash
# No linting configuration found - check package.json or pyproject.toml
# Common Python tools: black, flake8, mypy, ruff
```

## File Structure Context

### Key Files to Monitor
- `src/server.py` - Main MCP server logic and tool definitions
- `src/api/search.py` - Recipe search functionality
- `src/api/recipe.py` - Recipe detail extraction
- `src/api/eer.py` - EER equation fetching and profile management
- `src/models/filters.py` - Filter management and caching
- `src/db/` - Database operations and schema management
  - `src/db/queries.py` - Database tools registration
  - `src/db/math_tools.py` - Math and calculation tools (includes simple_math_calculator)
  - `src/db/eer_tools.py` - EER calculation and profile management tools
  - `src/db/schema.py` - Database schema and session management
- `src/models/` - Pydantic models for data validation
  - `src/models/db_models.py` - Database operation models
  - `src/models/math_models.py` - Math tool input models (includes SimpleMathInput)
  - `src/models/eer_models.py` - EER tool input/output models
- `src/config.py` - Configuration including database settings
- `requirements.txt` - Python dependencies

### Storage Directories
- `cache/` - Stores downloaded filter data to avoid repeated API calls
- `foodguide_data.db` - SQLite database for favorites and temporary recipe storage

### Database Configuration
- **Database file**: `foodguide_data.db` (configurable via `FOODGUIDE_DB_FILE` env var)  
- **Persistent tables**: `user_favorites` - stores user's saved recipes (ONLY persistent data)
- **Virtual sessions**: In-memory storage in `_recipe_sessions` global dict
  - `recipes` - recipe metadata (title, servings, etc.)
  - `ingredients` - ingredient data with `ingredient_list_org`, `ingredient_name`, `amount`, `unit`
  - `instructions` - cooking steps
  - `nutrient_profiles` - CNF nutrient data by food_code ✅ NEW!
  - `ingredient_cnf_matches` - Links ingredient_id to CNF food_code ✅ NEW!
  - `nutrition_summaries` - Calculated recipe nutrition data ✅ NEW!
  - `cnf_search_results` - Cached CNF search results ✅ NEW!
- **Session management**: Automatic memory cleanup, no database tables created

### Math & Calculation Features (✅ WORKING!)
- **Recipe scaling**: Scale entire recipes using parsed ingredient amounts/units  
- **Serving size adjustments**: Calculate ingredients needed for different serving counts
- **Ingredient parsing**: Extract amounts, units, names from ingredient text (`ingredient_list_org`)
- **Bulk operations**: Scale multiple ingredients with different factors simultaneously
- **Recipe comparison**: Compare recipes by servings, ingredient complexity, or portion analysis
- **Smart calculation**: Uses parsed data when available, falls back to text parsing
- **Dual-mode operation**: Handles both structured and unstructured ingredient data
- **Simple math calculator**: Safe arithmetic evaluation with string variables for any calculations

### EER (Energy Requirement) Features (✅ WORKING!)
- **Live equation fetching**: Gets current EER equations from Health Canada DRI website
- **42+ equations available**: All age groups, genders, PAL categories, pregnancy/lactation
- **Clean JSON format**: Simplified equation data with coefficients extracted
- **Profile management**: Virtual user profiles for repeated calculations
- **PAL descriptions**: Detailed activity level guidance with examples

### CNF (Canadian Nutrient File) Features (✅ SQL-POWERED!)
- **Live CNF food search**: Search Health Canada's official CNF database by food name
- **Complete nutrient profiles**: Get detailed nutrition data and populate SQL virtual tables
- **SQL-based nutrition analysis**: Write custom SQL queries for any nutrition calculation
- **Virtual table structure**: recipe_ingredients, cnf_foods, cnf_nutrients follow v2.0 schema
- **Simplified ingredient linking**: Direct cnf_food_code updates in recipe_ingredients table
- **Transparent calculations**: All nutrition logic visible in SQL queries
- **Serving size optimization**: Handle unit conversions with SQL CASE statements
- **Maximum flexibility**: Custom queries for comparisons, aggregations, complex analysis
- **No tool complexity**: Just SQL knowledge required for any nutrition question
- **Virtual session integration**: All data stored in memory following relational structure

### Future Nutritional Analysis (Next Phase)
- **DRI comparisons**: Compare recipes against Dietary Reference Intakes by age/gender
- **Enhanced macro/micronutrient analysis**: More detailed nutritional breakdowns per serving
- **Daily intake tracking**: Multi-recipe nutrition planning and analysis
- **Health Canada guideline alignment**: Scoring recipes against official dietary recommendations
- **Unit conversion improvements**: Better handling of recipe-to-CNF serving size conversions

### Future Considerations
- Database migration scripts when implementing v2.0
- API rate limiting for web scraping
- Error handling for website structure changes
- Integration with Canadian Nutrient File API
- Math tools for nutritional calculations

## Notes for Claude

When working on this project:
1. Always test changes against the live Canada's Food Guide website
2. Be mindful of web scraping ethics and rate limiting
3. Consider the transition path from v1.0 to v2.0 database architecture
4. Preserve existing MCP tool interfaces for backward compatibility
5. Focus on nutritional accuracy when implementing CNF integration