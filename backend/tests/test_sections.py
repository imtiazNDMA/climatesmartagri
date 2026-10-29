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
            "id": "t-punjab-lahore-city", "name": "Lahore City", "practice": "Drip, SP", "label": "Recommended practice: Drip, Sprinkler",
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
    # The figures speak for themselves: nothing is written under them.
    assert body["notes"] == []


def test_year_outside_the_data_uses_the_latest(providers):
    sections, _ = providers
    assert _figures(sections["emissions"](PK, None))["Total emissions"] == (198.63, "MtCO2e")
    assert _figures(sections["emissions"](PK, 1800))["Total emissions"] == (198.63, "MtCO2e")





def test_irrigation_with_a_missing_value_leaves_it_out(providers):
    sections, _ = providers
    figures = _figures(sections["irrigation"](ATTOCK, None))
    assert figures["Land actually irrigated"] == (None, "million acres")
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


def test_practice_layer_gives_each_tehsil_a_table_of_its_practices(providers):
    _, layers = providers
    table = layers["irrigation-practice"]()["features"][0]["properties"]["table"]
    assert table["title"] == "Recommended for Lahore City tehsil"
    assert table["columns"] == ["Irrigation type", "Why it is needed and how it helps"]
    # One row per recommended practice, in the order the recommendation lists them.
    assert [row["name"] for row in table["rows"]] == ["Drip irrigation", "Sprinkler irrigation"]
    assert [row["icon"] for row in table["rows"]] == ["drip", "sprinkler"]
    # Each practice says what it is, then where it suits and how it helps.
    for row in table["rows"]:
        assert [point.get("label") for point in row["points"]] == [None, "Suits", "Helps by"]
        assert all(point["text"].endswith(".") for point in row["points"])
        assert [point.get("tone") for point in row["points"]] == [None, "condition", "benefit"]
        # The highlights only cut the sentence up; put back together it reads the same, with no markers left.
        for point in row["points"]:
            assert "".join(part["text"] for part in point["parts"]) == point["text"]
            assert not set("{}+~") & set(point["text"])


def test_marked_words_become_highlights_in_their_tone():
    from csa_portal.sections import _highlighted

    assert _highlighted("It {+saves water+}, but {!costs more!} where {~water is scarce~}.") == {
        "text": "It saves water, but costs more where water is scarce.",
        "parts": [
            {"text": "It "}, {"text": "saves water", "tone": "benefit"}, {"text": ", but "},
            {"text": "costs more", "tone": "caution"}, {"text": " where "},
            {"text": "water is scarce", "tone": "condition"}, {"text": "."},
        ],
    }
    assert _highlighted("Nothing to pick out.") == {
        "text": "Nothing to pick out.", "parts": [{"text": "Nothing to pick out."}],
    }


def test_every_practice_picks_out_a_few_words_and_no_more():
    from csa_portal.sections import PRACTICE_GUIDE, _practice_row

    for code in PRACTICE_GUIDE:
        tones = [part["tone"] for point in _practice_row(code)["points"] for part in point["parts"] if "tone" in part]
        assert 2 <= len(tones) <= 4, code
        assert "condition" in tones and "benefit" in tones, code


def test_a_tehsil_without_a_recommendation_gets_no_table():
    from csa_portal.sections import _with_practice_tables

    collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": None, "properties": {"id": "t-1", "name": "A", "practice": None}},
        {"type": "Feature", "geometry": None, "properties": {"id": "t-2", "name": "B", "practice": "AWD, Other"}},
    ]}
    first, second = [f["properties"] for f in _with_practice_tables(collection)["features"]]
    assert "table" not in first
    # A code the guide does not know is left out rather than shown without an explanation.
    assert [row["name"] for row in second["table"]["rows"]] == ["Alternate wetting and drying"]


