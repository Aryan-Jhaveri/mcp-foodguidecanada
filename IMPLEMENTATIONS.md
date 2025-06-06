# Implementations
A list future ideas, tasks, and ideas to improve/maintain the mcp server

## June 6, 2025
#### Phase 1: EER Implementation COMPLETED ✅ 
[x] **EER equation fetching** - Live fetching from Health Canada DRI website
    - [x] Simplified equation parsing from HTML structure
    - [x] Clean JSON output with coefficients extracted
    - [x] All 42+ equations available (adult, child, pregnancy, lactation)
    - [x] Proper filtering by equation type and PAL category

[x] **Simple math calculator** - Safe arithmetic evaluation
    - [x] String variable substitution in mathematical expressions
    - [x] Safe AST-based evaluation (no exec/eval security risks)
    - [x] Support for basic operations: +, -, *, /, **, %, parentheses
    - [x] Perfect for EER calculations and any mathematical operations

[x] **EER workflow simplified** - No complex calculation methods needed
    - [x] Use get_eer_equations() to fetch equations
    - [x] Use simple_math_calculator() for calculations
    - [x] Profile management for repeated use (virtual storage)
    - [x] Deprecated old calculate_eer methods in favor of simple approach

[] **Future Enhancement**: Add persistent storage for user profiles in EERProfileManager

#### Phase 2: CNF Integration COMPLETED ✅ 
[x] **Created `src/api/cnf.py`** for Canadian Nutrient File integration
    - [x] Implemented NutrientFileScraper class with rate limiting and error handling
    - [x] Added food search functionality with CSRF token handling
    - [x] Created nutrient profile extraction with full category parsing
    - [x] Implemented serving size option retrieval and refuse information

[x] **Added CNF data models** in `src/models/cnf_models.py`
    - [x] Complete Pydantic models for food search, nutrient profiles, serving sizes
    - [x] Validation for CNF food codes and nutrient values
    - [x] Integration models for recipe-CNF data linking and nutrition summaries

[x] **Created `src/db/cnf_tools.py`** for MCP tool registration
    - [x] `search_cnf_foods` - Find foods by ingredient name with session storage
    - [x] `get_cnf_nutrient_profile` - Retrieve complete nutrient profile with all categories
    - [x] `link_ingredient_to_cnf` - Associate recipe ingredients with CNF codes
    - [x] `calculate_recipe_nutrition` - **FIXED**: Now prepares data for math tools instead of manual calculation
    - [x] `get_ingredient_nutrition_matches` - View ingredient-CNF linkage status
    - [x] `clear_cnf_session_data` - Clean up CNF data from virtual sessions

[x] **Extended virtual session system** in `src/db/schema.py` for CNF data storage
    - [x] Added nutrient_profiles, ingredient_cnf_matches, nutrition_summaries structures
    - [x] Implemented CNF helper functions for session management
    - [x] Integrated with existing virtual session cleanup system

[x] **Registered CNF tools** in `src/server.py` following EER pattern
    - [x] Added import statements and registration calls
    - [x] Implemented graceful fallback if CNF tools unavailable

#### Phase 2.1: CNF Math Tools Integration FIX COMPLETED ✅ 
[x] **Fixed CNF calculation workflow** - resolved LLM manual JSON parsing issues
    - [x] Updated `calculate_recipe_nutrition` to prepare data instead of calculating
    - [x] Tool now returns structured formulas for `simple_math_calculator` to use
    - [x] Removed manual JSON parsing and calculation logic from CNF tools
    - [x] Added explicit math tool workflow guidance in all CNF tool docstrings

[x] **Enhanced tool documentation** to guide LLMs toward math tools
    - [x] Updated `simple_math_calculator` docstring with CNF nutrition examples
    - [x] Added "DATA RETRIEVAL ONLY" guidance to `get_cnf_nutrient_profile`
    - [x] Added complete workflow examples in `search_cnf_foods` docstring
    - [x] Emphasized use of math tools in all CNF tool descriptions

