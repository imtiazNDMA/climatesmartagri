import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prepare_land_cover import CLASSES, class_areas, summarise_land_cover  # noqa: E402
from prepare_rasters import convert  # noqa: E402

# One degree of longitude and latitude on the ground at 30 degrees north, in metres.
LON_M, LAT_M = 111320 * np.cos(np.radians(29.5)), 110574


def _raster(tmp_path, name, fill):
    """A 2 x 2 degree raster at 0.001 degrees: lon 70-72, lat 28-30. `fill(data)` paints the classes."""
    data = np.full((2000, 2000), 15, dtype="uint8")
    fill(data)
    plain = tmp_path / f"{name}-plain.tif"
    with rasterio.open(
        plain, "w", driver="GTiff", height=2000, width=2000, count=1, dtype="uint8", crs="EPSG:4326",
        transform=from_origin(70, 30, 0.001, 0.001), nodata=15, tiled=True, blockxsize=128, blockysize=128,
    ) as dst:
        dst.write(data, 1)
    convert(plain, tmp_path / f"{name}.tif")
    return tmp_path / f"{name}.tif"


def _districts():
    return gpd.GeoDataFrame(
        {"id": ["d-west", "d-east", "d-far"], "name": ["West", "East", "Far"], "parent_id": ["p-a", "p-a", "p-b"]},
        geometry=[box(70, 29, 71, 30), box(71, 29, 72, 30), box(80, 29, 81, 30)],
        crs="EPSG:4326",
    )


def _forest_in_the_west(data):
    data[0:1000, 0:500] = 2  # the western half of district West: lon 70-70.5, lat 29-30


def test_class_areas_measures_each_class_inside_each_district(tmp_path):
    path = _raster(tmp_path, "forest", _forest_in_the_west)
    areas = class_areas(path, _districts(), {"forest": 2}, overview_level=None)

    half_district_ha = 0.5 * LON_M * 1.0 * LAT_M / 10_000
    assert areas.loc["d-west", "forest"] == pytest.approx(half_district_ha, rel=0.01)
    assert areas.loc["d-east", "forest"] == 0
    # A district the raster does not reach has no measurement, which is not the same as zero.
    assert np.isnan(areas.loc["d-far", "forest"])
    assert areas.loc["d-west", "measured_ha"] == pytest.approx(2 * half_district_ha, rel=0.01)


def test_class_areas_from_a_zoomed_out_copy_agree_with_full_detail(tmp_path):
    def scattered(data):
        rng = np.random.default_rng(3)
        data[0:1000, :] = np.where(rng.random((1000, 2000)) < 0.2, 2, 15)

    path = _raster(tmp_path, "forest", scattered)
    full = class_areas(path, _districts(), {"forest": 2}, overview_level=None)
    coarse = class_areas(path, _districts(), {"forest": 2}, overview_level=1)
    assert coarse.loc["d-west", "forest"] == pytest.approx(full.loc["d-west", "forest"], rel=0.03)
    assert coarse.loc["d-east", "forest"] == pytest.approx(full.loc["d-east", "forest"], rel=0.03)


def test_class_areas_separates_several_classes_in_one_raster(tmp_path):
    def cropland(data):
        data[0:1000, 0:1000] = 0     # other area, across West
        data[0:1000, 0:250] = 2      # irrigated: a quarter of West
        data[0:1000, 250:300] = 3    # rainfed: a twentieth of West

    path = _raster(tmp_path, "crops", cropland)
    areas = class_areas(path, _districts(), {"irrigated": 2, "rainfed": 3}, overview_level=None)
    west_ha = LON_M * LAT_M / 10_000
    assert areas.loc["d-west", "irrigated"] == pytest.approx(0.25 * west_ha, rel=0.01)
    assert areas.loc["d-west", "rainfed"] == pytest.approx(0.05 * west_ha, rel=0.02)
    assert areas.loc["d-west", "measured_ha"] == pytest.approx(west_ha, rel=0.01)


def test_summarise_land_cover_totals_districts_into_provinces_and_the_country():
    districts = _districts()
    provinces = gpd.GeoDataFrame(
        {"id": ["p-a", "p-b"], "name": ["A", "B"], "parent_id": ["PK", "PK"]},
        geometry=[box(70, 29, 72, 30), box(80, 29, 81, 30)], crs="EPSG:4326",
    )
    measured = {
        "forest": {"d-west": 100.0, "d-east": 50.0, "d-far": float("nan")},
        "irrigated": {"d-west": 10.0, "d-east": 0.0, "d-far": 5.0},
    }
    land = {"d-west": 1000.0, "d-east": 2000.0, "d-far": 500.0}
    summary = summarise_land_cover(measured, land, provinces, districts)
    places = summary["places"]

    assert places["d-west"] == {
        "name": "West", "level": "district", "parent_id": "p-a", "area_ha": 1000.0,
        "forest": 100.0, "irrigated": 10.0,
    }
    assert places["d-far"]["forest"] is None
    assert places["p-a"]["forest"] == 150.0
    assert places["p-a"]["area_ha"] == 3000.0
    # A province whose only district was not measured has no figure, not a zero.
    assert places["p-b"]["forest"] is None
    assert places["p-b"]["irrigated"] == 5.0
    assert places["PK"]["forest"] == 150.0
    assert places["PK"]["irrigated"] == 15.0
    assert places["PK"]["area_ha"] == 3500.0
    assert places["PK"]["name"] == "Pakistan"
    assert summary["classes"] == ["forest", "irrigated"]


def test_every_class_names_its_raster_and_value():
    assert set(CLASSES) == {"forest", "shrub", "bare", "irrigated", "rainfed"}
    assert CLASSES["irrigated"] == ("irrigated-rainfed", 2)
    assert CLASSES["rainfed"] == ("irrigated-rainfed", 3)
    assert CLASSES["forest"] == ("forest", 2)