def test_district_layers_carry_a_value_and_a_label(providers):
    _, layers = providers
    assert set(layers) == {
        "irrigation-practice", "equipped-area", "irrigated-share", "groundwater-share",
        "surface-water-area", "groundwater-area", "irrigation-balance",
    }

    def props(layer_id):
        return {f["properties"]["id"]: f["properties"] for f in layers[layer_id]()["features"]}

    equipped = props("equipped-area")
    # Areas are in million acres, like every other area in the portal.
    assert equipped["d-punjab-lahore"]["value"] == 1000 * 2.47105 / 1_000_000
    assert equipped["d-punjab-lahore"]["label"] == "Area equipped for irrigation: 0.0025 million acres"
    assert "value" not in equipped["d-sindh-ghost"]
    assert equipped["d-sindh-ghost"]["label"] == "Area equipped for irrigation: no figures reported"

    share = props("irrigated-share")
    assert share["d-punjab-lahore"]["value"] == 80.0
    assert share["d-punjab-lahore"]["label"] == "Share of equipped area irrigated: 80%"
    assert "value" not in share["d-punjab-attock"]

    groundwater = props("groundwater-share")
    assert groundwater["d-punjab-attock"]["value"] == 20.0
    assert len(layers["equipped-area"]()["features"]) == 3

    surface, ground, balance = props("surface-water-area"), props("groundwater-area"), props("irrigation-balance")
    assert surface["d-punjab-lahore"]["value"] == 600 * 2.47105 / 1_000_000
    assert surface["d-punjab-lahore"]["label"] == "Surface water irrigation: 0.0015 million acres"
    assert ground["d-punjab-lahore"]["value"] == 400 * 2.47105 / 1_000_000
    assert ground["d-punjab-lahore"]["label"] == "Groundwater irrigation: 0.00099 million acres"
    # The balance is surface water minus groundwater, and its label says which is ahead.
    assert balance["d-punjab-lahore"]["value"] == 200 * 2.47105 / 1_000_000
    assert balance["d-punjab-lahore"]["label"] == "Surface water irrigates 0.00049 million acres more than groundwater"
    assert "value" not in balance["d-sindh-ghost"]


def test_a_district_layer_marks_the_districts_furthest_each_way():
    from csa_portal.sections import _district_layer

    ids = "abcdefg"
    values = dict(zip(ids, [-9, -4, -1, 0, 2, 5, 8]))
    boundaries = {"features": [
        {"geometry": None, "properties": {"id": i, "name": i.upper()}} for i in [*ids, "none"]
    ]}
    places = {i: {"v": v} for i, v in values.items()} | {"none": {"v": None}}
    layer = _district_layer(boundaries, places, "Balance", lambda e: e["v"], "", extremes=2)
    marks = {f["properties"]["id"]: f["properties"].get("extreme") for f in layer()["features"]}
    assert marks == {"a": "low", "b": "low", "c": None, "d": None, "e": None, "f": "high", "g": "high", "none": None}
    # Fewer districts on one side than asked for: only those are marked, never one from the other side.
    lopsided = _district_layer(boundaries, places | {"a": {"v": 1}, "b": {"v": 3}, "c": {"v": 4}}, "B", lambda e: e["v"], "", extremes=2)
    assert [f["properties"]["id"] for f in lopsided()["features"] if f["properties"].get("extreme") == "low"] == []
    # Other layers mark nothing.
    plain = _district_layer(boundaries, places, "Balance", lambda e: e["v"], "")
    assert not any("extreme" in f["properties"] for f in plain()["features"])


def test_the_balance_label_names_the_larger_source():
    from csa_portal.sections import _water_balance_label

    assert _water_balance_label(-0.4958) == "Groundwater irrigates 0.5 million acres more than surface water"
    assert _water_balance_label(1.663) == "Surface water irrigates 1.66 million acres more than groundwater"
    # Less than half a hectare apart counts as equal.
    assert _water_balance_label(0.0000002) == "Surface water and groundwater irrigate the same area"


