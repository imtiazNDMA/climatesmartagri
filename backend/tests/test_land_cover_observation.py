"""The annual land-classification observation the map draws for a chosen year."""

import json
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi.testclient import TestClient

from csa_portal.land_cover_mpc import MpcLandCoverError, ResolvedLandCover
from csa_portal.main import create_app
from csa_portal.settings import Settings


class FakeResolver:
    """Stands in for the MPC resolver: one set of templates per year, and one failing year."""

    def __init__(self, failing: int | None = None):
        self.failing = failing
        self.calls: list[int] = []

    def resolve(self, year: int) -> ResolvedLandCover:
        self.calls.append(year)
        if year == self.failing:
            raise MpcLandCoverError(f"no land-classification items for {year}", "no-data")
        return ResolvedLandCover(
            year=year,
            collection="io-lulc-annual-v02",
            version="v02",
            item_ids=(f"42Q-{year}", f"43Q-{year}"),
            search_id=f"pc1.{year}.abc",
            bounds=(60.87, 23.81, 79.3, 37.09),
            attribution="Esri / Impact Observatory / Microsoft Planetary Computer",
            expires_at=0.0,
        )


def _catalogue() -> dict:
    return {
        "sections": [
            {"id": "land-cover", "title": "Land cover", "icon": "trees", "order": 1, "status": "ready",
             "place_levels": ["national"], "years": {"first": 2017, "last": 2023,
                                                    "available": [2017, 2018, 2019, 2020, 2021, 2022, 2023]}},
        ],
        "layers": [
            {"id": "annual-land-cover", "section_id": "land-cover", "title": "Annual land classification",
             "kind": "raster", "status": "ready", "tile_source": "mpc", "max_zoom": 14,
             "years": {"first": 2017, "last": 2023, "available": [2017, 2018, 2019, 2020, 2021, 2022, 2023]},
             "legend": {"type": "classes", "items": [
                 {"colour": "#419bdf", "label": "Water", "value": "1"},
                 {"colour": "#397d49", "label": "Trees", "value": "2"},
             ]}},
            {"id": "trees", "section_id": "land-cover", "title": "Trees",
             "kind": "raster", "status": "ready", "tile_source": "mpc", "max_zoom": 14,
             "years": {"first": 2017, "last": 2023, "available": [2017, 2018, 2019, 2020, 2021, 2022, 2023]},
             "legend": {"type": "classes", "items": [{"colour": "#397d49", "label": "Trees", "value": "2"}]}},
        ],
    }


def _client(tmp_path, resolver: FakeResolver | None = None) -> TestClient:
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(_catalogue()), encoding="utf-8")
    settings = Settings(path, tmp_path / "no-boundaries", "https://example.test/s.json")
    return TestClient(create_app(settings, land_cover=resolver or FakeResolver()))


def test_the_observation_defaults_to_the_latest_year(tmp_path):
    resolver = FakeResolver()
    body = _client(tmp_path, resolver).get("/api/land-cover/observation").json()

    assert body["year"] == 2023
    assert resolver.calls == [2023]
    assert body["search_id"] == "pc1.2023.abc"
    assert "tile_urls" not in body
    assert all(url.startswith("https://planetarycomputer.microsoft.com/") for url in body["tiles"].values())
    assert body["bounds"] == [60.87, 23.81, 79.3, 37.09]
    assert "Esri" in body["attribution"]


def test_a_chosen_year_resolves_that_year_only(tmp_path):
    resolver = FakeResolver()
    body = _client(tmp_path, resolver).get("/api/land-cover/observation?year=2019").json()

    assert body["year"] == 2019
    assert resolver.calls == [2019]
    assert all("/mosaic/pc1.2019.abc/" in url for url in body["tiles"].values())
    assert body["item_ids"] == ["42Q-2019", "43Q-2019"]


