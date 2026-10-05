import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prepare_data import (  # noqa: E402
    build_districts,
    build_practice_layer,
    match_districts,
    norm,
    practice_label,
    read_emissions,
    read_food_security,
    read_irrigation_sheet,
    read_water_balance,
    slug,
    summarise_irrigation,
)


def _tehsils():
    return gpd.GeoDataFrame(
        {
            "ADM3_EN": ["Lahore City", "Lahore Cantt", "Attock", "Thatta", "Peshawar"],
            "ADM2_EN": ["Lahore", "Lahore", "Attock", "Thatta", "Peshawar"],
            "ADM1_EN": ["Punjab", "Punjab", "Punjab", "Sindh", "Khyber Pakhtunkhwa"],
            "Irr_Rec": ["Drip, SP", "SP", "NA", "AWD, Drip, SP", "FI"],
        },
        geometry=[
            box(74, 31, 74.5, 31.5),
            box(74.5, 31, 75, 31.5),
            box(72, 33, 73, 34),
            box(67, 24, 68, 25),
            box(71, 33.5, 72, 34.5),
        ],
        crs="EPSG:4326",
    )


def _district_map():
    """A small stand-in for the main district map file."""
    return gpd.GeoDataFrame(
        {
            "Districts": ["Lahore", "Attock ", "Kot Addu", "Thatta", "Peshawar", "Indian Illegally Occupied Jammu Kashmir"],
            "province": ["Punjab", "Punjab", "PUNJAB", "Sindh", "Khyber Pakhtunkhwa", "Indian_Illegally_Occupied_Jammu_Kashmir"],
            "Population": [100.0, 50.0, 25.0, 80.0, 60.0, 40.0],
        },
        geometry=[
            box(74, 31, 75, 31.5),
            box(72, 33, 73, 34),
            box(70, 30, 71, 31),
            box(67, 24, 68, 25),
            box(71, 33.5, 72, 34.5),
            box(74, 32, 79.3, 35.5),
        ],
        crs="EPSG:4326",
    )


def test_build_districts_reads_provinces_and_districts_from_the_district_map():
    provinces, districts = build_districts(_district_map(), tolerance=0)

    assert list(provinces["id"]) == ["p-jammu-and-kashmir", "p-khyber-pakhtunkhwa", "p-punjab", "p-sindh"]
    assert list(provinces["parent_id"]) == ["PK"] * 4
    assert len(districts) == 6
    lahore = districts[districts["name"] == "Lahore"].iloc[0]
    assert (lahore["id"], lahore["parent_id"]) == ("d-punjab-lahore", "p-punjab")
    assert lahore.geometry.bounds == (74, 31, 75, 31.5)
    assert districts["id"].is_unique


def test_build_districts_merges_differently_cased_province_names():
    provinces, districts = build_districts(_district_map(), tolerance=0)
    assert list(provinces["name"]).count("Punjab") == 1
    kot_addu = districts[districts["name"] == "Kot Addu"].iloc[0]
    assert kot_addu["parent_id"] == "p-punjab"
    punjab = provinces[provinces["id"] == "p-punjab"].iloc[0]
    assert punjab.geometry.bounds == (70, 30, 75, 34)
    assert districts[districts["id"] == "d-punjab-attock"].iloc[0]["name"] == "Attock"


def test_build_districts_includes_the_kashmir_region_under_its_display_name():
    provinces, districts = build_districts(_district_map(), tolerance=0)
    region = provinces[provinces["id"] == "p-jammu-and-kashmir"].iloc[0]
    assert region["name"] == "Jammu and Kashmir"
    assert region.geometry.bounds == (74, 32, 79.3, 35.5)
    district = districts[districts["parent_id"] == "p-jammu-and-kashmir"].iloc[0]
    assert district["name"] == "Jammu and Kashmir"
    assert district["id"] == "d-jammu-and-kashmir-jammu-and-kashmir"


def test_build_districts_reports_missing_columns():
    frame = _district_map().rename(columns={"Districts": "Name"})
    with pytest.raises(ValueError, match="Districts"):
        build_districts(frame, tolerance=0)


def test_build_districts_rejects_two_districts_with_one_name_in_a_province():
    frame = _district_map()
    frame.loc[1, "Districts"] = "Lahore"
    with pytest.raises(ValueError, match="Lahore"):
        build_districts(frame, tolerance=0)


