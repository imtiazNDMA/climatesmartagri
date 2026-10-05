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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from csa_portal.geoenv import use_bundled_proj  # noqa: E402

use_bundled_proj()

from rio_cogeo.cogeo import cog_translate, cog_validate  # noqa: E402
from rio_cogeo.profiles import cog_profiles  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO / "data" / "geospatial" / "rasters"
OUT = REPO / "backend" / "rasters"

# Catalogue layer id -> source file.
RASTERS = {
    "irrigated-rainfed": "Irrigated&rainfed.tif",
    "forest": "Forest_cover.tif",
    "shrub-land": "ShrubLand.tif",
    "bare-land": "Bare_land.tif",
}


def _up_to_date(source: Path, target: Path) -> bool:
    if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
        return False
    return cog_validate(str(target), quiet=True)[0]


def convert(source: Path, target: Path) -> bool:
    """Write `source` as a COG at `target`. Returns False if the target was already up to date."""
    source, target = Path(source), Path(target)
    if source.exists() and _up_to_date(source, target):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    profile = cog_profiles.get("deflate")
    profile.update(blockxsize=512, blockysize=512)
    try:
        cog_translate(
            str(source),
            str(partial),
            profile,
            # These are class maps, and the zoomed-out copies must stay honest. Sampling ("nearest")
            # shows a class in proportion to how much of it there is. Voting ("mode") either drops a
            # scattered class or, if the empty cells are left out of the vote, floods the whole area
            # with it: forest on 5% of a plain would be drawn as forest everywhere.
            overview_resampling="nearest",
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
        source, target = SOURCE / RASTERS[layer_id], OUT / f"{layer_id}.tif"
        if not source.exists():
            print(f"{layer_id}: source file {source.name} not found, skipped", flush=True)
            continue
        started = time.time()
        print(f"{layer_id}: converting {source.name} ({source.stat().st_size / 1e9:.2f} GB)...", flush=True)
        changed = convert(source, target)
        size = target.stat().st_size / 1e6
        took = f"in {time.time() - started:.0f} s" if changed else "already up to date"
        print(f"{layer_id}: {target.relative_to(REPO)} {size:.0f} MB, {took}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
