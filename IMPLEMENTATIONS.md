# Implementations
A list future ideas, tasks, and ideas to improve/maintain the mcp server

## June 6, 2025

#### Phase 1: EER Testing & Refinement (Priority: HIGH)
[x] **Test EER functionality** with real user scenarios
    - Test profile creation, calculation, and management
        [] Add Persistent Storage for user profiles in class api.eer.EERProfileManager
    - Verify equation accuracy against Health Canada references
    [x] Test edge cases (pregnancy, lactation, different age groups)
     Validate PAL coefficient application

#### Phase 2: CNF Integration (Priority: HIGH)  
[] **Create `src/api/cnf.py`** for Canadian Nutrient File integration
    - Implement ingredient search by clean_name
    - Add food code lookup functionality
    - Create nutrient profile extraction
    - Handle serving size conversions between recipe units and CNF data

[] **Add CNF data models** in `src/models/cnf_models.py`
    - Models for food search, nutrient profiles, serving sizes
    - Validation for CNF food codes and nutrient values
    - Integration models for recipe-CNF data linking

[] **Create `src/db/cnf_tools.py`** for MCP tool registration
    - `search_cnf_foods` - Find foods by ingredient name
    - `get_food_nutrients` - Retrieve complete nutrient profile
    - `link_ingredient_to_cnf` - Associate recipe ingredients with CNF codes
    - `calculate_recipe_nutrition` - Sum nutritional values across all ingredients

#### Phase 3: DRI Tables Integration (Priority: MEDIUM)
[] **Create `src/api/dri.py`** for Dietary Reference Intake tables
    - Scrape complete DRI tables by life stage and gender
    - Extract EAR, RDA, AI, and UL values for all nutrients
    - Handle special populations (pregnancy, lactation, aging)

[] **Add DRI comparison tools** 
    - Compare recipe nutrition against user's DRI requirements
    - Calculate percentage of daily values (%DV)
    - Identify nutrient gaps or excesses
    - Generate nutritional recommendations

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
[] Clean up tool organization in downtime
[] Maybe remove compare recipe serving size  
[] Create a clean [xxx]tools.py that contains mcp tools for respective functionality, this way all def -xxx-tools classes are in a separate file to be easily navigated and edited

### <-Bug Fixes->
[] Test all new EER tools for proper error handling
[] Validate input models work correctly with MCP framework
[] Ensure proper fallback when web scraping fails

### <-Documentation->
[] Update README.md for v3.0 with EER capabilities
[] Create user guide for EER profile creation and calculation
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

### <-Next Steps for v3.0 Implementation->

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
        string food_group
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