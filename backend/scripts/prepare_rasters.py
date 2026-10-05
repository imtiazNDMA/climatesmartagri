"""Convert the project's land-cover rasters to Cloud-Optimized GeoTIFFs that TiTiler can serve quickly.

Run from the repo root (all four, or name the layers you want):
    uv run python backend/scripts/prepare_rasters.py
    uv run python backend/scripts/prepare_rasters.py forest shrub-land

Reads from data/geospatial/rasters (never changes it) and writes backend/rasters/<layer id>.tif.
The big files take a long time; a file that is already converted and newer than its source is skipped.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from csa_portal.geoenv import use_bundled_proj  # noqa: E402

use_bundled_proj()

import rasterio  # noqa: E402
from rio_cogeo.cogeo import cog_translate, cog_validate  # noqa: E402
from rio_cogeo.profiles import cog_profiles  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO / "data" / "geospatial" / "rasters"
OUT = REPO / "backend" / "rasters"

class Raster(NamedTuple):
    file: str
    # A value that means "nothing here". Marking it empty keeps scattered classes visible when
    # zoomed out; otherwise the zoomed-out copies keep only the commonest value in each area.
    empty_value: int | None = None


# Catalogue layer id -> source file.
RASTERS = {
    "irrigated-rainfed": Raster("Irrigated&rainfed.tif", empty_value=0),  # 0 is "Other Area"
    "forest": Raster("Forest_cover.tif"),
    "shrub-land": Raster("ShrubLand.tif"),
    "bare-land": Raster("Bare_land.tif"),
}


def _up_to_date(source: Path, target: Path, empty_value: int | None) -> bool:
    if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
        return False
    if not cog_validate(str(target), quiet=True)[0]:
        return False
    with rasterio.open(target) as made, rasterio.open(source) as original:
        return made.nodata == (original.nodata if empty_value is None else empty_value)


def convert(source: Path, target: Path, empty_value: int | None = None) -> bool:
    """Write `source` as a COG at `target`. Returns False if the target was already up to date."""
    source, target = Path(source), Path(target)
    if source.exists() and _up_to_date(source, target, empty_value):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    profile = cog_profiles.get("deflate")
    profile.update(blockxsize=512, blockysize=512)
    with rasterio.open(source) as original:
        signed_bytes = original.dtypes[0] == "int8"
    try:
        cog_translate(
            str(source),
            str(partial),
            profile,
            nodata=empty_value,
            # GDAL builds zoomed-out copies of signed-byte rasters very slowly; plain bytes hold the same classes.
            dtype="uint8" if signed_bytes else None,
            # These are class maps. "mode" keeps a class visible when zoomed out, because the
            # empty (nodata) cells around it are left out of the vote.
            overview_resampling="mode",
            in_memory=False,
            quiet=True,
            use_cog_driver=True,
            config={"GDAL_NUM_THREADS": "ALL_CPUS"},
        )
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return True


def main(names: list[str]) -> None:
    unknown = [name for name in names if name not in RASTERS]
    if unknown:
        sys.exit(f"Unknown layers {unknown}. Choose from {list(RASTERS)}.")
    for layer_id in names or list(RASTERS):
        raster = RASTERS[layer_id]
        source, target = SOURCE / raster.file, OUT / f"{layer_id}.tif"
        if not source.exists():
            print(f"{layer_id}: source file {source.name} not found, skipped", flush=True)
            continue
        started = time.time()
        print(f"{layer_id}: converting {source.name} ({source.stat().st_size / 1e9:.2f} GB)...", flush=True)
        changed = convert(source, target, raster.empty_value)
        size = target.stat().st_size / 1e6
        took = f"in {time.time() - started:.0f} s" if changed else "already up to date"
        print(f"{layer_id}: {target.relative_to(REPO)} {size:.0f} MB, {took}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
