# Real canada.ca pages saved as test fixtures

Copies of the live Health Canada pages, fetched on 2026-11-02 with:

    curl -A "foodguide-data-build/0.1 (+https://github.com/Aryan-Jhaveri/mcp-foodguidecanada)" \
         -H "Accept: */*" <url>

They are served by the `pages_server` pytest fixture (tests/conftest.py) from a
real `http.server` on 127.0.0.1 so the builders and CLI can be exercised
end-to-end with the real fetch/parse/validate code and no network access.

| Fixture | URL |
|---|---|
| dri_macronutrients.html | https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/reference-values-macronutrients.html |
| eer_equations.html | https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/dietary-reference-intakes/tables/equations-estimate-energy-requirement.html |
| recipes_index.html | https://www.canada.ca/en/health-canada/services/food-guide/eating-support/kitchen/recipes.html |
| recipes/&lt;slug&gt;.html | https://www.canada.ca/en/health-canada/services/food-guide/eating-support/kitchen/recipes/&lt;slug&gt;.html |

The 12 recipe pages are the 8 recipes sampled in
`tests/fixtures/golden_recipes.json` plus 4 more, so the fixture set contains a
page with two ingredient groups (baked-fish-chips) and one with three
(black-bean-enchiladas). If a fixture goes stale (upstream page changed, the
DRI/EER validators reject it, or a golden comparison fails), re-fetch the page
with the command above and re-run the suite.

canada.ca serves a dynamic analytics script, so raw-page sha256 values differ
between fetches; the builders strip script/style blocks before hashing, so
`page_sha256` in built payloads is stable (see tests/test_recipes_parser.py).
