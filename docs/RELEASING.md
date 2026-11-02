# Releasing

The package is published to PyPI as **`foodguidecanada`** (the import name and the commands stay
`foodguide` and `foodguide-mcp`). The name leaves room for more Health Canada data later.

## One-time setup (PyPI trusted publishing, no token)

1. Create the project's publisher on pypi.org: *Your projects → Publishing → Add a pending publisher*.
   - PyPI project name: `foodguidecanada`
   - Owner: `Aryan-Jhaveri`, repository: `mcp-foodguidecanada`
   - Workflow name: `release.yml`, environment name: `pypi`
2. In the GitHub repo, *Settings → Environments → New environment* named `pypi` (optionally require
   your approval for it).

## Each release

1. Update `version` in `pyproject.toml` (and `src/foodguide/__init__.py`, `src/foodguide/cli.py`
   fallbacks) and add a `## X.Y.Z (date)` section to `CHANGELOG.md`.
2. Merge to `main`. The tests must be green.
3. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. The `Release` workflow checks that the tag matches the version, runs lint and tests, builds the
   wheel and sdist, creates the GitHub release (notes come from `CHANGELOG.md`) and publishes to PyPI.

Datasets are separate from releases: the weekly `Data refresh` workflow publishes them to the
`data-latest` release. After a release, `pip install foodguidecanada` and `foodguide data fetch` give
a working install.
