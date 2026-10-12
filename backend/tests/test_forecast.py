"""Weather forecast layers: listed from PMD, fetched on first use, stored, and served by TiTiler."""

import io
import json
from datetime import datetime

import morecantile
import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from csa_portal.forecast import (
    ForecastError,
    ForecastService,
    RegistryError,
    cache_control,
    convert,
    load_registry,
    ramp_colourmap,
)
from csa_portal.main import create_app
from csa_portal.pmd import PmdError, PmdFile
from csa_portal.settings import Settings

RUN_OLD = datetime(2026, 10, 8, 12)
RUN_NEW = datetime(2026, 10, 9, 0)
T0, T1, T2 = datetime(2026, 10, 9, 0), datetime(2026, 10, 9, 6), datetime(2026, 10, 9, 12)

REGISTRY = {
    "bbox": [60, 20, 80, 40],
    "models": [
        {"id": "model-a", "label": "Model A", "source": "SRCA"},
        {"id": "model-b", "label": "Model B", "source": "SRCB"},
    ],
    "groups": [{"id": "heat", "title": "Heat"}, {"id": "air", "title": "Air"}],
    "layers": [
        {"id": "temperature", "title": "Temperature", "group": "heat", "code": "TEM", "unit": "°C",
         "colours": ["#0000ff", "#ff0000"], "min": 0, "max": 40, "ranges": {"500": {"min": -40, "max": 0}},
         "levels": {"model-a": [0, 500], "model-b": [0]}},
        {"id": "wind", "title": "Wind speed", "group": "air", "code": "UV", "unit": "m/s", "wind": True,
         "colours": ["#ffffff", "#000000"], "min": 0, "max": 50, "levels": {"model-a": [0]}},
        {"id": "rain", "title": "Rain", "group": "air", "code": "PRE", "unit": "mm", "hide_below": 1,
         "colours": ["#ffffff", "#0000ff"], "min": 0, "max": 100, "levels": {"model-a": [0]}},
        {"id": "showers", "title": "Showers", "group": "air", "code": "SHW", "unit": "mm",
         "colours": ["#ffffff", "#0000ff", "#000000"], "min": 0, "max": 100, "stops": [0, 10, 100],
         "levels": {"model-a": [0]}},
        {"id": "moisture", "title": "Moisture", "group": "air", "code": "SHU", "unit": "g/kg",
         "colours": ["#ffffff", "#0000ff"], "min": 0, "max": 20, "model_factors": {"model-b": 1000},
         "model_ranges": {"model-b": {"min": 0, "max": 10}}, "ignore_above": 500,
         "levels": {"model-a": [0], "model-b": [0]}},
        {"id": "old-only", "title": "Old only", "group": "air", "code": "OLD",
         "colours": ["#ffffff", "#0000ff"], "min": 0, "max": 1, "levels": {}},
    ],
}


def tif(values, west=50.0, north=50.0, cell=1.0, scale=10, nodata=-9999):
    """A GeoTIFF as PMD writes them: whole numbers that are the true values times `scale`."""
    bands = np.asarray(values, dtype="float64")
    if bands.ndim == 2:
        bands = bands[np.newaxis]
    stored = np.where(np.isnan(bands), nodata, np.rint(bands * scale)).astype("int16")
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff", width=stored.shape[2], height=stored.shape[1], count=stored.shape[0], dtype="int16",
            crs="EPSG:4326", transform=from_origin(west, north, cell, cell), nodata=nodata,
        ) as target:
            target.write(stored)
            target.update_tags(scale=str(scale), offset="0", unit="x")
        return memory.read()


def field(value, size=40):
    """A 40-degree square from 50E, 50N down to 90E, 10N, the same value everywhere."""
    return np.full((size, size), float(value))


