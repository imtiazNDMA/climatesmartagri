"""Land-cover rasters served by TiTiler, mounted inside the portal's backend."""

import json
import sys
import warnings
from pathlib import Path

import morecantile
import numpy as np
import pytest
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile

from csa_portal.catalogue import CatalogueError, load_catalogue
from csa_portal.main import create_app
from csa_portal.settings import Settings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prepare_rasters import convert  # noqa: E402
from test_prepare_rasters import write_plain_raster  # noqa: E402

FOREST = (46, 125, 50, 255)  # #2e7d32
TILE_URL = "/api/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?layer=forest"


def _catalogue(extra_layers=()):
    return {
        "sections": [
            {"id": "land-cover", "title": "Land cover", "icon": "trees", "order": 1, "status": "ready",
             "place_levels": ["national"]},
        ],
        "layers": [
            {"id": "forest", "section_id": "land-cover", "title": "Forest cover", "kind": "raster",
             "status": "ready", "source": "forest.tif", "max_zoom": 14,
             "legend": {"type": "classes", "items": [{"colour": "#2e7d32", "label": "Forest", "value": "2"}]}},
            {"id": "shrub-land", "section_id": "land-cover", "title": "Shrub land", "kind": "raster",
             "status": "ready", "source": "shrub-land.tif",
             "legend": {"type": "classes", "items": [{"colour": "#9ccc65", "label": "Shrub", "value": "3"}]}},
            {"id": "plain", "section_id": "land-cover", "title": "No source", "kind": "raster", "status": "ready",
             "legend": {"type": "classes", "items": [{"colour": "#000000", "label": "x"}]}},
            *extra_layers,
        ],
    }


@pytest.fixture(scope="module")
def rasters(tmp_path_factory):
    """A rasters folder holding one converted file: forest.tif. shrub-land.tif is deliberately absent."""
    folder = tmp_path_factory.mktemp("rasters")
    plain = folder / "plain-source.tif"
    write_plain_raster(plain)  # value 2 over lon 70.2-70.7, lat 29.6-29.9; nodata elsewhere in 70-71.2, 28.8-30
    convert(plain, folder / "forest.tif")
    plain.unlink()
    return folder


@pytest.fixture
def client(rasters, tmp_path):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(_catalogue()), encoding="utf-8")
    settings = Settings(path, tmp_path / "no-boundaries", "https://example.test/s.json", tmp_path / "no-data", rasters)
    return TestClient(create_app(settings))


def _layers(client):
    return {layer["id"]: layer for layer in client.get("/api/catalogue").json()["layers"]}


def _tile(lon, lat, zoom):
    tile = morecantile.tms.get("WebMercatorQuad").tile(lon, lat, zoom)
    return TILE_URL.format(z=tile.z, x=tile.x, y=tile.y)


def _pixels(response):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a PNG has no map position, which rasterio remarks on
        with MemoryFile(response.content) as memory, memory.open() as image:
            return np.moveaxis(image.read(), 0, -1)


def test_a_converted_raster_is_ready_and_says_where_its_tiles_are(client):
    forest = _layers(client)["forest"]
    assert forest["status"] == "ready"
    assert forest["tile_url"] == TILE_URL
    assert forest["max_zoom"] == 14
    assert client.get("/api/health").json()["layers"]["forest"] is True


def test_a_raster_that_is_not_converted_yet_is_not_ready(client):
    shrub = _layers(client)["shrub-land"]
    assert shrub["status"] == "no-data"
    assert shrub["tile_url"] is None
    assert client.get("/api/health").json()["layers"]["shrub-land"] is False


def test_a_raster_layer_without_a_source_is_left_alone(client):
    plain = _layers(client)["plain"]
    assert plain["status"] == "ready"
    assert plain["tile_url"] is None


def test_tiles_are_coloured_from_the_legend_and_clear_elsewhere(client):
    response = client.get(_tile(70.45, 29.75, 9))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    pixels = _pixels(response).reshape(-1, 4)
    colours = {tuple(int(v) for v in pixel) for pixel in pixels}
    assert FOREST in colours
    assert all(colour == FOREST or colour[3] == 0 for colour in colours)
    assert any(colour[3] == 0 for colour in colours)


def test_the_whole_world_tile_works_so_the_layer_can_be_checked_cheaply(client):
    response = client.get(TILE_URL.format(z=0, x=0, y=0))
    assert response.status_code == 200


def test_a_tile_outside_the_raster_is_not_found(client):
    assert client.get(_tile(-100.0, 40.0, 9)).status_code == 404


def test_tile_errors_name_the_problem(client):
    unknown = client.get(TILE_URL.replace("layer=forest", "layer=ghost").format(z=0, x=0, y=0))
    assert unknown.status_code == 404
    assert "ghost" in unknown.json()["detail"]["message"]
    unconverted = client.get(TILE_URL.replace("layer=forest", "layer=shrub-land").format(z=0, x=0, y=0))
    assert (unconverted.status_code, unconverted.json()["detail"]["reason"]) == (404, "no-data")
    no_source = client.get(TILE_URL.replace("layer=forest", "layer=plain").format(z=0, x=0, y=0))
    assert no_source.status_code == 404
    missing = client.get("/api/cog/tiles/WebMercatorQuad/0/0/0.png")
    assert missing.status_code == 422


def test_a_file_path_cannot_be_passed_in_place_of_a_layer(client, rasters):
    """TiTiler normally takes any file path or URL; the portal only serves catalogue layers."""
    by_url = client.get("/api/cog/tiles/WebMercatorQuad/0/0/0.png", params={"url": str(rasters / "forest.tif")})
    assert by_url.status_code == 422
    by_layer = client.get("/api/cog/tiles/WebMercatorQuad/0/0/0.png", params={"layer": str(rasters / "forest.tif")})
    assert by_layer.status_code == 404


def test_a_source_must_be_a_plain_file_name(tmp_path):
    for bad in ["../secret.tif", "C:/data/x.tif", "sub/x.tif", "x.png", ""]:
        data = _catalogue()
        data["layers"][0]["source"] = bad
        path = tmp_path / "catalogue.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(CatalogueError):
            load_catalogue(path)


def test_only_raster_layers_may_have_a_source(tmp_path):
    shapes = {"id": "shapes", "section_id": "land-cover", "title": "Shapes", "kind": "geojson", "status": "ready",
              "property": "p", "source": "x.tif",
              "legend": {"type": "classes", "items": [{"colour": "#000000", "label": "x"}]}}
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(_catalogue([shapes])), encoding="utf-8")
    with pytest.raises(CatalogueError, match="shapes"):
        load_catalogue(path)


def test_a_tile_may_be_kept_by_the_browser_for_an_hour_and_a_failure_not_at_all(client):
    assert client.get(_tile(70.4, 29.7, 9)).headers["cache-control"] == "public, max-age=3600"
    missing = client.get(TILE_URL.format(z=0, x=0, y=0).replace("layer=forest", "layer=shrub-land"))
    assert (missing.status_code, missing.headers["cache-control"]) == (404, "no-store")
