"""Tests for the DRI/EER page parsers and calculate_eer (offline fixtures).

The fixtures in tests/fixtures/dri_eer/ are hand-written minimal copies of the
canada.ca page markup shapes (table layout, details/summary blocks, NBSP,
en-dashes, Unicode ×, thousands separators). parse_eer_page / parse_dri_page
must reproduce the same values as the live-page build.
"""

from pathlib import Path

import pytest
from pages_fixture import FIXTURE_DIR as PAGES
from pages_fixture import truncate_html

from foodguide.builders.dri_eer import (
    DRI_URL,
    EER_URL,
    BuildError,
    build_dri,
    build_eer,
    calculate_eer,
    parse_dri_page,
    parse_eer_page,
)
from foodguide.recipes.fetch import CachedFetcher, cache_name

FIXTURES = Path(__file__).parent / "fixtures" / "dri_eer"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dri_payload() -> dict:
    return parse_dri_page(_fixture("dri_minimal.html"))


@pytest.fixture(scope="module")
def eer_payload() -> dict:
    return parse_eer_page(_fixture("eer_minimal.html"))


# --------------------------------------------------------------------------- DRI


def test_dri_reference_values_rows(dri_payload):
    rows = dri_payload["reference_values"]
    assert [row["category"] for row in rows] == ["Infants", "Males"]


def test_dri_nbsp_preserved_in_age_range(dri_payload):
    # The page renders age ranges with a non-breaking space ('0–6\xa0mo');
    # the parser preserves it verbatim so flexible age matching keeps working.
    assert dri_payload["reference_values"][0]["age_range"] == "0–6\xa0mo"
    assert dri_payload["reference_values"][1]["age_range"] == "19–30\xa0y"


def test_dri_nutrient_values(dri_payload):
    nutrients = dri_payload["reference_values"][0]["nutrients"]
    # Infants 0-6 mo: AI values carry the is_ai flag; EAR/UL stay None.
    protein = nutrients["protein"]
    assert protein["rda_ai_g_kg_day"] == 1.52
    assert protein["rda_ai_g_day"] == 9.1
    assert protein["ear_g_kg_day"] is None
    assert protein["ul_g_day"] is None
    assert protein["is_ai"] is True
    assert nutrients["carbohydrate"]["rda_ai_g_day"] == 60.0
    assert nutrients["total_fat"]["ai_g_day"] == 31.0
    assert nutrients["total_water"]["ai_litres_day"] == 0.7

    # Males 19-30 y: protein RDA is a bold RDA (not an AI), EAR 0.66 g/kg/day.
    male_protein = dri_payload["reference_values"][1]["nutrients"]["protein"]
    assert male_protein == {
        "ear_g_kg_day": 0.66,
        "rda_ai_g_kg_day": 0.8,
        "rda_ai_g_day": 56.0,
        "ul_g_day": None,
        "is_ai": False,
    }


def test_dri_other_sections(dri_payload):
    assert set(dri_payload["amino_acid_patterns"]) >= {"histidine", "lysine"}
    assert dri_payload["amino_acid_patterns"]["histidine"]["mg_per_g_protein"] == 18.0
    assert "19–30\xa0y" in dri_payload["amdrs"]
    assert dri_payload["amdrs"]["19–30\xa0y"]["carbohydrate_percent"] == "45–65%"
    assert set(dri_payload["footnotes"]) == {"fn_t1b1", "fn_t2b1"}
    assert "saturated_fatty_acids" in dri_payload["additional_recommendations"]


# --------------------------------------------------------------------------- EER


def test_eer_sections_present(eer_payload):
    equations = eer_payload["equations"]
    assert set(equations) == {
        "infant_toddler",
        "child_adolescent",
        "adult",
        "pregnancy",
        "lactation",
    }
    assert set(eer_payload["pal_category_definitions"]["age_groups"]) == {
        "3_to_9_years",
        "9_to_14_years",
        "14_to_19_years",
        "19_years_and_older",
    }
    assert set(eer_payload["pal_descriptions"]) == {
        "inactive",
        "low_active",
        "active",
        "very_active",
    }


def test_eer_adult_coefficients(eer_payload):
    inactive = eer_payload["equations"]["adult"]["male"]["inactive"]
    assert inactive["coefficients"] == {
        "intercept": 753.07,
        "age": -10.83,
        "height_cm": 6.5,
        "weight_kg": 14.1,
    }
    assert inactive["formula"] == (
        "EER = 753.07 + (-10.83 * age) + (6.50 * height_cm) + (14.10 * weight_kg)"
    )
    # Thousands separator on the live page ('1,004.82') parses to a float.
    active = eer_payload["equations"]["adult"]["male"]["active"]
    assert active["coefficients"]["intercept"] == 1004.82
    assert active["coefficients"] == {
        "intercept": 1004.82,
        "age": -10.83,
        "height_cm": 6.52,
        "weight_kg": 15.91,
    }