def test_amounts_keep_at_most_two_decimals_or_their_first_two_digits():
    from csa_portal.sections import _amount

    assert _amount(1.663) == "1.66"
    assert _amount(1234.5) == "1,234.5"
    assert _amount(80.0) == "80"
    assert _amount(0.34) == "0.34"
    assert _amount(0.0478) == "0.048"
    assert _amount(0.00123) == "0.0012"
    assert _amount(0) == "0"


def _charts(body):
    return {c["id"]: c for c in body["charts"]}


def test_every_chart_has_a_plain_headline_and_no_line_of_explanation(providers):
    sections, _ = providers
    for section_id, place in [("emissions", PK), ("water-balance", PK), ("food-security", PK), ("irrigation", LAHORE)]:
        for chart in sections[section_id](place, None)["charts"]:
            assert chart["title"].strip() and not chart["title"].endswith("."), chart["id"]
            assert len(chart["title"]) <= 110, chart["id"]
            assert "subtitle" not in chart, chart["id"]
            for series in chart["series"]:
                assert len(series["values"]) == len(chart["categories"]), chart["id"]


def test_emissions_story(providers):
    sections, _ = providers
    charts = _charts(sections["emissions"](PK, 1995))
    assert list(charts) == ["emissions-by-gas", "emissions-growth", "emissions-share"]

    by_gas = charts["emissions-by-gas"]
    assert by_gas["title"] == "Pakistan's annual emissions more than tripled since 1994"
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
    assert list(charts) == ["water-buffer", "water-explorer", "water-grid"]
    buffer = charts["water-buffer"]
    assert (buffer["kind"], buffer["time"], buffer["categories"]) == ("balance", True, [2026, 2027])
    assert buffer["title"] == "Higher efficiency protects the water buffer"
    # A balance for each efficiency level in every year: below zero is a deficit, above it a buffer.
    assert [(s["name"], s["values"]) for s in buffer["series"]] == [
        ("35% efficiency", [-23.0, -23.9]), ("50% efficiency", [16.6, 16.0]), ("70% efficiency", [43.0, 42.6]),
    ]
    # The two amounts behind each balance are there for the reader who points at a bar.
    assert buffer["balance"]["available"] == [109.0, 109.1]
    assert buffer["balance"]["needed"] == [[132.0, 133.0], [92.4, 93.1], [66.0, 66.5]]
    assert (buffer["balance"]["negative"], buffer["balance"]["positive"]) == ("Water deficit", "Water buffer")
    # The two charts that work the balance out at any efficiency carry what they need to do it: the water
    # available, the need at the lowest efficiency listed, and the range the reader may choose within.
    explorer, grid = charts["water-explorer"], charts["water-grid"]
    assert (explorer["kind"], grid["kind"]) == ("explorer", "grid")
    for chart in (explorer, grid):
        assert [(s["name"], s["values"]) for s in chart["series"]] == [
            ("Water available", [109.0, 109.1]), ("Water crops need at 35% efficiency", [132.0, 133.0]),
        ]
        assert chart["efficiency"] == {"min": 35, "max": 70, "base": 35, "start": 45, "given": [35, 50, 70]}
        assert chart["note"] == (
            "Efficiencies other than 35%, 50% and 70% are calculated from the source's figures, not given in it."
        )
    # The efficiency at which need would equal supply: 132 x 35% / 109 = 42.4, then 133 x 35% / 109.1 = 42.7.
    assert explorer["title"] == "Water stays enough to 2027 only if irrigation efficiency reaches 43%"
    assert grid["title"] == "The efficiency that breaks even climbs from 42% in 2026 to 43% in 2027"


def test_the_water_headline_falls_back_when_more_efficiency_does_not_always_leave_more(dirs):
    import json as _json

    data, boundaries = dirs
    (data / "water_balance.json").write_text(_json.dumps({
        "years": [2026, 2027], "availability": [140.0, 109.1],
        # In 2027 the 50% level needs more than the 35% level: the plain finding does not hold.
        "requirement": {"35": [132.0, 133.0], "50": [92.4, 140.0], "70": [66.0, 66.5]},
    }), encoding="utf-8")
    sections, _ = build_providers(data, boundaries)
    charts = _charts(sections["water-balance"](PK, 2027))
    assert charts["water-buffer"]["title"] == "At 35% efficiency, crops need more water than is available in 1 of 2 years"
    # Need is not in proportion to efficiency here, so the balance at other efficiencies cannot be worked
    # out, and the two charts that would do so are left out.
    assert list(charts) == ["water-buffer"]


