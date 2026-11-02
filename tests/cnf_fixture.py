"""Tiny deterministic mini-zip fixture that mirrors the CNF 2026 CSV layout.

Used by the offline CNF unit tests: same 9 file names, same headers, UTF-8 BOM,
just a handful of rows so builds are fast and assertions are easy.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

_FOOD_NAME_HEADER = [
    "Food_Code", "Food_Description_EN", "Food_Description_FR",
    "Alternate_Description_EN", "Alternate_Description_FR", "Food_Source_Code",
    "USDA_NDB_Code", "CNF_Food_Group_Code", "Comment_EN", "Comment_FR",
    "ScientificName", "Food_Last_Updated_Date",
]
_FOOD_NAME_ROWS = [
    ["100", "Red lentils, cooked", "Lentilles rouges, cuites", "", "", "20", "16069", "10", "", "", "Lens culinaris", "2020-01-01"],
    ["101", "White bread", "Pain blanc", "loaf", "miche", "20", "", "2", "", "", "Triticum", "2020-01-01"],
    ["102", "Boiled lentils", "Lentilles bouillies", "", "", "20", "", "10", "", "", "Lens culinaris", "2020-01-01"],
]

_FOOD_GROUP_HEADER = ["CNF_Food_Group_Code", "CNF_Food_Group_Description_EN", "CNF_Food_Group_Description_FR"]
_FOOD_GROUP_ROWS = [
    ["10", "Vegetables and vegetable products", "Légumes et produits végétaux"],
    ["2", "Baked goods", "Produits de boulangerie"],
]

_FOOD_SOURCE_HEADER = ["Food_Source_Code", "Food_Source_Description_EN", "Food_Source_Description_FR"]
_FOOD_SOURCE_ROWS = [["20", "Health Canada", "Santé Canada"]]

_NUTRIENT_NAME_HEADER = [
    "Nutrient_Code", "Nutrient_Symbol", "Nutrient_Unit",
    "Nutrient_Name_EN", "Nutrient_Name_FR", "Tagname", "Nutrient_Decimals",
]
_NUTRIENT_NAME_ROWS = [
    ["203", "PROT", "Gram", "Protein", "Protéines", "PROCNT", "2"],
    ["208", "KCAL", "kilocalorie", "Energy (kilocalories)", "Énergie", "", "0"],
    ["301", "CA", "Milligram", "Calcium", "Calcium", "CA", "2"],
]

_NUTRIENT_AMOUNT_HEADER = [
    "Food_Code", "Nutrient_Code", "Nutrient_Amount", "STD_Error", "Observations",
    "Nutrient_Source_Code", "Nutrient_Last_Updated_Date",
]
_NUTRIENT_AMOUNT_ROWS = [
    ["100", "203", "9.020000000", "0.150000000", "5", "51", "2020-01-01"],
    ["100", "208", "116.000000000", "", "", "51", "2020-01-01"],
    ["100", "301", "20.000000000", "", "", "51", "2020-01-01"],
    ["101", "203", "8.500000000", "", "", "51", "2020-01-01"],
    ["101", "208", "265.000000000", "", "", "51", "2020-01-01"],
    ["102", "203", "9.100000000", "", "", "51", "2020-01-01"],
    ["102", "208", "118.000000000", "", "", "51", "2020-01-01"],
    ["102", "301", "20.000000000", "", "", "", "2020-01-01"],
]

_MEASURE_NAME_HEADER = ["Measure_Code", "Measure_Description_and_Unit_EN", "Measure_Description_and_Unit_FR"]
_MEASURE_NAME_ROWS = [
    ["1", "100 g", "100 g"],
    ["2", "1 cup", "1 tasse"],
    ["3", "1 tbsp", "1 c. à soupe"],
]

_MEASURE_TYPE_HEADER = ["Measure_Type_Code", "Measure_Type_Description_EN", "Measure_Type_Description_FR"]
_MEASURE_TYPE_ROWS = [["1", "Household", "Ménager"]]

_MEASURE_WEIGHT_HEADER = [
    "Food_Code", "Measure_Type_Code", "Measure_Code",
    "Measure_Weight_Conversion", "Measure_Weight_Conversion_Last_Updated_Date",
]
_MEASURE_WEIGHT_ROWS = [
    ["100", "1", "1", "100", "2020-01-01"],
    ["100", "1", "2", "198", "2020-01-01"],
    ["100", "1", "3", "13.5", "2020-01-01"],
    ["101", "1", "2", "30", "2020-01-01"],
    ["102", "1", "1", "100", "2020-01-01"],
]

_NUTRIENT_SOURCE_HEADER = ["Nutrient_Source_Code", "Nutrient_Source_Description_EN", "Nutrient_Source_Description_FR"]
_NUTRIENT_SOURCE_ROWS = [["51", "Proximate", "Proximité"]]

_FILES: list[tuple[str, list[str], list[list[str]]]] = [
    ("Food_Name.csv", _FOOD_NAME_HEADER, _FOOD_NAME_ROWS),
    ("CNF_Food_Group.csv", _FOOD_GROUP_HEADER, _FOOD_GROUP_ROWS),
    ("Food_Source.csv", _FOOD_SOURCE_HEADER, _FOOD_SOURCE_ROWS),
    ("Nutrient_Name.csv", _NUTRIENT_NAME_HEADER, _NUTRIENT_NAME_ROWS),
    ("Nutrient_Amount.csv", _NUTRIENT_AMOUNT_HEADER, _NUTRIENT_AMOUNT_ROWS),
    ("Measure_Name.csv", _MEASURE_NAME_HEADER, _MEASURE_NAME_ROWS),
    ("Measure_Type.csv", _MEASURE_TYPE_HEADER, _MEASURE_TYPE_ROWS),
    ("Measure_Weight_Conversion.csv", _MEASURE_WEIGHT_HEADER, _MEASURE_WEIGHT_ROWS),
    ("Nutrient_Source.csv", _NUTRIENT_SOURCE_HEADER, _NUTRIENT_SOURCE_ROWS),
]


def _csv_text(header: list[str], rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def make_mini_zip(path: Path) -> Path:
    """Write the mini CNF zip to `path` (UTF-8 BOM, like the real data) and return it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, header, rows in _FILES:
            # Write with a UTF-8 BOM, matching the real CNF files.
            zf.writestr(name, _csv_text(header, rows).encode("utf-8-sig"))
    return path
