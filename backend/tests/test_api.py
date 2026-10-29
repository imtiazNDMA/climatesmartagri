from dataclasses import replace

import pytest

from fastapi.testclient import TestClient

from csa_portal.main import create_app


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["boundaries_loaded"] is True
    assert body["layers"]["fake-yearly"] is True
    assert body["layers"]["fake-static"] is False
    assert body["layers"]["provinces"] is True


def test_catalogue(client):
    body = client.get("/api/catalogue").json()
    assert body["basemap_style_url"] == "https://example.test/style.json"
    assert [s["id"] for s in body["sections"]][:2] == ["alpha-section", "beta-section"]
    assert body["sections"][1]["years"] is None
    assert any(layer["id"] == "fake-yearly" for layer in body["layers"])


def test_places(client):
    body = client.get("/api/places").json()
    assert body[0] == {
        "id": "PK", "name": "Pakistan", "level": "national",
        "parent_id": None, "bbox": [66, 26, 74, 30],
    }
    assert {p["id"] for p in body} == {"PK", "PK1", "PK2", "PK101", "PK102", "PK201"}


def test_boundaries(client):
    body = client.get("/api/places/boundaries", params={"level": "district"}).json()
    assert body["type"] == "FeatureCollection"
    assert {f["properties"]["id"] for f in body["features"]} == {"PK101", "PK102", "PK201"}


def test_boundaries_bad_level(client):
    assert client.get("/api/places/boundaries", params={"level": "tehsil"}).status_code == 422


def test_boundaries_missing_returns_no_data(settings, tmp_path):
    app = create_app(replace(settings, boundaries_dir=tmp_path / "absent"))
    client = TestClient(app)
    assert client.get("/api/health").json()["boundaries_loaded"] is False
    response = client.get("/api/places/boundaries", params={"level": "province"})
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "no-data"
    assert [p["id"] for p in client.get("/api/places").json()] == ["PK"]


def test_tile_served_by_provider(client):
    response = client.get("/api/tiles/fake-yearly/3/5/2", params={"year": 2005})
    assert response.status_code == 200
    assert response.content == b"tile-3-5-2-2005"
    assert response.headers["content-type"] == "image/png"


def test_tile_unknown_layer(client):
    response = client.get("/api/tiles/ghost/0/0/0")
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "not-found"
    assert "ghost" in response.json()["detail"]["message"]


def test_tile_boundary_layer_is_not_a_tile_layer(client):
    assert client.get("/api/tiles/provinces/0/0/0").status_code == 404


def test_tile_no_data_and_coming_soon(client):
    no_data = client.get("/api/tiles/fake-empty/0/0/0")
    assert (no_data.status_code, no_data.json()["detail"]["reason"]) == (404, "no-data")
    soon = client.get("/api/tiles/fake-later/0/0/0")
    assert (soon.status_code, soon.json()["detail"]["reason"]) == (404, "coming-soon")


def test_tile_ready_layer_without_provider_is_no_data(client):
    response = client.get("/api/tiles/fake-static/0/0/0")
    assert (response.status_code, response.json()["detail"]["reason"]) == (404, "no-data")


def test_tile_year_out_of_range(client):
    response = client.get("/api/tiles/fake-yearly/0/0/0", params={"year": 1990})
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "year-out-of-range"


def test_tile_coordinates_out_of_range(client):
    for path in ("/api/tiles/fake-yearly/1/2/0", "/api/tiles/fake-yearly/1/0/2",
                 "/api/tiles/fake-yearly/-1/0/0", "/api/tiles/fake-yearly/40/0/0",
                 "/api/tiles/fake-yearly/2/-1/0"):
        response = client.get(path)
        assert response.status_code == 422, path
        assert response.json()["detail"]["reason"] == "bad-tile"


def test_tile_empty_from_provider_is_204(settings):
    app = create_app(settings, tile_providers={"fake-static": lambda z, x, y, year: None})
    assert TestClient(app).get("/api/tiles/fake-static/0/0/0").status_code == 204


def test_section_data_defaults(client):
    body = client.get("/api/sections/alpha-section/data").json()
    assert body["section_id"] == "alpha-section"
    assert body["place_id"] == "PK"
    assert body["level_used"] == "national"
    assert body["year"] == 2010
    assert body["figures"] == [{"label": "Place", "value": "PK", "unit": ""}]
    assert body["charts"] == []


