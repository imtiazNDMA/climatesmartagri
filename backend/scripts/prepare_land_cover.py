"""Measure how much of each district each land-cover class covers, from the converted rasters.

Run from the repo root, after prepare_data.py and prepare_rasters.py:
    uv run python backend/scripts/prepare_land_cover.py

Reads backend/rasters/*.tif and backend/boundaries/*.geojson, and writes backend/data/land_cover.json.
A class whose raster has not been converted yet is left out; run this again once it has.

The 10 m rasters are measured on a one-in-64 sample of their cells (every eighth cell each way),
which keeps the run to minutes and is accurate to about 1% for all but the smallest patches.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from csa_portal.geoenv import use_bundled_proj  # noqa: E402

use_bundled_proj()

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.windows import Window  # noqa: E402
from rasterio.windows import transform as window_transform  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
RASTERS = REPO / "backend" / "rasters"
BOUNDARIES = REPO / "backend" / "boundaries"
OUT = REPO / "backend" / "data" / "land_cover.json"

COUNTRY_ID = "PK"
# Class -> (raster layer id, cell value).
CLASSES = {
    "forest": ("forest", 2),
    "shrub": ("shrub-land", 3),
    "bare": ("bare-land", 7),
    "irrigated": ("irrigated-rainfed", 2),
    "rainfed": ("irrigated-rainfed", 3),
}
# Which zoomed-out copy to measure on: index into the file's overviews (0 is half size). None is full detail.
OVERVIEW_LEVEL = {"forest": 2, "shrub-land": 2, "bare-land": 2, "irrigated-rainfed": 0}
ROWS_PER_STRIP = 2048


def _row_areas_ha(transform: Any, first_row: int, rows: int) -> np.ndarray:
    """The ground area of one cell in each row, in hectares. Cells get narrower away from the equator."""
    width_deg, height_deg = abs(transform.a), abs(transform.e)
    latitudes = transform.f + transform.e * (first_row + np.arange(rows) + 0.5)
    metres_wide = width_deg * 111_320.0 * np.cos(np.radians(latitudes))
    metres_high = height_deg * 110_574.0
    return metres_wide * metres_high / 10_000.0


def class_areas(
    raster_path: Path, districts: gpd.GeoDataFrame, values: dict[str, int], overview_level: int | None
) -> pd.DataFrame:
    """Hectares of each class inside each district, indexed by district id.

    `measured_ha` is the district land the raster covers. A district the raster does not reach
    gets NaN for every class: not measured, which is different from none.
    """
    options = {} if overview_level is None else {"overview_level": overview_level}
    ids = list(districts["id"])
    totals = {name: np.zeros(len(ids) + 1) for name in values}
    measured = np.zeros(len(ids) + 1)
    with rasterio.open(raster_path, **options) as raster:
        shapes = [
            (geometry, number + 1) for number, geometry in enumerate(districts.to_crs(raster.crs).geometry)
        ]
        for first_row in range(0, raster.height, ROWS_PER_STRIP):
            rows = min(ROWS_PER_STRIP, raster.height - first_row)
            window = Window(0, first_row, raster.width, rows)
            data = raster.read(1, window=window)
            labels = rasterize(
                shapes, out_shape=(rows, raster.width), transform=window_transform(window, raster.transform),
                fill=0, dtype="uint16",
            )
            area = np.broadcast_to(_row_areas_ha(raster.transform, first_row, rows)[:, None], data.shape)
            # Every cell of the raster counts as measured, including empty ones: in these rasters an
            # empty cell means "not this class", so a district with none of a class scores zero.
            measured += np.bincount(labels.ravel(), weights=area.ravel(), minlength=len(ids) + 1)
            for name, value in values.items():
                hit = data == value
                totals[name] += np.bincount(labels[hit], weights=area[hit], minlength=len(ids) + 1)

    frame = pd.DataFrame({name: total[1:] for name, total in totals.items()}, index=ids)
    frame["measured_ha"] = measured[1:]
    frame.loc[frame["measured_ha"] == 0, list(values)] = np.nan
    return frame


def _number(value: Any) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value), 1)


def summarise_land_cover(
    measured: dict[str, dict[str, float]],
    land_ha: dict[str, float],
    provinces: pd.DataFrame,
    districts: pd.DataFrame,
) -> dict[str, Any]:
    """Per-place class areas: districts as measured, provinces and the country as the sum of their districts."""
    classes = list(measured)
    table = pd.DataFrame(measured).reindex(list(districts["id"]))
    table["area_ha"] = pd.Series(land_ha)
    table["parent_id"] = list(districts["parent_id"])

    def entry(name: str, level: str, parent: str | None, rows: pd.DataFrame) -> dict[str, Any]:
        return {
            "name": name, "level": level, "parent_id": parent, "area_ha": _number(rows["area_ha"].sum()),
            # min_count=1: a place where nothing was measured has no figure, not a zero.
            **{c: _number(rows[c].sum(min_count=1)) for c in classes},
        }

    places: dict[str, Any] = {COUNTRY_ID: entry("Pakistan", "national", None, table)}
    for province in provinces.itertuples():
        places[province.id] = entry(province.name, "province", COUNTRY_ID, table[table["parent_id"] == province.id])
    for district in districts.itertuples():
        places[district.id] = entry(district.name, "district", district.parent_id, table.loc[[district.id]])
    return {"classes": classes, "places": places}


def main() -> None:
    provinces = gpd.read_file(BOUNDARIES / "provinces.geojson")
    districts = gpd.read_file(BOUNDARIES / "districts.geojson")
    # True land area of each district, measured on an equal-area projection.
    land_ha = dict(zip(districts["id"], districts.to_crs("ESRI:54034").geometry.area / 10_000.0))

    measured: dict[str, dict[str, float]] = {}
    by_layer: dict[str, dict[str, int]] = {}
    for name, (layer_id, value) in CLASSES.items():
        by_layer.setdefault(layer_id, {})[name] = value
    for layer_id, values in by_layer.items():
        path = RASTERS / f"{layer_id}.tif"
        if not path.is_file():
            print(f"{layer_id}: not converted yet, {list(values)} left out", flush=True)
            continue
        started = time.time()
        areas = class_areas(path, districts, values, OVERVIEW_LEVEL[layer_id])
        for name in values:
            measured[name] = areas[name].to_dict()
            print(f"{name}: {areas[name].sum() / 1e6:.2f} million ha in {time.time() - started:.0f} s", flush=True)

    summary = summarise_land_cover(measured, land_ha, provinces, districts)
    summary["method"] = (
        "Area of each class inside each district, measured from the land-cover rasters. "
        "The 10 m rasters are measured on a one-in-64 sample of their cells."
    )
    OUT.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}: {summary['classes']}", flush=True)


if __name__ == "__main__":
    main()
