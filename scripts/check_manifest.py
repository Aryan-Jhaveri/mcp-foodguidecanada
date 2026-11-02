"""Sanity-check a freshly built manifest before it is published.

Usage: check_manifest.py NEW_MANIFEST [PREVIOUS_MANIFEST]

Fails (exit 1) when a dataset is missing, is implausibly small, or shrank by more than 10%
compared with the previous release. This stops a broken scrape (for example after Health
Canada redesigns a page) from replacing good data.
"""
import json
import sys

MINIMUM = {"foods": 5000, "nutrient_amounts": 500_000, "recipes": 100}
REQUIRED = ["cnf.sqlite", "recipes.json", "dri_macronutrients.json", "eer_equations.json"]


def counts(manifest):
    out = {}
    for entry in manifest.get("files", []):
        for key, value in (entry.get("counts") or {}).items():
            out[key] = value
    return out


def main():
    new = json.load(open(sys.argv[1]))
    names = {f["name"] for f in new.get("files", [])}
    problems = [f"missing dataset: {n}" for n in REQUIRED if n not in names]
    new_counts = counts(new)
    for key, floor in MINIMUM.items():
        if new_counts.get(key, 0) < floor:
            problems.append(f"{key}: {new_counts.get(key)} is below the floor {floor}")
    if len(sys.argv) > 2:
        old_counts = counts(json.load(open(sys.argv[2])))
        for key, old in old_counts.items():
            if isinstance(old, int) and old > 0 and new_counts.get(key, 0) < old * 0.9:
                problems.append(f"{key}: dropped from {old} to {new_counts.get(key)} (more than 10%)")
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print("manifest looks sane:", new_counts)


main()