def test_food_story(providers):
    sections, _ = providers
    body = sections["food-security"](PK, 2027)
    figures = _figures(body)
    assert figures["Food needed"] == (95.85, "")
    assert figures["Food gap with climate smart agriculture"] == (12.58, "")
    assert figures["Food gap with traditional farming"] == (16.05, "")
    assert figures["Population"] == (259.8, "million")

    charts = _charts(body)
    assert list(charts) == ["food-outlook", "food-population"]
    outlook = charts["food-outlook"]
    assert outlook["kind"] == "outlook"
    # Need first, then the two supplies: the chart fills in the spaces between them in that order.
    assert [s["name"] for s in outlook["series"]] == [
        "Food needed", "With climate smart agriculture", "With traditional farming", "Population",
    ]
    assert [s["values"][-1] for s in outlook["series"]] == [95.85, 83.27, 79.81, 259.8]
    assert outlook["title"] == (
        "By 2027 climate smart agriculture adds 3.5 over traditional farming, yet 12.6 of the food needed is unmet"
    )
    assert charts["food-population"]["title"] == "Population grows from 255 to 260 million by 2027"


def test_irrigation_story_for_a_district(providers):
    sections, _ = providers
    body = sections["irrigation"](LAHORE, None)
    figures = _figures(body)
    assert figures["Land equipped for irrigation"] == (1000 * 2.47105 / 1_000_000, "million acres")
    assert figures["Served by groundwater"] == (400 * 2.47105 / 1_000_000, "million acres")
    assert figures["Served by surface water"] == (600 * 2.47105 / 1_000_000, "million acres")
    assert figures["Land actually irrigated"] == (800 * 2.47105 / 1_000_000, "million acres")
    assert figures["Share of equipped land irrigated"] == (80.0, "%")

    charts = _charts(body)
    assert list(charts) == ["irrigation-source", "irrigation-practices"]
    assert [charts[c]["kind"] for c in charts] == ["diverging", "counts"]


def _acres(hectares):
    return hectares * 2.47105 / 1_000_000


def test_water_sources_run_either_side_of_a_centre_line(providers):
    sections, _ = providers
    country = _charts(sections["irrigation"](PK, None))["irrigation-source"]
    assert [side["label"] for side in country["sides"]] == ["Groundwater", "Surface water"]
    # The sides wear the colours of the two ends of the irrigation balance map.
    assert [side["colour"] for side in country["sides"]] == ["#3b4cc0", "#b40426"]
    sindh, punjab = country["splits"]
    assert (sindh["name"], sindh["left"], sindh["right"]) == ("Sindh", 0.5, 99.5)
    assert (punjab["name"], punjab["left"], punjab["right"]) == ("Punjab", 33.3, 66.7)
    # Rows are weighted by how much land each has equipped.
    assert (sindh["weight"], punjab["weight"]) == (_acres(2050), _acres(1500))
    # With no place chosen the chart singles none out, in its headline or its rows.
    assert country["title"] == "Where each province's irrigation water comes from"
    assert [split["highlight"] for split in country["splits"]] == [False, False]
    punjab_districts = _charts(sections["irrigation"](PUNJAB, None))["irrigation-source"]
    assert punjab_districts["title"] == "Where each district's irrigation water comes from in Punjab"
    assert not any(split["highlight"] for split in punjab_districts["splits"])

    lahore = _charts(sections["irrigation"](LAHORE, None))["irrigation-source"]
    assert [split["name"] for split in lahore["splits"]] == ["Lahore", "Attock"]
    assert lahore["title"] == "Lahore takes 60% of its irrigation water from surface water"
    assert [split["highlight"] for split in lahore["splits"]] == [True, False]