def test_each_year_has_its_own_templates(tmp_path):
    client = _client(tmp_path)
    first = client.get("/api/land-cover/observation?year=2017").json()
    second = client.get("/api/land-cover/observation?year=2018").json()
    assert first["tiles"] != second["tiles"]


def _colormap(url: str) -> dict:
    return json.loads(dict(parse_qsl(urlsplit(url).query))["colormap"])


def test_the_observation_gives_every_mpc_layer_its_own_template(tmp_path):
    body = _client(tmp_path).get("/api/land-cover/observation?year=2019").json()

    assert set(body["tiles"]) == {"annual-land-cover", "trees"}
    assert _colormap(body["tiles"]["annual-land-cover"]) == {"1": [65, 155, 223, 255], "2": [57, 125, 73, 255]}
    assert _colormap(body["tiles"]["trees"]) == {"2": [57, 125, 73, 255]}


def test_an_unsupported_year_is_refused(tmp_path):
    response = _client(tmp_path).get("/api/land-cover/observation?year=2024")
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "year-out-of-range"


def test_a_year_without_data_is_reported_as_missing(tmp_path):
    response = _client(tmp_path, FakeResolver(failing=2020)).get("/api/land-cover/observation?year=2020")
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "no-data"


def test_upstream_failures_are_reported_as_unavailable(tmp_path):
    class Broken:
        def resolve(self, year: int) -> ResolvedLandCover:
            raise MpcLandCoverError("Microsoft Planetary Computer is unavailable", "upstream-unavailable")

    response = _client(tmp_path, Broken()).get("/api/land-cover/observation?year=2020")
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "upstream-unavailable"


def test_the_catalogue_marks_the_layer_as_served_from_the_observation(tmp_path):
    layers = {layer["id"]: layer for layer in _client(tmp_path).get("/api/catalogue").json()["layers"]}
    layer = layers["annual-land-cover"]
    assert layer["tile_source"] == "mpc"
    assert layer["status"] == "ready"
    assert layer["tile_url"] is None
    assert layer["years"]["available"] == [2017, 2018, 2019, 2020, 2021, 2022, 2023]


def test_health_reports_the_observation_service(tmp_path):
    health = _client(tmp_path).get("/api/health").json()
    assert health["land_cover"]["status"] == "ready"
    assert health["land_cover"]["years"] == [2017, 2018, 2019, 2020, 2021, 2022, 2023]


def test_health_reports_a_service_that_cannot_start(tmp_path):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(_catalogue()), encoding="utf-8")
    settings = Settings(path, tmp_path / "no-boundaries", "https://example.test/s.json")
    client = TestClient(create_app(settings, land_cover=None, land_cover_error="no boundaries"))
    health = client.get("/api/health").json()
    assert health["land_cover"]["status"] == "unavailable"
    assert health["land_cover"]["error"] == "no boundaries"
    response = client.get("/api/land-cover/observation")
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "not-configured"


def test_the_outline_is_the_country_the_map_is_clipped_to(tmp_path):
    boundaries = tmp_path / "boundaries"
    boundaries.mkdir()
    provinces = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[60, 20], [70, 20], [70, 30], [60, 30], [60, 20]]]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[70, 20], [80, 20], [80, 30], [70, 30], [70, 20]]]}},
    ]}
    (boundaries / "provinces.geojson").write_text(json.dumps(provinces), encoding="utf-8")
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(_catalogue()), encoding="utf-8")
    client = TestClient(create_app(Settings(path, boundaries, "https://example.test/s.json"), land_cover=FakeResolver()))

    response = client.get("/api/land-cover/outline")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=86400"
    body = response.json()
    assert body["type"] == "Feature"
    assert body["geometry"]["type"] == "Polygon"
    xs = [x for x, _ in body["geometry"]["coordinates"][0]]
    assert (min(xs), max(xs)) == (pytest.approx(60), pytest.approx(80))


def test_without_boundaries_there_is_no_outline(tmp_path):
    response = _client(tmp_path).get("/api/land-cover/outline")
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "not-configured"