class FakeSource:
    """Stands in for PMD: runs and files by (source, element, level), file contents by path."""

    def __init__(self):
        self.listing = {}
        self.contents = {}
        self.downloads = []
        self.attempts = 0
        self.listed = 0
        self.down = False

    def add(self, source, element, level, run, valid, data):
        path = f"/static/{source}/{run:%Y%m%d%H}/{element}/{valid:%Y%m%d%H}_{level}.tif"
        self.listing.setdefault((source, element), {}).setdefault(run, {}).setdefault(level, []).append(
            PmdFile(run=run, valid=valid, path=path)
        )
        self.contents[path] = data
        return path

    def runs(self, source, element):
        self.listed += 1
        if self.down:
            raise PmdError("down")
        return sorted(self.listing.get((source, element), {}), reverse=True)

    def files(self, source, element, level, run):
        if self.down:
            raise PmdError("down")
        return list(self.listing.get((source, element), {}).get(run, {}).get(level, []))

    def download(self, path):
        self.attempts += 1
        if self.down:
            raise PmdError("down")
        self.downloads.append(path)
        return self.contents[path]


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "forecast_layers.json"
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    return load_registry(path)


@pytest.fixture
def source():
    fake = FakeSource()
    fake.add("SRCA", "TEM", 0, RUN_OLD, T0, tif(field(10)))
    fake.add("SRCA", "TEM", 0, RUN_OLD, T1, tif(field(10)))
    fake.add("SRCA", "TEM", 0, RUN_NEW, T1, tif(field(40)))
    fake.add("SRCA", "TEM", 0, RUN_NEW, T2, tif(field(0)))
    return fake


@pytest.fixture
def service(registry, source, tmp_path):
    return ForecastService(registry, source, tmp_path / "cache")


def stored(path):
    with rasterio.open(path) as ds:
        return ds.read(1), ds.bounds, ds.nodata


# --- the layer list


def test_registry_rejects_a_layer_naming_an_unknown_model(tmp_path):
    bad = json.loads(json.dumps(REGISTRY))
    bad["layers"][0]["levels"]["model-z"] = [0]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(RegistryError, match="unknown model 'model-z'"):
        load_registry(path)


def test_registry_rejects_an_unknown_group_and_a_missing_file(tmp_path):
    bad = json.loads(json.dumps(REGISTRY))
    bad["layers"][0]["group"] = "nowhere"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(RegistryError, match="unknown group"):
        load_registry(path)
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "absent.json")


def test_colourmap_runs_from_the_first_colour_to_the_last():
    colours = ramp_colourmap(["#0000ff", "#ff0000"])
    assert set(colours) == set(range(1, 256))
    assert colours[1] == (0, 0, 255, 255)
    assert colours[255] == (255, 0, 0, 255)
    assert colours[128][0] == pytest.approx(127, abs=2)


# --- which run is shown


def test_times_take_each_time_from_the_newest_run_that_has_it(service):
    slots = service.times("temperature", "model-a", 0)
    assert [(s.valid, s.run) for s in slots] == [(T0, RUN_OLD), (T1, RUN_NEW), (T2, RUN_NEW)]


class Later:
    """Collects the work the service would do in the background, to run when the test says."""

    def __init__(self):
        self.work = []

    def __call__(self, work):
        self.work.append(work)

    def run(self):
        for work in self.work[:]:
            self.work.remove(work)
            work()


@pytest.fixture
def timed(registry, source, tmp_path):
    """A service with a clock the test sets and background work the test runs."""
    now = [1000.0]
    later = Later()
    service = ForecastService(registry, source, tmp_path / "cache", clock=lambda: now[0], background=later)
    return service, now, later


def test_a_fresh_list_is_used_without_asking_pmd_again(timed, source):
    service, now, later = timed
    assert len(service.times("temperature", "model-a", 0)) == 3
    source.add("SRCA", "TEM", 0, RUN_NEW, datetime(2026, 10, 9, 18), tif(field(5)))
    now[0] += 599
    assert len(service.times("temperature", "model-a", 0)) == 3
    assert source.listed == 1 and later.work == []


