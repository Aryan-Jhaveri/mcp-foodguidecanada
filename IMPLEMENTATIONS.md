# Implementations
A list future ideas, tasks, and ideas to improve/maintain the mcp server

### June 4, 2025
## <-Bugs->
[] Edit recipe add prompt , and show recipes prompt to always ask user for feedback

## <-Features->
[] Add Access to Canadian Nutrient File to convert and search for nutrition profiles for ingredients https://food-nutrition.canada.ca/cnf-fce/?lang=eng (https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data.html)
    - Maybe this will be kept as a virtual table with fetched recipe ingredient nutrient profiles
    - Consider instead https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data/nutrient-value-some-common-foods-2008.html#tbl_con_mat
    - There is search by food, but also search by nutrient https://food-nutrition.canada.ca/cnf-fce/newNutrientSearch

[] Add Access to Dietary Reference Intake tables https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables.html
    -
    - Consider adding math support for equations for EER https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/equations-estimate-energy-requirement.html
        - Prompt the LLM to ask the user for the values required for the calculation

[] Remove nutritional information tag for recipes       
 
## <-Installation->
[] Make windows version of setup and installation
[] Add a smithery installation package to automatically install the server instead of having to add working directories

![] **Maybe** create a tool to create .ics files (need to see how different LLM clients display artifacts)


### June 1, 2025
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

### May 30, 2025
[x] Add a temporary and/or permanent database system for LLMs to:

[x] To input ingredients (see 'access to Food nutrition Canada)

[!!] To use *math tools* to adjust serving size,  NOTE: I WOULD NOT COMPLETELY TRUST THESE MEASUREMENTS!!!

[x] To store favorites in recipes

[!!]- To calculate calories and calories per serving 
    - Maybe add table/webapi for unit conversions + cooking units

## Notes

<details>
<summary> List of notes and questions to consider </summary>


* In V2.0, The MCP server becomes and amalgam of access to dietary reference intake values + Canadian Nutrient File, and a temporary local database access. The workflow of the agent becomes something like:

Input Recipe Query --> Download recipe to temporary db as an sql table [Ingredients, serving size, units, and amount] --> When asked: Fetch recipe nutrient profile for different ingredients --|--> If asked: Compare values for recipes for a days worth, with DRI Table values to find if food the user is planning on consuming meets DRI requirments

* Questions to Consider:

    - What can be the most efficient template database design ready for the agent to go look like?

    - What math tools can be added for Database (serving size calculator/multiplyer) and EER?
    
    = What database would be ideal for LLMS to - add calculated coloumns to adjust serving size, pull recipe information (q: what to include?), DRI information, and nutrient information for recipes.

</details>

## Plan


1. Add Database functionality 
    - Because majority of the following features for nutritional information depend on the LLM already having the data for recipe downloaded

2. Add values Nutrient Value of Some Common Foods as a default template 
    - Canandian Nutrient File could be a 3.0 update

3. 

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