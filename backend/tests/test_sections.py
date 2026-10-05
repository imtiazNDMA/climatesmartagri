import json

import pytest

from csa_portal.places import Place
from csa_portal.sections import build_providers

PK = Place("PK", "Pakistan", "national", None, (60, 23, 78, 37))
PUNJAB = Place("p-punjab", "Punjab", "province", "PK", (69, 27, 75, 34))
LAHORE = Place("d-punjab-lahore", "Lahore", "district", "p-punjab", (74, 31, 75, 31.5))
ATTOCK = Place("d-punjab-attock", "Attock", "district", "p-punjab", (72, 33, 73, 34))
GHOST = Place("d-sindh-ghost", "Ghost", "district", "p-sindh", (67, 24, 68, 25))

SQUARE = {"type": "Polygon", "coordinates": [[[74, 31], [75, 31], [75, 32], [74, 32], [74, 31]]]}


def _entry(name, level, parent, equipped, groundwater, surface, irrigated, reported):
    return {
        "name": name, "level": level, "parent_id": parent, "equipped": equipped,
        "groundwater": groundwater, "surface": surface, "irrigated": irrigated,
        "districts_reported": reported,
    }


@pytest.fixture
def dirs(tmp_path):
    data = tmp_path / "data"
    boundaries = tmp_path / "boundaries"
    data.mkdir()
    boundaries.mkdir()
    (data / "emissions.json").write_text(json.dumps({
        "unit": "MtCO2e", "source": "NC3, UNFCCC, 2025", "years": [1994, 1995, 1996],
        "co2": [94.57, 99.88, 105.18], "ch4": [72.27, 75.84, 79.41], "n2o": [11.0, 12.52, 14.04],
        "total": [177.84, 188.24, 198.63], "official": [True, False, True],
    }), encoding="utf-8")
    (data / "water_balance.json").write_text(json.dumps({
        "years": [2026, 2027], "availability": [109.0, 109.1],
        "requirement": {"35": [132.0, 133.0], "50": [92.4, 93.1], "70": [66.0, 66.5]},
    }), encoding="utf-8")
    (data / "food_security.json").write_text(json.dumps({
        "years": [2026, 2027], "demand": [92.79, 95.85], "csa_availability": [82.86, 83.27],
        "traditional_availability": [82.86, 79.81], "csa_gap": [9.94, 12.58],
        "traditional_gap": [9.94, 16.05], "population": [254.71, 259.8],
    }), encoding="utf-8")
    (data / "irrigation.json").write_text(json.dumps({
        "unmatched": ["Nowhere (Sindh)"],
        "places": {
            "PK": _entry("Pakistan", "national", None, 3850, 810, 3040, 1975, 5),
            "p-punjab": _entry("Punjab", "province", "PK", 1500, 500, 1000, 800, 2),
            "p-sindh": _entry("Sindh", "province", "PK", 2050, 10, 2040, 1025, 2),
            "d-punjab-lahore": _entry("Lahore", "district", "p-punjab", 1000, 400, 600, 800, 1),
            "d-punjab-attock": _entry("Attock", "district", "p-punjab", 500, 100, 400, None, 1),
        },
    }), encoding="utf-8")
    (data / "irrigation_practice.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": SQUARE, "properties": {
            "id": "t-1", "name": "Lahore City", "practice": "Drip, SP", "label": "Recommended practice: Drip, Sprinkler",
        }}],
    }), encoding="utf-8")
    (boundaries / "districts.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": SQUARE, "properties": {"id": "d-punjab-lahore", "name": "Lahore", "parent_id": "p-punjab"}},
            {"type": "Feature", "geometry": SQUARE, "properties": {"id": "d-punjab-attock", "name": "Attock", "parent_id": "p-punjab"}},
            {"type": "Feature", "geometry": SQUARE, "properties": {"id": "d-sindh-ghost", "name": "Ghost", "parent_id": "p-sindh"}},
        ],
    }), encoding="utf-8")
    return data, boundaries