[x] **Updated project workflow documentation**
    - [x] Updated CLAUDE.md CNF workflow to emphasize math tools usage
    - [x] Added critical reminders about never manually calculating JSON values
    - [x] Updated key points for LLMs to highlight math tools requirement

#### Phase 2.2: CNF Serving Size Matching Enhancement (Priority: HIGH)
[x] **Enhance serving size extraction in `calculate_recipe_nutrition`** COMPLETED ✅
    - [x] Parse ALL CNF serving size columns (5mL, 15mL, 100mL, etc.)
    - [x] Extract serving amounts and units from column headers
    - [x] Store serving-specific nutrient values for each ingredient
    - [x] Identify which serving columns contain actual data vs empty values

[x] **Implement intelligent unit matching logic** COMPLETED ✅
    - [x] Create unit normalization function (ml→mL, tsp→teaspoon, etc.)
    - [x] Match recipe ingredient units to CNF serving column units
    - [x] Calculate scaling factors: recipe_amount ÷ cnf_serving_amount = multiplier
    - [x] Rank calculation options by accuracy (direct match > unit conversion > 100g baseline)

[x] **Update calculation formula generation** COMPLETED ✅
    - [x] Provide multiple calculation options per ingredient (serving-based + 100g fallback)
    - [x] Mark preferred calculation method based on unit matching accuracy
    - [x] Include descriptive text explaining why each method is recommended
    - [x] Generate specific formulas for `simple_math_calculator` usage

[x] **Enhance tool output structure** COMPLETED ✅
    - [x] Return ranked calculation options with accuracy indicators
    - [x] Provide clear guidance on which calculation method to prefer
    - [x] Include serving size matching explanations for transparency
    - [x] Add serving size analysis showing optimization success rates

[x] **Add helper functions for serving size processing** COMPLETED ✅
    - [x] `_parse_cnf_serving_columns()` - extract serving data from nutrient profiles
    - [x] `_match_recipe_units_to_servings()` - find best CNF serving matches
    - [x] `_normalize_unit()` - standardize unit variations for matching
    - [x] Enhanced accuracy ranking and preferred method selection

[x] **Update tool documentation and examples** COMPLETED ✅
    - [x] Add serving size preference guidance to `calculate_recipe_nutrition` docstring
    - [x] Include examples showing serving-based calculation workflows
    - [x] Update CLAUDE.md with serving size matching best practices
    - [x] Enhanced workflow documentation with serving size optimization highlights

#### Phase 2.3: Code Cleanup and TODO Consolidation (Priority: MEDIUM)
[] **Clean up scattered TODO comments in codebase** - Move project planning out of code files
    - Current: TODO items scattered across multiple Python files
    - Target: Centralized planning in IMPLEMENTATIONS.md, clean code comments

[] **EER Profile Management TODOs** in `src/api/eer.py`
    - [] Line 417: Implement persistent database storage for user profiles
    - [] Line 435: Add database retrieval for saved profiles  
    - [] Line 447: Implement database query for profile listing
    - [] Line 463: Add database deletion for profile management
    - [] Decision needed: Implement persistence or remove TODO comments

[] **CNF Tools Enhancement Comments** in `src/db/cnf_tools.py`
    - [] Line 309: Add proper CNF food name lookup instead of 'Unknown' placeholder
    - [] Line 313: Enhance serving_conversion with unit conversion capabilities
    - [] Consider adding CNF food search by code for reverse lookups

[] **Remove Future Tool Placeholders** in `src/db/math_tools.py`
    - [] Lines 566-617: Remove large commented-out section for future nutrition tools
    - [] These are superseded by our current CNF integration implementation
    - [] Move any useful concepts to this IMPLEMENTATIONS.md file instead

[] **Fix Recipe Attribution** in `src/api/recipe.py`
    - [] Line 595: Update hardcoded website URL to use proper URL builder
    - [] Replace static 'https://food-guide.canada.ca/' with dynamic slug + URL builder