def test_eer_infant_growth_constants(eer_payload):
    male = eer_payload["equations"]["infant_toddler"]["male"]
    assert male["growth_constants"] == {
        "0_to_3_months": 200,
        "3_to_6_months": 50,
        "6_to_12_months": 20,
        "1_to_3_years": 20,
    }
    assert male["coefficients"] == {
        "intercept": -716.45,
        "age": -1.0,
        "height_cm": 17.82,
        "weight_kg": 15.06,
    }
    female = eer_payload["equations"]["infant_toddler"]["female"]
    assert female["growth_constants"] == {
        "0_to_3_months": 180,
        "3_to_6_months": 60,
        "6_to_12_months": 20,
        "1_to_3_years": 15,
    }


def test_eer_child_adolescent(eer_payload):
    child = eer_payload["equations"]["child_adolescent"]["male"]
    assert child["growth_constants"] == {
        "3_to_4_years": 20,
        "4_to_9_years": 15,
        "9_to_14_years": 25,
        "14_to_19_years": 20,
    }
    assert child["active"]["coefficients"] == {
        "intercept": -388.19,
        "age": 3.68,
        "height_cm": 12.66,
        "weight_kg": 20.46,
    }
    # Female formulas use the sign-inside rendering style.
    female_active = eer_payload["equations"]["child_adolescent"]["female"]["active"]
    assert female_active["coefficients"] == {
        "intercept": -189.55,
        "age": -22.25,
        "height_cm": 11.74,
        "weight_kg": 18.34,
    }
    assert "(-22.25 * age)" in female_active["formula"]


def test_eer_pregnancy(eer_payload):
    pregnancy = eer_payload["equations"]["pregnancy"]
    deposition = pregnancy["energy_deposition_by_bmi"]
    assert {key: value["kcal_per_day"] for key, value in deposition.items()} == {
        "underweight": 300,
        "normal_weight": 200,
        "overweight": 150,
        "obese": -50,
    }
    assert deposition["underweight"]["bmi_range"] == "< 18.5"
    assert deposition["normal_weight"]["bmi_range"] == "18.5 - 24.9"
    assert deposition["overweight"]["bmi_range"] == "25.0 - 29.9"
    assert deposition["obese"]["bmi_range"] == ">= 30.0"
    active = pregnancy["equations_by_pal"]["active"]
    assert active["coefficients"] == {
        "intercept": -223.84,
        "age": -2.04,
        "height_cm": 13.23,
        "weight_kg": 8.15,
        "gestation_weeks": 9.16,
    }
    assert "energy_deposition" in active["formula"]


def test_eer_lactation(eer_payload):
    lactation = eer_payload["equations"]["lactation"]
    milk = lactation["milk_energy_constants"]
    assert milk["0_to_6_months_postpartum"] == {
        "total_addition_kcal": 400,
        "breakdown": "540 (milk energy output) - 140 (weight loss allowance)",
    }
    assert milk["7_to_12_months_postpartum"] == {
        "total_addition_kcal": 380,
        "breakdown": "380 (milk energy output, no weight loss allowance)",
    }
    base = lactation["base_equations"]
    assert set(base) == {"age_under_19", "age_19_plus"}
    assert base["age_under_19"]["inactive"]["coefficients"] == {
        "intercept": 55.59,
        "age": -22.25,
        "height_cm": 8.43,
        "weight_kg": 17.07,
    }
    assert base["age_19_plus"]["active"]["coefficients"]["intercept"] == 710.25


# --------------------------------------------------------------------------- broken


