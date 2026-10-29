"""Annual land-classification statistics measured from the source items."""

import json
import sys
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely import affinity
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import prepare_land_cover_stats as script  # noqa: E402
from prepare_land_cover_stats import (  # noqa: E402
    CLASS_CODES,
    CLOUD,
    NODATA,
    LandCoverStatsError,
    Measurement,
    aggregate_places,
    build_artifact,
    measure_areas,
    quality_gates,
)

CELL = 10.0  # metres, so a cell is 0.01 ha
ORIGIN = (500_000.0, 4_000_000.0)
SIZE = 120  # cells a side, so each band below is 40 cells wide and 48 ha
PARENTS = {"PK101": "PK1", "PK102": "PK1", "PK201": "PK2", "PK1": "PK", "PK2": "PK", "PK": None}
LAND_HA = {"PK101": 48.0, "PK102": 48.0, "PK201": 48.0, "PK1": 96.0, "PK2": 48.0, "PK": 144.0}


def write_raster(path: Path, data: np.ndarray, origin=ORIGIN) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="uint8",
        crs="EPSG:32642",
        transform=from_origin(origin[0], origin[1], CELL, CELL),
        nodata=NODATA,
    ) as target:
        target.write(data, 1)
    return path


def band(value: int, rows: int = SIZE, columns: int = 40) -> np.ndarray:
    """A block of the same class value."""
    return np.full((rows, columns), value, dtype="uint8")


@pytest.fixture
def raster(tmp_path) -> Path:
    """Three districts side by side: trees, crops, then half cloud and half no data."""
    data = np.concatenate(
        [band(2), band(5), np.concatenate([band(CLOUD, 60), band(NODATA, 60)])], axis=1
    )
    return write_raster(tmp_path / "item.tif", data)


@pytest.fixture
def districts() -> gpd.GeoDataFrame:
    """The three bands, as districts."""
    third = SIZE * CELL / 3
    bottom = ORIGIN[1] - SIZE * CELL
    geometries = [
        box(ORIGIN[0] + n * third, bottom, ORIGIN[0] + (n + 1) * third, ORIGIN[1]) for n in range(3)
    ]
    return gpd.GeoDataFrame(
        {"id": ["PK101", "PK102", "PK201"], "name": ["Alpha", "Beta", "Gamma"], "parent_id": ["PK1", "PK1", "PK2"]},
        geometry=geometries,
        crs="EPSG:32642",
    )


def test_each_district_is_measured_with_its_own_class_areas(raster, districts):
    measured = measure_areas([raster], districts)

    alpha = measured["PK101"]
    assert alpha.classes_ha[2] == pytest.approx(48.0)
    assert alpha.classified_ha == pytest.approx(48.0)
    assert alpha.cloud_ha == pytest.approx(0.0)
    assert measured["PK102"].classes_ha[5] == pytest.approx(48.0)


def test_a_class_with_no_cells_is_a_zero(raster, districts):
    measured = measure_areas([raster], districts)

    assert set(measured["PK101"].classes_ha) == set(CLASS_CODES)
    assert measured["PK101"].classes_ha[7] == 0.0
    assert build_artifact({"2019": {"PK101": measured["PK101"]}}, {"PK101": {"area_ha": 48.0}},
                          provenance={}, method="")["places"]["PK101"]["by_year"]["2019"]["classes_ha"]["7"] == 0.0


def test_cloud_and_no_data_are_counted_apart(raster, districts):
    measured = measure_areas([raster], districts)

    published = measured["PK201"].as_dict(48.0)
    assert published["classified_ha"] == pytest.approx(0.0)
    assert published["cloud_ha"] == pytest.approx(24.0)
    assert published["measured_ha"] == pytest.approx(24.0)
    assert published["nodata_ha"] == pytest.approx(24.0)
    assert published["coverage_pct"] == pytest.approx(50.0)
    assert "10" not in published["classes_ha"]


def test_items_side_by_side_add_up_without_counting_twice(tmp_path, districts):
    # The left half of the ground in one item, the right half in another.
    left = np.concatenate([band(2, columns=60), band(NODATA, columns=60)], axis=1)
    right = np.concatenate([band(NODATA, columns=60), band(5, columns=60)], axis=1)
    paths = [write_raster(tmp_path / "a.tif", left), write_raster(tmp_path / "b.tif", right)]

    measured = measure_areas(paths, districts)

    beta = measured["PK102"]
    assert beta.classes_ha[2] == pytest.approx(24.0)
    assert beta.classes_ha[5] == pytest.approx(24.0)
    assert beta.as_dict(48.0)["coverage_pct"] == pytest.approx(100.0)


def test_a_place_the_data_does_not_reach_is_missing_rather_than_zero(raster, districts):
    geometries = list(districts.geometry)
    geometries[0] = affinity.translate(geometries[0], 50_000)
    elsewhere = gpd.GeoDataFrame(districts.drop(columns="geometry"), geometry=geometries, crs=districts.crs)

    measured = measure_areas([raster], elsewhere)

    assert measured["PK102"].classes_ha[5] == pytest.approx(48.0)
    assert measured["PK101"] is None
    places = aggregate_places(measured, PARENTS)
    assert "PK101" not in places
    artifact = build_artifact({"2019": places}, {"PK101": {"area_ha": 48.0}}, provenance={}, method="")
    assert artifact["places"]["PK101"]["by_year"] == {}