[] **Clean Model Placeholders** in `src/models/math_models.py`
    - [] Remove placeholder DRI comparison model
    - [] Remove placeholder nutrient analysis model
    - [] These should align with actual planned DRI integration work

[] **Documentation Consolidation**
    - [] Move all project planning comments from code files to IMPLEMENTATIONS.md
    - [] Keep only implementation-specific comments in code
    - [] Update code comments to be focused on technical details, not project plans
    - [] Organize discovered todo items by priority and dependencies

#### Phase 3: DRI Tables Integration for Macronutrients COMPLETED ✅
[x] **Created `src/api/dri.py`** - Comprehensive MacronutrientScraper implementation
    - [x] Complete DRI table parsing by life stage and gender
    - [x] Extract EAR, RDA, AI, and UL values for all macronutrients
    - [x] Parse additional macronutrient recommendations (saturated fats, trans fats, cholesterol, added sugars)
    - [x] Extract amino acid patterns for protein quality evaluation (PDCAAS)
    - [x] Parse Acceptable Macronutrient Distribution Ranges (AMDRs)
    - [x] Comprehensive footnote and metadata extraction
    - [x] **FIXED**: Simplified scraper approach following successful EER pattern
    - [x] **FIXED**: Non-breaking space parsing issues resolved
    - [x] **IMPROVED**: Rate limiting and 10-second timeout like working scrapers
    - [x] 24-hour caching system to minimize website requests

[x] **Created `src/models/dri_models.py`** - Complete Pydantic data models
    - [x] Comprehensive models for all DRI value types (EAR, RDA, AI, UL)
    - [x] Specific models for each macronutrient type with appropriate units
    - [x] AMDR range models with validation
    - [x] Amino acid pattern models for protein quality assessment
    - [x] Input/output models for MCP tool integration
    - [x] Utility functions for data parsing and formatting

[x] **Created `src/db/dri_tools.py`** - MCP tool registration following established patterns
    - [x] `get_macronutrient_dri_tables` - Complete DRI dataset access
    - [x] `get_specific_macronutrient_dri` - Targeted nutrient lookup by age/gender
    - [x] `get_amdrs` - Acceptable Macronutrient Distribution Ranges
    - [x] `get_amino_acid_patterns` - Protein quality evaluation patterns
    - [x] `compare_intake_to_dri` - Comprehensive intake adequacy assessment
    - [x] Integrated with existing MCP server architecture

[x] **DRI tools integration** - Registered in main MCP server
    - [x] Added DRI tools registration to `src/db/queries.py`
    - [x] Follows same pattern as EER and CNF tools
    - [x] Graceful fallback if DRI tools unavailable
    - [x] Complete import handling and error management

[x] **Phase 3 Key Features Delivered**
    - [x] Live scraping from Health Canada's official DRI macronutrient tables
    - [x] Structured JSON output with complete validation
    - [x] Cache management for performance optimization  
    - [x] Integration with existing math tools for calculations
    - [x] Comprehensive error handling and data quality metrics
    - [x] Support for all age groups from infants to elderly
    - [x] Special handling for pregnancy and lactation values
    - [x] **TESTED**: Successfully fetching 22 reference values, 10 amino acids, 3 AMDRs

#### Phase 3.1: CNF SQL-Centric Architecture COMPLETED ✅ 
[x] **Revolutionary SQL-based nutrition analysis** - Complete architecture transformation
    - [x] Created `VirtualSQLEngine` for executing SQL queries on nutrition data
    - [x] Implemented virtual table structure following v2.0 database schema exactly
    - [x] Added `execute_nutrition_sql` tool for direct SQL queries on nutrition data
    - [x] Added `get_nutrition_tables_info` tool for table schema documentation

