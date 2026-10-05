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



def test_year_outside_the_data_uses_the_latest(providers):
    sections, _ = providers
    assert _figures(sections["emissions"](PK, None))["Total emissions"] == (198.63, "MtCO2e")
    assert _figures(sections["emissions"](PK, 1800))["Total emissions"] == (198.63, "MtCO2e")





def test_irrigation_with_a_missing_value_leaves_it_out(providers):
    sections, _ = providers
    figures = _figures(sections["irrigation"](ATTOCK, None))
    assert figures["Land actually irrigated"] == (None, "ha")
    assert "Share of equipped land irrigated" not in figures



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


def _charts(body):
    return {c["id"]: c for c in body["charts"]}


def test_every_chart_has_a_plain_headline_and_a_how_to_read_line(providers):
    sections, _ = providers
    for section_id, place in [("emissions", PK), ("water-balance", PK), ("food-security", PK), ("irrigation", LAHORE)]:
        for chart in sections[section_id](place, None)["charts"]:
            assert chart["title"].strip() and not chart["title"].endswith("."), chart["id"]
            assert len(chart["title"]) <= 110, chart["id"]
            assert chart["subtitle"].strip().endswith("."), chart["id"]
            for series in chart["series"]:
                assert len(series["values"]) == len(chart["categories"]), chart["id"]


def test_emissions_story(providers):
    sections, _ = providers
    charts = _charts(sections["emissions"](PK, 1995))
    assert list(charts) == ["emissions-by-gas", "emissions-growth", "emissions-share", "emissions-official"]

    by_gas = charts["emissions-by-gas"]
    assert by_gas["title"] == "Pakistan's yearly emissions grew 1.1 times between 1994 and 1996"
    assert by_gas["kind"] == "stacked-area"
    assert by_gas["end_labels"] is True
    assert [(s["name"], s["slot"]) for s in by_gas["series"]] == [
        ("Carbon dioxide", 1), ("Methane", 2), ("Nitrous oxide", 3),
    ]

    growth = charts["emissions-growth"]
    assert growth["title"] == "Nitrous oxide grew fastest: 1.3 times its 1994 level"
    assert growth["categories"] == ["Carbon dioxide", "Methane", "Nitrous oxide"]
    assert growth["series"][0]["values"] == [1.1, 1.1, 1.3]
    assert growth["bar_slots"] == [1, 2, 3]
    assert growth["unit"] == "times"

    share = charts["emissions-share"]
    assert share["title"] == "In 1995, carbon dioxide made up 53% of emissions"
    assert share["series"][0]["values"] == [53.1, 40.3, 6.7]
    assert share["unit"] == "%"

    official = charts["emissions-official"]
    assert official["title"] == "Only 2 of the 3 years shown are official measurements"
    assert official["series"][0]["points"] == [0, 2]


def test_emissions_share_follows_the_year(providers):
    sections, _ = providers
    assert _charts(sections["emissions"](PK, 1994))["emissions-share"]["title"].startswith("In 1994,")


def test_water_story(providers):
    sections, _ = providers
    body = sections["water-balance"](PK, 2027)
    figures = _figures(body)
    assert figures["Water available"] == (109.1, "")
    assert figures["Water crops need at 50% efficiency"] == (93.1, "")
    assert figures["Shortfall at 35% efficiency"] == (23.9, "")
    assert figures["Water to spare at 70% efficiency"] == (42.6, "")

    charts = _charts(body)
    assert list(charts) == ["water-need-vs-supply", "water-balance-year", "water-balance"]
    need = charts["water-need-vs-supply"]
    assert need["title"] == "At 35% efficiency, crops need more water than is available in every year to 2027"
    assert [(s["name"], s.get("emphasis")) for s in need["series"]] == [
        ("Water available", "strong"),
        ("Needed at 35% efficiency", None),
        ("Needed at 50% efficiency", None),
        ("Needed at 70% efficiency", None),
    ]
    year = charts["water-balance-year"]
    assert year["title"] == "In 2027: short by 23.9 at 35% efficiency, 16 to spare at 50%"
    assert year["categories"] == ["35% efficiency", "50% efficiency", "70% efficiency"]
    assert year["series"][0]["values"] == [-23.9, 16.0, 42.6]
    assert year["colour_by_sign"] is True
    balance = charts["water-balance"]
    assert balance["zero_line"] is True
    assert balance["series"][0]["values"] == [-23.0, -23.9]
    # An efficiency level keeps its colour across the charts.
    slots = {s["name"][-14:]: s["slot"] for s in need["series"][1:]}
    assert {s["name"][-14:]: s["slot"] for s in balance["series"]} == slots


