import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_validate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prepare_rasters import RASTERS, convert  # noqa: E402


def write_plain_raster(path: Path, size: int = 1200) -> np.ndarray:
    """A class raster laid out like the project's: small blocks, no overviews, value 2 on nodata 15."""
    data = np.full((size, size), 15, dtype="uint8")
    data[100:400, 200:700] = 2
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1, dtype="uint8", crs="EPSG:4326",
        transform=from_origin(70, 30, 0.001, 0.001), nodata=15, tiled=True, blockxsize=128, blockysize=128,
    ) as dst:
        dst.write(data, 1)
    return data


def test_convert_writes_a_valid_cloud_optimized_geotiff(tmp_path):
    source, target = tmp_path / "plain.tif", tmp_path / "out" / "forest.tif"
    data = write_plain_raster(source)

    assert convert(source, target) is True

    valid, errors, _ = cog_validate(str(target))
    assert valid, errors
    with rasterio.open(target) as cog:
        assert cog.overviews(1), "a COG needs overviews to be fast when zoomed out"
        assert cog.block_shapes[0] == (512, 512)
        assert cog.nodata == 15
        assert cog.crs.to_epsg() == 4326
        np.testing.assert_array_equal(cog.read(1), data)
        # Zoomed out, the class is still there: overviews keep the valid value, not the nodata around it.
        smallest = cog.read(1, out_shape=(cog.height // cog.overviews(1)[-1], cog.width // cog.overviews(1)[-1]))
        assert 2 in smallest


def test_convert_skips_a_target_that_is_already_up_to_date(tmp_path):
    source, target = tmp_path / "plain.tif", tmp_path / "forest.tif"
    write_plain_raster(source, size=600)
    assert convert(source, target) is True
    stamp = target.stat().st_mtime_ns
    assert convert(source, target) is False
    assert target.stat().st_mtime_ns == stamp


def test_convert_leaves_no_partial_file_when_the_source_is_unreadable(tmp_path):
    source, target = tmp_path / "broken.tif", tmp_path / "forest.tif"
    source.write_bytes(b"not a raster")
    try:
        convert(source, target)
    except Exception:
        pass
    else:
        raise AssertionError("an unreadable source should raise")
    assert list(tmp_path.glob("forest*")) == []


def test_every_land_cover_layer_has_a_source_file_name():
    assert set(RASTERS) == {"forest", "shrub-land", "bare-land", "irrigated-rainfed"}


def write_sparse_raster(path: Path, size: int = 1024) -> None:
    """Like the irrigated/rainfed file: 0 means 'other area' and fills most cells; cropland (2) is scattered."""
    data = np.zeros((size, size), dtype="int8")
    data[::4, ::4] = 2
    data[:, :64] = 127
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1, dtype="int8", crs="EPSG:4326",
        transform=from_origin(70, 30, 0.001, 0.001), nodata=127, tiled=True, blockxsize=128, blockysize=128,
    ) as dst:
        dst.write(data, 1)


def _smallest_overview(path: Path) -> np.ndarray:
    with rasterio.open(path) as cog:
        factor = cog.overviews(1)[-1]
        return cog.read(1, out_shape=(cog.height // factor, cog.width // factor))


def test_scattered_classes_vanish_when_zoomed_out_unless_the_background_is_marked_empty(tmp_path):
    source = tmp_path / "sparse.tif"
    write_sparse_raster(source)

    convert(source, tmp_path / "as-is.tif")
    assert 2 not in _smallest_overview(tmp_path / "as-is.tif")

    convert(source, tmp_path / "kept.tif", empty_value=0)
    assert 2 in _smallest_overview(tmp_path / "kept.tif")
    with rasterio.open(tmp_path / "kept.tif") as cog:
        assert cog.nodata == 0
        # Stored as plain bytes: GDAL builds zoomed-out copies of signed-byte rasters very slowly.
        assert cog.dtypes[0] == "uint8"
        assert int((cog.read(1) == 2).sum()) == (1024 // 4) * ((1024 - 64) // 4)


def test_convert_redoes_a_target_made_with_a_different_empty_value(tmp_path):
    source, target = tmp_path / "sparse.tif", tmp_path / "out.tif"
    write_sparse_raster(source)
    assert convert(source, target) is True
    assert convert(source, target, empty_value=0) is True
    assert convert(source, target, empty_value=0) is False


def test_the_irrigated_and_rainfed_layer_treats_other_area_as_empty():
    assert RASTERS["irrigated-rainfed"].empty_value == 0
    assert RASTERS["forest"].empty_value is None