def test_practice_layer_keeps_each_tehsil_with_its_recommended_practice():
    tehsils = build_practice_layer(_tehsils(), tolerance=0)
    assert list(tehsils.columns) == ["id", "name", "practice", "label", "geometry"]
    city = tehsils[tehsils["name"] == "Lahore City"].iloc[0]
    assert city["practice"] == "Drip, SP"
    assert city["label"] == "Recommended practice: Drip, Sprinkler"
    attock = tehsils[tehsils["name"] == "Attock"].iloc[0]
    assert attock["practice"] is None
    assert attock["label"] == "Recommended practice: No recommendation"
    assert tehsils["id"].is_unique


def test_practice_layer_keeps_ids_unique_when_names_repeat():
    frame = _tehsils()
    frame.loc[1, "ADM3_EN"] = "Lahore City"
    tehsils = build_practice_layer(frame, tolerance=0)
    assert tehsils["id"].is_unique
    assert len(tehsils) == 5


def test_norm_and_slug():
    assert norm(" D.I. Khan ") == "dikhan"
    assert norm("Dera-Ismail  Khan") == "deraismailkhan"
    assert slug("Khyber Pakhtunkhwa") == "khyber-pakhtunkhwa"
    assert slug(" D.I. Khan ") == "d-i-khan"


def test_practice_label_spells_out_codes():
    assert practice_label("AWD, Drip, SP") == "Alternate wetting and drying, Drip, Sprinkler"
    assert practice_label("FI") == "Flood irrigation"
    assert practice_label("NA") == "No recommendation"
    assert practice_label(None) == "No recommendation"
    assert practice_label("Mystery") == "Mystery"





def _sheet_file(tmp_path):
    rows = [
        ["District", "Province", "Area equipped for irrigation (ha) Infrastrucher", None, None, "Area actually irrigated (ha)", None],
        [None, None, "Total Equiped (ha)", "with groundwater (ha)", "with surface water (ha)", None, "a stray note"],
        ["Lahore", "Punjab", 1000, 400, 600, 800, None],
        ["Attok", "Punjab", 500, 100, 400, None, None],
        [None, None, None, None, None, None, "another note"],
        ["Thatta", "Sindh", 2000, 0, 2000, 1000, None],
        ["Peshawar", "KPK", 300, 300, 0, 150, None],
        ["Nowhere", "Sindh ", 50, 10, 40, 25, None],
        ["Pakistan total", None, 3850, 810, 3040, 1975, None],
    ]
    path = tmp_path / "irrigation.xlsx"
    pd.DataFrame(rows).to_excel(path, sheet_name="Irrigation System of Pakistan", header=False, index=False)
    return path


def test_read_irrigation_sheet_keeps_only_district_rows(tmp_path):
    sheet = read_irrigation_sheet(_sheet_file(tmp_path))
    assert list(sheet["district"]) == ["Lahore", "Attok", "Thatta", "Peshawar", "Nowhere"]
    assert list(sheet["province"]) == ["Punjab", "Punjab", "Sindh", "Khyber Pakhtunkhwa", "Sindh"]
    assert list(sheet["equipped"]) == [1000, 500, 2000, 300, 50]
    assert pd.isna(sheet["irrigated"].iloc[1])
    assert sheet["groundwater"].iloc[3] == 300


def test_match_districts_uses_spelling_pairs_and_reports_the_rest(tmp_path):
    sheet = read_irrigation_sheet(_sheet_file(tmp_path))
    _, districts = build_districts(_district_map(), tolerance=0)
    matches, unmatched = match_districts(sheet, districts, {"attok": "Attock"})
    assert matches == {
        0: "d-punjab-lahore",
        1: "d-punjab-attock",
        2: "d-sindh-thatta",
        3: "d-khyber-pakhtunkhwa-peshawar",
    }
    assert unmatched == ["Nowhere (Sindh)"]


def test_match_districts_without_pairs_leaves_misspellings_unmatched(tmp_path):
    sheet = read_irrigation_sheet(_sheet_file(tmp_path))
    _, districts = build_districts(_district_map(), tolerance=0)
    _, unmatched = match_districts(sheet, districts, {})
    assert unmatched == ["Attok (Punjab)", "Nowhere (Sindh)"]