def test_an_unknown_class_value_is_refused(tmp_path, districts):
    path = write_raster(tmp_path / "odd.tif", np.full((SIZE, SIZE), 99, dtype="uint8"))

    with pytest.raises(LandCoverStatsError, match="unknown class"):
        measure_areas([path], districts)


def test_districts_add_up_to_provinces_and_the_country(raster, districts):
    places = aggregate_places(measure_areas([raster], districts), PARENTS)

    assert places["PK1"].classes_ha[2] == pytest.approx(48.0)
    assert places["PK1"].classes_ha[5] == pytest.approx(48.0)
    assert places["PK2"].cloud_ha == pytest.approx(24.0)
    assert places["PK"].classified_ha == pytest.approx(96.0)
    assert places["PK"].measured_ha == pytest.approx(120.0)


def full_cover(raster_path: Path, districts) -> dict[str, Measurement]:
    return aggregate_places(measure_areas([raster_path], districts), PARENTS)


def test_the_quality_gates_pass_a_sound_year(tmp_path, districts):
    data = np.concatenate([band(2), band(5), band(CLOUD)], axis=1)
    places = full_cover(write_raster(tmp_path / "sound.tif", data), districts)

    quality_gates(places, LAND_HA, PARENTS)


def test_the_quality_gates_refuse_thin_coverage(raster, districts):
    places = full_cover(raster, districts)

    quality_gates(places, LAND_HA, PARENTS, minimum_coverage_pct=40.0)
    with pytest.raises(LandCoverStatsError, match=r"coverage is 83.33%, below 98.00%"):
        quality_gates(places, LAND_HA, PARENTS)


def test_a_thinly_covered_district_is_published_when_its_province_and_country_are_covered(tmp_path, districts):
    # Like a coastal district whose boundary takes in sea the product leaves unclassified.
    beta = np.concatenate([band(5, rows=96), band(NODATA, rows=24)])
    data = np.concatenate([band(2), beta, band(CLOUD)], axis=1)
    places = full_cover(write_raster(tmp_path / "coast.tif", data), districts)

    # Beta is 80% covered, its province 90% and the country 93%.
    quality_gates(places, LAND_HA, PARENTS, minimum_coverage_pct=85.0)
    assert places["PK102"].measured_ha / LAND_HA["PK102"] == pytest.approx(0.8)
    with pytest.raises(LandCoverStatsError, match=r"PK1: coverage is 90.00%, below 92.00%"):
        quality_gates(places, LAND_HA, PARENTS, minimum_coverage_pct=92.0)


def test_the_quality_gates_refuse_a_measurement_larger_than_its_land(tmp_path, districts):
    data = np.concatenate([band(2), band(5), band(CLOUD)], axis=1)
    path = write_raster(tmp_path / "sound.tif", data)
    # The same ground served by two items is counted twice.
    places = aggregate_places(measure_areas([path, path], districts), PARENTS)

    with pytest.raises(LandCoverStatsError, match="larger than"):
        quality_gates(places, LAND_HA, PARENTS)


def test_the_quality_gates_refuse_an_aggregation_that_does_not_reconcile(tmp_path, districts):
    data = np.concatenate([band(2), band(5), band(CLOUD)], axis=1)
    places = full_cover(write_raster(tmp_path / "sound.tif", data), districts)
    places["PK1"].classes_ha[2] -= 1.0

    with pytest.raises(LandCoverStatsError, match="class 2 does not add up"):
        quality_gates(places, LAND_HA, PARENTS)

    with pytest.raises(LandCoverStatsError, match="its parts cover"):
        quality_gates(full_cover(write_raster(tmp_path / "again.tif", data), districts),
                      {**LAND_HA, "PK1": 150.0}, PARENTS, minimum_coverage_pct=0.0)


def test_the_artifact_is_versioned_deterministic_and_auditable(raster, districts):
    places = full_cover(raster, districts)
    meta = {
        "PK": {"name": "Pakistan", "level": "national", "parent_id": None, "area_ha": 144.0},
        "PK1": {"name": "One", "level": "province", "parent_id": "PK", "area_ha": 96.0},
        "PK2": {"name": "Two", "level": "province", "parent_id": "PK", "area_ha": 48.0},
        "PK101": {"name": "Alpha", "level": "district", "parent_id": "PK1", "area_ha": 48.0},
        "PK102": {"name": "Beta", "level": "district", "parent_id": "PK1", "area_ha": 48.0},
        "PK201": {"name": "Gamma", "level": "district", "parent_id": "PK2", "area_ha": 48.0},
    }
    provenance = {"years": {"2019": [{"id": "42Q-2019", "size": 1, "etag": '"0x8D"', "last_modified": "Thu"}]}}

    artifact = build_artifact({"2019": places}, meta, provenance=provenance, method="counted")
    again = build_artifact({"2019": full_cover(raster, districts)}, meta, provenance=provenance, method="counted")

    assert json.dumps(artifact, sort_keys=True) == json.dumps(again, sort_keys=True)
    assert artifact["schema_version"] == 1
    assert artifact["years"] == ["2019"]
    assert artifact["classes"] == [str(code) for code in CLASS_CODES]
    assert artifact["provenance"]["years"]["2019"][0]["etag"] == '"0x8D"'
    alpha = artifact["places"]["PK101"]
    assert alpha["area_ha"] == 48.0
    assert alpha["by_year"]["2019"]["classes_ha"]["2"] == pytest.approx(48.0)
    assert alpha["by_year"]["2019"]["coverage_pct"] == pytest.approx(100.0)


