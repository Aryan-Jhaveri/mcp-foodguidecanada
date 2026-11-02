"""Sanity-check a freshly built manifest before it is published.

Usage: check_manifest.py NEW_MANIFEST [PREVIOUS_MANIFEST]

Fails (exit 1) when a dataset is missing, is implausibly small, or shrank by more than 10%
compared with the previous release. This stops a broken scrape (for example after Health
Canada redesigns a page) from replacing good data.
"""
import json
import sys

REQUIRED = ["cnf.sqlite", "cnf.sqlite.gz", "recipes.json", "dri_macronutrients.json", "eer_equations.json"]
# (dataset, key inside record_counts or "record_count", minimum)
FLOORS = [
    ("cnf.sqlite", "food", 5000),
    ("cnf.sqlite", "nutrient_amount", 500_000),
    ("recipes.json", "record_count", 100),
    ("dri_macronutrients.json", "record_count", 5),
    ("eer_equations.json", "record_count", 3),
]


def count(manifest, dataset, key):
    entry = manifest.get("datasets", {}).get(dataset, {})
    if key == "record_count":
        return entry.get("record_count")
    return (entry.get("record_counts") or {}).get(key)


def main():
    new = json.load(open(sys.argv[1]))
    old = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None
    problems = [f"missing dataset: {n}" for n in REQUIRED if n not in new.get("datasets", {})]
    for dataset, key, floor in FLOORS:
        value = count(new, dataset, key)
        if value is None or value < floor:
            problems.append(f"{dataset} {key}: {value} is below the floor {floor}")
        if old is not None:
            before = count(old, dataset, key)
            if before and value is not None and value < before * 0.9:
                problems.append(f"{dataset} {key}: dropped from {before} to {value} (more than 10%)")
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print("manifest looks sane:", {f"{d}.{k}": count(new, d, k) for d, k, _ in FLOORS})


main()
