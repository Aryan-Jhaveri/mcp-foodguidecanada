# Implementations
A list future ideas, tasks, and ideas to improve/maintain the mcp server

### May 30, 2025
[] Add a temporary and/or permanent database system for LLMs to

    - To input ingredients (see 'access to Food nutrition Canada)

    - To use *math tools* to adjust serving size, 

    - To store favorites in recipes

    - To calculate calories and calories per serving 
    
    (look into creating embedding for recipe titles, and creating an automated pipe that pulls and updated recipe title db)

[] Remove nutritional information tag for recipes

[] Make windows version of setup and installation

[] Maybe create a tool to create .ics files (need to see how different LLM clients display artifacts)

[] Add Access to Canadian Nutrient File  to convert and search for nutrition profiles for ingredients https://food-nutrition.canada.ca/cnf-fce/?lang=eng (https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data.html)

    - To fetch recipe ingredient nutrient profiles
    
    - Consider instead https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data/nutrient-value-some-common-foods-2008.html#tbl_con_mat

    - There is search by food, but also search by nutrient https://food-nutrition.canada.ca/cnf-fce/newNutrientSearch

[] Add Access to Dietary Reference Intake tables https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes.html

    - Also Consider references for tables and academic sources to be cited

    - Consider adding math support for equations for EER https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/equations-estimate-energy-requirement.html



## Notes


<summary> List of notes and questions to consider </summary>

<details>
* In V2.0, The MCP server becomes and amalgam of access to reference intake values and Canadian Nutrient File, and a temporary local database access. The workflow of the agent becomes something like:

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
graph TD;
    A-->B;
    A-->C;
    B-->D;
    C-->D;
```    