[x] **Enhanced virtual session structure**
    - [x] Added SQL-ready table structures: recipe_ingredients, cnf_foods, cnf_nutrients
    - [x] Updated `get_cnf_nutrient_profile` to populate SQL tables automatically
    - [x] Updated `parse_and_update_ingredients` to maintain both legacy and SQL structures
    - [x] Maintained backward compatibility with existing tools

[x] **Simplified ingredient-CNF linking**
    - [x] Created `link_ingredient_to_cnf_simple` tool for direct cnf_food_code updates
    - [x] Eliminated complex matching logic in favor of simple SQL table updates
    - [x] Made ingredient linkages immediately available for SQL queries

[x] **Comprehensive SQL query engine**
    - [x] Supports SELECT, FROM, JOIN, WHERE, GROUP BY, ORDER BY operations
    - [x] Handles unit conversion logic within SQL CASE statements
    - [x] Provides transparent calculations with all logic visible in queries
    - [x] Enables custom nutrition analysis for any use case

[x] **Updated documentation and workflow guidance**
    - [x] Updated CLAUDE.md to emphasize SQL-centric approach
    - [x] Provided comprehensive SQL query examples for common nutrition calculations
    - [x] Updated key points for LLMs to highlight SQL flexibility
    - [x] Marked legacy tools (calculate_recipe_nutrition, get_recipe_nutrition_summary) appropriately

[x] **Benefits delivered**
    - [x] Maximum flexibility: Any nutrition query possible with SQL
    - [x] Transparent calculations: All logic visible in SQL statements
    - [x] Follows intended v2.0 schema: Proper relational table structure
    - [x] Eliminates tool complexity: Just SQL knowledge required
    - [x] Scalable analysis: Easy to extend for multiple recipes, nutrients, comparisons

#### Phase 3.2: DRI Virtual Tables and Math Tool Integration PENDING 🚧
[] **Fix parsing issues and enhance robustness**
    - [] Normalize non-breaking spaces (`\xa0`) to regular spaces in all parsed data
    - [] Improve age range matching with flexible text normalization
    - [] Add validation for parsed DRI values

[] **Add virtual session support for DRI data storage**
    - [] Extend `src/db/schema.py` with DRI data structures in virtual sessions
    - [] Add `'dri_reference_tables'`, `'dri_user_profiles'`, `'dri_lookups'`, `'dri_comparisons'` to sessions
    - [] Create DRI session management functions (store, retrieve, clear, list)
    - [] Enable cross-tool data sharing between EER, CNF, and DRI systems

[] **Session-aware DRI tools for LLM interaction**
    - [] `store_dri_tables_in_session` - Cache complete DRI tables in virtual session
    - [] `get_dri_lookup_from_session` - Retrieve specific DRI values from session
    - [] `store_dri_user_profile_in_session` - Store user demographics for DRI analysis
    - [] `calculate_dri_adequacy_in_session` - Calculate and store adequacy results
    - [] `list_session_dri_analysis` - View all DRI calculations in session

[] **Complete math tool integration in ALL DRI tool prompts**
    - [] Update all DRI tools to mandate `simple_math_calculator` usage
    - [] Add comprehensive examples for AMDR calculations, adequacy percentages, comparisons
    - [] Include cross-tool integration examples (CNF → DRI, EER → DRI workflows)
    - [] Emphasize "NEVER manually calculate" with math tool alternatives

[] **EER → DRI macronutrient calculation workflow**
    - [] Create `calculate_dri_from_eer` tool for energy-based macro targets
    - [] Integrate EER energy values with AMDR distribution ranges
    - [] Calculate specific macronutrient targets based on energy requirements
    - [] Enable EER profile → DRI macro planning workflow
    - [] Add examples: EER kcal → AMDR % → specific gram targets via simple_math_calculator

[] **Enhanced tool documentation with mandatory math tool usage**
    - [] All DRI tools reference `simple_math_calculator` for calculations
    - [] Clear examples for adequacy: `(intake/rda)*100`, deficit: `intake - rda`, AMDR compliance
    - [] Integration workflow examples: Recipe → CNF → EER → DRI → Math Tools
    - [] Cross-system calculation patterns and best practices