def test_a_stale_list_is_handed_out_at_once_and_refreshed_behind(timed, source):
    service, now, later = timed
    service.times("temperature", "model-a", 0)
    source.add("SRCA", "TEM", 0, RUN_NEW, datetime(2026, 10, 9, 18), tif(field(5)))
    now[0] += 601
    assert len(service.times("temperature", "model-a", 0)) == 3  # the old list, with no wait
    assert len(service.times("temperature", "model-a", 0)) == 3
    assert len(later.work) == 1  # one refresh for the two requests
    later.run()
    assert len(service.times("temperature", "model-a", 0)) == 4
    assert source.listed == 2 and later.work == []


def test_a_refresh_that_fails_keeps_the_old_list_and_is_not_retried_at_once(timed, source):
    service, now, later = timed
    service.times("temperature", "model-a", 0)
    source.down = True
    now[0] += 601
    service.times("temperature", "model-a", 0)
    later.run()
    assert len(service.times("temperature", "model-a", 0)) == 3
    assert later.work == []  # asked again within the minute: no new attempt
    now[0] += 61
    service.times("temperature", "model-a", 0)
    assert len(later.work) == 1


def test_the_list_survives_a_restart_even_with_pmd_down(registry, source, tmp_path):
    ForecastService(registry, source, tmp_path / "cache").times("temperature", "model-a", 0)
    source.down = True
    restarted = ForecastService(registry, source, tmp_path / "cache", background=lambda work: None)
    slots = restarted.times("temperature", "model-a", 0)
    assert [(s.valid, s.run) for s in slots] == [(T0, RUN_OLD), (T1, RUN_NEW), (T2, RUN_NEW)]
    assert source.listed == 1


def test_a_damaged_saved_list_is_ignored(registry, source, tmp_path):
    ForecastService(registry, source, tmp_path / "cache").times("temperature", "model-a", 0)
    saved = next((tmp_path / "cache" / "_listings").glob("*.json"))
    saved.write_text("{not json", encoding="utf-8")
    assert len(ForecastService(registry, source, tmp_path / "cache").times("temperature", "model-a", 0)) == 3
    assert source.listed == 2


def test_an_old_list_is_served_while_pmd_is_down(registry, source, tmp_path):
    now = [0.0]
    service = ForecastService(registry, source, tmp_path / "cache", clock=lambda: now[0])
    service.times("temperature", "model-a", 0)
    source.down = True
    now[0] = 5000
    assert len(service.times("temperature", "model-a", 0)) == 3


def test_pmd_down_with_nothing_remembered_is_reported(service, source):
    source.down = True
    with pytest.raises(ForecastError) as caught:
        service.times("temperature", "model-a", 0)
    assert (caught.value.status, caught.value.reason) == (424, "source-unreachable")


@pytest.mark.parametrize(
    ("layer", "model", "level"),
    [("nope", "model-a", 0), ("temperature", "nope", 0), ("temperature", "model-b", 500), ("old-only", "model-a", 0)],
)
def test_a_choice_the_list_does_not_offer_is_not_found(service, layer, model, level):
    with pytest.raises(ForecastError) as caught:
        service.times(layer, model, level)
    assert (caught.value.status, caught.value.reason) == (404, "not-found")


def test_without_a_pmd_account_the_forecast_says_it_is_not_set_up(registry, tmp_path):
    service = ForecastService(registry, None, tmp_path / "cache")
    assert service.describe()["configured"] is False
    with pytest.raises(ForecastError) as caught:
        service.times("temperature", "model-a", 0)
    assert (caught.value.status, caught.value.reason) == (501, "not-configured")


# --- fetching and storing