def test_section_data_for_district_and_year(client):
    body = client.get(
        "/api/sections/alpha-section/data", params={"place": "PK101", "year": 2003}
    ).json()
    assert (body["place_id"], body["level_used"], body["year"]) == ("PK101", "district", 2003)


def test_section_data_falls_back_to_national(client):
    body = client.get("/api/sections/beta-section/data", params={"place": "PK101"}).json()
    assert body["place_id"] == "PK"
    assert body["level_used"] == "national"
    assert body["year"] is None


def test_section_data_unknown_section_and_place(client):
    section = client.get("/api/sections/ghost/data")
    assert section.status_code == 404
    assert "ghost" in section.json()["detail"]["message"]
    place = client.get("/api/sections/alpha-section/data", params={"place": "XX"})
    assert place.status_code == 404
    assert "XX" in place.json()["detail"]["message"]


def test_section_data_year_out_of_range(client):
    response = client.get("/api/sections/alpha-section/data", params={"year": 2011})
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "year-out-of-range"


def test_section_data_no_data_and_coming_soon(client):
    empty = client.get("/api/sections/empty-section/data")
    assert (empty.status_code, empty.json()["detail"]["reason"]) == (404, "no-data")
    later = client.get("/api/sections/later-section/data")
    assert (later.status_code, later.json()["detail"]["reason"]) == (404, "coming-soon")


def test_shell_has_no_providers(bare_client):
    data = bare_client.get("/api/sections/alpha-section/data")
    assert (data.status_code, data.json()["detail"]["reason"]) == (404, "no-data")
    tile = bare_client.get("/api/tiles/fake-yearly/0/0/0")
    assert (tile.status_code, tile.json()["detail"]["reason"]) == (404, "no-data")


@pytest.mark.parametrize("content", ["{oops", '{"type": "FeatureCollection", "features": [42]}'])
def test_unusable_boundary_file_does_not_stop_the_backend(settings, tmp_path, content):
    (tmp_path / "provinces.geojson").write_text(content, encoding="utf-8")
    client = TestClient(create_app(replace(settings, boundaries_dir=tmp_path)))
    health = client.get("/api/health").json()
    assert health["boundaries_loaded"] is False
    assert "provinces.geojson" in health["boundaries_error"]
    assert [p["id"] for p in client.get("/api/places").json()] == ["PK"]
    response = client.get("/api/places/boundaries", params={"level": "province"})
    assert response.json()["detail"]["reason"] == "no-data"
    assert client.get("/api/catalogue").status_code == 200


def test_health_has_no_boundary_error_when_boundaries_load(client):
    assert client.get("/api/health").json()["boundaries_error"] is None


def test_section_data_carries_notes(client):
    assert client.get("/api/sections/alpha-section/data").json()["notes"] == ["A note"]


def test_geojson_layer_is_served(client):
    response = client.get("/api/layers/fake-shapes/geojson")
    assert response.status_code == 200
    assert response.json() == {"type": "FeatureCollection", "features": []}


def test_geojson_route_errors(client, bare_client):
    unknown = client.get("/api/layers/ghost/geojson")
    assert (unknown.status_code, unknown.json()["detail"]["reason"]) == (404, "not-found")
    raster = client.get("/api/layers/fake-yearly/geojson")
    assert (raster.status_code, raster.json()["detail"]["reason"]) == (404, "not-found")
    unprovided = bare_client.get("/api/layers/fake-shapes/geojson")
    assert (unprovided.status_code, unprovided.json()["detail"]["reason"]) == (404, "no-data")


def test_geojson_layers_are_not_tile_layers(client):
    response = client.get("/api/tiles/fake-shapes/0/0/0")
    assert (response.status_code, response.json()["detail"]["reason"]) == (404, "not-found")


def test_health_reports_geojson_layers(client, bare_client):
    assert client.get("/api/health").json()["layers"]["fake-shapes"] is True
    assert bare_client.get("/api/health").json()["layers"]["fake-shapes"] is False


def test_providers_default_to_the_data_folder(settings, tmp_path):
    """With no providers passed in, the app builds them from the data folder (here: an empty one)."""
    client = TestClient(create_app(replace(settings, data_dir=tmp_path)))
    response = client.get("/api/sections/alpha-section/data")
    assert response.json()["detail"]["reason"] == "no-data"