@pytest.fixture
def providers(dirs):
    return build_providers(*dirs)


def _figures(body):
    return {f["label"]: (f["value"], f["unit"]) for f in body["figures"]}


def test_nothing_is_provided_when_the_data_folder_is_empty(tmp_path):
    sections, layers = build_providers(tmp_path / "absent", tmp_path / "absent")
    assert sections == {}
    assert layers == {}


def test_a_broken_data_file_only_disables_its_own_section(dirs):
    data, boundaries = dirs
    (data / "emissions.json").write_text("{oops", encoding="utf-8")
    sections, _ = build_providers(data, boundaries)
    assert "emissions" not in sections
    assert "water-balance" in sections


def test_emissions_figures_follow_the_year(providers):
    sections, _ = providers
    body = sections["emissions"](PK, 1995)
    assert _figures(body) == {
        "Total emissions": (188.24, "MtCO2e"),
        "Carbon dioxide (CO2)": (99.88, "MtCO2e"),
        "Methane (CH4)": (75.84, "MtCO2e"),
        "Nitrous oxide (N2O)": (12.52, "MtCO2e"),
    }
    assert "1995 is an interpolated estimate, not an official inventory value." in body["notes"]
    assert any("NC3, UNFCCC, 2025" in note for note in body["notes"])
    official = sections["emissions"](PK, 1994)
    assert "1994 is an official inventory year." in official["notes"]


def test_emissions_charts(providers):
    sections, _ = providers
    charts = {c["id"]: c for c in sections["emissions"](PK, 1995)["charts"]}
    by_gas = charts["emissions-by-gas"]
    assert by_gas["kind"] == "stacked-area"
    assert by_gas["time"] is True
    assert by_gas["categories"] == [1994, 1995, 1996]
    assert [(s["name"], s["slot"]) for s in by_gas["series"]] == [("CO2", 1), ("CH4", 2), ("N2O", 3)]
    assert by_gas["series"][0]["values"] == [94.57, 99.88, 105.18]
    total = charts["emissions-total"]
    assert total["kind"] == "line"
    assert total["series"][0]["points"] == [0, 2]


def test_year_outside_the_data_uses_the_latest(providers):
    sections, _ = providers
    assert _figures(sections["emissions"](PK, None))["Total emissions"] == (198.63, "MtCO2e")
    assert _figures(sections["emissions"](PK, 1800))["Total emissions"] == (198.63, "MtCO2e")


def test_water_balance(providers):
    sections, _ = providers
    body = sections["water-balance"](PK, 2027)
    figures = _figures(body)
    assert figures["Water availability"] == (109.1, "")
    assert figures["Requirement at 50% efficiency"] == (93.1, "")
    assert figures["Balance at 35% efficiency"] == (-23.9, "")
    assert figures["Balance at 70% efficiency"] == (42.6, "")
    charts = {c["id"]: c for c in body["charts"]}
    assert [s["name"] for s in charts["water-availability-requirement"]["series"]] == [
        "Water availability", "Requirement at 35%", "Requirement at 50%", "Requirement at 70%",
    ]
    balance = charts["water-balance"]
    assert balance["zero_line"] is True
    assert balance["series"][0]["values"] == [-23.0, -23.9]
    # A requirement and its balance keep the same colour across the two charts.
    slots = {s["name"][-3:]: s["slot"] for s in charts["water-availability-requirement"]["series"][1:]}
    assert {s["name"][-3:]: s["slot"] for s in balance["series"]} == slots


def test_food_security(providers):
    sections, _ = providers
    body = sections["food-security"](PK, 2027)
    figures = _figures(body)
    assert figures["Food demand"] == (95.85, "")
    assert figures["Food gap with CSA"] == (12.58, "")
    assert figures["Food gap with traditional practice"] == (16.05, "")
    assert figures["Population"] == (259.8, "")
    charts = {c["id"]: c for c in body["charts"]}
    assert set(charts) == {"food-demand-availability", "food-gap", "food-population"}
    assert [s["name"] for s in charts["food-gap"]["series"]] == ["With CSA", "With traditional practice"]