def _broken_cache(tmp_path: Path, key: str, page_html: str) -> CachedFetcher:
    """A real CachedFetcher whose cache holds a broken copy of a real page.

    The builder's failure path is exercised through the production fetcher —
    no stub classes. The broken page is derived from the committed REAL page
    (tests/fixtures/pages) by truncation, not hand-written.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / cache_name(key)).write_text(truncate_html(page_html, 5000), encoding="utf-8")
    return CachedFetcher(cache, delay=0.0)


def test_broken_dri_raises_missing_table(tmp_path):
    real = (PAGES / "dri_macronutrients.html").read_text(encoding="utf-8")
    with pytest.raises(BuildError, match="missing table 'reference_values'"):
        build_dri(tmp_path / "dri.json", _broken_cache(tmp_path, DRI_URL, real))


def test_broken_eer_raises_missing_section(tmp_path):
    real = (PAGES / "eer_equations.html").read_text(encoding="utf-8")
    with pytest.raises(BuildError, match="missing section"):
        build_eer(tmp_path / "eer.json", _broken_cache(tmp_path, EER_URL, real))


# --------------------------------------------------------------------------- calculate_eer


def test_calculate_eer_adult_male_active(eer_payload):
    # 1004.82 - 10.83*30 + 6.52*175 + 15.91*70 = 1004.82 - 324.9 + 1141.0 + 1113.7
    #                                          = 2934.62 -> 2934.6
    result = calculate_eer(eer_payload, "male", 30, 70, 175, "active")
    assert result["eer_kcal"] == 2934.6
    assert result["section"] == "adult"
    assert result["pal"] == "active"
    assert result["growth_constant"] is None
    assert result["components"] == {
        "intercept": 1004.82,
        "age": -324.9,
        "height_cm": 1141.0,
        "weight_kg": 1113.7,
    }


def test_calculate_eer_adult_female_low_active(eer_payload):
    # 575.77 - 7.01*30 + 6.60*165 + 12.14*60 = 575.77 - 210.3 + 1089.0 + 728.4
    #                                        = 2182.87 -> 2182.9
    result = calculate_eer(eer_payload, "female", 30, 60, 165, "low_active")
    assert result["eer_kcal"] == 2182.9


def test_calculate_eer_child_male_active(eer_payload):
    # 9_to_14_years band, growth constant 25:
    # -388.19 + 3.68*10 + 12.66*140 + 20.46*35 + 25
    #   = -388.19 + 36.8 + 1772.4 + 716.1 + 25 = 2162.11 -> 2162.1
    result = calculate_eer(eer_payload, "male", 10, 35, 140, "active")
    assert result["section"] == "child_adolescent"
    assert result["growth_constant"] == 25
    assert result["eer_kcal"] == 2162.1


def test_calculate_eer_infant_male(eer_payload):
    # 6_to_12_months band (age 0.5 y = 6 months), growth constant 20:
    # -716.45 - 1.00*0.5 + 17.82*70 + 15.06*8 + 20
    #   = -716.45 - 0.5 + 1247.4 + 120.48 + 20 = 670.93 -> 670.9
    result = calculate_eer(eer_payload, "male", 0.5, 8, 70, "active")
    assert result["section"] == "infant_toddler"
    assert result["growth_constant"] == 20
    assert result["eer_kcal"] == 670.9


def test_calculate_eer_infant_growth_bands(eer_payload):
    # 0.2 y = 2.4 months -> 0_to_3_months (growth 200)
    result = calculate_eer(eer_payload, "male", 0.2, 5, 60, "active")
    assert result["growth_constant"] == 200
    # 0.6 y = 7.2 months -> 6_to_12_months (growth 20)
    assert calculate_eer(eer_payload, "male", 0.6, 6, 65, "active")["growth_constant"] == 20
    # 1.5 y = 18 months -> 1_to_3_years (growth 20)
    assert calculate_eer(eer_payload, "male", 1.5, 11, 80, "active")["growth_constant"] == 20
    # Band selection is exact at the boundaries: 3 months and 12 months.
    assert calculate_eer(eer_payload, "male", 0.25, 6, 65, "active")["growth_constant"] == 50
    assert calculate_eer(eer_payload, "male", 1.0, 9, 74, "active")["growth_constant"] == 20


def test_calculate_eer_child_bands(eer_payload):
    # 3.5 y -> 3_to_4_years (growth 20); 10 y -> 9_to_14_years (25);
    # 18 y -> 14_to_19_years (20); 3.0 y -> 3_to_4_years; 4.0 y -> 4_to_9_years (15).
    assert calculate_eer(eer_payload, "male", 3.5, 14, 98, "active")["growth_constant"] == 20
    assert calculate_eer(eer_payload, "male", 10, 35, 140, "active")["growth_constant"] == 25
    assert calculate_eer(eer_payload, "male", 18, 60, 175, "active")["growth_constant"] == 20
    assert calculate_eer(eer_payload, "male", 4.0, 16, 102, "active")["growth_constant"] == 15
    # Adults: >= 19 years, no growth constant.
    assert calculate_eer(eer_payload, "male", 19, 65, 176, "active")["growth_constant"] is None


def test_calculate_eer_sex_and_pal_aliases(eer_payload):
    male_active = calculate_eer(eer_payload, "male", 30, 70, 175, "active")
    assert calculate_eer(eer_payload, "M", 30, 70, 175, "active")["eer_kcal"] == male_active["eer_kcal"]
    assert calculate_eer(eer_payload, "F", 30, 70, 175, "active")["eer_kcal"] != male_active["eer_kcal"]
    assert calculate_eer(eer_payload, "female", 30, 60, 165, "Low active")["eer_kcal"] == 2182.9
    assert calculate_eer(eer_payload, "female", 30, 60, 165, "LOW_ACTIVE")["eer_kcal"] == 2182.9
    assert calculate_eer(eer_payload, "female", 30, 60, 165, "low-active")["pal"] == "low_active"


def test_calculate_eer_unknown_sex_and_pal(eer_payload):
    with pytest.raises(ValueError, match="Unknown sex"):
        calculate_eer(eer_payload, "unknown", 30, 70, 175, "active")
    with pytest.raises(ValueError, match="Unknown PAL category"):
        calculate_eer(eer_payload, "male", 30, 70, 175, "extreme")
    with pytest.raises(ValueError, match="Unknown sex"):
        calculate_eer(eer_payload, "", 30, 70, 175, "active")


def test_calculate_eer_accepts_bare_equations_dict(eer_payload):
    result = calculate_eer(eer_payload["equations"], "male", 30, 70, 175, "active")
    assert result["eer_kcal"] == 2934.6