def test_a_file_is_fetched_once_cut_to_the_kept_area_and_stored_as_colour_positions(service, source):
    path = service.file("temperature", "model-a", 0, T1)
    values, bounds, nodata = stored(path)
    assert tuple(bounds) == (60, 20, 80, 40)
    assert nodata == 0
    assert set(np.unique(values)) == {255}  # 40 degrees, the top of a 0-40 range
    assert service.file("temperature", "model-a", 0, T1) == path
    assert len(source.downloads) == 1
    assert "2026100900" in source.downloads[0]  # the newer run's file


def test_the_bottom_of_the_range_is_position_one_not_empty(service):
    values, _, _ = stored(service.file("temperature", "model-a", 0, T2))
    assert set(np.unique(values)) == {1}


def test_a_level_with_its_own_range_is_scaled_by_it(service, source):
    source.add("SRCA", "TEM", 500, RUN_NEW, T1, tif(field(-20)))
    values, _, _ = stored(service.file("temperature", "model-a", 500, T1))
    assert set(np.unique(values)) == {128}  # -20 is halfway through -40 to 0


def test_a_time_no_run_has_is_no_data(service):
    with pytest.raises(ForecastError) as caught:
        service.file("temperature", "model-a", 0, datetime(2026, 10, 20, 0))
    assert (caught.value.status, caught.value.reason) == (404, "no-data")


def test_wind_is_stored_as_speed_from_its_two_components(service, source):
    source.add("SRCA", "UV", 0, RUN_NEW, T1, tif([field(3), field(4)]))
    values, _, _ = stored(service.file("wind", "model-a", 0, T1))
    assert set(np.unique(values)) == {1 + round(5 / 50 * 254)}


def test_missing_cells_and_values_under_the_threshold_are_left_empty(service, source):
    rain = field(50)
    rain[:, :20] = 0.4  # under the 1 mm threshold: west half, 50E to 70E
    rain[25:, :] = np.nan  # no value: south of 25N
    source.add("SRCA", "PRE", 0, RUN_NEW, T1, tif(rain))
    values, bounds, _ = stored(service.file("rain", "model-a", 0, T1))
    assert tuple(bounds) == (60, 20, 80, 40)
    assert (values[:, :10] == 0).all()  # 60E to 70E: too little rain
    assert (values[:15, 10:] == 128).all()  # 70E to 80E north of 25N: 50 of 100
    assert (values[15:, :] == 0).all()  # south of 25N: no value


def test_a_model_covering_part_of_the_kept_area_is_stored_over_all_of_it(service, source):
    # A regional grid from 70E, 35N down to 90E, 15N: it misses the kept area's west and its far north.
    source.add("SRCA", "TEM", 0, RUN_NEW, datetime(2026, 10, 9, 18), tif(field(40, size=20), west=70, north=35))
    values, bounds, _ = stored(service.file("temperature", "model-a", 0, datetime(2026, 10, 9, 18)))
    assert tuple(bounds) == (60, 20, 80, 40)
    assert (values[5:, 10:] == 255).all()  # 70E to 80E, south of 35N
    assert (values[:5, :] == 0).all() and (values[:, :10] == 0).all()


def test_stops_put_each_colour_at_its_own_value(service, source):
    showers = field(10)  # the middle colour's value: halfway along the colours, though a tenth of the range
    showers[:, 20:] = 55  # halfway between the middle and last colours' values
    source.add("SRCA", "SHW", 0, RUN_NEW, T1, tif(showers))
    path = service.file("showers", "model-a", 0, T1)
    values, _, _ = stored(path)
    assert set(np.unique(values[:, :10])) == {128}
    assert set(np.unique(values[:, 10:])) == {1 + round(254 * 0.75)}
    assert path.name.endswith("_0_10_100.tif")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"stops": [0, 100]}, "one rising stop per colour"),
        ({"stops": [0, 50, 20]}, "one rising stop per colour"),
        ({"stops": [1, 10, 100]}, "from min to max"),
        ({"ranges": {"500": {"min": 0, "max": 5}}}, "from min to max"),
        ({"model_ranges": {"model-a": {"min": 0, "max": 5}}}, "from min to max"),
    ],
)
def test_registry_rejects_stops_that_do_not_fit_the_colours(tmp_path, change, message):
    bad = json.loads(json.dumps(REGISTRY))
    next(layer for layer in bad["layers"] if layer["id"] == "showers").update(change)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(RegistryError, match=message):
        load_registry(path)