def test_irrigation_for_a_district(providers):
    sections, _ = providers
    body = sections["irrigation"](LAHORE, None)
    figures = _figures(body)
    assert figures["Area equipped for irrigation"] == (1000, "ha")
    assert figures["Equipped with groundwater"] == (400, "ha")
    assert figures["Equipped with surface water"] == (600, "ha")
    assert figures["Area actually irrigated"] == (800, "ha")
    assert figures["Share of equipped area irrigated"] == (80.0, "%")
    charts = {c["id"]: c for c in body["charts"]}
    assert charts["irrigation-source"]["categories"] == ["Groundwater", "Surface water"]
    assert charts["irrigation-source"]["series"][0]["values"] == [400, 600]
    ranking = charts["irrigation-ranking"]
    assert ranking["title"] == "Area equipped for irrigation by district, Punjab"
    assert ranking["categories"] == ["Lahore", "Attock"]
    assert ranking["series"][0]["values"] == [1000, 500]
    assert ranking["highlight"] == 0


def test_irrigation_with_a_missing_value_leaves_it_out(providers):
    sections, _ = providers
    figures = _figures(sections["irrigation"](ATTOCK, None))
    assert figures["Area actually irrigated"] == (None, "ha")
    assert "Share of equipped area irrigated" not in figures


def test_irrigation_for_a_province_and_the_country(providers):
    sections, _ = providers
    province = sections["irrigation"](PUNJAB, None)
    assert _figures(province)["Area equipped for irrigation"] == (1500, "ha")
    assert "Totals from 2 districts reported in the spreadsheet." in province["notes"]
    assert {c["id"]: c for c in province["charts"]}["irrigation-ranking"]["highlight"] is None

    country = sections["irrigation"](PK, None)
    ranking = {c["id"]: c for c in country["charts"]}["irrigation-ranking"]
    assert ranking["title"] == "Area equipped for irrigation by province"
    assert ranking["categories"] == ["Sindh", "Punjab"]
    assert any("Nowhere (Sindh)" in note for note in country["notes"])


def test_irrigation_for_a_place_with_no_figures(providers):
    sections, _ = providers
    body = sections["irrigation"](GHOST, None)
    assert body["figures"] == []
    assert body["notes"] == ["No irrigation figures are reported for Ghost."]
    assert body["charts"] == []


def test_practice_layer_is_served_as_prepared(providers):
    _, layers = providers
    collection = layers["irrigation-practice"]()
    assert collection["features"][0]["properties"]["practice"] == "Drip, SP"


def test_district_layers_carry_a_value_and_a_label(providers):
    _, layers = providers
    assert set(layers) == {"irrigation-practice", "equipped-area", "irrigated-share", "groundwater-share"}

    def props(layer_id):
        return {f["properties"]["id"]: f["properties"] for f in layers[layer_id]()["features"]}

    equipped = props("equipped-area")
    assert equipped["d-punjab-lahore"]["value"] == 1000
    assert equipped["d-punjab-lahore"]["label"] == "Area equipped for irrigation: 1,000 ha"
    assert "value" not in equipped["d-sindh-ghost"]
    assert equipped["d-sindh-ghost"]["label"] == "Area equipped for irrigation: no figures reported"

    share = props("irrigated-share")
    assert share["d-punjab-lahore"]["value"] == 80.0
    assert share["d-punjab-lahore"]["label"] == "Share of equipped area irrigated: 80%"
    assert "value" not in share["d-punjab-attock"]

    groundwater = props("groundwater-share")
    assert groundwater["d-punjab-attock"]["value"] == 20.0
    assert len(layers["equipped-area"]()["features"]) == 3