def test_a_year_can_be_measured_on_an_overview(tmp_path, districts):
    data = np.concatenate([band(2), band(5), band(CLOUD)], axis=1)
    path = write_raster(tmp_path / "with-overviews.tif", data)
    with rasterio.open(path, "r+") as target:
        target.build_overviews([2, 4], rasterio.enums.Resampling.nearest)

    measured = measure_areas([path], districts, overview_level=1)

    # On the 4x overview each cell is 40 m, and the bands still split cleanly between districts.
    assert measured["PK101"].classes_ha[2] == pytest.approx(48.0)
    assert measured["PK102"].classes_ha[5] == pytest.approx(48.0)
    assert measured["PK201"].cloud_ha == pytest.approx(48.0)


def test_only_the_part_of_an_item_the_districts_cover_is_read(tmp_path, districts, monkeypatch):
    # A large item with the districts in one corner: over the network, the rest is bytes not to fetch.
    data = np.zeros((SIZE * 4, SIZE * 4), dtype="uint8")
    data[:SIZE, :SIZE] = np.concatenate([band(2), band(5), band(CLOUD)], axis=1)
    path = write_raster(tmp_path / "large.tif", data)
    windows = []
    read = rasterio.io.DatasetReader.read

    def spy(self, *args, **kwargs):
        windows.append(kwargs["window"])
        return read(self, *args, **kwargs)

    monkeypatch.setattr(rasterio.io.DatasetReader, "read", spy)

    measured = measure_areas([path], districts)

    assert windows and all(w.col_off + w.width <= SIZE and w.row_off + w.height <= SIZE for w in windows)

    assert measured["PK101"].classes_ha[2] == pytest.approx(48.0)
    assert measured["PK201"].cloud_ha == pytest.approx(48.0)


ITEM = {
    "id": "42R-2019",
    "href": "https://lulcstore.blob.core.windows.net/io-lulc-annual-v02/items/42R_20190101-20200101.tif",
    "size": 136,
}


def mpc(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_items_are_read_through_one_signed_address_per_container():
    asked = []

    def handler(request):
        asked.append(request.url.path)
        return httpx.Response(200, json={"token": "sv=1&sig=abc"})

    source = script.MpcSource(mpc(handler))
    first = source.signed_href(ITEM)
    second = source.signed_href({**ITEM, "id": "42S-2019", "href": ITEM["href"].replace("42R", "42S")})

    assert first == f"{ITEM['href']}?sv=1&sig=abc"
    assert second.endswith("42S_20190101-20200101.tif?sv=1&sig=abc")
    assert asked == ["/api/sas/v1/token/lulcstore/io-lulc-annual-v02"]


def test_a_failed_token_request_is_tried_again_once():
    replies = [httpx.Response(503, text="busy"), httpx.Response(200, json={"token": "sig=ok"})]

    source = script.MpcSource(mpc(lambda request: replies.pop(0)), retry_delay=0)

    assert source.signed_href(ITEM).endswith("?sig=ok")


def test_an_item_is_fingerprinted_by_its_blob_version_without_reading_it():
    def handler(request):
        if request.url.path.startswith("/api/sas"):
            return httpx.Response(200, json={"token": "sig=ok"})
        assert request.method == "HEAD"
        return httpx.Response(200, headers={
            "content-length": "136", "etag": '"0x8DC"', "last-modified": "Thu, 08 Feb 2024 14:59:02 GMT",
        })

    source = script.MpcSource(mpc(handler))

    assert source.fingerprint(ITEM) == {
        "id": "42R-2019", "href": ITEM["href"], "size": 136,
        "etag": '"0x8DC"', "last_modified": "Thu, 08 Feb 2024 14:59:02 GMT",
    }


def test_an_item_whose_size_disagrees_with_the_catalogue_is_refused():
    def handler(request):
        if request.url.path.startswith("/api/sas"):
            return httpx.Response(200, json={"token": "sig=ok"})
        return httpx.Response(200, headers={"content-length": "999", "etag": '"x"', "last-modified": "Thu"})

    with pytest.raises(LandCoverStatsError, match="999 bytes, but the catalogue says 136"):
        script.MpcSource(mpc(handler)).fingerprint(ITEM)