def test_summarise_irrigation_totals_by_district_province_and_country(tmp_path):
    sheet = read_irrigation_sheet(_sheet_file(tmp_path))
    provinces, districts = build_districts(_district_map(), tolerance=0)
    matches, unmatched = match_districts(sheet, districts, {"attok": "Attock"})
    summary = summarise_irrigation(sheet, matches, unmatched, provinces, districts)
    places = summary["places"]

    assert places["d-punjab-lahore"] == {
        "name": "Lahore", "level": "district", "parent_id": "p-punjab",
        "equipped": 1000, "groundwater": 400, "surface": 600, "irrigated": 800, "districts_reported": 1,
    }
    assert places["d-punjab-attock"]["irrigated"] is None
    # Province and country totals count every spreadsheet row, matched to the map or not.
    assert places["p-punjab"]["equipped"] == 1500
    assert places["p-punjab"]["irrigated"] == 800
    assert places["p-punjab"]["districts_reported"] == 2
    assert places["p-sindh"]["equipped"] == 2050
    assert places["p-sindh"]["districts_reported"] == 2
    assert places["PK"]["equipped"] == 3850
    assert places["PK"]["districts_reported"] == 5
    assert places["PK"]["name"] == "Pakistan"
    assert summary["unmatched"] == ["Nowhere (Sindh)"]


def test_read_emissions(tmp_path):
    path = tmp_path / "ghg.xlsx"
    frame = pd.DataFrame(
        {
            "Year": [1994, 1995],
            "CO2 (MtCO2e)": [94.57, 99.88],
            "CH4 (MtCO2e)": [72.27, 75.84],
            "N2O (MtCO2e)": [11.0, 12.52],
            "Total GHG (MtCO2e)": [177.84, 188.24],
            "Data Status": ["Official reported inventory", "Interpolated between official inventory years"],
            "stray": [None, None],
        }
    )
    meta = pd.DataFrame({"Item": ["Official source", "Unit"], "Details": ["NC3, UNFCCC, 2025", "MtCO2e = million tonnes"]})
    with pd.ExcelWriter(path) as writer:
        frame.to_excel(writer, sheet_name="GHG_1994_2021", index=False)
        meta.to_excel(writer, sheet_name="Metadata", index=False)
    data = read_emissions(path)
    assert data["years"] == [1994, 1995]
    assert data["co2"] == [94.57, 99.88]
    assert data["total"] == [177.84, 188.24]
    assert data["official"] == [True, False]
    assert data["unit"] == "MtCO2e"
    assert data["source"] == "NC3, UNFCCC, 2025"


def test_read_water_balance(tmp_path):
    path = tmp_path / "cwr.xlsx"
    pd.DataFrame(
        {"year": [2026, 2027], "WAv": [109.0, 109.1], "CWR(35%)": [132.0, 133.0], "CWR(50%)": [92.4, 93.1], "CWR(70%)": [66.0, 66.5]}
    ).to_excel(path, index=False)
    data = read_water_balance(path)
    assert data == {
        "years": [2026, 2027],
        "availability": [109.0, 109.1],
        "requirement": {"35": [132.0, 133.0], "50": [92.4, 93.1], "70": [66.0, 66.5]},
    }


def test_read_food_security(tmp_path):
    path = tmp_path / "food.xlsx"
    frame = pd.DataFrame(
        {
            "Year": [2026, 2027],
            "food Demand": [92.79, 95.85],
            "CSA Availability": [82.86, 83.27],
            "Pop": [254.71, 259.8],
            "CSA Food Gap": [9.94, 12.58],
            "Traditional Avl": [82.86, 79.81],
            "Traditional food gap": [9.94, 16.05],
        }
    )
    with pd.ExcelWriter(path) as writer:
        frame.to_excel(writer, sheet_name="csa", index=False)
    data = read_food_security(path)
    assert data["years"] == [2026, 2027]
    assert data["demand"] == [92.79, 95.85]
    assert data["csa_availability"] == [82.86, 83.27]
    assert data["traditional_availability"] == [82.86, 79.81]
    assert data["csa_gap"] == [9.94, 12.58]
    assert data["traditional_gap"] == [9.94, 16.05]
    assert data["population"] == [254.71, 259.8]


def test_missing_column_is_reported_by_name(tmp_path):
    path = tmp_path / "cwr.xlsx"
    pd.DataFrame({"year": [2026], "WAv": [109.0]}).to_excel(path, index=False)
    with pytest.raises(ValueError, match="CWR"):
        read_water_balance(path)
