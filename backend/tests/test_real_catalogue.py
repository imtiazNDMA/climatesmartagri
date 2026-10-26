from fastapi.testclient import TestClient

from csa_portal.catalogue import load_catalogue
from csa_portal.main import create_app
from csa_portal.settings import BACKEND_DIR, Settings

EXPECTED = [
    ("land-cover", "ready"),
    ("irrigation", "ready"),
    ("emissions", "ready"),
    ("water-balance", "ready"),
    ("food-security", "ready"),
    ("climate-calendar", "ready"),
    ("forecast", "ready"),
    ("crop-classification", "ready"),
    ("hazards", "ready"),
    ("exposure", "coming-soon"),
]
IRRIGATION_LAYERS = [
    "irrigation-practice", "irrigated-share", "equipped-area", "groundwater-share",
    "surface-water-area", "groundwater-area", "irrigation-balance",
]
ANNUAL_LAND_CLASSES = {
    "1": ("Water", "#419bdf"),
    "2": ("Trees", "#397d49"),
    "4": ("Flooded vegetation", "#7a87c6"),
    "5": ("Crops", "#e49635"),
    "7": ("Built area", "#c4281b"),
    "8": ("Bare ground", "#a59b8f"),
    "9": ("Snow/ice", "#a8ebff"),
    "10": ("Clouds", "#616161"),
    "11": ("Rangeland", "#e3e2c3"),
}


def _client():
    return TestClient(create_app(Settings.from_env()))


def test_shipped_catalogue_is_valid_and_complete():
    catalogue = load_catalogue(BACKEND_DIR / "catalogue.json")
    ordered = sorted(catalogue.sections, key=lambda s: s.order)
    assert [(s.id, s.status) for s in ordered] == EXPECTED
    assert [s.order for s in ordered] == list(range(1, 11))
    assert all(s.summary for s in ordered if s.status == "coming-soon")
    boundary_ids = {layer.id for layer in catalogue.layers if layer.kind == "boundary"}
    assert boundary_ids == {"provinces", "districts"}
    by_id = {layer.id: layer for layer in catalogue.layers}
    for layer_id in IRRIGATION_LAYERS:
        assert (by_id[layer_id].kind, by_id[layer_id].status, by_id[layer_id].section_id) == (
            "geojson", "ready", "irrigation",
        )
    years = {s.id: s.years for s in catalogue.sections}
    assert (years["emissions"].first, years["emissions"].last) == (1994, 2025)
    assert (years["water-balance"].first, years["water-balance"].last) == (2026, 2047)
    assert (years["food-security"].first, years["food-security"].last) == (2026, 2047)


def test_annual_land_classification_contract_is_authoritative():
    catalogue = load_catalogue(BACKEND_DIR / "catalogue.json")
    section = next(section for section in catalogue.sections if section.id == "land-cover")
    layer = next(layer for layer in catalogue.layers if layer.id == "annual-land-cover")

    assert (section.years.first, section.years.last, section.years.available) == (
        2017, 2023, list(range(2017, 2024)),
    )
    assert layer.years == section.years
    assert (layer.kind, layer.status, layer.section_id) == ("raster", "ready", "land-cover")
    assert layer.tile_source == "mpc"
    assert {
        item.value: (item.label, item.colour) for item in layer.legend.items
    } == ANNUAL_LAND_CLASSES
    assert layer.product is not None
    assert layer.product.model_dump() == {
        "provider": "Esri / Impact Observatory",
        "collection": "io-lulc-annual-v02",
        "version": "v02",
        "resolution_metres": 10,
        "area_unit": "hectares",
        "nodata_value": "0",
    }


def test_boundaries_are_loaded_from_the_prepared_files():
    client = _client()
    health = client.get("/api/health").json()
    assert health["boundaries_loaded"] is True
    assert health["boundaries_error"] is None
    places = client.get("/api/places").json()
    levels = [p["level"] for p in places]
    assert levels.count("province") == 8
    assert levels.count("district") == 167
    kashmir = next(p for p in places if p["id"] == "p-jammu-and-kashmir")
    assert kashmir["name"] == "Jammu and Kashmir"
    assert sum(1 for p in places if p["name"] == "Punjab") == 1
    punjab = next(p for p in places if p["name"] == "Punjab")
    assert punjab["id"] == "p-punjab"
    pakistan = next(p for p in places if p["id"] == "PK")
    assert pakistan["bbox"][2] > 79


