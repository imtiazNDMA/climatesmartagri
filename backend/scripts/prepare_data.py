"""Turn the project's source spreadsheets and map file into the small files the portal serves.

Run from the repo root:
    uv run python backend/scripts/prepare_data.py

Reads from data/ (never changes it) and writes backend/boundaries/ and backend/data/.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import shapely

REPO = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO / "data"
BOUNDARIES_OUT = REPO / "backend" / "boundaries"
DATA_OUT = REPO / "backend" / "data"

TEHSILS_FILE = SOURCE / "geospatial" / "vectors" / "Irr_Prac.shp"
# The main map: districts and provinces, including the Kashmir region.
DISTRICTS_FILE = SOURCE / "geospatial" / "vectors" / "sajid(2oct)" / "Join_Irrigated_Full.shp"
IRRIGATION_FILE = SOURCE / "spreadsheets" / "Complete GHG and Irrigation data 30 Sep.xls"
EMISSIONS_FILE = SOURCE / "spreadsheets" / "Pakistan_GHG_1994_2021_Excel_Data.xlsx"
WATER_FILE = SOURCE / "spreadsheets" / "CRW(efficiency) 25sep.xlsx"
FOOD_FILE = SOURCE / "spreadsheets" / "food security projection CSA 17 sep.xlsx"

COUNTRY_ID = "PK"
PRACTICES = {
    "SP": "Sprinkler",
    "AWD": "Alternate wetting and drying",
    "FI": "Flood irrigation",
    "Drip": "Drip",
}
# How the spreadsheet names provinces, against how the map file names them.
PROVINCE_ALIASES = {"kpk": "Khyber Pakhtunkhwa", "gilgit": "Gilgit Baltistan"}
# Spreadsheet spelling or former name -> the map file's name, for districts that are the same place.
# Rows that cover several map districts (Karachi, Dir, Chitral, Kohistan, "Mirpurkhas and Umerkot",
# "Sheikhupura (Nankana)") are deliberately absent: they stay in province totals only.
DISTRICT_SPELLINGS = {
    "bolan": "Kachhi",
    "jhallmagsi": "Jhal Magsi",
    "kechturbat": "Kech",
    "abottabad": "Abbottabad",
    "bajauragency": "Bajaur",
    "battagram": "Batagram",
    "deraismailkhan": "D. I. Khan",
    "khyberagency": "Khyber",
    "kurramagency": "Kurram",
    "mohmandagency": "Mohmand",
    "orakzaiagency": "Orakzai",
    "ghizar": "Ghizer",
    "attok": "Attock",
    "gujarat": "Gujrat",
    "kushab": "Khushab",
    "layyah": "Leiah",
    "mainwali": "Mianwali",
    "khaipur": "Khairpur",
    "nausheroferoze": "Naushahro Feroze",
    "nawabshah": "Shaheed Benazir Abad",
}
# Names the portal shows in place of the ones in the district map file.
PROVINCE_DISPLAY_NAMES = {
    "Indian_Illegally_Occupied_Jammu_Kashmir": "Jammu and Kashmir",
}
DISTRICT_DISPLAY_NAMES = {
    "Indian Illegally Occupied Jammu Kashmir": "Jammu and Kashmir",
}


def norm(name: Any) -> str:
    """A name reduced to lowercase letters and digits, for comparing spellings."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def slug(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def canonical_province(name: Any) -> str:
    text = str(name).strip()
    return PROVINCE_ALIASES.get(norm(text), text)


def practice_label(code: Any) -> str:
    if code is None or (isinstance(code, float) and pd.isna(code)) or str(code).strip() in ("", "NA"):
        return "No recommendation"
    return ", ".join(PRACTICES.get(part.strip(), part.strip()) for part in str(code).split(","))


def _simplify(geometries: gpd.GeoSeries, tolerance: float) -> gpd.GeoSeries:
    if tolerance <= 0:
        return geometries
    try:
        # Simplifies neighbours together, so shared borders stay shared.
        simplified = shapely.coverage_simplify(geometries.to_numpy(), tolerance)
    except shapely.errors.GEOSException:
        simplified = shapely.simplify(geometries.to_numpy(), tolerance, preserve_topology=True)
    return gpd.GeoSeries(simplified, index=geometries.index, crs=geometries.crs)


def _display_province(name: Any) -> str:
    """A province name as the portal shows it: trimmed, consistently cased, with display names applied."""
    text = str(name).strip()
    if text in PROVINCE_DISPLAY_NAMES:
        return PROVINCE_DISPLAY_NAMES[text]
    return text.title() if text.isupper() else text


