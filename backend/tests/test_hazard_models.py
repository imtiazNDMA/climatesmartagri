"""Forecast-derived hazard models: frost degree-hours computed from a window of real values."""

import json
from datetime import datetime, timedelta

import numpy as np
import pytest
import rasterio

from csa_portal.forecast import ForecastError, ForecastService, load_registry
from csa_portal.hazard_models import (
    DerivedRegistryError,
    DerivedService,
    load_hazard_models,
    step_hours,
)
from csa_portal.models.frost import degree_hours_below
from csa_portal.pmd import PmdError, PmdFile

# --- pure functions


def test_degree_hours_below_accumulates_cold_and_clips_warm():
    # One time-step, three cells: mild, at base, deep cold.
    stack = np.array([[[-1.0, 0.0, -3.0]]])
    result = degree_hours_below(stack, np.array([6.0]), {"base_c": 0.0})
    assert result.tolist() == [[6.0, 0.0, 18.0]]


def test_degree_hours_below_over_stacked_times():
    # Two times on a 2x1 grid; one cell stays warm, the other stays cold.
    stack = np.array([[[-2.0, 1.0]], [[-2.0, 1.0]]])
    result = degree_hours_below(stack, np.array([3.0, 6.0]), {"base_c": 0.0})
    # Cold cell: 2·3 + 2·6 = 18. Warm cell: 0.
    assert result.tolist() == [[18.0, 0.0]]


def test_degree_hours_below_respects_base_c():
    stack = np.array([[[-1.0, -3.0]]])
    result = degree_hours_below(stack, np.array([4.0]), {"base_c": -2.0})
    # Only the second cell is below -2: 1 °C × 4 h = 4.
    assert result.tolist() == [[0.0, 4.0]]


def test_step_hours_repeats_last_gap_and_handles_even_spacing():
    start = datetime(2026, 10, 9, 0)
    even = [start + timedelta(hours=3 * i) for i in range(4)]
    assert step_hours(even).tolist() == [3.0, 3.0, 3.0, 3.0]
    uneven = [start, start + timedelta(hours=3), start + timedelta(hours=6), start + timedelta(hours=12)]
    assert step_hours(uneven).tolist() == [3.0, 3.0, 6.0, 6.0]


# --- test data


def tif(values, west=50.0, north=50.0, cell=1.0, scale=10, nodata=-9999):
    """A GeoTIFF as PMD writes them: whole numbers that are the true values times `scale`."""
    bands = np.asarray(values, dtype="float64")
    if bands.ndim == 2:
        bands = bands[np.newaxis]
    stored = np.where(np.isnan(bands), nodata, np.rint(bands * scale)).astype("int16")
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

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

    def add(self, source, element, level, run, valid, data):
        path = f"/static/{source}/{run:%Y%m%d%H}/{element}/{valid:%Y%m%d%H}_{level}.tif"
        self.listing.setdefault((source, element), {}).setdefault(run, {}).setdefault(level, []).append(
            PmdFile(run=run, valid=valid, path=path)
        )
        self.contents[path] = data
        return path

    def runs(self, source, element):
        return sorted(self.listing.get((source, element), {}), reverse=True)

    def files(self, source, element, level, run):
        return list(self.listing.get((source, element), {}).get(run, {}).get(level, []))

    def download(self, path):
        self.attempts += 1
        self.downloads.append(path)
        return self.contents[path]


REGISTRY = {
    "bbox": [60, 20, 80, 40],
    "models": [{"id": "model-a", "label": "Model A", "source": "SRCA"}],
    "groups": [{"id": "heat", "title": "Heat"}],
    "layers": [
        {"id": "temperature", "title": "Temperature", "group": "heat", "code": "TEM", "unit": "°C",
         "colours": ["#0000ff", "#ff0000"], "min": -10, "max": 40,
         "levels": {"model-a": [0]}},
    ],
}

SPEC = {
    "version": "test",
    "models": [
        {
            "id": "frost-degree-hours",
            "title": "Frost severity",
            "unit": "°C·h",
            "colours": ["#f7fbff", "#08306b"],
            "min": 0,
            "max": 48,
            "stops": [0, 48],
            "hide_below": 0.5,
            "input_layer": "temperature",
            "input_level": 0,
            "window_hours": 24,
            "min_points": 4,
            "compute": "frost_degree_hours",
            "params": {"base_c": 0},
        }
    ],
}