#### Phase 4: Integrated Nutrition Analysis (Priority: MEDIUM)
[] **Recipe-to-Nutrition Pipeline**
    - Complete workflow: Recipe → Parse Ingredients → CNF Lookup → Nutrition Calculation → DRI Comparison
    - Batch processing for multiple recipes (meal planning)
    - Export capabilities for nutrition reports

[] **Enhanced User Profiles**
    - Add persistent storage for user profiles in SQLite
    - Link profiles to nutrition history and preferences
    - Support for multiple household members

### <-Current Architecture Improvements->
[x] **Simplified EER approach implemented** - Using simple_math_calculator instead of complex coefficient extraction
    - [x] Removed calculate_eer_with_equation method from eer.py 
    - [x] Cleaned JSON output to remove clutter from equation data
    - [x] Streamlined workflow: get_eer_equations → simple_math_calculator
    - [x] Deprecated complex profile-based calculation methods

### <-Bug Fixes->
[x] **Fixed EER implementation issues**
    - [x] Resolved Pydantic model validation errors in eer_models.py
    - [x] Removed orphaned validators and missing imports
    - [x] Fixed server startup issues with EER tools
    - [x] Improved equation parsing to handle all section types

[] Test all new EER tools for proper error handling  
[] Ensure proper fallback when web scraping fails

### <-Documentation->
[x] **Updated project documentation**
    - [x] Updated CLAUDE.md with EER workflow and new tools
    - [x] Updated IMPLEMENTATIONS.md with current status
    - [x] Documented simplified EER approach
    - [x] Added simple_math_calculator workflow examples

[] Update README.md for v3.0 with EER capabilities  
[] Document CNF integration workflow when implemented
[] Add API documentation for all new tools

### <-Legacy Features->
[] Add Access to Dietary Reference Intake tables https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes.html
    - Also Consider references for tables and academic sources to be cited
    - ✅ EER equations implemented and working

[] Add Access to Canadian Nutrient File to convert and search for nutrition profiles for ingredients https://food-nutrition.canada.ca/cnf-fce/?lang=eng 
    - Maybe this will be kept as a virtual table with fetched recipe ingredient nutrient profiles
    - Consider instead https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data/nutrient-value-some-common-foods-2008.html#tbl_con_mat
    - There is search by food, but also search by nutrient https://food-nutrition.canada.ca/cnf-fce/newNutrientSearch

[] Remove nutritional information tag for recipes       

### <-Documentation->
[] Update README.md for v2.0 before sending a virtual push 
[] Make windows version of setup and installation
[] Add a smithery installation package to automatically install the server instead of having to add working directories

![] **Maybe** create a tool to create .ics files (need to see how different LLM clients display artifacts)


## June 5, 2025
* REMEMBER! Use testcnf and testdri as starting points, and update the CLI as you go

### <-Recently Completed->
[x] **EER Calculator Implementation** - Added comprehensive EER calculation functionality
    - Created `src/api/eer.py` with EER calculations and user profile management
    - Added `src/models/eer_models.py` with Pydantic models for validation
    - Created `src/db/eer_tools.py` with MCP tool registration
    - Integrated EER tools into main server (`src/server.py`)
    - Supports both virtual session and persistent user profiles
    - Implements Health Canada DRI equations for accurate calculations
    - Includes PAL (Physical Activity Level) guidance and BMI calculations

## June 4, 2025
### <-Bugs->
[x] Edit prompt to always use search_filter simple text before adding additional filters
    - [] Edit prompt to always 
[x] Edit recipe add prompt , and show recipes prompt to always ask user for feedback
[x] 158 in server.py a empty text string for source which needs to be removed to be replace with the url being the source

## June 1, 2025
[x] FIX!! The Temp db seems to create a new/multiple entry for the same recipe fetch. 
    - editted to the prompt.