def test_practices_are_counted_by_the_tehsils_they_are_recommended_in(dirs):
    data, boundaries = dirs

    def tehsil(tehsil_id, practice):
        return {"type": "Feature", "geometry": SQUARE, "properties": {"id": tehsil_id, "name": tehsil_id, "practice": practice}}

    (data / "irrigation_practice.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        tehsil("t-punjab-lahore-city", "Drip, SP"), tehsil("t-punjab-lahore-cantt", "SP"),
        tehsil("t-punjab-kasur-kasur", "AWD, SP"), tehsil("t-sindh-thatta-thatta", "FI"),
        # No recommendation: not counted at all.
        tehsil("t-sindh-thatta-sujawal", None),
    ]}), encoding="utf-8")
    sections, _ = build_providers(data, boundaries)
    country = _charts(sections["irrigation"](PK, None))["irrigation-practices"]
    assert (country["kind"], country["total"], country["unit"]) == ("counts", 4, "tehsils")
    # A tehsil recommended two practices counts towards both; the most recommended comes first.
    assert [(item["icon"], item["name"], item["value"]) for item in country["items"]] == [
        ("sprinkler", "Sprinkler irrigation", 3), ("drip", "Drip irrigation", 1),
        ("paddy", "Alternate wetting and drying", 1), ("flood", "Flood irrigation", 1),
    ]
    assert [item["highlight"] for item in country["items"]] == [True, False, False, False]
    assert country["title"] == "Sprinkler irrigation is recommended in 3 of 4 tehsils; flood irrigation in only 1"

    # A province or district counts its own tehsils.
    punjab = _charts(sections["irrigation"](PUNJAB, None))["irrigation-practices"]
    assert (punjab["total"], punjab["title"]) == (3, "Sprinkler irrigation is recommended in 3 of 3 tehsils in Punjab")
    lahore = _charts(sections["irrigation"](LAHORE, None))["irrigation-practices"]
    assert (lahore["total"], lahore["title"]) == (2, "Sprinkler irrigation is recommended in 2 of 2 tehsils in Lahore")
    # A district the tehsil map does not know by that name shows its province's count instead.
    attock = _charts(sections["irrigation"](ATTOCK, None))["irrigation-practices"]
    assert attock["title"] == "Sprinkler irrigation is recommended in 3 of 3 tehsils in Punjab"
    sindh = _charts(sections["irrigation"](Place("p-sindh", "Sindh", "province", "PK", (0, 0, 1, 1)), None))
    assert sindh["irrigation-practices"]["title"] == "Flood irrigation is recommended in 1 of 1 tehsil in Sindh"


def test_irrigation_story_without_an_irrigated_figure(providers):
    sections, _ = providers
    charts = _charts(sections["irrigation"](ATTOCK, None))
    assert charts["irrigation-source"]["title"] == "Attock takes 80% of its irrigation water from surface water"


def test_irrigation_story_for_a_province_and_the_country(providers):
    sections, _ = providers
    province = sections["irrigation"](PUNJAB, None)
    assert _figures(province)["Land equipped for irrigation"] == (1500 * 2.47105 / 1_000_000, "million acres")
    # The figures speak for themselves: nothing is written under them.
    assert province["notes"] == []

    country = sections["irrigation"](PK, None)
    country_figures = _figures(country)
    assert country_figures["Land equipped for irrigation"] == (3850 * 2.47105 / 1_000_000, "million acres")
    assert country_figures["Served by groundwater"] == (810 * 2.47105 / 1_000_000, "million acres")
    assert country_figures["Served by surface water"] == (3040 * 2.47105 / 1_000_000, "million acres")
    assert country_figures["Land actually irrigated"] == (1975 * 2.47105 / 1_000_000, "million acres")
    assert country["notes"] == []
    assert "irrigation-use" not in _charts(country)