def test_every_ready_section_serves_figures_and_charts():
    client = _client()
    for section_id, status in EXPECTED:
        if section_id in {"forecast", "crop-classification", "hazards"}:
            continue  # specialized interactive sections have no static figures or charts
        response = client.get(f"/api/sections/{section_id}/data")
        if status != "ready":
            assert response.json()["detail"]["reason"] == status
            continue
        body = response.json()
        assert response.status_code == 200, section_id
        assert body["figures"], section_id
        assert body["charts"], section_id
        for chart in body["charts"]:
            for series in chart["series"]:
                assert len(series["values"]) == len(chart["categories"]), chart["id"]
            assert chart["series"] or chart["kind"] in ("calendar", "shares", "diverging", "counts"), chart["id"]


def test_emissions_match_the_spreadsheet():
    body = _client().get("/api/sections/emissions/data", params={"year": 2025}).json()
    total = next(f for f in body["figures"] if f["label"] == "Total emissions")
    assert (total["value"], total["unit"]) == (572.45, "MtCO2e")
    assert body["year"] == 2025


def test_irrigation_figures_for_a_district_and_the_country():
    client = _client()
    country = client.get("/api/sections/irrigation/data").json()
    equipped = next(f for f in country["figures"] if f["label"] == "Land equipped for irrigation")
    assert round(equipped["value"], 2) == 41.33
    assert equipped["unit"] == "million acres"
    places = client.get("/api/places").json()
    thatta = next(p for p in places if p["name"] == "Thatta")
    district = client.get("/api/sections/irrigation/data", params={"place": thatta["id"]}).json()
    assert district["level_used"] == "district"
    figures = {f["label"]: f["value"] for f in district["figures"]}
    assert round(figures["Land equipped for irrigation"], 2) == round(376320 * 2.47105 / 1_000_000, 2)
    assert round(figures["Land actually irrigated"], 2) == round(143175 * 2.47105 / 1_000_000, 2)
    assert all(f["unit"] in ("million acres", "%") for f in district["figures"])


def test_irrigation_layers_are_served_and_match_their_legends():
    client = _client()
    catalogue = load_catalogue(BACKEND_DIR / "catalogue.json")
    by_id = {layer.id: layer for layer in catalogue.layers}
    practice = client.get("/api/layers/irrigation-practice/geojson").json()
    assert len(practice["features"]) == 577
    legend_values = {item.value for item in by_id["irrigation-practice"].legend.items}
    found = {f["properties"].get("practice") for f in practice["features"]} - {None}
    assert found <= legend_values
    # Every tehsil with a recommendation explains each practice in it.
    for feature in practice["features"]:
        props = feature["properties"]
        if props.get("practice"):
            assert len(props["table"]["rows"]) == len(props["practice"].split(",")), props["id"]
    for layer_id in IRRIGATION_LAYERS[1:]:
        collection = client.get(f"/api/layers/{layer_id}/geojson").json()
        assert len(collection["features"]) == 167
        values = [f["properties"]["value"] for f in collection["features"] if "value" in f["properties"]]
        assert len(values) >= 80, layer_id
        legend = by_id[layer_id].legend
        assert legend.min <= min(values) and max(values) <= legend.max, layer_id
    # The balance has districts on both sides of its neutral middle.
    balance = by_id["irrigation-balance"].legend
    assert balance.min < balance.mid == 0 < balance.max
    # Five districts are picked out at each end of the balance, and none on the other layers.
    marked = [f["properties"] for f in client.get("/api/layers/irrigation-balance/geojson").json()["features"]
              if "extreme" in f["properties"]]
    assert sorted(p["extreme"] for p in marked) == ["high"] * 5 + ["low"] * 5
    assert all((p["value"] > 0) == (p["extreme"] == "high") for p in marked)
    assert "Tharparkar" in {p["name"] for p in marked}
    surface = client.get("/api/layers/surface-water-area/geojson").json()["features"]
    assert not any("extreme" in f["properties"] for f in surface)


