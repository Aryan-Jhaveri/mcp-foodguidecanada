# IMPLEMENTATIONS.md
Future improvements To-Do list, tasks, Project wishlists, Notes

## August 12, 2025
### -- Rate Limiting & Web Scraping Improvements
[] Implement exponential backoff with jitter for CNF web scraping
    - Current 0.5s fixed delay insufficient for bulk operations
    - Add randomized delays (2-4 seconds) to mimic human behavior
    - Implement exponential backoff on HTTP 429 responses

[] Add request chunking for bulk_get_cnf_macronutrients operations  
    - Break large bulk requests (20 foods) into smaller chunks (3-5 foods)
    - Add progressive delays between chunks
    - Reduce concurrent workers from 3 to 1-2 for better server respect

[] Enhanced error handling and retry mechanisms
    - Distinguish between rate limits, network errors, and data errors
    - Implement circuit breaker pattern for repeated failures  
    - Better caching strategy for failed requests

[] Configuration improvements for production stability
    - Increase CNF_RATE_LIMIT from 0.5s to 2-3s
    - Add environment variables for rate limit customization
    - Add monitoring for rate limit hit frequency

[] Long-term solutions to reduce web scraping dependency
    - Investigate Health Canada official API access
    - Build offline CNF database cache for common foods
    - Implement MCP resources for frequently requested nutrients

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
[] Simplify installaion with an npm or smithery installation packaging

### -- Potential ideas
[] Extend DRI support to include micro nutrients, vitamins and minerals too
[] add tools to allow users to store temp_recipe_ info to permanent database for ingredients they keep in stock
[] add functionality to vary how long you like to store recipe information


## Notes
-> Current LLM clients already have great web crawlers, though the current mcp idea is a good example of using html webscraping, it might be an outdated feature in light of current crawlers and their developments. Maybe a good justification of using a smaller model on a phone in a kitchen. 

-> Need to think of tests, and evaluating tool call frequencies to make this server more sustainable.
