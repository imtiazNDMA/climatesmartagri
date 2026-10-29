"""Measure how much of each land class covers each place, for every annual land-cover year.

Run from the repository root:
    uv run python backend/scripts/prepare_land_cover_stats.py
    uv run python backend/scripts/prepare_land_cover_stats.py 2019 2023

The source items are the Microsoft Planetary Computer annual LULC COGs. Nothing is downloaded or
kept: each item is read over HTTP on one of its own overviews (80 m cells by default), and only
the part the districts cover, so a year costs tens of megabytes rather than a gigabyte. Every year
is measured the same way. Against full 10 m resolution, the 80 m overview moved a district's class
shares by 0.04 percentage points at the median and 0.42 at worst (a small Karachi district). The
MPC statistics service is not used: it counts against the item's own extent rather than the place.
Each item is recorded by its blob version (ETag, last-modified time and size), since MPC publishes
no checksum. The result is written to backend/data/land_cover_annual.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from csa_portal.geoenv import use_bundled_proj  # noqa: E402

use_bundled_proj()
# Reading a COG over HTTP: open it without listing its folder, and ride out brief network failures.
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "4")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")

import geopandas as gpd  # noqa: E402
import httpx  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.windows import Window  # noqa: E402
from rasterio.windows import transform as window_transform  # noqa: E402
from shapely.geometry import box  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
BOUNDARIES = REPO / "backend" / "boundaries"
OUT = REPO / "backend" / "data" / "land_cover_annual.json"

SAS_API = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
SCHEMA_VERSION = 1
COLLECTION = "io-lulc-annual-v02"
VERSION = "v02"
YEARS = tuple(range(2017, 2024))
# The items' overviews halve the 10 m grid at each level: 0 is 20 m, 1 is 40 m, 2 is 80 m.
OVERVIEW_LEVEL = 2
NODATA = 0
CLOUD = 10
# The land classes of the annual classification, by their code in the source items. Clouds are
# the ninth value of the product, but they say nothing about the ground, so they are kept apart.
CLASS_CODES = (1, 2, 4, 5, 7, 8, 9, 11)
KNOWN_VALUES = frozenset((NODATA, CLOUD, *CLASS_CODES))
ROWS_PER_STRIP = 1024
# How much of each province and of Pakistan the data must reach before a year is published;
# less means an item is missing or broken. A district may fall short and is still published, its
# coverage saying so: coastal districts take in sea the product leaves unclassified (Sujawal 86%).
MINIMUM_COVERAGE_PCT = 98.0
# How much larger than the land it covers a measurement may be before it is refused. Drawing a
# boundary on 10 m cells moves its area by a fraction of this; overlapping items move it by more.
MAXIMUM_AREA_FACTOR = 1.02
# How far the parts of a place may differ from the whole, as a share of the whole's land area.
RECONCILIATION_TOLERANCE = 0.005


class LandCoverStatsError(RuntimeError):
    """The annual statistics cannot be produced or published safely."""


@dataclass
class Measurement:
    """What one place looked like in one year, in hectares."""

    classes_ha: dict[int, float] = field(default_factory=lambda: {code: 0.0 for code in CLASS_CODES})
    cloud_ha: float = 0.0

    @property
    def classified_ha(self) -> float:
        return sum(self.classes_ha.values())

    @property
    def measured_ha(self) -> float:
        return self.classified_ha + self.cloud_ha

    def add(self, other: Measurement) -> None:
        for code, area in other.classes_ha.items():
            self.classes_ha[code] = self.classes_ha.get(code, 0.0) + area
        self.cloud_ha += other.cloud_ha

    def as_dict(self, land_ha: float) -> dict[str, Any]:
        """The published form, with what the data did not reach counted against the land."""
        measured = self.measured_ha
        return {
            "classes_ha": {str(code): round(self.classes_ha.get(code, 0.0), 1) for code in CLASS_CODES},
            "classified_ha": round(self.classified_ha, 1),
            "cloud_ha": round(self.cloud_ha, 1),
            "nodata_ha": round(max(land_ha - measured, 0.0), 1),
            "measured_ha": round(measured, 1),
            "coverage_pct": round(min(measured / land_ha * 100, 100.0), 2) if land_ha > 0 else 0.0,
        }


def _open_for_measurement(source: str | Path, name: str, overview_level: int | None):
    """The raster at full resolution, or on one of its overviews."""
    if overview_level is None:
        return rasterio.open(source)
    with rasterio.open(source) as raster:
        levels = raster.overviews(1)
    if overview_level >= len(levels):
        raise LandCoverStatsError(f"{name} has no overview level {overview_level}")
    return rasterio.open(source, OVERVIEW_LEVEL=overview_level)


def _covered_window(raster, bounds: Sequence[float]) -> Window:
    """The cells of the raster inside the bounds, rounded outward and kept on the raster."""
    left, bottom, right, top = bounds
    first_col, first_row = ~raster.transform @ (left, top)
    last_col, last_row = ~raster.transform @ (right, bottom)
    col_off, row_off = max(int(np.floor(first_col)), 0), max(int(np.floor(first_row)), 0)
    col_end = min(int(np.ceil(last_col)), raster.width)
    row_end = min(int(np.ceil(last_row)), raster.height)
    return Window(col_off, row_off, max(col_end - col_off, 0), max(row_end - row_off, 0))


def measure_raster(
    source: str | Path,
    districts: gpd.GeoDataFrame,
    *,
    overview_level: int | None = None,
    name: str | None = None,
) -> dict[str, Measurement]:
    """What one item, a file or a signed address, shows inside each district it reaches."""
    name = name or Path(source).name
    with _open_for_measurement(source, name, overview_level) as raster:
        if not (raster.crs and raster.crs.is_projected):
            raise LandCoverStatsError(f"{name} is not on a projected grid")
        cell_ha = abs(raster.transform.a * raster.transform.e) / 10_000.0
        local = districts.to_crs(raster.crs)
        covering = local[local.geometry.intersects(box(*raster.bounds))]
        if covering.empty:
            return {}
        ids = list(covering["id"])
        shapes = [(geometry, number + 1) for number, geometry in enumerate(covering.geometry)]
        counts = np.zeros((len(ids) + 1) * 256, dtype=np.int64)
        # Only the cells under the districts are read; over the network the rest is never fetched.
        area = _covered_window(raster, covering.total_bounds)
        for first_row in range(area.row_off, area.row_off + area.height, ROWS_PER_STRIP):
            rows = min(ROWS_PER_STRIP, area.row_off + area.height - first_row)
            window = Window(area.col_off, first_row, area.width, rows)
            labels = rasterize(
                shapes,
                out_shape=(rows, area.width),
                transform=window_transform(window, raster.transform),
                fill=0,
                dtype="uint16",
            )
            inside = labels > 0
            if not inside.any():
                continue
            data = raster.read(1, window=window)
            # One count for every pairing of district and class value in the strip.
            counts += np.bincount(
                labels[inside].astype(np.int64) * 256 + data[inside], minlength=counts.size
            )
    by_value = counts.reshape(len(ids) + 1, 256)
    seen = {int(value) for value in np.nonzero(by_value[1:].sum(axis=0))[0]}
    unknown = sorted(seen - KNOWN_VALUES)
    if unknown:
        raise LandCoverStatsError(f"{name}: unknown class values {unknown}")
    measured: dict[str, Measurement] = {}
    for number, place_id in enumerate(ids, start=1):
        row = by_value[number]
        measurement = Measurement(
            classes_ha={code: float(row[code]) * cell_ha for code in CLASS_CODES},
            cloud_ha=float(row[CLOUD]) * cell_ha,
        )
        if measurement.measured_ha > 0:
            measured[place_id] = measurement
    return measured


def combine(
    parts: Iterable[Mapping[str, Measurement]], place_ids: Iterable[str]
) -> dict[str, Measurement | None]:
    """Every district, with what all the items show inside it; None where no item reaches it."""
    totals: dict[str, Measurement | None] = {place_id: None for place_id in place_ids}
    for part in parts:
        for place_id, measurement in part.items():
            total = totals.get(place_id)
            if total is None:
                total = totals[place_id] = Measurement()
            total.add(measurement)
    return totals


def measure_areas(
    paths: Sequence[Path], districts: gpd.GeoDataFrame, *, overview_level: int | None = None
) -> dict[str, Measurement | None]:
    """Measure every district against the items, and leave out the ones no item reaches."""
    parts = [measure_raster(Path(path), districts, overview_level=overview_level) for path in paths]
    return combine(parts, districts["id"])


def aggregate_places(
    measured: Mapping[str, Measurement | None], parents: Mapping[str, str | None]
) -> dict[str, Measurement]:
    """Districts as measured, provinces and the country as the sum of their districts."""
    places: dict[str, Measurement] = {}
    for place_id in sorted(measured):
        measurement = measured[place_id]
        if measurement is None:
            continue
        places[place_id] = measurement
        province = parents[place_id]
        if province:
            places.setdefault(province, Measurement()).add(measurement)
        places.setdefault("PK", Measurement()).add(measurement)
    return places


def quality_gates(
    places: Mapping[str, Measurement],
    land_ha: Mapping[str, float],
    parents: Mapping[str, str | None],
    *,
    minimum_coverage_pct: float = MINIMUM_COVERAGE_PCT,
) -> None:
    """Refuse a year whose measurements cannot be right."""
    wholes = {parent for parent in parents.values() if parent}
    for place_id in sorted(places):
        measurement = places[place_id]
        area = land_ha.get(place_id, 0.0)
        if area <= 0:
            raise LandCoverStatsError(f"{place_id}: no administrative land area to measure against")
        if measurement.measured_ha > area * MAXIMUM_AREA_FACTOR:
            raise LandCoverStatsError(
                f"{place_id}: measured {measurement.measured_ha:.0f} ha, "
                f"larger than the {area:.0f} ha of land it covers"
            )
        coverage = measurement.measured_ha / area * 100
        if place_id in wholes and coverage < minimum_coverage_pct:
            raise LandCoverStatsError(
                f"{place_id}: coverage is {coverage:.2f}%, below {minimum_coverage_pct:.2f}%"
            )
    _reconcile(places, land_ha, parents)


def _reconcile(
    places: Mapping[str, Measurement], land_ha: Mapping[str, float], parents: Mapping[str, str | None]
) -> None:
    """Every province and the country must be the sum of its parts, in land and in class."""
    children: dict[str, list[str]] = {}
    for place_id, parent in parents.items():
        if parent:
            children.setdefault(parent, []).append(place_id)
    for parent, parts in sorted(children.items()):
        whole = places.get(parent)
        if whole is None:
            continue
        tolerance = land_ha[parent] * RECONCILIATION_TOLERANCE
        land = sum(land_ha[part] for part in parts)
        if abs(land - land_ha[parent]) > tolerance:
            raise LandCoverStatsError(
                f"{parent}: its parts cover {land:.0f} ha of its {land_ha[parent]:.0f} ha of land"
            )
        totals = Measurement()
        for part in parts:
            if part in places:
                totals.add(places[part])
        for code in CLASS_CODES:
            if abs(totals.classes_ha[code] - whole.classes_ha[code]) > tolerance:
                raise LandCoverStatsError(f"{parent}: class {code} does not add up from its parts")
        if abs(totals.cloud_ha - whole.cloud_ha) > tolerance:
            raise LandCoverStatsError(f"{parent}: cloud does not add up from its parts")


def build_artifact(
    by_year: Mapping[str, Mapping[str, Measurement]],
    meta: Mapping[str, Mapping[str, Any]],
    *,
    provenance: Mapping[str, Any],
    method: str,
) -> dict[str, Any]:
    """The published artifact: every place, every year, and how it was measured."""
    places: dict[str, Any] = {}
    for place_id in sorted(meta):
        entry = {**meta[place_id], "by_year": {}}
        for year in sorted(by_year):
            measurement = by_year[year].get(place_id)
            if measurement is not None:
                entry["by_year"][year] = measurement.as_dict(float(meta[place_id]["area_ha"]))
        places[place_id] = entry
    return {
        "schema_version": SCHEMA_VERSION,
        "collection": COLLECTION,
        "version": VERSION,
        "area_unit": "hectares",
        "classes": [str(code) for code in CLASS_CODES],
        "years": sorted(by_year),
        "method": method,
        "gates": {
            "minimum_coverage_pct": MINIMUM_COVERAGE_PCT,
            "maximum_area_factor": MAXIMUM_AREA_FACTOR,
            "reconciliation_tolerance": RECONCILIATION_TOLERANCE,
        },
        "provenance": dict(provenance),
        "places": places,
    }


def _search_items(year: int) -> list[dict[str, Any]]:
    """The source items covering Pakistan for a year, straight from the catalogue."""
    from csa_portal.land_cover_mpc import STAC_API, pakistan_geometry

    body = httpx.post(
        f"{STAC_API}/search",
        json={
            "collections": [COLLECTION],
            "intersects": pakistan_geometry(BOUNDARIES),
            "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
            "limit": 100,
        },
        timeout=60,
    ).json()
    if any(link.get("rel") == "next" for link in body.get("links", [])):
        raise LandCoverStatsError(f"more than one page of items for {year}")
    items = []
    for feature in body.get("features", []):
        # An item's period runs into the next year, so the search also returns the year before.
        if not str(feature.get("properties", {}).get("start_datetime", "")).startswith(str(year)):
            continue
        asset = feature["assets"]["data"]
        items.append({"id": feature["id"], "href": asset["href"], "size": asset.get("file:size")})
    if not items:
        raise LandCoverStatsError(f"no source items for {year}")
    return sorted(items, key=lambda item: item["id"])


class MpcSource:
    """Reads MPC items where they are: signed addresses to read, and blob versions for the record."""

    def __init__(self, client: httpx.Client, *, retry_delay: float = 5.0) -> None:
        self.client = client
        self.retry_delay = retry_delay
        self._tokens: dict[tuple[str, str], str] = {}

    def _token(self, href: str) -> str:
        # The storage account is private, so an item needs a short-lived token to be read; one
        # token serves every item in the same container.
        account = href.split("//", 1)[1].split(".", 1)[0]
        container = href.split(".net/", 1)[1].split("/", 1)[0]
        key = (account, container)
        if key not in self._tokens:
            for attempt in range(2):
                response = self.client.get(f"{SAS_API}/{account}/{container}", timeout=60)
                if response.is_success:
                    self._tokens[key] = response.json()["token"]
                    break
                if attempt == 0:
                    time.sleep(self.retry_delay)
            else:
                raise LandCoverStatsError(
                    f"no read token for {account}/{container}: HTTP {response.status_code}"
                )
        return self._tokens[key]

    def signed_href(self, item: Mapping[str, Any]) -> str:
        return f"{item['href']}?{self._token(item['href'])}"

    def fingerprint(self, item: Mapping[str, Any]) -> dict[str, Any]:
        """Which version of the item's file is read, from its headers alone."""
        response = self.client.head(self.signed_href(item), timeout=60)
        response.raise_for_status()
        size = int(response.headers["content-length"])
        if item.get("size") is not None and size != item["size"]:
            raise LandCoverStatsError(
                f"{item['id']}: the file is {size} bytes, but the catalogue says {item['size']}"
            )
        return {
            "id": item["id"],
            "href": item["href"],
            "size": size,
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
        }