def build_districts(
    source: gpd.GeoDataFrame, tolerance: float = 0.004
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Provinces and districts, each with id, name and parent, from the main district map."""
    missing = [c for c in ("Districts", "province") if c not in source.columns]
    if missing:
        raise ValueError(f"District map is missing columns {missing}; found {list(source.columns)}")
    frame = source.to_crs(4326).copy()
    frame["province"] = frame["province"].map(_display_province)
    frame["name"] = frame["Districts"].astype(str).str.strip().map(lambda n: DISTRICT_DISPLAY_NAMES.get(n, n))
    frame = frame.set_geometry(_simplify(frame.geometry.make_valid(), tolerance))
    frame["parent_id"] = "p-" + frame["province"].map(slug)
    frame["id"] = "d-" + frame["province"].map(slug) + "-" + frame["name"].map(slug)
    repeated = frame.loc[frame["id"].duplicated(), "name"].tolist()
    if repeated:
        raise ValueError(f"District map has more than one district with the same name in a province: {repeated}")

    districts = frame[["id", "name", "parent_id", "geometry"]].sort_values("id").reset_index(drop=True)
    provinces = (
        frame.dissolve(by="parent_id", as_index=False, aggfunc="first")[["parent_id", "province", "geometry"]]
        .rename(columns={"parent_id": "id", "province": "name"})
        .sort_values("id")
        .reset_index(drop=True)
    )
    provinces.insert(2, "parent_id", COUNTRY_ID)
    return provinces, districts


def build_practice_layer(tehsils: gpd.GeoDataFrame, tolerance: float = 0.004) -> gpd.GeoDataFrame:
    """The recommended irrigation practice for each tehsil, from the tehsil map file."""
    frame = tehsils.to_crs(4326).copy()
    frame["name"] = frame["ADM3_EN"].astype(str).str.strip()
    frame = frame.set_geometry(_simplify(frame.geometry.make_valid(), tolerance))
    base = (
        "t-" + frame["ADM1_EN"].map(slug) + "-" + frame["ADM2_EN"].map(slug) + "-" + frame["name"].map(slug)
    )
    repeat = base.groupby(base).cumcount()
    frame["id"] = base.where(repeat == 0, base + "-" + (repeat + 1).astype(str))
    practice = frame["Irr_Rec"].astype(str).str.strip()
    frame["practice"] = practice.where(~practice.isin(["NA", "", "nan", "None"]), None).astype(object)
    frame["practice"] = frame["practice"].where(frame["practice"].notna(), None)
    frame["label"] = "Recommended practice: " + frame["Irr_Rec"].map(practice_label)
    return frame[["id", "name", "practice", "label", "geometry"]].reset_index(drop=True)


def _require(frame: pd.DataFrame, columns: list[str], path: Path) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{Path(path).name}: missing columns {missing}; found {list(frame.columns)}")


def read_irrigation_sheet(path: Path) -> pd.DataFrame:
    """One row per district from the 'Irrigation System of Pakistan' sheet."""
    raw = pd.read_excel(path, sheet_name="Irrigation System of Pakistan", header=None)
    rows = raw.iloc[2:, :6].copy()
    rows.columns = ["district", "province", "equipped", "groundwater", "surface", "irrigated"]
    rows = rows[rows["district"].notna() & rows["province"].notna()]
    rows["district"] = rows["district"].astype(str).str.strip()
    rows["province"] = rows["province"].map(canonical_province)
    for column in ["equipped", "groundwater", "surface", "irrigated"]:
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    return rows[rows["equipped"].notna()].reset_index(drop=True)


def match_districts(
    sheet: pd.DataFrame, districts: pd.DataFrame, name_pairs: dict[str, str]
) -> tuple[dict[int, str], list[str]]:
    """Match spreadsheet rows to map districts by name. Rows that do not match are reported, never guessed."""
    province_of = {row.id: row.parent_id for row in districts.itertuples()}
    by_name: dict[str, list[str]] = {}
    for row in districts.itertuples():
        by_name.setdefault(norm(row.name), []).append(row.id)

    matches: dict[int, str] = {}
    unmatched: list[str] = []
    for index, row in sheet.iterrows():
        spellings = [norm(row["district"])]
        if spellings[0] in name_pairs:
            spellings.append(norm(name_pairs[spellings[0]]))
        candidates = [district_id for spelling in spellings for district_id in by_name.get(spelling, [])]
        in_province = [c for c in candidates if province_of[c] == "p-" + slug(row["province"])]
        chosen = in_province[0] if in_province else candidates[0] if len(set(candidates)) == 1 else None
        if chosen is None or chosen in matches.values():
            unmatched.append(f"{row['district']} ({row['province']})")
        else:
            matches[int(index)] = chosen
    return matches, unmatched


def _number(value: Any) -> float | int | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def _total(values: pd.Series) -> float | int | None:
    return _number(values.sum()) if values.notna().any() else None


def summarise_irrigation(
    sheet: pd.DataFrame,
    matches: dict[int, str],
    unmatched: list[str],
    provinces: pd.DataFrame,
    districts: pd.DataFrame,
) -> dict[str, Any]:
    measures = ["equipped", "groundwater", "surface", "irrigated"]

    def entry(name: str, level: str, parent: str | None, rows: pd.DataFrame) -> dict[str, Any]:
        return {
            "name": name, "level": level, "parent_id": parent,
            **{m: _total(rows[m]) for m in measures},
            "districts_reported": int(len(rows)),
        }

    places: dict[str, Any] = {COUNTRY_ID: entry("Pakistan", "national", None, sheet)}
    for province in provinces.itertuples():
        rows = sheet[sheet["province"].map(lambda p: "p-" + slug(p)) == province.id]
        if len(rows):
            places[province.id] = entry(province.name, "province", COUNTRY_ID, rows)
    lookup = {row.id: row for row in districts.itertuples()}
    for index, district_id in matches.items():
        district = lookup[district_id]
        places[district_id] = entry(district.name, "district", district.parent_id, sheet.loc[[index]])
    return {"places": places, "unmatched": unmatched}


def _column(frame: pd.DataFrame, name: str) -> list[float]:
    return [round(float(v), 4) for v in frame[name]]


def read_emissions(path: Path) -> dict[str, Any]:
    frame = pd.read_excel(path, sheet_name="GHG_1994_2021")
    columns = ["Year", "CO2 (MtCO2e)", "CH4 (MtCO2e)", "N2O (MtCO2e)", "Total GHG (MtCO2e)", "Data Status"]
    _require(frame, columns, path)
    frame = frame[frame["Year"].notna() & frame["Total GHG (MtCO2e)"].notna()]
    meta = pd.read_excel(path, sheet_name="Metadata")
    details = {str(item).strip(): str(detail).strip() for item, detail in meta.iloc[:, :2].itertuples(index=False)}
    return {
        "unit": "MtCO2e",
        "source": details.get("Official source", ""),
        "years": [int(y) for y in frame["Year"]],
        "co2": _column(frame, "CO2 (MtCO2e)"),
        "ch4": _column(frame, "CH4 (MtCO2e)"),
        "n2o": _column(frame, "N2O (MtCO2e)"),
        "total": _column(frame, "Total GHG (MtCO2e)"),
        "official": [not str(status).lower().startswith("interpolated") for status in frame["Data Status"]],
    }


def read_water_balance(path: Path) -> dict[str, Any]:
    frame = pd.read_excel(path)
    _require(frame, ["year", "WAv", "CWR(35%)", "CWR(50%)", "CWR(70%)"], path)
    frame = frame[frame["year"].notna()]
    return {
        "years": [int(y) for y in frame["year"]],
        "availability": _column(frame, "WAv"),
        "requirement": {level: _column(frame, f"CWR({level}%)") for level in ("35", "50", "70")},
    }


def read_food_security(path: Path) -> dict[str, Any]:
    frame = pd.read_excel(path, sheet_name="csa")
    columns = {
        "demand": "food Demand",
        "csa_availability": "CSA Availability",
        "traditional_availability": "Traditional Avl",
        "csa_gap": "CSA Food Gap",
        "traditional_gap": "Traditional food gap",
        "population": "Pop",
    }
    _require(frame, ["Year", *columns.values()], path)
    frame = frame[frame["Year"].notna()]
    return {"years": [int(y) for y in frame["Year"]], **{key: _column(frame, col) for key, col in columns.items()}}


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    return value


def _write_geojson(frame: gpd.GeoDataFrame, path: Path) -> None:
    collection = json.loads(frame.to_json(drop_id=True))
    for feature in collection["features"]:
        feature["geometry"] = _rounded(feature["geometry"])
        feature["properties"] = {k: v for k, v in feature["properties"].items() if v is not None}
    path.write_text(json.dumps(collection, separators=(",", ":")), encoding="utf-8")
    print(f"  {path.relative_to(REPO)}: {len(frame)} features, {path.stat().st_size / 1e6:.1f} MB")


def _write_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"  {path.relative_to(REPO)}")


def main() -> None:
    BOUNDARIES_OUT.mkdir(exist_ok=True)
    DATA_OUT.mkdir(exist_ok=True)

    print("Provinces and districts, from", DISTRICTS_FILE.name)
    provinces, districts = build_districts(gpd.read_file(DISTRICTS_FILE))
    _write_geojson(provinces, BOUNDARIES_OUT / "provinces.geojson")
    _write_geojson(districts, BOUNDARIES_OUT / "districts.geojson")

    print("Irrigation practice by tehsil, from", TEHSILS_FILE.name)
    _write_geojson(build_practice_layer(gpd.read_file(TEHSILS_FILE)), DATA_OUT / "irrigation_practice.geojson")

    print("Irrigation figures, from", IRRIGATION_FILE.name)
    sheet = read_irrigation_sheet(IRRIGATION_FILE)
    matches, unmatched = match_districts(sheet, districts, DISTRICT_SPELLINGS)
    _write_json(summarise_irrigation(sheet, matches, unmatched, provinces, districts), DATA_OUT / "irrigation.json")
    print(f"  {len(matches)} of {len(sheet)} spreadsheet districts matched to the map")
    for name in unmatched:
        print("  not matched:", name)

    print("Emissions, water balance and food security")
    _write_json(read_emissions(EMISSIONS_FILE), DATA_OUT / "emissions.json")
    _write_json(read_water_balance(WATER_FILE), DATA_OUT / "water_balance.json")
    _write_json(read_food_security(FOOD_FILE), DATA_OUT / "food_security.json")


if __name__ == "__main__":
    main()