def test_a_model_in_other_units_is_brought_into_line_and_can_have_its_own_range(service, source):
    source.add("SRCA", "SHU", 0, RUN_NEW, T1, tif(field(10)))  # grams per kilogram, range 0 to 20
    source.add("SRCB", "SHU", 0, RUN_NEW, T1, tif(field(0.005), scale=10000))  # kilograms per kilogram, 0 to 10
    a = service.file("moisture", "model-a", 0, T1)
    b = service.file("moisture", "model-b", 0, T1)
    assert set(np.unique(stored(a)[0])) == {128}
    assert set(np.unique(stored(b)[0])) == {128}
    assert a.name.endswith("_0_20.tif") and b.name.endswith("_0_10_x1000.tif")


def test_a_files_nothing_here_marker_is_left_empty(service, source):
    marked = field(10)
    marked[:, 20:] = 3000  # stored as 30000 with the scale of ten: a marker, not a measurement
    source.add("SRCA", "SHU", 0, RUN_NEW, T2, tif(marked))
    values, _, _ = stored(service.file("moisture", "model-a", 0, T2))
    assert set(np.unique(values[:, :10])) == {128}
    assert (values[:, 10:] == 0).all()


# --- files by run, and what is remembered about failures


def test_a_stored_file_is_served_by_its_run_with_pmd_down_and_no_list(registry, source, tmp_path):
    first = ForecastService(registry, source, tmp_path / "cache")
    path = first.file("temperature", "model-a", 0, T1, RUN_NEW)
    for saved in (tmp_path / "cache" / "_listings").glob("*.json"):
        saved.unlink()
    source.down = True
    restarted = ForecastService(registry, source, tmp_path / "cache")
    assert restarted.file("temperature", "model-a", 0, T1, RUN_NEW) == path
    assert source.listed == 1  # the restarted service asked PMD nothing


def test_an_older_runs_file_can_still_be_asked_for_by_name(service, source):
    newest = service.file("temperature", "model-a", 0, T1)
    older = service.file("temperature", "model-a", 0, T1, RUN_OLD)
    assert newest != older
    assert set(np.unique(stored(newest)[0])) == {255}  # 40 degrees in the newer run
    assert set(np.unique(stored(older)[0])) == {1 + round(10 / 40 * 254)}  # 10 degrees in the older


def test_a_run_that_never_had_the_time_is_no_data(service):
    with pytest.raises(ForecastError) as caught:
        service.file("temperature", "model-a", 0, T2, RUN_OLD)
    assert (caught.value.status, caught.value.reason) == (404, "no-data")


def test_a_failed_fetch_is_remembered_for_a_minute_then_tried_again(timed, source):
    service, now, _ = timed
    service.times("temperature", "model-a", 0)
    source.down = True
    for _ in range(3):  # the tiles of one map view, all wanting the same file
        with pytest.raises(ForecastError) as caught:
            service.file("temperature", "model-a", 0, T1)
        assert caught.value.reason == "source-unreachable"
    assert source.attempts == 1
    source.down = False
    now[0] += 61
    assert service.file("temperature", "model-a", 0, T1).is_file()
    assert source.attempts == 2


def test_a_file_that_is_no_use_is_not_fetched_again_for_ten_minutes(timed, source):
    service, now, _ = timed
    source.add("SRCA", "TEM", 0, RUN_NEW, datetime(2026, 10, 9, 18), b"not a tiff")
    for _ in range(2):
        with pytest.raises(ForecastError):
            service.file("temperature", "model-a", 0, datetime(2026, 10, 9, 18))
    now[0] += 61
    with pytest.raises(ForecastError):
        service.file("temperature", "model-a", 0, datetime(2026, 10, 9, 18))
    assert source.attempts == 1
    now[0] += 600
    with pytest.raises(ForecastError):
        service.file("temperature", "model-a", 0, datetime(2026, 10, 9, 18))
    assert source.attempts == 2


