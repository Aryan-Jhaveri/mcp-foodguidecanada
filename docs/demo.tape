# Records docs/demo.gif. Run from the repo root: vhs docs/demo.tape
# Expects the datasets in /tmp/fg-demo (foodguide data fetch --dest /tmp/fg-demo).
Output docs/demo.gif
Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 760
Set Padding 16
Set TypingSpeed 40ms
Set Theme "Catppuccin Mocha"

Hide
Type "source .venv/bin/activate && export FOODGUIDE_DATA_DIR=/tmp/fg-demo PS1='$ ' COLUMNS=110" Enter
Type "clear" Enter
Show

Type "# foodguide: Canada's Food Guide data as a CLI (and an MCP server)" Enter
Sleep 800ms
Type "foodguide --help | head -22" Enter
Sleep 3s

Type "clear" Enter
Type "# Canadian Nutrient File 2026, offline" Enter
Type "foodguide data status | head -12" Enter
Sleep 2500ms
Type "foodguide cnf search lentille --lang fr --limit 4" Enter
Sleep 2500ms
Type "foodguide cnf nutrients 3393 --per 100g --nutrient PROT --nutrient KCAL" Enter
Sleep 3s

Type "clear" Enter
Type "# Recipes from the Food Guide kitchen" Enter
Type "foodguide recipes search --tag collection__vegetarian --tag meal__breakfast --limit 4 | cut -c1-66" Enter
Sleep 3s
Type "foodguide recipes show apple-berry-crisp | head -24" Enter
Sleep 4s

Type "clear" Enter
Type "# Energy needs from Health Canada's EER equations" Enter
Type "foodguide eer calc --sex female --age 34 --weight-kg 62 --height-cm 168 --pal active" Enter
Sleep 3s
Type "foodguide dri lookup --age-range '19-30 y' --nutrient protein" Enter
Sleep 4s
