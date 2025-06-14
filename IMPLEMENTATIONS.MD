# IMPLEMENTATIONS.md
Future improvements To-Do list, tasks, Project wishlists, Notes

## June 14, 2025
[] CNF database updated robot.txt limits web api calls to prevent bloat - Now only 2 of, say 4, recipes are being fetched.
    
    Alternatives
    --> Add mcp.resource or mcp.tool for table values for common foods

    --> Possibly add offline database for Canada's nutrient file

    --> Update rate for api calls.

## June 10, 2025
### TO-DO
[] Update the outdate CLI to include db, EER, and CNF compatibility. LLM's waste water, and this in itself can have a standalone value too.
### -- Improvements
[] Macros Analysis is the most resource consuming tool set, and it also tends to time out on the Nutrient File's side. An API key here would really efficient.
[] Combine these tools (potentially), to make tool calling efficient, and reduce tool calls:
    - [] calculate_recipe_nutrition_summary and query_recipe_macros_table. The first tool simple parses and sets up the table for query recipes
    - [] store_recipe_in_temp_tables and simple_recipe_setup. the setup function parses the stored ingredients, they should be ideally combined, so to reduce LLM tool calls.

[] refactor and breakdown cnf_tools.py file. The current size is too big, and contains helper functions
[] Add mermaid diagram to implementations.md to show dataflow.

### -- Potential ideas
[] Extend DRI support to include micro nutrients, vitamins and minerals too
[] add tools to allow users to store temp_recipe_ info to permanent database for ingredients they keep in stock
[] add functionality to vary how long you like to store recipe information