def test_a_file_outside_the_kept_area_is_no_data(registry, tmp_path):
    with pytest.raises(ForecastError) as caught:
        convert(tif(field(1), west=-120), tmp_path / "x.tif", registry.layers[0], 0, registry.bbox)
    assert caught.value.reason == "no-data"
    assert not list(tmp_path.glob("x.tif*")) and not list(tmp_path.glob("*.part"))


def test_a_file_that_is_not_a_raster_is_reported_and_leaves_nothing_behind(service, source, tmp_path):
    path = source.add("SRCA", "TEM", 0, RUN_NEW, datetime(2026, 10, 9, 18), b"not a tiff")
    assert path
    with pytest.raises(ForecastError) as caught:
        service.file("temperature", "model-a", 0, datetime(2026, 10, 9, 18))
    assert (caught.value.status, caught.value.reason) == (424, "bad-source")
    assert not list((tmp_path / "cache").rglob("*.tif")) and not list((tmp_path / "cache").rglob("*.part"))


# --- over HTTP


def _catalogue(with_forecast=True):
    sections = [{"id": "plain", "title": "Plain", "icon": "trees", "order": 1, "status": "ready",
                 "place_levels": ["national"]}]
    if with_forecast:
        sections.append({"id": "forecast", "title": "Weather forecast", "icon": "cloud-sun", "order": 2,
                         "status": "ready", "kind": "forecast", "place_levels": ["national"]})
    return {"sections": sections, "layers": []}


def _client(tmp_path, source, with_forecast=True):
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(json.dumps(_catalogue(with_forecast)), encoding="utf-8")
    layers = tmp_path / "forecast_layers.json"
    layers.write_text(json.dumps(REGISTRY), encoding="utf-8")
    settings = Settings(
        catalogue, tmp_path / "no-boundaries", "https://example.test/s.json", tmp_path / "no-data",
        tmp_path / "no-rasters", forecast_layers_path=layers, forecast_dir=tmp_path / "cache",
    )
    return TestClient(create_app(settings, forecast_source=source))


@pytest.fixture
def client(tmp_path, source):
    return _client(tmp_path, source)


def test_the_catalogue_carries_the_forecast_layer_list(client):
    forecast = client.get("/api/catalogue").json()["forecast"]
    assert forecast["configured"] is True
    assert forecast["bbox"] == [60, 20, 80, 40]
    assert [m["id"] for m in forecast["models"]] == ["model-a", "model-b"]
    temperature = forecast["layers"][0]
    assert temperature["levels"] == {"model-a": [0, 500], "model-b": [0]}
    assert temperature["ranges"] == {"500": [-40, 0]}
    assert temperature["stops"] is None
    assert next(l for l in forecast["layers"] if l["id"] == "moisture")["model_ranges"] == {"model-b": [0, 10]}
    assert next(l for l in forecast["layers"] if l["id"] == "showers")["stops"] == [0, 10, 100]
    assert "source" not in forecast["models"][0] and "code" not in temperature


def test_a_catalogue_without_a_forecast_section_has_no_forecast(tmp_path, source):
    client = _client(tmp_path, source, with_forecast=False)
    assert client.get("/api/catalogue").json()["forecast"] is None
    assert client.get("/api/forecast/times?layer=temperature&model=model-a").status_code == 404


def test_times_over_http(client):
    body = client.get("/api/forecast/times?layer=temperature&model=model-a&level=0").json()
    assert body == {"times": [
        {"time": "2026100900", "run": "2026100812"},
        {"time": "2026100906", "run": "2026100900"},
        {"time": "2026100912", "run": "2026100900"},
    ]}