BASE = datetime(2026, 10, 9, 0)
TIMES = [BASE + timedelta(hours=3 * i) for i in range(9)]  # 0h .. 24h at 3-hourly steps
# Cold enough to accumulate; only the first slot is warm so the earliest window is thinner.
TEMPERATURES = [5, 0, -1, -3, -2, 0, 4, 8, 10]


@pytest.fixture
def forecast(tmp_path):
    path = tmp_path / "forecast_layers.json"
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    source = FakeSource()
    for valid, value in zip(TIMES, TEMPERATURES, strict=True):
        source.add("SRCA", "TEM", 0, BASE, valid, tif(field(value)))
    service = ForecastService(load_registry(path), source, tmp_path / "cache")
    service.source = source  # what the test's counter reads
    return service


@pytest.fixture
def derived(forecast):
    path = forecast.cache_dir.parent / "hazard_models.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(SPEC), encoding="utf-8")
    return DerivedService(forecast, load_hazard_models(path))


# --- loading and validation


def test_load_hazard_models_rejects_missing_and_bad_json(tmp_path):
    with pytest.raises(DerivedRegistryError, match="not found"):
        load_hazard_models(tmp_path / "absent.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(DerivedRegistryError, match="not valid JSON"):
        load_hazard_models(bad)


def test_load_hazard_models_rejects_unknown_compute_and_duplicate_ids(tmp_path):
    unknown = json.loads(json.dumps(SPEC))
    unknown["models"][0]["compute"] = "no-such-function"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(unknown), encoding="utf-8")
    with pytest.raises(DerivedRegistryError, match="unknown compute"):
        load_hazard_models(path)
    duplicate = json.loads(json.dumps(SPEC))
    duplicate["models"].append(json.loads(json.dumps(SPEC["models"][0])))
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(DerivedRegistryError, match="duplicate id"):
        load_hazard_models(path)


def test_load_hazard_models_rejects_bad_stops(tmp_path):
    bad = json.loads(json.dumps(SPEC))
    bad["models"][0]["stops"] = [0, 10, 48]  # wrong count for two colours
    path = tmp_path / "stops.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DerivedRegistryError, match="one rising stop per colour"):
        load_hazard_models(path)


def test_derived_service_rejects_unknown_input_layer(forecast, tmp_path):
    bad = json.loads(json.dumps(SPEC))
    bad["models"][0]["input_layer"] = "no-such-layer"
    path = tmp_path / "bad-input.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DerivedRegistryError, match="unknown input layer"):
        DerivedService(forecast, load_hazard_models(path))


# --- times


def test_times_lists_only_slots_with_a_full_window(derived):
    # The window needs four times: the earliest slot that has three behind it is +9h.
    slots = derived.times("frost-degree-hours", "model-a", 0)
    first = BASE + timedelta(hours=3 * 3)
    assert slots[0].valid == first
    assert all(s.run == BASE for s in slots)


def test_times_hides_the_model_at_the_wrong_level(derived):
    with pytest.raises(ForecastError) as err:
        derived.times("frost-degree-hours", "model-a", 500)
    assert err.value.status == 404


# --- file


def test_file_computes_degree_hours_and_writes_value_files(derived, forecast):
    # Window ending at the last time (24h): values [0,-1,-3,-2,0,4,8,10], all 3h steps.
    # Cold = clip(-v, 0): 0+3+9+6+0+0+0+0 = 18 degree-hours.
    target = BASE + timedelta(hours=24)
    path = derived.file("frost-degree-hours", "model-a", 0, target)
    assert path.is_file()
    with rasterio.open(path) as ds:
        data = ds.read(1, masked=True)
    # 18/48 of the way to the top colour → rint(95.25) + 1 = 96. The kept area is a 20x20 grid.
    assert not data.mask.any()
    assert data.shape == (20, 20)
    assert int(data[10, 10]) == 96
    # One download per input time, and the real-value files were stored too.
    assert forecast.source.attempts == 8
    for valid in TIMES[1:]:
        values = forecast.value_file("temperature", "model-a", 0, valid, BASE)
        with rasterio.open(values) as ds:
            assert ds.dtypes == ("float32",)
            assert np.isnan(ds.nodata)
            assert float(np.ma.median(ds.read(1, masked=True))) == pytest.approx(
                TEMPERATURES[TIMES.index(valid)], abs=0.05
            )