def test_water_headline_when_the_shortfall_is_not_every_year(dirs):
    import json as _json

    data, boundaries = dirs
    (data / "water_balance.json").write_text(_json.dumps({
        "years": [2026, 2027], "availability": [140.0, 109.1],
        "requirement": {"35": [132.0, 133.0], "50": [92.4, 93.1], "70": [66.0, 66.5]},
    }), encoding="utf-8")
    sections, _ = build_providers(data, boundaries)
    title = _charts(sections["water-balance"](PK, 2027))["water-need-vs-supply"]["title"]
    assert title == "At 35% efficiency, crops need more water than is available in 1 of 2 years"


def test_food_story(providers):
    sections, _ = providers
    body = sections["food-security"](PK, 2027)
    figures = _figures(body)
    assert figures["Food needed"] == (95.85, "")
    assert figures["Food gap with climate smart agriculture"] == (12.58, "")
    assert figures["Food gap with traditional farming"] == (16.05, "")
    assert figures["Population"] == (259.8, "million")

    charts = _charts(body)
    assert list(charts) == ["food-demand-availability", "food-gap", "food-population"]
    assert charts["food-demand-availability"]["title"] == (
        "Food needs rise 3% by 2027, while supply with climate smart agriculture rises 0.5%"
    )
    assert charts["food-demand-availability"]["series"][0]["emphasis"] == "strong"
    assert charts["food-gap"]["title"] == (
        "By 2027, climate smart agriculture makes the food gap 22% smaller than traditional farming"
    )
    assert [s["name"] for s in charts["food-gap"]["series"]] == [
        "With climate smart agriculture", "With traditional farming",
    ]
    assert charts["food-population"]["title"] == "Population grows from 255 to 260 million by 2027"


def test_irrigation_story_for_a_district(providers):
    sections, _ = providers
    body = sections["irrigation"](LAHORE, None)
    figures = _figures(body)
    assert figures["Land equipped for irrigation"] == (1000, "ha")
    assert figures["Served by groundwater"] == (400, "ha")
    assert figures["Served by surface water"] == (600, "ha")
    assert figures["Land actually irrigated"] == (800, "ha")
    assert figures["Share of equipped land irrigated"] == (80.0, "%")

    charts = _charts(body)
    assert list(charts) == ["irrigation-use", "irrigation-source", "irrigation-ranking"]
    use = charts["irrigation-use"]
    assert use["title"] == "80% of Lahore's irrigation-ready land is actually irrigated"
    assert use["categories"] == ["Equipped for irrigation", "Actually irrigated"]
    assert use["series"][0]["values"] == [1000, 800]
    source = charts["irrigation-source"]
    assert source["title"] == "Surface water serves 60% of the irrigation-ready land in Lahore"
    assert source["categories"] == ["Groundwater", "Surface water"]
    assert source["series"][0]["values"] == [40.0, 60.0]
    assert source["unit"] == "%"
    ranking = charts["irrigation-ranking"]
    assert ranking["title"] == "Lahore ranks 1st of 2 districts in Punjab for irrigation-ready land"
    assert ranking["categories"] == ["Lahore", "Attock"]
    assert ranking["highlight"] == 0


def test_irrigation_story_without_an_irrigated_figure(providers):
    sections, _ = providers
    charts = _charts(sections["irrigation"](ATTOCK, None))
    assert "irrigation-use" not in charts
    assert charts["irrigation-source"]["title"] == "Surface water serves 80% of the irrigation-ready land in Attock"
    assert charts["irrigation-ranking"]["title"] == "Attock ranks 2nd of 2 districts in Punjab for irrigation-ready land"


def test_irrigation_story_for_a_province_and_the_country(providers):
    sections, _ = providers
    province = sections["irrigation"](PUNJAB, None)
    assert _figures(province)["Land equipped for irrigation"] == (1500, "ha")
    assert "Totals from 2 districts reported in the spreadsheet." in province["notes"]
    ranking = _charts(province)["irrigation-ranking"]
    assert ranking["title"] == "Lahore has the most irrigation-ready land in Punjab"
    assert ranking["highlight"] is None

    country = sections["irrigation"](PK, None)
    ranking = _charts(country)["irrigation-ranking"]
    assert ranking["title"] == "Sindh has the most irrigation-ready land of any province"
    assert ranking["categories"] == ["Sindh", "Punjab"]
    assert any("Nowhere (Sindh)" in note for note in country["notes"])
    assert _charts(country)["irrigation-source"]["title"] == (
        "Surface water serves 79% of the irrigation-ready land in Pakistan"
    )