def test_times_errors_carry_a_reason(client, source):
    assert client.get("/api/forecast/times?layer=nope&model=model-a").json()["detail"]["reason"] == "not-found"
    source.down = True
    response = client.get("/api/forecast/times?layer=temperature&model=model-b")
    assert response.status_code == 424
    assert response.json()["detail"]["reason"] == "source-unreachable"


def _tile_url(lon, lat, zoom, query):
    tile = morecantile.tms.get("WebMercatorQuad").tile(lon, lat, zoom)
    return f"/api/forecast/cog/tiles/WebMercatorQuad/{tile.z}/{tile.x}/{tile.y}.png?{query}"


def test_a_tile_is_drawn_in_the_layers_colours(client):
    response = client.get(_tile_url(70, 30, 5, "layer=temperature&model=model-a&level=0&time=2026100906"))
    assert response.status_code == 200
    image = Image.open(io.BytesIO(response.content)).convert("RGBA")
    assert image.getpixel((128, 128)) == (255, 0, 0, 255)  # 40 degrees: the ramp's last colour


def test_a_tile_outside_the_kept_area_is_refused(client):
    far = client.get(_tile_url(-100, 40, 5, "layer=temperature&model=model-a&level=0&time=2026100906"))
    assert far.status_code == 404


def test_tile_errors(client):
    bad_time = client.get(_tile_url(70, 30, 5, "layer=temperature&model=model-a&time=yesterday"))
    assert (bad_time.status_code, bad_time.json()["detail"]["reason"]) == (422, "bad-time")
    missing = client.get(_tile_url(70, 30, 5, "layer=temperature&model=model-a&time=2026102000"))
    assert (missing.status_code, missing.json()["detail"]["reason"]) == (404, "no-data")
    unknown = client.get(_tile_url(70, 30, 5, "layer=nope&model=model-a&time=2026100906"))
    assert unknown.status_code == 404


# --- what the browser may keep


def test_cache_control_by_kind_of_answer():
    assert cache_control(200, is_tile=True, names_run=True) == "public, max-age=604800, immutable"
    assert cache_control(200, is_tile=True, names_run=False) == "public, max-age=300"
    assert cache_control(200, is_tile=False, names_run=False) == "private, max-age=60"
    assert cache_control(404, is_tile=True, names_run=True) == "no-store"
    assert cache_control(424, is_tile=False, names_run=False) == "no-store"


def test_answers_say_how_long_they_may_be_kept(client):
    query = "layer=temperature&model=model-a&level=0&time=2026100906"
    by_run = client.get(_tile_url(70, 30, 5, f"{query}&run=2026100900"))
    assert by_run.status_code == 200
    assert by_run.headers["cache-control"] == "public, max-age=604800, immutable"
    assert client.get(_tile_url(70, 30, 5, query)).headers["cache-control"] == "public, max-age=300"
    times = client.get("/api/forecast/times?layer=temperature&model=model-a")
    assert times.headers["cache-control"] == "private, max-age=60"
    missing = client.get(_tile_url(70, 30, 5, "layer=temperature&model=model-a&time=2026102000&run=2026100900"))
    assert (missing.status_code, missing.headers["cache-control"]) == (404, "no-store")
    assert "cache-control" not in client.get("/api/catalogue").headers


def test_a_tile_names_its_run_and_a_bad_run_is_refused(client):
    older = client.get(_tile_url(70, 30, 5, "layer=temperature&model=model-a&time=2026100906&run=2026100812"))
    assert older.status_code == 200
    pixel = Image.open(io.BytesIO(older.content)).convert("RGBA").getpixel((128, 128))
    assert pixel != (255, 0, 0, 255)  # the older run's 10 degrees, not the newer run's 40
    bad = client.get(_tile_url(70, 30, 5, "layer=temperature&model=model-a&time=2026100906&run=lately"))
    assert (bad.status_code, bad.json()["detail"]["reason"]) == (422, "bad-time")