LAND_COVER = {"forest": {"2"}, "shrub-land": {"3"}, "bare-land": {"7"}, "irrigated-rainfed": {"2", "3"}}


def test_land_cover_layers_name_their_files_and_class_values():
    catalogue = load_catalogue(BACKEND_DIR / "catalogue.json")
    by_id = {layer.id: layer for layer in catalogue.layers}
    for layer_id, values in LAND_COVER.items():
        layer = by_id[layer_id]
        assert (layer.kind, layer.section_id, layer.source) == ("raster", "land-cover", f"{layer_id}.tif")
        assert {item.value for item in layer.legend.items} == values
        assert layer.max_zoom in (13, 14)


def test_each_land_cover_layer_is_ready_exactly_when_its_file_is_converted():
    client = _client()
    served = {layer["id"]: layer for layer in client.get("/api/catalogue").json()["layers"]}
    for layer_id in LAND_COVER:
        converted = (BACKEND_DIR / "rasters" / f"{layer_id}.tif").is_file()
        layer = served[layer_id]
        assert layer["status"] == ("ready" if converted else "no-data"), layer_id
        if converted:
            tile = client.get(layer["tile_url"].format(z=0, x=0, y=0))
            assert (tile.status_code, tile.headers["content-type"]) == (200, "image/png"), layer_id
        else:
            assert layer["tile_url"] is None


def test_real_headlines_read_as_findings():
    client = _client()
    titles = {
        chart["id"]: chart["title"]
        for section in ("emissions", "water-balance", "food-security", "irrigation")
        for chart in client.get(f"/api/sections/{section}/data").json()["charts"]
    }
    assert titles["emissions-by-gas"] == "Pakistan's annual emissions more than tripled since 1994"
    assert titles["emissions-growth"] == "Nitrous oxide grew fastest: 9.9 times its 1994 level"
    assert titles["water-buffer"] == "Higher efficiency protects the water buffer"
    assert titles["water-explorer"] == "Water stays enough to 2047 only if irrigation efficiency reaches 48%"
    assert titles["water-grid"] == "The efficiency that breaks even climbs from 42% in 2026 to 48% in 2047"
    assert titles["food-population"] == "Population grows from 255 to 386 million by 2047"
    assert titles["food-outlook"] == (
        "By 2047 climate smart agriculture adds 23.8 over traditional farming, yet 76.7 of the food needed is unmet"
    )
    assert titles["irrigation-source"] == "Where each province's irrigation water comes from"
    assert titles["irrigation-practices"] == (
        "Sprinkler irrigation is recommended in 480 of 558 tehsils; flood irrigation in only 25"
    )
    assert all(len(title) <= 110 for title in titles.values())


def test_land_cover_figures_come_from_the_rasters():
    client = _client()
    country = client.get("/api/sections/land-cover/data").json()
    figures = {f["label"]: f["value"] for f in country["figures"]}
    assert 222 < figures["Land area"] < 260
    assert 9.8 < figures["Forest"] < 22.3
    assert 37 < figures["Irrigated cropland"] < 59.5
    assert all(f["unit"] == "million acres" for f in country["figures"])
    places = client.get("/api/places").json()
    faisalabad = next(p for p in places if p["name"] == "Faisalabad")
    district = client.get("/api/sections/land-cover/data", params={"place": faisalabad["id"]}).json()
    assert district["level_used"] == "district"
    shares = next(c for c in district["charts"] if c["id"] == "land-cover-shares")
    assert shares["title"] == "How Faisalabad's land is classified"
    assert sum(cell["squares"] for cell in shares["cells"]) == 100
    # The country as a whole: what the charts say, from the real figures.
    titles = {c["id"]: c["title"] for c in country["charts"]}
    assert titles["land-cover-shares"] == "How Pakistan's land is classified"
    assert "Others" in [cell["label"] for cell in next(c for c in country["charts"] if c["id"] == "land-cover-shares")["cells"]]
    assert titles["land-cover-cropland"] == "Balochistan and Khyber Pakhtunkhwa farm mostly on rain"
    assert titles["land-cover-forest-ranking"] == (
        "Khyber Pakhtunkhwa and Jammu and Kashmir hold 58% of Pakistan's forest"
    )
    forest = next(c for c in country["charts"] if c["id"] == "land-cover-forest-ranking")
    assert forest["note"] == "Balochistan is 35% of Pakistan's land and holds 0.8% of its forest."
    assert all(len(title) <= 110 for title in titles.values())


