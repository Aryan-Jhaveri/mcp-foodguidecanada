<a href="https://food-guide.canada.ca/en/" target="_blank"><img src="https://food-guide.canada.ca/themes/custom/food_guide/images/social-image-en.jpg" alt="Canada's Food Guide MCP Server" width="600"></a>

# 🍲 Canada's Food Guide Sous Chef MCP Server

<a href="https://www.python.org/downloads/" target="_blank"><img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python 3.8+"></a>
<a href="https://opensource.org/licenses/MIT" target="_blank"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
<a href="https://modelcontextprotocol.io/" target="_blank"><img src="https://img.shields.io/badge/MCP-ModelContextProtocol-green.svg" alt="MCP"></a>

## 📝 Description

This project implements a <a href="https://modelcontextprotocol.io/" target="_blank">Model Context Protocol (MCP)</a> server that provides tools for discovering, searching, and retrieving recipes from Canada's Food Guide. It enables LLMs and other MCP clients to access nutritious recipes and meal ideas through a structured API.

The server is built using the <a href="https://github.com/jlowin/fastmcp" target="_blank">FastMCP</a> library and interacts with the Canada's Food Guide website via custom web scraping tools.

## 📑 Table of Contents

- [📝 Description](#-description)
- [✨ Features](#-features)
- [🏗️ Project Structure](#️-project-structure)
- [📥 Installation](#-installation)
- [🚀 Running the Server](#-running-the-server)
- [🔧 Claude Desktop Integration](#-claude-desktop-integration)
- [⚠️ Known Issues](#️-known-issues-and-limitations)
- [📋 API Reference](#-api-reference)

## ✨ Features

This server exposes Canada's Food Guide recipe functionalities as MCP tools, including:

### Recipe Search & Retrieval

* **Search Operations:**
    * Search for recipes by text query
    * Filter by ingredients (fruits, vegetables, proteins, whole grains)
    * Filter by meal type (breakfast, lunch, dinner, snacks)
    * Filter by cooking appliance (oven, stovetop, etc.)
    * Filter by collections (vegetarian, kid-friendly, etc.)
    * Configure maximum search pages
* **Recipe Operations:**
    * Fetch detailed recipe information by URL
    * Get ingredients, instructions, cooking times, and servings
    * Retrieve recipe tips and nutritional highlights
* **Filter Operations:**
    * List all available filter categories
    * Get specific filter options (e.g., all available vegetables)
    * Find valid collections for recipe filtering

## 🏗️ Project Structure

* **`src/`**: Contains the main source code for the MCP server.
    * **`api/`**: Handles interactions with Canada's Food Guide website.
        * **`recipe.py`**: Recipe fetching and parsing functionality.
        * **`search.py`**: Recipe search functionality.
    * **`models/`**: Contains data structures for recipes and search filters.
        * **`recipe.py`**: Recipe data model.
        * **`filters.py`**: Search filter models and normalization.
    * **`utils/`**: Utility functions for the application.
        * **`parser.py`**: HTML parsing utilities.
        * **`url_builder.py`**: URL construction for API requests.
    * **`cli.py`**: Command-line interface for the application.
    * **`server.py`**: Main FastMCP server definition with tool registrations.
* **`prompts/`**: Contains MCP prompt definitions.
* **`main.py`**: Entry point for the CLI interface.
* **`requirements.txt`**: Project dependencies.

## 📥 Installation

1. **Prerequisites**:
   - Python 3.8 or higher
   - pip (Python package installer)

2. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd mcp-foodguide-souschef/mcp-test
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## 🚀 Running the Server

### Using Python

Run the FastMCP server directly with Python:

```bash
# Method 1: Run the Python file directly
python src/server.py

# Method 2: Using Python module notation (may require PYTHONPATH adjustment)
PYTHONPATH=. python -m src.server
```

The server will start and listen for MCP client connections using the default STDIO transport.

### Using the FastMCP CLI

If you prefer using the FastMCP CLI:

```bash
# Direct file execution
fastmcp run src/server.py

# Or with module notation (may require PYTHONPATH adjustment)
PYTHONPATH=. fastmcp run src.server
```

### Transport Options

The server supports different transport options:

1. **STDIO** (Default):
   ```bash
   python src/server.py
   ```

2. **HTTP Transport**:
   ```bash
   python src/server.py --transport streamable-http --host 127.0.0.1 --port 8000
   ```

3. **Server-Sent Events (SSE)**:
   ```bash
   python src/server.py --transport sse --host 127.0.0.1 --port 8000
   ```

## 🔧 Claude Desktop Integration

To use this server with Claude Desktop:

1. **Open Claude Desktop settings**:
   - Navigate to Settings (⌘ + ,) → Developer → Edit Config

2. **Add the server configuration**:
   ```json
   {
     "mcpServers": {
       "FoodGuideSousChef": {
         "command": "/opt/anaconda3/bin/python3",
         "args": [
           "/Users/aryanjhaveri/Desktop/Projects/mcp/mcp-foodguide-souschef/mcp-test/src/server.py"
         ],
         "cwd": "/Users/aryanjhaveri/Desktop/Projects/mcp/mcp-foodguide-souschef/mcp-test"
       }
     }
   }
   ```

3. **Verify the Python path**:
   - The example uses `/opt/anaconda3/bin/python3` - you should replace this with the result of running `which python3` in your terminal if it's different

4. **Restart Claude Desktop**:
   - The server will now be available in your conversations

## ⚠️ Known Issues and Limitations

- **Website Dependency**: Will break if Canada's Food Guide website structure changes
- **Data Inconsistency**: Depends on food guide to upload clean data (e.g., searching for `--fruits apple` vs `search apple` results in 1 missing recipe in filtered search due to data editing anomalies)
- **Search Limitations**: Maximum number of pages and results is capped
- **Performance**: Web scraping may be slow compared to a direct API
- **Availability**: Requires internet connection to access the Canada's Food Guide website
- **Parsing Errors**: Complex recipe formats may occasionally be parsed incorrectly

## 📋 API Reference

### Tool: `search_recipes`

Search for recipes on Canada's Food Guide website.

**Parameters**:
- `search_text` (string, optional): Text to search for in recipes
- `fruits` (array of strings, optional): Filter by fruits (e.g., apple, banana)
- `vegetables` (array of strings, optional): Filter by vegetables (e.g., carrot, broccoli)
- `proteins` (array of strings, optional): Filter by proteins (e.g., chicken, tofu)
- `whole_grains` (array of strings, optional): Filter by whole grains (e.g., rice, quinoa)
- `meals` (array of strings, optional): Filter by meal type (e.g., breakfast, dinner)
- `appliances` (array of strings, optional): Filter by cooking appliance (e.g., oven, stovetop)
- `collections` (array of strings, optional): Filter by collections (e.g., vegetarian, kid-friendly)
- `max_pages` (integer, optional, default=5): Maximum pages to search

**Returns**:
- Array of recipe metadata objects with title, URL, and slug

### Tool: `get_recipe`

Fetch detailed recipe information from a URL.

**Parameters**:
- `url` (string, required): The full URL to the recipe on Canada's Food Guide website

**Returns**:
- Recipe object with detailed information including ingredients, instructions, preparation time, etc.

### Tool: `list_filters`

Get available filters for searching recipes.

**Parameters**:
- `filter_type` (string, optional): Specific filter type to retrieve (vegetables, fruits, proteins, whole_grains, meal, cooking_appliance)

**Returns**:
- Dictionary of filter types and their available values

---

<div align="center">
<p>Made with ❤️ for Canada's Food Guide</p>
<p>
<a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide</a>
</p>
</div>