def test_land_cover_has_no_data_without_the_annual_statistics(dirs):
    data, boundaries = dirs
    (data / "land_cover.json").write_text(json.dumps({"classes": ["forest"], "places": {}}), encoding="utf-8")

    sections, _ = build_providers(data, boundaries)

    assert "land-cover" not in sections



def _calendar_record(province_id, province, crop, old_sowing, new_sowing, earlier):
    return {
        "province_id": province_id, "province": province, "crop": crop,
        "traditional": {"text": "old", "sowing": old_sowing, "harvest": [[2.0, 4.0]]},
        "adjusted": {"text": "new", "sowing": new_sowing, "harvest": [[2.0, 4.0]]},
        "reason": f"Why {crop} moves.", "changed": old_sowing != new_sowing, "sown_earlier": earlier,
    }


@pytest.fixture
def calendar(dirs):
    data, boundaries = dirs
    (data / "crop_calendar.json").write_text(json.dumps({"records": [
        _calendar_record("p-punjab", "Punjab", "Wheat", [[9.0, 12.0]], [[9.0, 11.0]], True),
        _calendar_record("p-punjab", "Punjab", "Rice", [[4.0, 7.0]], [[4.0, 6.0]], True),
        _calendar_record("p-punjab", "Punjab", "Sugarcane", [[1.0, 3.0]], [[1.0, 3.0]], False),
        _calendar_record("p-sindh", "Sindh", "Cotton", [[3.0, 6.0]], [[3.0, 6.0]], False),
    ]}), encoding="utf-8")
    sections, _ = build_providers(data, boundaries)
    return sections["climate-calendar"]


SINDH = Place("p-sindh", "Sindh", "province", "PK", (66, 23, 71, 28))
KASHMIR = Place("p-azad-kashmir", "Azad Kashmir", "province", "PK", (73, 33, 75, 35))


def test_calendar_for_a_province_is_one_chart_of_its_crops(calendar):
    body = calendar(PUNJAB, None)
    assert _figures(body) == {
        "Crops with a calendar": (3, ""),
        "Calendars adjusted for climate": (2, ""),
        "Crops to sow earlier": (2, ""),
    }
    assert body["notes"] == []
    (chart,) = body["charts"]
    assert chart["id"] == "calendar-punjab"
    assert chart["kind"] == "calendar"
    assert chart["title"] == "In Punjab, 2 of 3 crops should be sown earlier than before"
    assert "subtitle" not in chart
    assert [row["crop"] for row in chart["rows"]] == ["Wheat", "Rice", "Sugarcane"]
    wheat = chart["rows"][0]
    assert wheat["traditional"] == {"text": "old", "sowing": [[9.0, 12.0]], "harvest": [[2.0, 4.0]]}
    assert wheat["adjusted"]["sowing"] == [[9.0, 11.0]]
    assert (wheat["changed"], wheat["sown_earlier"], wheat["reason"]) == (True, True, "Why Wheat moves.")
    # Generic chart fields are present and empty, so code that walks every chart keeps working.
    assert (chart["series"], chart["categories"], chart["time"]) == ([], [], False)


def test_calendar_headline_when_nothing_moves(calendar):
    (chart,) = calendar(SINDH, None)["charts"]
    assert chart["title"] == "In Sindh, crop calendars keep their traditional sowing dates"


def test_calendar_for_the_country_has_a_chart_for_each_province(calendar):
    body = calendar(PK, None)
    assert _figures(body) == {
        "Provinces with a calendar": (2, ""),
        "Crops with a calendar": (4, ""),
        "Calendars adjusted for climate": (2, ""),
        "Crops to sow earlier": (2, ""),
    }
    assert [chart["id"] for chart in body["charts"]] == ["calendar-punjab", "calendar-sindh"]


def test_calendar_for_a_province_without_one_says_so(calendar):
    body = calendar(KASHMIR, None)
    assert body == {"figures": [], "charts": [], "notes": ["No crop calendar is available for Azad Kashmir."]}
