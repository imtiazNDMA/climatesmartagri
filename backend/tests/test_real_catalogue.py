from fastapi.testclient import TestClient

from csa_portal.catalogue import load_catalogue
from csa_portal.main import create_app
from csa_portal.settings import BACKEND_DIR, Settings

EXPECTED = [
    ("land-cover", "no-data"),
    ("irrigation", "ready"),
    ("emissions", "ready"),
    ("water-balance", "ready"),
    ("food-security", "ready"),
    ("climate-calendar", "no-data"),
    ("hazards", "coming-soon"),
    ("exposure", "coming-soon"),
]
IRRIGATION_LAYERS = ["irrigation-practice", "irrigated-share", "equipped-area", "groundwater-share"]


def _client():
    return TestClient(create_app(Settings.from_env()))


def test_shipped_catalogue_is_valid_and_complete():
    catalogue = load_catalogue(BACKEND_DIR / "catalogue.json")
    ordered = sorted(catalogue.sections, key=lambda s: s.order)
    assert [(s.id, s.status) for s in ordered] == EXPECTED
    assert [s.order for s in ordered] == list(range(1, 9))
    assert all(s.summary for s in ordered if s.status == "coming-soon")
    boundary_ids = {layer.id for layer in catalogue.layers if layer.kind == "boundary"}
    assert boundary_ids == {"provinces", "districts"}
    by_id = {layer.id: layer for layer in catalogue.layers}
    for layer_id in IRRIGATION_LAYERS:
        assert (by_id[layer_id].kind, by_id[layer_id].status, by_id[layer_id].section_id) == (
            "geojson", "ready", "irrigation",
        )
    years = {s.id: s.years for s in catalogue.sections}
    assert (years["emissions"].first, years["emissions"].last) == (1994, 2021)
    assert (years["water-balance"].first, years["water-balance"].last) == (2026, 2047)
    assert (years["food-security"].first, years["food-security"].last) == (2026, 2047)


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


def test_emissions_match_the_spreadsheet():
    body = _client().get("/api/sections/emissions/data", params={"year": 2021}).json()
    total = next(f for f in body["figures"] if f["label"] == "Total emissions")
    assert (total["value"], total["unit"]) == (521.46, "MtCO2e")


def test_irrigation_figures_for_a_district_and_the_country():
    client = _client()
    country = client.get("/api/sections/irrigation/data").json()
    equipped = next(f for f in country["figures"] if f["label"] == "Land equipped for irrigation")
    assert round(equipped["value"]) == 16725843
    places = client.get("/api/places").json()
    thatta = next(p for p in places if p["name"] == "Thatta")
    district = client.get("/api/sections/irrigation/data", params={"place": thatta["id"]}).json()
    assert district["level_used"] == "district"
    figures = {f["label"]: f["value"] for f in district["figures"]}
    assert figures["Land equipped for irrigation"] == 376320
    assert figures["Land actually irrigated"] == 143175


def test_irrigation_layers_are_served_and_match_their_legends():
    client = _client()
    catalogue = load_catalogue(BACKEND_DIR / "catalogue.json")
    by_id = {layer.id: layer for layer in catalogue.layers}
    practice = client.get("/api/layers/irrigation-practice/geojson").json()
    assert len(practice["features"]) == 577
    legend_values = {item.value for item in by_id["irrigation-practice"].legend.items}
    found = {f["properties"].get("practice") for f in practice["features"]} - {None}
    assert found <= legend_values
    for layer_id in IRRIGATION_LAYERS[1:]:
        collection = client.get(f"/api/layers/{layer_id}/geojson").json()
        assert len(collection["features"]) == 167
        values = [f["properties"]["value"] for f in collection["features"] if "value" in f["properties"]]
        assert len(values) >= 80, layer_id
        legend = by_id[layer_id].legend
        assert legend.min <= min(values) and max(values) <= legend.max, layer_id


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
    assert titles["emissions-by-gas"] == "Pakistan's yearly emissions grew 2.9 times between 1994 and 2021"
    assert titles["emissions-growth"] == "Nitrous oxide grew fastest: 6.8 times its 1994 level"
    assert titles["water-need-vs-supply"] == (
        "At 35% efficiency, crops need more water than is available in every year to 2047"
    )
    assert titles["food-population"] == "Population grows from 255 to 386 million by 2047"
    assert titles["irrigation-ranking"].endswith("has the most irrigation-ready land of any province")
