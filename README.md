# 🍲 <a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide - MCP Server</a>
<a href="https://www.python.org/downloads/" target="_blank"><img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python 3.8+"></a>
<a href="https://opensource.org/licenses/MIT" target="_blank"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
<a href="https://modelcontextprotocol.io/" target="_blank"><img src="https://img.shields.io/badge/MCP-ModelContextProtocol-green.svg" alt="MCP"></a>

[![Watch the trailer](https://img.youtube.com/vi/VtKMYpnC2EI/maxresdefault.jpg)](https://youtu.be/VtKMYpnC2EI)
## 📝 Description

This is a **comprehensive nutrition analysis platform** that integrates <a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide</a> recipes with Health Canada's official nutrition databases through a <a href="https://modelcontextprotocol.io/" target="_blank">Model Context Protocol (MCP)</a> server.

**What makes this powerful:**

Instead of LLMs manually parsing multiple government websites and performing complex nutrition calculations, this server provides **42+ specialized tools** organized into six major categories:

🍲 **Recipe Discovery & Management** - Smart search, detailed extraction, favorites storage  
🗄️ **Database & Session Management** - Virtual sessions, persistent storage, bulk operations  
🧮 **Math & Calculation Tools** - Recipe scaling, ingredient calculations, safe arithmetic  
🥗 **CNF Nutrition Analysis** - Canadian Nutrient File integration with LLM-driven unit conversion  
⚡ **Energy Requirements (EER)** - Health Canada energy equation calculations  
📊 **Dietary Reference Intakes (DRI)** - Macronutrient recommendations and adequacy assessment  

Built using <a href="https://github.com/jlowin/fastmcp" target="_blank">FastMCP</a> with custom integrations to Health Canada's <a href="https://food-nutrition.canada.ca/cnf-fce/index-eng.jsp" target="_blank">Canadian Nutrient File (CNF)</a> database, <a href="https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables.html" target="_blank">Dietary Reference Intakes (DRI)</a> tables, and EER equations, this server transforms complex nutrition analysis into simple tool calls for AI assistants.

Check IMPLEMENTATIONS.MD if you'd like to contribute or collaborate! Always looking for suggestions!

## 📑 Table of Contents

- [📝 Description](#-description)
- [✨ Features](#-features)
- [📥 Installation](#-installation)
- [🚀 Running the Server using Claude](#-running-the-server-using-Claude-Desktop-Integration)
- [🏗️ Project Structure](#️-project-structure)
- [⚠️ Known Issues](#️-known-issues-and-limitations)
- [📋 API Reference](#-api-reference)

## ✨ Features

This comprehensive nutrition analysis platform provides **42+ specialized tools** organized into six major categories:

### 🍲 Recipe Discovery & Management (Core Tools)
* **Smart Recipe Search** - Text queries with advanced filtering by ingredients, meal types, appliances, and collections
* **Detailed Recipe Extraction** - Complete ingredients, instructions, prep times, tips, and nutritional information
* **Filter Discovery** - Dynamic exploration of available search filters and categories
* **Favorites Management** - Persistent storage of user's preferred recipes with SQLite database

### 🗄️ Database & Session Management
* **Virtual Sessions** - In-memory storage for temporary recipe analysis (prevents database bloat)
* **Recipe Storage & Parsing** - Automatic ingredient parsing with amounts, units, and names
* **Session Cleanup** - Automatic memory management for optimal performance
* **Bulk Operations** - Process multiple recipes efficiently with reduced tool calls

### 🧮 Math & Calculation Tools
* **Recipe Scaling** - Scale entire recipes or individual ingredients using parsed data
* **Serving Size Adjustments** - Calculate ingredients for different serving counts
* **Bulk Calculations** - Process multiple calculations in one operation (3x-10x efficiency gain)
* **Simple Calculator** - Safe arithmetic evaluation with string variables for any calculations
* **Recipe Comparisons** - Compare recipes by servings, complexity, or nutritional content

### 🥗 CNF Nutrition Analysis (Canadian Nutrient File Integration)
* **Food Search & Retrieval** - Search Health Canada's official CNF database by food name
* **Macronutrient Analysis** - Complete nutritional profiles with 13+ core nutrients
* **LLM-Driven Unit Conversion** - Intelligent handling of non-standard units like "4 fillets" with full transparency
* **Bulk Processing** - Analyze multiple foods in single operations for efficiency
* **Unit Matching Intelligence** - Clear status indicators for conversion decisions with LLM reasoning

### ⚡ Energy Requirements (EER Integration)
* **Live EER Equations** - Fetch current Energy Expenditure equations from Health Canada DRI tables
* **Profile Management** - Create and manage user profiles for repeated calculations
* **PAL Categories** - Physical Activity Level descriptions with examples
* **42+ Equations Available** - Complete coverage of age groups, genders, and activity levels

### 📊 Dietary Reference Intakes (DRI Analysis)
* **Complete DRI Tables** - Macronutrient recommendations (EAR, RDA, AI, UL) for all age groups
* **Adequacy Assessment** - Compare actual intake against Health Canada recommendations
* **AMDR Analysis** - Acceptable Macronutrient Distribution Range evaluation
* **Session-Based Workflows** - Cache DRI data for complex multi-step nutrition analysis
* **EER Integration** - Convert energy requirements to macronutrient targets for meal planning

## 📥 Installation
Click the image to Watch the setup tutorial!
[![Watch the setup tutorial](https://img.youtube.com/vi/FWH9_HMKwro/maxresdefault.jpg)](https://youtu.be/FWH9_HMKwro)

1. **Prerequisites**:
   - <a href="https://www.python.org/#:~:text=Download" target="_blank">Python 3.8 or higher</a>
   - <a href="https://pip.pypa.io/en/stable/installation/" target="_blank">pip (Python package installer)</a>

2. **Clone the repository**:
   ```bash
   git clone https://github.com/Aryan-Jhaveri/mcp-foodguidecanada
   cd mcp-foodguidecanada
   ```

3. **Install dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```

## 🚀 Running the Server using Claude Desktop Integration

To use this server with Claude Desktop:

1. **Find your Python path**:
   Open your terminal and run:
   ```bash
   which python3
   ```
   This will show the full path to your Python installation (e.g., `/usr/bin/python3`, `/opt/homebrew/bin/python3`, or `/opt/anaconda3/bin/python3`)

2. **Get the absolute path to your project**:
   In your terminal, navigate to the project directory and run:
   ```bash
   pwd
   ```
   This shows your full project path (e.g., `mcp-foodguidecanada`)

3. **Open Claude Desktop settings**:
   - Navigate to Settings (⌘ + ,) → Developer → Edit Config

4. **Add the server configuration**:
   Replace the paths below with your actual paths from steps 1 and 2:
   ```json
   {
     "mcpServers": {
       "FoodGuideSousChef": {
         "command": "/opt/homebrew/bin/python3",
         "args": [
           "path/to/mcp-foodguidecanada/src/server.py"
         ],
         "cwd": "path/to/mcp-foodguidecanada"
       }
     }
   }
   ```

   **Common Python paths by system**:
   - **Homebrew (Mac)**: `/opt/homebrew/bin/python3`
   - **System Python (Mac)**: `/usr/bin/python3`
   - **Anaconda**: `/opt/anaconda3/bin/python3`
   - **Linux**: `/usr/bin/python3`

5. **Save and restart Claude Desktop**:
   - Save the configuration file
   - Completely quit and restart Claude Desktop
   - The server will now be available in your conversations

### Troubleshooting
- If the server doesn't appear, check the Claude Desktop logs for error messages
- Verify Python 3.8+ is installed: `python3 --version`

4. **Restart Claude Desktop**:
   - The server will now be available in your conversations

## 🏗️ Project Structure

Here's how the comprehensive nutrition platform is organized:

### 🗂️ **Root Files**
* **`main.py`**: Command-line interface for testing (alternative to MCP server)
* **`requirements.txt`**: Python dependencies for the entire platform
* **`IMPLEMENTATIONS.md`**: Development roadmap and architecture plans

### 📁 **`src/` Folder - Core Platform**

* **`server.py`**: Main MCP server with **42+ specialized tools** across 6 categories:
  - Recipe discovery and management tools
  - Database and session management tools
  - Math and calculation tools
  - CNF nutrition analysis tools
  - EER energy requirement tools
  - DRI dietary reference intake tools

* **`config.py`**: Platform configuration including database settings and Health Canada endpoints
* **`cli.py`**: Command-line interface for development and testing

#### 📁 **`api/` Folder - Health Canada Integrations**
* **`search.py`**: Canada's Food Guide recipe search and filtering
* **`recipe.py`**: Detailed recipe extraction and ingredient parsing
* **`cnf.py`**: Canadian Nutrient File food search and nutrition data retrieval
* **`eer.py`**: Energy Expenditure Requirements from DRI tables
* **`dri.py`**: Dietary Reference Intake tables and macronutrient recommendations

#### 📁 **`db/` Folder - Database & Calculation Layer**
* **`connection.py`**: SQLite database connection and management
* **`schema.py`**: Database schema and virtual session management
* **`queries.py`**: Database operation tools registration
* **`cnf_tools.py`**: CNF nutrition analysis and unit conversion tools
* **`math_tools.py`**: Recipe scaling, calculations, and arithmetic tools
* **`eer_tools.py`**: Energy requirement calculation and profile management
* **`dri_tools.py`**: DRI analysis and adequacy assessment tools

#### 📁 **`models/` Folder - Data Structures & Validation**
* **`recipe.py`**: Recipe data models with ingredient parsing
* **`filters.py`**: Search filter management and caching
* **`cnf_models.py`**: CNF food and nutrition data models
* **`eer_models.py`**: EER calculation and profile models
* **`dri_models.py`**: DRI table and assessment models
* **`math_models.py`**: Calculation tool input/output models
* **`db_models.py`**: Database operation models

#### 📁 **`utils/` Folder - Support Functions**
* **`url_builder.py`**: Canada's Food Guide URL construction
* **`downloader.py`**: Recipe export functionality (JSON/Markdown)

### 📁 **Storage & Data**
* **`cache/`**: Filter data and temporary file storage
* **`docs/`**: Additional documentation and guides
* **`downloads/`**: Recipe export output directory
* **`foodguide_data.db`**: SQLite database for persistent favorites storage

### 🔄 **Platform Architecture**:
1. **MCP Server Layer**: `server.py` exposes 42+ tools to AI assistants
2. **Health Canada APIs**: Live integration with CNF, DRI, and recipe databases
3. **Database Layer**: Virtual sessions (memory) + persistent favorites (SQLite)
4. **Calculation Engine**: Math tools for scaling, nutrition analysis, and comparisons
5. **LLM Integration**: Intelligent unit conversion and decision-making workflows


## ⚠️ Known Issues and Limitations

### Data Dependencies
- **Multiple Website Dependencies**: Functionality depends on Canada's Food Guide, Health Canada CNF database, and DRI tables maintaining consistent structure
- **Internet Required**: All nutrition data is fetched live from Health Canada websites
- **Data Quality**: Recipe and nutrition accuracy depends on Health Canada's data quality and updates

### Performance Considerations
- **Web Scraping Overhead**: Recipe search may be slower than direct APIs due to HTML parsing
- **Virtual Session Memory**: Large datasets in virtual sessions consume RAM (auto-cleanup helps)
- **Bulk Operation Limits**: Some tools have built-in limits to prevent resource exhaustion

### Calculation Accuracy
- **LLM-Dependent Unit Conversion**: Non-standard units like "4 fillets" require LLM reasoning for accurate conversion
- **Math Verification Recommended**: Complex calculations should be spot-checked for accuracy
- **Ingredient Parsing Limitations**: Unusual ingredient formats may not parse correctly

## 📋 API Reference

This platform provides **42+ specialized tools** across 6 major categories. Below are representative examples from each category.

### 🍲 Recipe Discovery Tools

#### `search_recipes`
Search Canada's Food Guide with advanced filtering.
- **Parameters**: `search_text`, `fruits`, `vegetables`, `proteins`, `meals`, `appliances`, `collections`, `max_pages`
- **Returns**: Array of recipe metadata with titles, URLs, and slugs

#### `get_recipe`
Extract complete recipe details from URL.
- **Parameters**: `url` (required)
- **Returns**: Full recipe with ingredients, instructions, prep time, tips

#### `add_to_favorites`
Save recipes to persistent SQLite storage.
- **Parameters**: `recipe_url`, `notes` (optional)
- **Returns**: Confirmation with recipe stored in database

### 🗄️ Database & Session Tools

#### `store_recipe_in_session`
Store recipes in virtual memory sessions.
- **Parameters**: `session_id`, `recipe_data`
- **Returns**: Confirmation with parsed ingredient data

#### `simple_recipe_setup`
Combined recipe transfer, parsing, and nutrition preparation.
- **Parameters**: `session_id`, `recipe_url`
- **Returns**: Complete recipe setup for analysis

### 🧮 Math & Calculation Tools

#### `scale_recipe_servings`
Scale entire recipes using parsed ingredient data.
- **Parameters**: `session_id`, `recipe_id`, `target_servings`
- **Returns**: Scaled ingredient amounts with units

#### `bulk_math_calculator`
Process multiple calculations in one operation (3x-10x efficiency gain).
- **Parameters**: `calculations` (array of expression objects)
- **Returns**: All calculation results in single response

### 🥗 CNF Nutrition Analysis Tools

#### `search_and_get_cnf_macronutrients`
Search Canadian Nutrient File and retrieve nutrition data.
- **Parameters**: `food_name`, `max_results`
- **Returns**: CNF foods with complete macronutrient profiles

#### `calculate_recipe_nutrition_summary`
Analyze unit matching for LLM-driven conversion workflow.
- **Parameters**: `session_id`, `recipe_id`
- **Returns**: Unit matching analysis with conversion recommendations

#### `bulk_get_cnf_macronutrients`
Process multiple CNF foods efficiently.
- **Parameters**: `food_codes` (up to 20 foods)
- **Returns**: Batch nutrition data with 90% tool call reduction

### ⚡ Energy Requirements (EER) Tools

#### `get_eer_equations`
Fetch Energy Expenditure Requirements from Health Canada.
- **Parameters**: `equation_type`, `pal_category`
- **Returns**: Live EER equations with coefficients in JSON format

#### `create_user_profile`
Create profiles for repeated EER calculations.
- **Parameters**: `profile_name`, `age`, `gender`, `height`, `weight`, `pal_category`
- **Returns**: Stored profile for calculation workflows

### 📊 Dietary Reference Intakes (DRI) Tools

#### `get_macronutrient_dri_tables`
Fetch complete DRI tables from Health Canada.
- **Parameters**: None (fetches all current DRI data)
- **Returns**: Complete macronutrient recommendations (EAR, RDA, AI, UL)

#### `compare_intake_to_dri`
Assess nutritional adequacy against Health Canada standards.
- **Parameters**: `age_range`, `gender`, `intake_data`
- **Returns**: Adequacy assessment with risk evaluation

---

### 🔄 Complete Workflow Example

```
1. search_recipes(search_text="salmon") → Find recipes
2. get_recipe(url="recipe_url") → Extract details  
3. store_recipe_in_session(session_id="nutrition", recipe_data=...) → Store in memory
4. search_and_get_cnf_macronutrients(food_name="salmon") → Get nutrition data
5. calculate_recipe_nutrition_summary(session_id="nutrition") → Analyze unit matching
6. scale_recipe_servings(target_servings=6) → Scale for family dinner
7. get_eer_equations(equation_type="adult") → Calculate energy needs
8. compare_intake_to_dri(age_range="19-30 y", gender="males") → Assess adequacy
```

---

<div align="center">
<p>Made with ❤️ for Canada's Food Guide</p>
<p>
<a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide</a>
<a href="https://food-nutrition.canada.ca/cnf-fce/?lang=eng" target="_blank">Health Canada's Canadian Nutrient File</a>
<a href="https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables.html" target="_blank">Health Canada's Dietary Reference Intakes</a>
</p>
</div>
