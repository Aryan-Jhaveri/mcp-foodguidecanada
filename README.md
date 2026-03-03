 # 🍲 <a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide - MCP Server</a>
 
<a href="https://www.python.org/downloads/" target="_blank"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
<a href="https://opensource.org/licenses/MIT" target="_blank"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
<a href="https://modelcontextprotocol.io/" target="_blank"><img src="https://img.shields.io/badge/MCP-ModelContextProtocol-green.svg" alt="MCP"></a>

## 📝 Description

The **FoodGuide MCP Server** bundles three powerful Health Canada resources into a single toolset for comprehensive nutritional analysis:

*   **Official Recipes:** Search and scrape the [Canada's Food Guide](https://food-guide.canada.ca/en/recipes/) recipe database.
*   **CNF Database:** Fetch exact nutrient data for ingredients from the [Canadian Nutrient File](https://produits-sante.canada.ca/api/documentation/cnf-documentation-en.html).
*   **DRI Calculations:** Use cached [Dietary Reference Intake](https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes.html) tables to calculate demographic-specific macronutrient targets and energy requirements (EER).



| Example  | Video |
| ------------- | ------------- |
| Find Themed recipes for a week  | <a href="https://youtu.be/CjWSxeWg-O0?t=223" target="_blank"> ![themed-recipe-spedup](https://github.com/user-attachments/assets/284795c7-17df-4715-a7b2-98a7c6b1241a) </a>|
| Suggest recipes from an image of your groceries  | <a href="https://youtu.be/CjWSxeWg-O0?t=307" target="_blank"> ![from-image-to-show-recipes-spedup](https://github.com/user-attachments/assets/75bc1976-2a3c-4b5e-b1cd-45006b190b5b) </a> |
| Calculate your estimated macros intake and energy requirements | <a href="https://youtu.be/CjWSxeWg-O0?t=40" target="_blank"> ![calculate-eer-spedup](https://github.com/user-attachments/assets/ba30be42-e4d0-4d86-a379-35fe51cdeb40) </a> |
| Calculate Macros for a recipe | <a href ="https://youtu.be/CjWSxeWg-O0?t=116" target="_blank">![calculate-macros-spedup](https://github.com/user-attachments/assets/c7912d00-773f-4781-959b-56d0b8d86727) </a> |

#### Two setup modes:

| Mode | Tools available | DB/Storage? | Best for |
|---|---|---|---|
| **HTTP** (remote/self-hosted) | Scraping + calculation tools (24 tools) | No | Most users -- nutrition lookups, recipe search, EER/DRI calculations |
| **stdio** (full) | All tools incl. SQLite (46 tools) | Yes | Power users -- recipe macro analysis, favorites, user profiles |

Check **IMPLEMENTATIONS.MD** if you'd like to contribute or collaborate! Always looking for suggestions!

You can use this <a href="https://docs.google.com/spreadsheets/d/1TELVtKLN35yxGFC10751WnByRtpWndYPjC4WKWw4Cgo/edit?usp=sharing" target="_blank">**google sheet**</a> to verify EER and CNF calculations shown in the trailer videos in the current repository. 



## 📑 Table of Contents

- [📝 Description](#-description)
- [📥 Installation](#-installation)
- [🚀 Setup by Client](#-setup-by-client)


## 📥 Installation

Click the image to watch the setup tutorial!
[![Watch the setup tutorial](https://img.youtube.com/vi/FWH9_HMKwro/maxresdefault.jpg)](https://youtu.be/FWH9_HMKwro)

1. **Prerequisites**:
   - <a href="https://www.python.org/#:~:text=Download" target="_blank">Python 3.10 or higher</a>
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

4. **Find your Python path** (needed for client config):
   ```bash
   which python3
   ```

5. **Get the absolute path to the project**:
   ```bash
   pwd
   ```

### HTTP mode -- scraping + calculation, no DB (24 tools)

Start the server in a terminal and leave it running:

```bash
python3 src/server.py --transport http --port 8000
# Server running at http://0.0.0.0:8000/mcp
```

Then configure your client to connect to `http://localhost:8000/mcp` -- see [Setup by Client](#-setup-by-client) below.

### Full mode -- all tools incl. SQLite (46 tools)

Run via stdio -- no separate server process needed. Configure your client with the stdio snippets in [Setup by Client](#-setup-by-client).

---

## 🚀 Setup by Client

| Mode | DB tools? | Tools available |
|---|---|---|
| **HTTP** (start server first) | No | Scraping + calculation (24 tools) |
| **stdio** (full) | Yes | All tools incl. SQLite (46 tools) |

---

### HTTP mode -- scraping + calculation (no DB)

> **Before configuring your client:** start the server in a separate terminal:
> ```bash
> python3 src/server.py --transport http --port 8000
> ```
> Keep it running while using your client.

Most clients use <a href="https://github.com/sparfenyuk/mcp-proxy" target="_blank">`mcp-proxy`</a> to bridge stdio to HTTP. Claude Code connects natively.

**Claude Desktop**

Navigate to: Claude Desktop → Settings (⌘,) → Developer → Edit Config

```json
{
  "mcpServers": {
    "FoodGuideSousChef": {
      "command": "uvx",
      "args": ["mcp-proxy", "--transport", "streamablehttp", "http://localhost:8000/mcp"]
    }
  }
}
```

Restart Claude Desktop after saving.

**Claude Code**

```bash
claude mcp add FoodGuideSousChef --transport http http://localhost:8000/mcp
```

**Cursor**

In `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "FoodGuideSousChef": {
      "command": "uvx",
      "args": ["mcp-proxy", "--transport", "streamablehttp", "http://localhost:8000/mcp"]
    }
  }
}
```

**VS Code (GitHub Copilot)**

In `.vscode/mcp.json`:

```json
{
  "servers": {
    "FoodGuideSousChef": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-proxy", "--transport", "streamablehttp", "http://localhost:8000/mcp"]
    }
  }
}
```

---

### Full mode -- all tools incl. SQLite DB

No separate server process needed. The client launches the server directly via stdio.

Replace `<python-path>` and `<project-path>` with your actual paths from the [Installation](#-installation) steps.

**Common Python paths by system**:
- **Homebrew (Mac)**: `/opt/homebrew/bin/python3`
- **System Python (Mac)**: `/usr/bin/python3`
- **Anaconda**: `/opt/anaconda3/bin/python3`
- **Linux**: `/usr/bin/python3`

**Claude Desktop**

Navigate to: Claude Desktop → Settings (⌘,) → Developer → Edit Config

```json
{
  "mcpServers": {
    "FoodGuideSousChef": {
      "command": "<python-path>",
      "args": ["<project-path>/src/server.py"],
      "cwd": "<project-path>"
    }
  }
}
```

Restart Claude Desktop after saving.

**Claude Code**

```bash
claude mcp add FoodGuideSousChef -- <python-path> <project-path>/src/server.py
```

**Cursor**

In `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "FoodGuideSousChef": {
      "command": "<python-path>",
      "args": ["<project-path>/src/server.py"],
      "cwd": "<project-path>"
    }
  }
}
```

**VS Code (GitHub Copilot)**

In `.vscode/mcp.json`:

```json
{
  "servers": {
    "FoodGuideSousChef": {
      "type": "stdio",
      "command": "<python-path>",
      "args": ["<project-path>/src/server.py"],
      "cwd": "<project-path>"
    }
  }
}
```

---

### Optional flags

```bash
# HTTP mode with custom port
python3 src/server.py --transport http --port 9000 --host 0.0.0.0

# Environment variable alternative (for deployment)
MCP_TRANSPORT=http PORT=8000 python3 src/server.py
```

### Troubleshooting
- If the server doesn't appear, check the Claude Desktop logs for error messages
- Verify Python 3.10+ is installed: `python3 --version`
- For HTTP mode, verify the server is running: `curl http://localhost:8000/mcp/`



---

<div align="center">
<p>Made with ❤️ for Canada's Food Guide</p>
<p><a href="https://food-guide.canada.ca/en/" target="_blank">Canada's Food Guide</a></p>
<p><a href="https://food-nutrition.canada.ca/cnf-fce/?lang=eng" target="_blank">Health Canada's Canadian Nutrient File</a></p>
<p><a href="https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables.html" target="_blank">Health Canada's Dietary Reference Intakes</a></p>
Built using <a href="https://github.com/jlowin/fastmcp" target="_blank">FastMCP</a>
</p>
</div>