def test_the_crop_calendar_covers_four_provinces():
    client = _client()
    country = client.get("/api/sections/climate-calendar/data").json()
    assert [chart["id"] for chart in country["charts"]] == [
        "calendar-punjab", "calendar-sindh", "calendar-khyber-pakhtunkhwa", "calendar-balochistan",
    ]
    figures = {f["label"]: f["value"] for f in country["figures"]}
    assert figures["Crops with a calendar"] == 20
    punjab = country["charts"][0]
    assert punjab["title"] == "In Punjab, 4 of 6 crops should be sown earlier than before"
    assert len(punjab["rows"]) == 6


def test_a_district_gets_its_province_calendar_not_the_national_one():
    client = _client()
    places = client.get("/api/places").json()
    lahore = next(p for p in places if p["name"] == "Lahore")
    body = client.get("/api/sections/climate-calendar/data", params={"place": lahore["id"]}).json()
    assert (body["place_id"], body["level_used"]) == ("p-punjab", "province")
    assert [chart["id"] for chart in body["charts"]] == ["calendar-punjab"]
    # A section with national figures only still falls back to the country.
    emissions = client.get("/api/sections/emissions/data", params={"place": lahore["id"]}).json()
    assert (emissions["place_id"], emissions["level_used"]) == ("PK", "national")


def test_the_shipped_forecast_layer_list_is_valid_and_served():
    from csa_portal.forecast import load_registry

    registry = load_registry(BACKEND_DIR / "forecast_layers.json")
    assert len(registry.layers) == 47
    assert {model.id for model in registry.models} == {
        "cma-gfs", "cma-gowfs", "pmd-icon", "pmd-wrf", "ecmwf-ifs", "fengqing", "pangu", "fengshun",
    }
    # Every level with its own value range is a level some model offers.
    for layer in registry.layers:
        offered = {level for levels in layer.levels.values() for level in levels}
        assert set(layer.ranges) <= offered, layer.id
    served = _client().get("/api/catalogue").json()["forecast"]
    fetched = [layer["id"] for layer in served["layers"]]
    # The derived frost model is appended after the layers fetched straight from PMD.
    assert fetched[:-1] == [layer.id for layer in registry.layers]
    assert fetched[-1] == "frost-degree-hours"
    without_data = [layer["id"] for layer in served["layers"] if not any(layer["levels"].values())]
    assert without_data == ["max-wind-10m", "cin", "theta-se", "vapour-transport"]


def test_every_live_section_turns_into_facts_for_a_district_and_the_country():
    from csa_portal.facts import Facts
    from csa_portal.places import load_places
    from csa_portal.sections import build_providers

    settings = Settings.from_env()
    catalogue = load_catalogue(settings.catalogue_path)
    places = load_places(settings.boundaries_dir)
    providers, _ = build_providers(settings.data_dir, settings.boundaries_dir)
    facts = Facts(catalogue, places, providers)
    faisalabad = next(p for p in places.places if p.name == "Faisalabad")
    for section in catalogue.sections:
        if section.id not in providers:
            continue
        for place_id in ("PK", faisalabad.id):
            answer = facts.section(section.id, place_id)
            assert answer.facts, (section.id, place_id)
            assert all(fact.source.startswith(section.title) for fact in answer.facts)
    # The water balance chart's values are facts that a grounding check can find.
    water = facts.section("water-balance", "PK", 2047)
    assert any(f.label == "35% efficiency" and f.value == -38.7 and f.when == "2047" for f in water.facts)