[x] Math tools not using parsed ingredient data properly
    - Issue: Scaling tools show "ingredients_scaled": 0 even after successful parsing
    - Problem: _scale_ingredient_amount() function re-parses text instead of using parsed amount/unit fields
    - Fix needed: Update scaling logic to use ingredient_data['amount'] and ingredient_data['unit'] directly
    - Current workflow broken: parse_and_update_ingredients works → scaling tools ignore parsed data

[x] LLM workflow guidance unclear for math tools
    - Issue: LLMs don't know proper sequence after parsing ingredients  
    - Problem: Tools don't clearly show how to use parsed vs original data
    - Fix needed: Better tool prompts explaining when to use parsed_amount vs original text
    - Current: LLMs manually calculate instead of using math tools

## May 30, 2025
[x] Add a temporary and/or permanent database system for LLMs to:
[x] To input ingredients (see 'access to Food nutrition Canada)
[!!] To use *math tools* to adjust serving size,  NOTE: I WOULD NOT COMPLETELY TRUST THESE MEASUREMENTS!!!
[x] To store favorites in recipes
[!!]- To calculate calories and calories per serving 
    - Maybe add table/webapi for unit conversions + cooking units

## Next steps
~~0. Add Database functionality ~~
    - Because majority of the following features for nutritional information depend on the LLM already having the data for recipe downloaded

1. Add EER calculations functionality,
    
    <<Steps for data retrieval>>
    0) Ask for Age, Gender, Height (cm), Weight(kg)
        - Here we can either use virtual storage, or add a tool to add the basic information to persistent storage as user-eer with userid

    1) FIND Physical activity level category (PA CAT): (Inactive, Low active, Active, Very active) vs. (3 to <9 years, 9 to <14 years, 14 to <19 years, 19 years and older) 
        - LLM selects a coloumn and values after asking from (Example of daily activities associated with physical activity level categories in adults for Inactive, Low active, Active, Very active)

    2) If Gender is Female
        Ask if pregnant or Breastfeeding
            If Pregnant
                Ask Trimester (First, Second, Third)
                    If First
                        use the appropriate non-pregnant equation.) 
                    If Second and Third
                        Ask for BMI
                            Use Pal SCORE + BMI to find Table Response
    Else if Male or No
            If No to Pregnancy
                use the appropriate non-pregnant equation.
            If Male
            use the appropriate equation. 
                Use AGE, GENDER, PAL SCORE to find EER equation
        
    Use math tools class for EER to calculate EER required     
    3) **RESPONSE** gives the required energy in kcal (check units j/kcal)

2. Start with CNF workflow to extract only Energy coloumns in kCal for an ingredient
    - Add SQLite tool to add kCal for all ingredients
    - Add SQLite tool to calculate total kCal from ingredients in a dish
    - Add a tool to compare the required kCal for a user or user profile, with that of a dish (or multiple dishes)
        - Maybe create a new virtual table for total kCal output, 

    <<Steps for Data Retrieval>>

3. Then Move forward with DRI Macros Nutrients by Age and Gender (or other relevant information)
4. CNF table for Other macros and Nurtients     


## Notes

<details>
<summary> List of notes and questions to consider </summary>
* *What is the most efficient way to create a tool, that fetches relevant options from CNF, for the ingredients in a recipe?**

* In V2.0, The MCP server becomes and amalgam of access to dietary reference intake values + Canadian Nutrient File, and a temporary local database access. The workflow of the agent becomes something like:

Input Recipe Query --> Download recipe to temporary db as an sql table [Ingredients, serving size, units, and amount] --> When asked: Fetch recipe nutrient profile for different ingredients --|--> If asked: Compare values for recipes for a days worth, with DRI Table values to find if food the user is planning on consuming meets DRI requirments

* Questions to Consider:

    - ~~What can be the most efficient template database design ready for the agent to go look like?~~ <- SQLite3 Virtual Tables for nonpersistent storage for sessions

    - What math tools can be added for Database (serving size calculator/multiplyer) and EER?
    
    = What database would be ideal for LLMS to - ~~add calculated coloumns to adjust serving size,~~ ~~pull recipe information (q: what to include?),~~ DRI information, and nutrient information for recipes.

