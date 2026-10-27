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
    assert set(RASTERS) == {"irrigated-rainfed"}


def write_scattered_raster(path: Path, share: float = 0.10, size: int = 2048) -> None:
    """A class scattered thinly over an otherwise empty raster, like forest across a plain."""
    rng = np.random.default_rng(7)
    data = np.where(rng.random((size, size)) < share, 2, 15).astype("uint8")
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1, dtype="uint8", crs="EPSG:4326",
        transform=from_origin(70, 30, 0.001, 0.001), nodata=15, tiled=True, blockxsize=128, blockysize=128,
    ) as dst:
        dst.write(data, 1)


def test_zoomed_out_copies_show_a_scattered_class_in_its_true_proportion(tmp_path):
    """A class on 10% of the land must not vanish when zoomed out, and must not flood the map either."""
    source, target = tmp_path / "scattered.tif", tmp_path / "out.tif"
    write_scattered_raster(source, share=0.10)
    convert(source, target)
    with rasterio.open(target) as cog:
        for factor in cog.overviews(1):
            coarse = cog.read(1, out_shape=(cog.height // factor, cog.width // factor))
            share = float((coarse == 2).mean())
            assert 0.05 < share < 0.15, f"at 1/{factor} scale the class covers {share:.0%} of cells"


def test_signed_byte_rasters_convert_too(tmp_path):
    """The irrigated and rainfed file stores its classes as signed bytes, with 0 for 'other area'."""
    source, target = tmp_path / "signed.tif", tmp_path / "out.tif"
    data = np.zeros((1024, 1024), dtype="int8")
    data[100:300, 100:600] = 2
    data[500:700, 100:600] = 3
    with rasterio.open(
        source, "w", driver="GTiff", height=1024, width=1024, count=1, dtype="int8", crs="EPSG:4326",
        transform=from_origin(70, 30, 0.001, 0.001), nodata=127, tiled=True, blockxsize=128, blockysize=128,
    ) as dst:
        dst.write(data, 1)
    convert(source, target)
    with rasterio.open(target) as cog:
        np.testing.assert_array_equal(cog.read(1), data)
        assert cog.nodata == 127
        # The zoomed-out copies must hold the classes too, not just empty cells.
        for factor in cog.overviews(1):
            coarse = cog.read(1, out_shape=(cog.height // factor, cog.width // factor))
            assert 0.05 < float((coarse == 2).mean()) < 0.15, factor
            assert 0.05 < float((coarse == 3).mean()) < 0.15, factor
            assert 127 not in coarse, factor


def test_a_file_whose_zoomed_out_copies_are_empty_is_caught(tmp_path):
    """Seen for real: a conversion that kept the full-detail data but lost every zoomed-out copy."""
    from rasterio.enums import Resampling

    from prepare_rasters import overviews_are_empty

    path = tmp_path / "stale.tif"
    profile = dict(driver="GTiff", height=1024, width=1024, count=1, dtype="uint8", crs="EPSG:4326",
                   transform=from_origin(70, 30, 0.001, 0.001), nodata=15, tiled=True, blockxsize=128, blockysize=128)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.full((1024, 1024), 15, dtype="uint8"), 1)
        dst.build_overviews([2, 4, 8], Resampling.nearest)
    with rasterio.open(path, "r+") as dst:
        dst.write(np.full((1024, 1024), 2, dtype="uint8"), 1)  # data arrives, overviews stay empty
    assert overviews_are_empty(path) is True

    good = tmp_path / "good.tif"
    write_scattered_raster(tmp_path / "scattered.tif")
    convert(tmp_path / "scattered.tif", good)
    assert overviews_are_empty(good) is False


def test_an_all_empty_raster_is_not_mistaken_for_a_broken_one(tmp_path):
    from prepare_rasters import overviews_are_empty

    source, target = tmp_path / "empty.tif", tmp_path / "out.tif"
    with rasterio.open(
        source, "w", driver="GTiff", height=1024, width=1024, count=1, dtype="uint8", crs="EPSG:4326",
        transform=from_origin(70, 30, 0.001, 0.001), nodata=15, tiled=True, blockxsize=128, blockysize=128,
    ) as dst:
        dst.write(np.full((1024, 1024), 15, dtype="uint8"), 1)
    convert(source, target)
    assert overviews_are_empty(target) is False