def _measure_item(task: tuple[str, str, Path, int | None]) -> tuple[str, dict[str, Measurement]]:
    """Measure one item where it is stored against every district, in its own process."""
    item_id, href, districts_path, overview_level = task
    districts = gpd.read_file(districts_path)
    return item_id, measure_raster(f"/vsicurl/{href}", districts, overview_level=overview_level, name=item_id)


def place_meta(
    districts: gpd.GeoDataFrame, provinces: gpd.GeoDataFrame
) -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    """Every place with its name, level and parent, and its land area on an equal-area grid."""
    equal_area = "ESRI:54034"
    land_ha = dict(zip(districts["id"], districts.to_crs(equal_area).geometry.area / 10_000.0))
    land_ha.update(zip(provinces["id"], provinces.to_crs(equal_area).geometry.area / 10_000.0))
    land_ha["PK"] = float(sum(land_ha[place_id] for place_id in provinces["id"]))
    meta: dict[str, dict[str, Any]] = {
        "PK": {"name": "Pakistan", "level": "national", "parent_id": None, "area_ha": round(land_ha["PK"], 1)}
    }
    for frame, level in ((provinces, "province"), (districts, "district")):
        for row in frame.itertuples():
            meta[row.id] = {
                "name": str(row.name),
                "level": level,
                "parent_id": str(row.parent_id),
                "area_ha": round(float(land_ha[row.id]), 1),
            }
    return meta, land_ha


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("years", nargs="*", type=int, help="Observation years; default: every published year")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--overview", type=int, default=OVERVIEW_LEVEL, choices=range(5),
        help="Overview to read: 0 is 20 m, 1 is 40 m, 2 is 80 m (default), 3 is 160 m, 4 is 320 m",
    )
    parser.add_argument("--workers", type=int, default=8, help="Items read at once (default 8)")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    years = sorted(set(args.years or YEARS))
    unsupported = [year for year in years if year not in YEARS]
    if unsupported:
        raise SystemExit(f"unsupported years {unsupported}; choose {YEARS[0]}-{YEARS[-1]}")

    source = MpcSource(httpx.Client(follow_redirects=True))
    items = {year: _search_items(year) for year in years}
    fingerprints = {item["id"]: source.fingerprint(item) for year in years for item in items[year]}

    districts_path = BOUNDARIES / "districts.geojson"
    districts = gpd.read_file(districts_path)
    provinces = gpd.read_file(BOUNDARIES / "provinces.geojson")
    meta, land_ha = place_meta(districts, provinces)
    parents = {place_id: entry["parent_id"] for place_id, entry in meta.items()}

    started = time.time()
    tasks = [
        (item["id"], source.signed_href(item), districts_path, args.overview)
        for year in years
        for item in items[year]
    ]
    with ProcessPoolExecutor(max_workers=max(1, min(args.workers, len(tasks)))) as pool:
        results = dict(pool.map(_measure_item, tasks))

    by_year: dict[str, dict[str, Measurement]] = {}
    cell_m = 10 * 2 ** (args.overview + 1)
    provenance: dict[str, Any] = {
        "collection": COLLECTION,
        "version": VERSION,
        "overview_level": args.overview,
        "cell_size_m": cell_m,
        "years": {},
    }
    for year in years:
        ids = [item["id"] for item in items[year]]
        measured = combine((results[item_id] for item_id in ids), districts["id"])
        places = aggregate_places(measured, parents)
        try:
            quality_gates(places, land_ha, parents)
        except LandCoverStatsError as error:
            raise LandCoverStatsError(f"{year}: {error}") from error
        by_year[str(year)] = places
        provenance["years"][str(year)] = [fingerprints[item_id] for item_id in ids]
    method = (
        "Area of each class inside each place, counted cell by cell from the annual source items, "
        f"read from Microsoft Planetary Computer on their own {cell_m} m overview. "
        "Districts are measured; provinces and Pakistan are the sum of their "
        "districts. Classified area excludes clouds; what the data does not reach is no data, "
        "counted against the administrative land area of the place."
    )
    artifact = build_artifact(by_year, meta, provenance=provenance, method=method)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    partial = args.out.with_suffix(".json.part")
    partial.write_text(json.dumps(artifact, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(partial, args.out)
    print(
        f"wrote {args.out}: {len(artifact['places'])} places, {artifact['years']}, "
        f"in {time.time() - started:.0f} s"
    )


if __name__ == "__main__":
    main()
