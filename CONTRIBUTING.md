# 🤝 Contributing to Canada's Food Guide MCP Server

Thank you for your interest in contributing to this comprehensive nutrition analysis platform! This project integrates <a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide</a> with Health Canada's nutrition databases through a <a href="https://modelcontextprotocol.io/" target="_blank">Model Context Protocol (MCP)</a> server, providing **42+ specialized tools** for AI-powered nutrition analysis.

We welcome contributions of all kinds - from bug fixes and documentation improvements to new features and tool optimizations. This guide will help you get started and ensure your contributions align with the project's standards.

## 📑 Table of Contents

- [🚀 Getting Started](#-getting-started)
- [🔄 Development Workflow](#-development-workflow)
- [📏 Code Standards](#-code-standards)
- [🏗️ Project Architecture](#️-project-architecture)
- [🧪 Testing Guidelines](#-testing-guidelines)
- [🎯 Priority Contribution Areas](#-priority-contribution-areas)
- [📝 Submission Guidelines](#-submission-guidelines)
- [🤝 Community Guidelines](#-community-guidelines)

## 🚀 Getting Started

### Prerequisites

- **Python 3.8 or higher** - <a href="https://www.python.org/downloads/" target="_blank">Download Python</a>
- **pip** (Python package installer) - <a href="https://pip.pypa.io/en/stable/installation/" target="_blank">Install pip</a>
- **Git** for version control
- **Claude Desktop** for testing MCP integration (optional but recommended)

### Development Environment Setup

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/mcp-foodguidecanada.git
   cd mcp-foodguidecanada
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Test the installation**:
   ```bash
   python3 src/server.py --help
   ```

5. **Set up Claude Desktop integration** (for testing):
   - Follow the setup instructions in the [README.md](README.md#-running-the-server-using-claude-desktop-integration)
   - Use your local development path in the Claude Desktop configuration

## 🔄 Development Workflow

### Git Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

2. **Make your changes** following the code standards below

3. **Test your changes locally**:
   - Test with the CLI: `python3 main.py`
   - Test with Claude Desktop integration
   - Verify nutrition calculations if applicable

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add new CNF bulk processing tool"
   # or
   git commit -m "fix: resolve recipe parsing issue with special characters"
   ```

5. **Push and create a pull request**:
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Convention

Use clear, descriptive commit messages:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `refactor:` for code refactoring
- `test:` for adding tests
- `perf:` for performance improvements

## 📏 Code Standards

### Python Code Style

Follow the existing code patterns observed in the project:

```python
"""
Module docstring describing the purpose of the file
"""

import os
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# External imports first, then internal imports
from fastmcp import FastMCP
from src.models.recipe import Recipe
```

### Type Hints

- **Always use type hints** for function parameters and return values
- Use `Optional[Type]` for nullable values
- Use `List[Type]`, `Dict[str, Any]` for collections

```python
def process_recipe(recipe_url: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Process a recipe and return nutrition data."""
    pass
```

### Documentation

- **Module docstrings**: Use triple quotes for file-level documentation
- **Inline comments**: Use `#` for field explanations in dataclasses
- **Function docstrings**: Brief description of purpose and parameters

```python
@dataclass
class Recipe:
    title: str  # The title of the recipe
    slug: str   # A URL-friendly version of the title
    ingredients: List[str]  # A list of ingredients required for the recipe
```

### Error Handling

- Use try-except blocks for external API calls
- Log errors appropriately using the configured logger
- Return meaningful error messages to users

```python
try:
    response = requests.get(url, timeout=TOOL_TIMEOUT_SECONDS)
    response.raise_for_status()
except requests.RequestException as e:
    logger.error(f"Failed to fetch recipe: {e}")
    return {"error": f"Unable to fetch recipe: {str(e)}"}
```

## 🏗️ Project Architecture

Understanding the project structure helps you contribute effectively:

### Core Architecture

- **`src/server.py`**: Main MCP server with 42+ tools across 6 categories
- **`src/api/`**: Health Canada integrations (CNF, DRI, recipes, search)
- **`src/db/`**: Database operations and calculation tools
- **`src/models/`**: Data structures and validation
- **`src/utils/`**: Helper functions and utilities

### Six Tool Categories

1. **🍲 Recipe Discovery & Management** - Search, extraction, favorites
2. **🗄️ Database & Session Management** - Virtual sessions, storage
3. **🧮 Math & Calculation Tools** - Scaling, arithmetic, comparisons
4. **🥗 CNF Nutrition Analysis** - Canadian Nutrient File integration
5. **⚡ Energy Requirements (EER)** - Health Canada energy calculations
6. **📊 Dietary Reference Intakes (DRI)** - Macronutrient recommendations

### FastMCP Integration

Tools are registered using the FastMCP framework:

```python
@mcp.tool()
def tool_name(parameter: str) -> Dict[str, Any]:
    """Tool description for AI assistants."""
    # Implementation
    return result
```

## 🧪 Testing Guidelines

### Local Testing

1. **CLI Testing**:
   ```bash
   python3 main.py
   # Test specific functionality interactively
   ```

2. **Claude Desktop Testing**:
   - Configure your local development server in Claude Desktop
   - Test tools with real queries
   - Verify nutrition calculations against known values

3. **Manual Verification**:
   - Use the <a href="https://docs.google.com/spreadsheets/d/1TELVtKLN35yxGFC10751WnByRtpWndYPjC4WKWw4Cgo/edit?usp=sharing" target="_blank">verification spreadsheet</a> for EER and CNF calculations
   - Test edge cases and error handling
   - Verify with different recipe types and ingredients

### Testing Checklist

- [ ] Tool functions execute without errors
- [ ] Return values match expected schema
- [ ] Error handling works for invalid inputs
- [ ] Performance is acceptable for bulk operations
- [ ] Database operations don't leak memory
- [ ] External API calls handle timeouts gracefully

## 🎯 Priority Contribution Areas

Based on the current development roadmap in [IMPLEMENTATIONS.MD](IMPLEMENTATIONS.MD):

### High Priority Improvements

- **Tool Efficiency**: Combine related tools to reduce LLM tool calls
  - Merge `calculate_recipe_nutrition_summary` and `query_recipe_macros_table`
  - Combine `store_recipe_in_temp_tables` and `simple_recipe_setup`

- **Code Organization**: Refactor large files
  - Break down `cnf_tools.py` (currently too large)
  - Extract helper functions into utility modules

- **Documentation**: Add architecture diagrams
  - Create Mermaid diagram showing data flow
  - Document tool interaction patterns

### Medium Priority Features

- **Installation Simplification**: Package management improvements
  - npm or Smithery installation packaging
  - Automated setup scripts

- **DRI Extension**: Expand nutritional analysis
  - Add support for micronutrients, vitamins, and minerals
  - Extend adequacy assessment tools

- **User Experience**: Enhanced recipe management
  - Allow users to store temporary recipe info permanently
  - Configurable recipe information storage duration

### New Feature Ideas

- **Recipe Planning**: Weekly meal planning tools
- **Inventory Management**: Track ingredients in stock
- **Nutritional Goals**: Personal nutrition target setting
- **Export Functionality**: Enhanced data export formats

## 📝 Submission Guidelines

### Pull Request Process

1. **Before submitting**:
   - Ensure your code follows the established patterns
   - Test thoroughly with both CLI and Claude Desktop
   - Update documentation if you've added new features
   - Check that existing functionality still works

2. **Pull Request Template**:
   ```markdown
   ## Description
   Brief description of changes and motivation

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update

   ## Testing
   - [ ] Tested with CLI
   - [ ] Tested with Claude Desktop
   - [ ] Verified nutrition calculations
   - [ ] Tested error handling

   ## Related Issues
   Closes #(issue number)
   ```

3. **Review Process**:
   - Maintainers will review your PR within a few days
   - Be responsive to feedback and suggestions
   - Update your PR based on review comments

### Documentation Updates

If your contribution adds new tools or changes existing functionality:
- Update relevant docstrings
- Add examples to the API Reference section in README.md
- Update IMPLEMENTATIONS.MD if you've addressed TODO items

## 🤝 Community Guidelines

### Code of Conduct

- **Be Respectful**: Treat all contributors with respect and kindness
- **Be Collaborative**: Work together to improve the project
- **Be Constructive**: Provide helpful feedback and suggestions
- **Be Patient**: Remember that everyone is learning and contributing their time

### Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions about the codebase or nutrition analysis
- **Pull Requests**: Get feedback on your contributions

### Communication

- Use clear, descriptive issue titles
- Provide detailed reproduction steps for bugs
- Include relevant Health Canada documentation links when discussing nutrition features
- Be specific about which tools or categories your contribution affects

---

<div align="center">
<p><strong>Thank you for contributing to Canada's Food Guide MCP Server!</strong></p>
<p>Your contributions help make nutrition analysis more accessible through AI assistants.</p>
<p>
<a href="https://food-guide.canada.ca/en/" target="_blank">🍲 Canada's Food Guide</a> •
<a href="https://food-nutrition.canada.ca/cnf-fce/?lang=eng" target="_blank">🥗 Canadian Nutrient File</a> •
<a href="https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables.html" target="_blank">📊 Dietary Reference Intakes</a>
</p>
</div>
# 🤝 Contributing to Canada's Food Guide MCP Server

Thank you for your interest in contributing to this comprehensive nutrition analysis platform! This project integrates <a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide</a> with Health Canada's nutrition databases through a <a href="https://modelcontextprotocol.io/" target="_blank">Model Context Protocol (MCP)</a> server, providing **42+ specialized tools** for AI-powered nutrition analysis.

We welcome contributions of all kinds - from bug fixes and documentation improvements to new features and tool optimizations. This guide will help you get started and ensure your contributions align with the project's standards.

## 📑 Table of Contents

- [🚀 Getting Started](#-getting-started)
- [🔄 Development Workflow](#-development-workflow)
- [📏 Code Standards](#-code-standards)
- [🏗️ Project Architecture](#️-project-architecture)
- [🧪 Testing Guidelines](#-testing-guidelines)
- [🎯 Priority Contribution Areas](#-priority-contribution-areas)
- [📝 Submission Guidelines](#-submission-guidelines)
- [🤝 Community Guidelines](#-community-guidelines)

## 🚀 Getting Started

### Prerequisites

- **Python 3.8 or higher** - <a href="https://www.python.org/downloads/" target="_blank">Download Python</a>
- **pip** (Python package installer) - <a href="https://pip.pypa.io/en/stable/installation/" target="_blank">Install pip</a>
- **Git** for version control
- **Claude Desktop** for testing MCP integration (optional but recommended)

### Development Environment Setup

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/mcp-foodguidecanada.git
   cd mcp-foodguidecanada
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Test the installation**:
   ```bash
   python3 src/server.py --help
   ```

5. **Set up Claude Desktop integration** (for testing):
   - Follow the setup instructions in the [README.md](README.md#-running-the-server-using-claude-desktop-integration)
   - Use your local development path in the Claude Desktop configuration

## 🔄 Development Workflow

### Git Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

2. **Make your changes** following the code standards below

3. **Test your changes locally**:
   - Test with the CLI: `python3 main.py`
   - Test with Claude Desktop integration
   - Verify nutrition calculations if applicable

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add new CNF bulk processing tool"
   # or
   git commit -m "fix: resolve recipe parsing issue with special characters"
   ```

5. **Push and create a pull request**:
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Convention

Use clear, descriptive commit messages:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `refactor:` for code refactoring
- `test:` for adding tests
- `perf:` for performance improvements

## 📏 Code Standards

### Python Code Style

Follow the existing code patterns observed in the project:

```python
"""
Module docstring describing the purpose of the file
"""

import os
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# External imports first, then internal imports
from fastmcp import FastMCP
from src.models.recipe import Recipe
```

### Type Hints

- **Always use type hints** for function parameters and return values
- Use `Optional[Type]` for nullable values
- Use `List[Type]`, `Dict[str, Any]` for collections

```python
def process_recipe(recipe_url: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Process a recipe and return nutrition data."""
    pass
```

### Documentation

- **Module docstrings**: Use triple quotes for file-level documentation
- **Inline comments**: Use `#` for field explanations in dataclasses
- **Function docstrings**: Brief description of purpose and parameters

```python
@dataclass
class Recipe:
    title: str  # The title of the recipe
    slug: str   # A URL-friendly version of the title
    ingredients: List[str]  # A list of ingredients required for the recipe
```

### Error Handling

- Use try-except blocks for external API calls
- Log errors appropriately using the configured logger
- Return meaningful error messages to users

```python
try:
    response = requests.get(url, timeout=TOOL_TIMEOUT_SECONDS)
    response.raise_for_status()
except requests.RequestException as e:
    logger.error(f"Failed to fetch recipe: {e}")
    return {"error": f"Unable to fetch recipe: {str(e)}"}
```

## 🏗️ Project Architecture

Understanding the project structure helps you contribute effectively:

### Core Architecture

- **`src/server.py`**: Main MCP server with 42+ tools across 6 categories
- **`src/api/`**: Health Canada integrations (CNF, DRI, recipes, search)
- **`src/db/`**: Database operations and calculation tools
- **`src/models/`**: Data structures and validation
- **`src/utils/`**: Helper functions and utilities

### Six Tool Categories

1. **🍲 Recipe Discovery & Management** - Search, extraction, favorites
2. **🗄️ Database & Session Management** - Virtual sessions, storage
3. **🧮 Math & Calculation Tools** - Scaling, arithmetic, comparisons
4. **🥗 CNF Nutrition Analysis** - Canadian Nutrient File integration
5. **⚡ Energy Requirements (EER)** - Health Canada energy calculations
6. **📊 Dietary Reference Intakes (DRI)** - Macronutrient recommendations

### FastMCP Integration

Tools are registered using the FastMCP framework:

```python
@mcp.tool()
def tool_name(parameter: str) -> Dict[str, Any]:
    """Tool description for AI assistants."""
    # Implementation
    return result
```

## 🧪 Testing Guidelines

### Local Testing

1. **CLI Testing**:
   ```bash
   python3 main.py
   # Test specific functionality interactively
   ```

2. **Claude Desktop Testing**:
   - Configure your local development server in Claude Desktop
   - Test tools with real queries
   - Verify nutrition calculations against known values

3. **Manual Verification**:
   - Use the <a href="https://docs.google.com/spreadsheets/d/1TELVtKLN35yxGFC10751WnByRtpWndYPjC4WKWw4Cgo/edit?usp=sharing" target="_blank">verification spreadsheet</a> for EER and CNF calculations
   - Test edge cases and error handling
   - Verify with different recipe types and ingredients

### Testing Checklist

- [ ] Tool functions execute without errors
- [ ] Return values match expected schema
- [ ] Error handling works for invalid inputs
- [ ] Performance is acceptable for bulk operations
- [ ] Database operations don't leak memory
- [ ] External API calls handle timeouts gracefully

## 🎯 Priority Contribution Areas

Based on the current development roadmap in [IMPLEMENTATIONS.MD](IMPLEMENTATIONS.MD):

### High Priority Improvements

- **Tool Efficiency**: Combine related tools to reduce LLM tool calls
  - Merge `calculate_recipe_nutrition_summary` and `query_recipe_macros_table`
  - Combine `store_recipe_in_temp_tables` and `simple_recipe_setup`

- **Code Organization**: Refactor large files
  - Break down `cnf_tools.py` (currently too large)
  - Extract helper functions into utility modules

- **Documentation**: Add architecture diagrams
  - Create Mermaid diagram showing data flow
  - Document tool interaction patterns

### Medium Priority Features

- **Installation Simplification**: Package management improvements
  - npm or Smithery installation packaging
  - Automated setup scripts

- **DRI Extension**: Expand nutritional analysis
  - Add support for micronutrients, vitamins, and minerals
  - Extend adequacy assessment tools

- **User Experience**: Enhanced recipe management
  - Allow users to store temporary recipe info permanently
  - Configurable recipe information storage duration

### New Feature Ideas

- **Recipe Planning**: Weekly meal planning tools
- **Inventory Management**: Track ingredients in stock
- **Nutritional Goals**: Personal nutrition target setting
- **Export Functionality**: Enhanced data export formats

## 📝 Submission Guidelines

### Pull Request Process

1. **Before submitting**:
   - Ensure your code follows the established patterns
   - Test thoroughly with both CLI and Claude Desktop
   - Update documentation if you've added new features
   - Check that existing functionality still works

2. **Pull Request Template**:
   ```markdown
   ## Description
   Brief description of changes and motivation

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update

   ## Testing
   - [ ] Tested with CLI
   - [ ] Tested with Claude Desktop
   - [ ] Verified nutrition calculations
   - [ ] Tested error handling

   ## Related Issues
   Closes #(issue number)
   ```

3. **Review Process**:
   - Maintainers will review your PR within a few days
   - Be responsive to feedback and suggestions
   - Update your PR based on review comments

### Documentation Updates

If your contribution adds new tools or changes existing functionality:
- Update relevant docstrings
- Add examples to the API Reference section in README.md
- Update IMPLEMENTATIONS.MD if you've addressed TODO items

## 🤝 Community Guidelines

### Code of Conduct

- **Be Respectful**: Treat all contributors with respect and kindness
- **Be Collaborative**: Work together to improve the project
- **Be Constructive**: Provide helpful feedback and suggestions
- **Be Patient**: Remember that everyone is learning and contributing their time

### Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions about the codebase or nutrition analysis
- **Pull Requests**: Get feedback on your contributions

### Communication

- Use clear, descriptive issue titles
- Provide detailed reproduction steps for bugs
- Include relevant Health Canada documentation links when discussing nutrition features
- Be specific about which tools or categories your contribution affects

---

<div align="center">
<p><strong>Thank you for contributing to Canada's Food Guide MCP Server!</strong></p>
<p>Your contributions help make nutrition analysis more accessible through AI assistants.</p>
<p>
<a href="https://food-guide.canada.ca/en/" target="_blank">🍲 Canada's Food Guide</a> •
<a href="https://food-nutrition.canada.ca/cnf-fce/?lang=eng" target="_blank">🥗 Canadian Nutrient File</a> •
<a href="https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables.html" target="_blank">📊 Dietary Reference Intakes</a>
</p>
</div>