</details>



## Chart
```mermaid
%% PK - Primary Key: uniquely identifies each row in a table; in a data model, it identifies each instance of the entity
%% Unique key: an attribute that could identify each row in a database or instance of an entity.
%% FK - Foreign Key: an attribute that’s ‘borrowed’ from another entity. They are used to show the relationship between two entities

---
title: Canada Food Guide MCP Server - Database Architecture v2.0
---
erDiagram
    %% Core Recipe System
    RECIPES {
        %% A unique Recipe ID
        string recipe_id PK 
        %% Recipe Title
        string title 
        %% A URL-friendly recipe identifier for referencing
        string slug
        %%  Direct link to the full recipe on food-guide.canada.ca
        string url
        %% NOTE: called servings in RecipeFetcher tool, this is the base serving size for the recipe online
        int base_servings
        %% Prep time
        string prep_time
        %% Cook time
        string cook_time 
        %% Categories
        json categories
        %% Tips
        json tips
        %% Recipe highglights
        json recipe_highlights
        %% recipe imageurl
        string image_url
        %% datetime created_at
        %% datetime updated_at
    }
    
    %% Recipe Components
    RECIPE_INGREDIENTS {
        string ingredient_id PK
        string recipe_id FK
        string ingredient_name
        float amount
        string unit
        int ingredient_order
        string cnf_food_code FK
    }
    
    %% Canadian Nutrient File Integration
    CNF_FOODS {
        string cnf_food_code PK
        string food_description
        %% Might need to remove this
        string food_group
        %% Might need to remove this
        string food_source
        boolean refuse_flag
        float refuse_amount
    }
    
    CNF_NUTRIENTS {
        string nutrient_id PK
        string cnf_food_code FK
        string nutrient_name
        string nutrient_symbol
        string nutrient_unit
        float nutrient_value
        string standard_error
        int number_observations
    }
    
    %% Dietary Reference Intakes
    DRI_VALUES {
        string dri_id PK
        string nutrient_symbol FK
        string life_stage_gender
        int age_min
        int age_max
        string gender
        float ear_value
        float rda_value
        float ai_value
        float ul_value
        string special_considerations
    }
    
    %% Recipe Customization & Calculations
    RECIPE_CALCULATIONS {
        string calc_id PK
        string recipe_id FK
        float serving_multiplier
        int adjusted_servings
        datetime calculated_at
        json nutritional_totals
    }
    
    USER_FAVORITES {
        string favorite_id PK
        string recipe_id FK
        string user_session
        datetime added_at
        json custom_notes
    }
    
    %% Meal Planning -- Most probably not going to be added
    MEAL_PLANS {
        string plan_id PK
        string user_session
        date plan_date
        string meal_type
        string recipe_id FK
        float serving_size
        datetime created_at
    }
    
    %% Nutritional Analysis
    DAILY_NUTRITION_SUMMARY {
        string summary_id PK
        string user_session
        date analysis_date
        json total_nutrients
        json dri_comparison
        %% json recommendations: Do not give medical advice!
        datetime calculated_at
    }

    %% Relationships
    RECIPES ||--o{ RECIPE_INGREDIENTS : contains
    RECIPE_INGREDIENTS }o--|| CNF_FOODS : references
    CNF_FOODS ||--o{ CNF_NUTRIENTS : has
    CNF_NUTRIENTS }o--|| DRI_VALUES : compared_against
    RECIPES ||--o{ RECIPE_CALCULATIONS : can_be_scaled
    RECIPES ||--o{ USER_FAVORITES : saved_by_users
    RECIPES ||--o{ MEAL_PLANS : used_in
    MEAL_PLANS }o--|| DAILY_NUTRITION_SUMMARY : contributes_to
    USER_FAVORITES }o--|| RECIPES : references
```