def test_file_is_cached_and_rebuilt_from_values_without_downloading_again(derived, forecast):
    target = BASE + timedelta(hours=24)
    first = derived.file("frost-degree-hours", "model-a", 0, target)
    attempts = forecast.source.attempts
    # Second call is a cache hit: no new downloads.
    assert derived.file("frost-degree-hours", "model-a", 0, target) == first
    assert forecast.source.attempts == attempts
    # Delete the derived file; it is rebuilt from the stored values, still without downloading.
    first.unlink()
    rebuilt = derived.file("frost-degree-hours", "model-a", 0, target)
    assert rebuilt == first and rebuilt.is_file()
    assert forecast.source.attempts == attempts


def test_value_file_keeps_the_derived_physical_values(derived):
    target = BASE + timedelta(hours=24)
    path = derived.value_file("frost-degree-hours", "model-a", 0, target)
    with rasterio.open(path) as stored:
        values = stored.read(1, masked=True)
    assert stored.dtypes == ("float32",)
    assert float(np.ma.median(values)) == pytest.approx(18, abs=0.05)


def test_file_rejects_a_run_that_never_had_that_time(derived):
    with pytest.raises(ForecastError) as err:
        derived.file("frost-degree-hours", "model-a", 0, BASE + timedelta(hours=24), run=datetime(1999, 1, 1))
    assert err.value.status == 404


def test_file_hides_a_warm_window(derived, forecast):
    # Windows that end in the warm stretch (6h and later of the last three slots) have no frost.
    # The window ending at +21h still includes the cold cells, so pick +18h: values [0,-1,-3,-2,0,4,8].
    # cold = 0+3+9+6+0+0+0 = 18. Use +12h instead: values [0,-1,-3] only three points — too thin.
    # All remaining windows ending after the cold snap still include it; force warm by using a
    # second source run that is warm throughout.
    warm = FakeSource()
    for valid in TIMES:
        warm.add("SRCA", "TEM", 0, BASE, valid, tif(field(20)))
    warm_forecast = ForecastService(
        forecast.registry, warm, forecast.cache_dir.parent / "warm-cache"
    )
    warm_spec = json.loads(json.dumps(SPEC))
    warm_spec["models"][0]["window_hours"] = 6  # three 3-hourly steps: warm only
    warm_spec["models"][0]["min_points"] = 2
    path = warm_forecast.cache_dir.parent / "warm-models.json"
    path.write_text(json.dumps(warm_spec), encoding="utf-8")
    warm_derived = DerivedService(warm_forecast, load_hazard_models(path))
    target = BASE + timedelta(hours=24)
    result = warm_derived.file("frost-degree-hours", "model-a", 0, target)
    with rasterio.open(result) as ds:
        data = ds.read(1)
    # hide_below 0.5 wipes a result of exactly zero: everything is the "nothing here" marker.
    assert (data == 0).all()


# --- describe


def test_describe_lists_the_group_and_layer_with_levels(derived):
    body = derived.describe()
    assert body["groups"] == [{"id": "hazard-models", "title": "Hazard models"}]
    (layer,) = body["layers"]
    assert layer["id"] == "frost-degree-hours"
    assert layer["levels"] == {"model-a": [0]}
    assert layer["colours"] == ["#f7fbff", "#08306b"]


def test_layer_synthesises_an_ordinary_forecast_layer(derived):
    layer = derived.layer("frost-degree-hours")
    assert layer.id == "frost-degree-hours"
    assert layer.code == "frost-degree-hours"
    assert layer.group == "hazard-models"
    # Two colours, stops [0, 48]: the mid-point value 24 sits halfway up the ramp.
    colours = layer.colour_values(0, "model-a")
    assert colours[0] == 0 and colours[-1] == 48


def test_has_and_spec(derived):
    assert derived.has("frost-degree-hours")
    assert not derived.has("temperature")
    with pytest.raises(ForecastError):
        derived.spec("no-such-model")
