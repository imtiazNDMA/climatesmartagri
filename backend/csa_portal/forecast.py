"""Weather forecast layers, fetched from PMD the first time each is asked for and kept on disk.

A forecast layer is a quantity (temperature, 24-hour rain), shown for one model, one pressure level
and one time. PMD's server cannot be read in parts, so a file is downloaded whole, cut down to the
area around Pakistan, and stored as a small GeoTIFF that TiTiler serves from then on.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Protocol

import numpy as np
import rasterio
from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError, model_validator
from rasterio.io import MemoryFile
from rasterio.windows import from_bounds
from rasterio.windows import transform as window_transform
from titiler.core.dependencies import parse_color
from titiler.core.factory import TilerFactory

from .catalogue import Identifier
from .pmd import PmdError, PmdFile

logger = logging.getLogger("uvicorn.error")

FORECAST_PREFIX = "/api/forecast"
HOUR = "%Y%m%d%H"
# A stored file holds colour positions, not values: 0 is "nothing here", 1 to 255 run along the ramp.
STEPS = 254
# How many of a model's newest runs are searched for files. Runs are often incomplete, so one is not enough.
RUNS_CONSIDERED = 4
# A list of times younger than this is used as it is. An older one is still handed out at once, and
# a fresh one is fetched behind it: PMD can take a minute to answer, and nobody should wait on that twice.
LISTING_SECONDS = 600
# After PMD fails to refresh a list, how long before it is asked again.
REFRESH_RETRY_SECONDS = 60
# How long a failed fetch is remembered, so the dozen tiles of one map view do not each try it again.
UNREACHABLE_SECONDS = 60
BAD_FILE_SECONDS = 600
KEEP_DAYS = 10
PRUNE_EVERY_SECONDS = 3600
# The status for "PMD let us down". Not 502 to 504: the frontend reads those as the portal's own backend
# being unreachable, which it is not.
SOURCE_FAILED = 424


class ForecastError(Exception):
    """A forecast could not be served. `reason` is a short code the frontend can act on."""

    def __init__(self, status: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message


class RegistryError(ValueError):
    """The forecast layer list is missing or invalid."""


class ValueRange(BaseModel):
    min: float
    max: float

    @model_validator(mode="after")
    def _ordered(self) -> ValueRange:
        if self.min >= self.max:
            raise ValueError(f"range {self.min} to {self.max} is empty or reversed")
        return self


class ForecastModel(BaseModel):
    id: Identifier
    label: str
    # The model's name in PMD's data requests.
    source: str


class ForecastGroup(BaseModel):
    id: Identifier
    title: str


class ForecastLayer(BaseModel):
    id: Identifier
    title: str
    group: str
    # The quantity's name in PMD's data requests.
    code: str
    unit: str = ""
    colours: list[str] = Field(min_length=2)
    min: float
    max: float
    # A different value range at some pressure levels, by level: upper-air temperature is far colder.
    ranges: dict[int, ValueRange] = {}
    # A different value range for some models, by model id, where a model's figure is not comparable
    # with the others'. It wins over a level's range.
    model_ranges: dict[str, ValueRange] = {}
    # A further multiplier for some models, by model id, where a model stores the quantity in other
    # units than the rest: kilograms per kilogram rather than grams, a fraction rather than a percentage.
    model_factors: dict[str, float] = {}
    # Values above this are a file's "nothing here" marker, not measurements, and are left clear.
    ignore_above: float | None = None
    # The value each colour sits at, one per colour, rising, from min to max. For a quantity that is
    # mostly small with rare large values, such as rain: evenly spread colours would show almost none of
    # it. Without stops the colours are spread evenly between min and max.
    stops: list[float] | None = None
    # Shown value = stored value x factor + add, for a source that stores other units (kelvin, pascals).
    factor: float = 1.0
    add: float = 0.0
    # The file holds wind's two components; the layer shows the speed worked out from them.
    wind: bool = False
    # Values below this are left clear, so dry areas do not hide the map under a rain layer.
    hide_below: float | None = None
    # The levels each model offers, by model id. 0 is the surface. Empty: PMD has no current data.
    levels: dict[str, list[int]] = {}

    def value_range(self, level: int, model_id: str = "") -> tuple[float, float]:
        chosen = self.model_ranges.get(model_id) or self.ranges.get(level)
        return (chosen.min, chosen.max) if chosen else (self.min, self.max)

    def colour_values(self, level: int, model_id: str = "") -> list[float]:
        """The value each colour sits at, for a level and model."""
        if self.stops is not None:
            return list(self.stops)
        low, high = self.value_range(level, model_id)
        last = len(self.colours) - 1
        return [low + (high - low) * index / last for index in range(last + 1)]


class ForecastRegistry(BaseModel):
    # West, south, east, north: the area kept from each file.
    bbox: tuple[float, float, float, float]
    models: list[ForecastModel]
    groups: list[ForecastGroup]
    layers: list[ForecastLayer]

    @model_validator(mode="after")
    def _consistent(self) -> ForecastRegistry:
        west, south, east, north = self.bbox
        if west >= east or south >= north:
            raise ValueError("bbox must be west, south, east, north")
        model_ids = {model.id for model in self.models}
        group_ids = {group.id for group in self.groups}
        seen: set[str] = set()
        for layer in self.layers:
            if layer.id in seen:
                raise ValueError(f"duplicate forecast layer '{layer.id}'")
            seen.add(layer.id)
            if layer.group not in group_ids:
                raise ValueError(f"forecast layer '{layer.id}' names unknown group '{layer.group}'")
            if layer.min >= layer.max:
                raise ValueError(f"forecast layer '{layer.id}' has an empty value range")
            if layer.stops is not None:
                rising = all(a < b for a, b in zip(layer.stops, layer.stops[1:], strict=False))
                if len(layer.stops) != len(layer.colours) or not rising:
                    raise ValueError(f"forecast layer '{layer.id}' needs one rising stop per colour")
                if (layer.stops[0], layer.stops[-1]) != (layer.min, layer.max) or layer.ranges or layer.model_ranges:
                    raise ValueError(
                        f"forecast layer '{layer.id}': stops must run from min to max, without other ranges"
                    )
            for model_id in [*layer.model_ranges, *layer.model_factors]:
                if model_id not in model_ids:
                    raise ValueError(f"forecast layer '{layer.id}' names unknown model '{model_id}'")
            for model_id in layer.levels:
                if model_id not in model_ids:
                    raise ValueError(f"forecast layer '{layer.id}' names unknown model '{model_id}'")
        return self


def load_registry(path: Path) -> ForecastRegistry:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise RegistryError(f"Forecast layer list not found: {path}") from err
    except json.JSONDecodeError as err:
        raise RegistryError(f"Forecast layer list is not valid JSON: {path}: {err}") from err
    try:
        return ForecastRegistry.model_validate(raw)
    except ValidationError as err:
        raise RegistryError(f"Forecast layer list is invalid: {path}: {err}") from err


class ForecastSource(Protocol):
    """What the forecast needs from PMD. The real one is `PmdClient`."""

    def runs(self, source: str, element: str) -> list[datetime]: ...
    def files(self, source: str, element: str, level: int, run: datetime) -> list[PmdFile]: ...
    def download(self, path: str) -> bytes: ...


def ramp_colourmap(colours: list[str]) -> dict[int, tuple[int, int, int, int]]:
    """A colour for each of the 255 stored positions, spread evenly along the ramp."""
    stops = [parse_color(colour) for colour in colours]
    last = len(stops) - 1
    result: dict[int, tuple[int, int, int, int]] = {}
    for position in range(STEPS + 1):
        at = position / STEPS * last
        low = min(int(at), last - 1)
        share = at - low
        mixed = [round(a + (b - a) * share) for a, b in zip(stops[low], stops[low + 1], strict=True)]
        result[position + 1] = (mixed[0], mixed[1], mixed[2], mixed[3])
    return result


def read_physical(
    data: bytes,
    layer: ForecastLayer,
    level: int,
    bbox: tuple[float, float, float, float],
    model_id: str = "",
) -> tuple[np.ma.MaskedArray, Any]:
    """Cut a downloaded forecast file down to the kept area, as real values rather than colours."""
    with MemoryFile(data) as memory, memory.open() as source:
        grid = source.transform
        if grid.b != 0 or grid.d != 0 or grid.a <= 0 or grid.e >= 0:
            raise ForecastError(SOURCE_FAILED, "bad-source", "PMD's file is not a plain north-up grid")
        bounds = source.bounds
        west, south = max(bbox[0], bounds.left), max(bbox[1], bounds.bottom)
        east, north = min(bbox[2], bounds.right), min(bbox[3], bounds.top)
        if west >= east or south >= north:
            raise ForecastError(404, "no-data", "This forecast does not cover the area the portal shows")
        # The stored file always spans the whole kept area, empty where this model has no cells, so that
        # every tile inside the area can be drawn and none is refused for lying outside a smaller grid.
        window = from_bounds(*bbox, source.transform).round_offsets().round_lengths()
        if layer.wind and source.count < 2:
            raise ForecastError(SOURCE_FAILED, "bad-source", "The wind file does not hold two components")
        tags = source.tags()
        scale = float(tags.get("scale") or 1) or 1.0
        offset = float(tags.get("offset") or 0)
        bands = source.read(
            [1, 2] if layer.wind else [1], window=window, masked=True, boundless=True
        ).astype("float64")
        transform = window_transform(window, source.transform)

    stored = bands / scale + offset
    values = np.ma.hypot(stored[0], stored[1]) if layer.wind else stored[0]
    if layer.ignore_above is not None:
        values = np.ma.masked_greater(values, layer.ignore_above)
    values = values * layer.factor * layer.model_factors.get(model_id, 1.0) + layer.add
    return values, transform


def _write_geotiff(out: np.ndarray, transform: Any, destination: Path, *, dtype: str, nodata: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".part")
    os.close(handle)
    try:
        with rasterio.open(
            temporary, "w", driver="GTiff", width=out.shape[1], height=out.shape[0], count=1, dtype=dtype,
            crs="EPSG:4326", transform=transform, nodata=nodata, tiled=True, blockxsize=256, blockysize=256,
            compress="deflate",
        ) as target:
            target.write(out, 1)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def write_positions(
    values: np.ma.MaskedArray,
    transform: Any,
    destination: Path,
    layer: ForecastLayer,
    level: int,
    model_id: str = "",
) -> None:
    """Store real values as colour positions: 0 is "nothing here", 1 to 255 run along the ramp."""
    # Each colour sits at a value; a value between two of them takes a position between theirs.
    at = layer.colour_values(level, model_id)
    along = np.interp(np.ma.filled(values, at[0]), at, np.linspace(0, STEPS, len(at)))
    positions = np.rint(along) + 1
    empty = np.ma.getmaskarray(values) | ~np.isfinite(np.ma.filled(values, np.nan))
    if layer.hide_below is not None:
        empty |= np.ma.filled(values, np.nan) < layer.hide_below
    out = np.where(empty, 0, positions).astype("uint8")
    _write_geotiff(out, transform, destination, dtype="uint8", nodata=0)


def write_values(values: np.ma.MaskedArray, transform: Any, destination: Path) -> None:
    """Store real values as a float32 GeoTIFF, for the models that read them back."""
    out = np.ma.filled(values.astype("float32"), np.nan)
    _write_geotiff(out, transform, destination, dtype="float32", nodata=float("nan"))


def convert(
    data: bytes,
    destination: Path,
    layer: ForecastLayer,
    level: int,
    bbox: tuple[float, float, float, float],
    model_id: str = "",
) -> None:
    """Cut a downloaded forecast file down to the kept area and store it as colour positions."""
    values, transform = read_physical(data, layer, level, bbox, model_id)
    write_positions(values, transform, destination, layer, level, model_id)


@dataclass(frozen=True)
class Slot:
    """A time a layer can be shown for, and the file that shows it: the newest run that has one."""

    valid: datetime
    run: datetime
    path: str


def _in_background(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


ListingKey = tuple[str, str, int]


class ForecastService:
    def __init__(
        self,
        registry: ForecastRegistry,
        source: ForecastSource | None,
        cache_dir: Path,
        clock: Callable[[], float] = time.time,
        background: Callable[[Callable[[], None]], None] = _in_background,
    ) -> None:
        self.registry = registry
        self._source = source
        self._cache_dir = Path(cache_dir)
        self._clock = clock
        self._background = background
        self._layers = {layer.id: layer for layer in registry.layers}
        self._models = {model.id: model for model in registry.models}
        # What is remembered, and where: lists of times in memory and on disk; every file a list has
        # named, by time and run, in memory; fetched files on disk; recent failures in memory.
        self._listings: dict[ListingKey, tuple[float, list[Slot]]] = {}
        self._known: dict[tuple[ListingKey, datetime, datetime], str] = {}
        self._refreshing: set[ListingKey] = set()
        self._retry_after: dict[ListingKey, float] = {}
        self._failed: dict[Any, tuple[float, ForecastError]] = {}
        self._locks: dict[Any, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._pruned_at: float | None = None

    @property
    def configured(self) -> bool:
        return self._source is not None

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def lock(self, key: Any) -> threading.Lock:
        """A lock others may share for one stored path, so it is written only once."""
        return self._lock(key)

    def prune(self) -> None:
        self._prune()

    def describe(self) -> dict[str, Any]:
        """The layer list as the frontend needs it."""
        return {
            "configured": self.configured,
            "bbox": list(self.registry.bbox),
            "models": [{"id": model.id, "label": model.label} for model in self.registry.models],
            "groups": [group.model_dump() for group in self.registry.groups],
            "layers": [
                {
                    "id": layer.id,
                    "title": layer.title,
                    "group": layer.group,
                    "unit": layer.unit,
                    "colours": layer.colours,
                    "min": layer.min,
                    "max": layer.max,
                    "ranges": {str(level): [r.min, r.max] for level, r in layer.ranges.items()},
                    "model_ranges": {model_id: [r.min, r.max] for model_id, r in layer.model_ranges.items()},
                    "stops": layer.stops,
                    "levels": layer.levels,
                }
                for layer in self.registry.layers
            ],
        }

    def layer(self, layer_id: str) -> ForecastLayer:
        layer = self._layers.get(layer_id)
        if layer is None:
            raise ForecastError(404, "not-found", f"Unknown forecast layer '{layer_id}'")
        return layer

    def _choice(self, layer_id: str, model_id: str, level: int) -> tuple[ForecastLayer, ForecastModel, ForecastSource]:
        layer = self.layer(layer_id)
        model = self._models.get(model_id)
        if model is None:
            raise ForecastError(404, "not-found", f"Unknown forecast model '{model_id}'")
        if level not in layer.levels.get(model_id, []):
            raise ForecastError(404, "not-found", f"{model.label} has no '{layer.title}' at level {level}")
        if self._source is None:
            raise ForecastError(501, "not-configured", "The forecast source is not set up on this server")
        return layer, model, self._source

    def _lock(self, key: Any) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    def times(self, layer_id: str, model_id: str, level: int) -> list[Slot]:
        """Every time the layer can be shown for, earliest first, each from the newest run that has it."""
        layer, model, source = self._choice(layer_id, model_id, level)
        key = (layer_id, model_id, level)
        cached = self._listing(key)
        if cached is not None:
            fetched_at, slots = cached
            if self._clock() - fetched_at >= LISTING_SECONDS:
                self._refresh_behind(key, layer, model, source)
            return slots
        with self._lock(("listing", key)):
            cached = self._listing(key)  # another request may have fetched it while this one waited
            if cached is not None:
                return cached[1]
            try:
                return self._fetch_listing(key, layer, model, source)
            except PmdError as err:
                raise ForecastError(SOURCE_FAILED, "source-unreachable", f"PMD could not be reached: {err}") from err

    def _listing(self, key: ListingKey) -> tuple[float, list[Slot]] | None:
        """The remembered list for a choice: from memory, or from disk after a restart."""
        if key not in self._listings:
            stored = self._listing_file(key)
            try:
                raw = json.loads(stored.read_text(encoding="utf-8"))
                slots = [
                    Slot(valid=parse_hour(s["valid"]), run=parse_hour(s["run"]), path=s["path"]) for s in raw["slots"]
                ]
                self._remember(key, float(raw["fetched_at"]), slots)
            except (OSError, ValueError, KeyError, TypeError, ForecastError):
                return None  # no file yet, or one that cannot be read: as good as none
        return self._listings[key]

    def _listing_file(self, key: ListingKey) -> Path:
        layer_id, model_id, level = key
        return self._cache_dir / "_listings" / f"{model_id}__{layer_id}__{level}.json"

    def _remember(self, key: ListingKey, fetched_at: float, slots: list[Slot]) -> None:
        self._listings[key] = (fetched_at, slots)
        for slot in slots:
            self._known[(key, slot.valid, slot.run)] = slot.path

    def _fetch_listing(self, key: ListingKey, layer: ForecastLayer, model: ForecastModel, source: ForecastSource) -> list[Slot]:
        """Ask PMD for a choice's times, remember them, and keep a copy on disk."""
        _, _, level = key
        runs = source.runs(model.source, layer.code)[:RUNS_CONSIDERED]  # newest first
        # PMD answers slowly, so the runs are asked about side by side rather than one after another.
        with ThreadPoolExecutor(max_workers=RUNS_CONSIDERED) as pool:
            listings = list(pool.map(lambda run: source.files(model.source, layer.code, level, run), runs))
        chosen: dict[datetime, Slot] = {}
        for files in listings:
            for file in files:
                # A run's own file for a time stays fetchable after a newer run takes the time over.
                self._known[(key, file.valid, file.run)] = file.path
                chosen.setdefault(file.valid, Slot(valid=file.valid, run=file.run, path=file.path))
        slots = sorted(chosen.values(), key=lambda slot: slot.valid)
        fetched_at = self._clock()
        self._remember(key, fetched_at, slots)
        stored = self._listing_file(key)
        body = {
            "fetched_at": fetched_at,
            "slots": [{"valid": f"{s.valid:{HOUR}}", "run": f"{s.run:{HOUR}}", "path": s.path} for s in slots],
        }
        try:
            stored.parent.mkdir(parents=True, exist_ok=True)
            temporary = stored.with_suffix(".part")
            temporary.write_text(json.dumps(body), encoding="utf-8")
            os.replace(temporary, stored)
        except OSError:
            logger.warning("Could not save the forecast list %s", stored)
        return slots

    def _refresh_behind(self, key: ListingKey, layer: ForecastLayer, model: ForecastModel, source: ForecastSource) -> None:
        """Fetch a fresh list without keeping anyone waiting. One at a time per choice, and not straight after a failure."""
        with self._locks_guard:
            if key in self._refreshing or self._clock() < self._retry_after.get(key, 0):
                return
            self._refreshing.add(key)

        def refresh() -> None:
            try:
                self._fetch_listing(key, layer, model, source)
            except PmdError as err:
                # PMD is down: the old list goes on being used, which is more use than none.
                self._retry_after[key] = self._clock() + REFRESH_RETRY_SECONDS
                logger.warning("Could not refresh the forecast list for %s: %s", key, err)
            finally:
                self._refreshing.discard(key)

        self._background(refresh)

    def _paths(self, layer: ForecastLayer, model_id: str, level: int, valid: datetime, run: datetime) -> tuple[Path, Path]:
        """Where a stored time's colour file and real-value file live."""
        # The colours' values are part of the name: a file stored for others would be coloured wrongly.
        scale = "_".join(f"{value:g}" for value in layer.colour_values(level, model_id))
        factor = layer.model_factors.get(model_id, 1.0)
        folder = self._cache_dir / model_id / layer.id / str(level)
        return (
            folder / f"{valid:{HOUR}}_{run:{HOUR}}_{scale}{'' if factor == 1 else f'_x{factor:g}'}.tif",
            folder / f"{valid:{HOUR}}_{run:{HOUR}}_values.tif",
        )

    def _run_for(
        self, key: ListingKey, layer_id: str, model_id: str, level: int, valid: datetime, run: datetime | None
    ) -> tuple[datetime, str]:
        """Which run's file to use for a time, and where it is."""
        slot = next((s for s in self.times(layer_id, model_id, level) if s.valid == valid), None)
        if run is None:
            if slot is None:
                raise ForecastError(404, "no-data", f"No forecast for {valid:%d %b %H:%M} UTC")
            return slot.run, slot.path
        known = self._known.get((key, valid, run))
        if known is None:
            raise ForecastError(404, "no-data", f"No forecast for {valid:%d %b %H:%M} UTC from that run")
        return run, known

    def _ensure(
        self,
        layer: ForecastLayer,
        model_id: str,
        level: int,
        valid: datetime,
        run: datetime,
        remote: str,
        source: ForecastSource,
        want: str,
    ) -> Path:
        """The colour file or the real-value file for a time, fetched from PMD at most once for both.

        A colour file is rebuilt from stored values when they are there; values cannot be
        rebuilt from colours (the colours are a lossy quantisation), so they are fetched again.
        """
        colour, values = self._paths(layer, model_id, level, valid, run)
        wanted = colour if want == "colour" else values
        # Colour tiles and district statistics may ask for the same remote field together.
        # One shared lock keeps those two views from downloading it twice.
        with self._lock(("file", colour, values)):
            if wanted.is_file():
                return wanted
            failed = self._failed.get(("download", remote))
            if failed and self._clock() < failed[0]:
                raise failed[1]
            try:
                if want == "colour" and values.is_file():
                    with rasterio.open(values) as stored:
                        write_positions(stored.read(1, masked=True), stored.transform, colour, layer, level, model_id)
                else:
                    data = source.download(remote)
                    physical, transform = read_physical(data, layer, level, self.registry.bbox, model_id)
                    if not colour.is_file():
                        write_positions(physical, transform, colour, layer, level, model_id)
                    if not values.is_file():
                        write_values(physical, transform, values)
            except PmdError as err:
                problem = ForecastError(SOURCE_FAILED, "source-unreachable", f"PMD could not be reached: {err}")
                self._failed[("download", remote)] = (self._clock() + UNREACHABLE_SECONDS, problem)
                raise problem from err
            except rasterio.errors.RasterioError as err:
                problem = ForecastError(SOURCE_FAILED, "bad-source", f"PMD's file could not be read: {err}")
                self._failed[("download", remote)] = (self._clock() + BAD_FILE_SECONDS, problem)
                raise problem from err
            except ForecastError as problem:  # a file that is no use: outside the area, or not a plain grid
                self._failed[("download", remote)] = (self._clock() + BAD_FILE_SECONDS, problem)
                raise
            self._failed.pop(("download", remote), None)
        self._prune()
        return wanted

    def file(self, layer_id: str, model_id: str, level: int, valid: datetime, run: datetime | None = None) -> Path:
        """The stored file for a layer at a time, fetched from PMD if this is the first request for it.

        With a run named, the file is that run's own; without, it is the newest run's.
        """
        layer, _, source = self._choice(layer_id, model_id, level)
        key = (layer_id, model_id, level)
        # A file already here needs nothing from PMD, not even the list of times.
        if run is not None and self._paths(layer, model_id, level, valid, run)[0].is_file():
            return self._paths(layer, model_id, level, valid, run)[0]
        run, remote = self._run_for(key, layer_id, model_id, level, valid, run)
        return self._ensure(layer, model_id, level, valid, run, remote, source, want="colour")

    def value_file(self, layer_id: str, model_id: str, level: int, valid: datetime, run: datetime | None = None) -> Path:
        """The stored real values for a layer at a time, as a float32 GeoTIFF, fetched if need be.

        The same download writes both this and the colour file, so a time is fetched at most once.
        """
        layer, _, source = self._choice(layer_id, model_id, level)
        key = (layer_id, model_id, level)
        if run is not None and self._paths(layer, model_id, level, valid, run)[1].is_file():
            return self._paths(layer, model_id, level, valid, run)[1]
        run, remote = self._run_for(key, layer_id, model_id, level, valid, run)
        return self._ensure(layer, model_id, level, valid, run, remote, source, want="values")

    def known_valids(self, layer_id: str, model_id: str, level: int, run: datetime) -> list[datetime]:
        """The times a run offers for a layer, from the lists already fetched, earliest first."""
        key = (layer_id, model_id, level)
        return sorted(valid for (k, valid, r) in self._known if k == key and r == run)

    def _prune(self) -> None:
        """Delete stored files past their keeping time. Runs at most once an hour."""
        now = self._clock()
        if self._pruned_at is not None and now - self._pruned_at < PRUNE_EVERY_SECONDS:
            return
        self._pruned_at = now
        cutoff = time.time() - KEEP_DAYS * 86400
        for stored in self._cache_dir.rglob("*.tif"):
            try:
                if stored.stat().st_mtime < cutoff:
                    stored.unlink()
            except OSError:
                logger.warning("Could not remove old forecast file %s", stored)


def parse_hour(value: str) -> datetime:
    try:
        return datetime.strptime(value, HOUR)
    except ValueError as err:
        raise ForecastError(422, "bad-time", f"'{value}' is not a time written as YYYYMMDDHH") from err


def cache_control(status: int, *, is_tile: bool, names_run: bool) -> str:
    """How long a browser may keep a forecast answer.

    A tile that names its run can never change, so it is kept for a week and not asked about again.
    One that does not may be taken over by a newer run. A list of times goes stale within minutes.
    A failure is never kept: the next request should try afresh.
    """
    if status != 200:
        return "no-store"
    if is_tile:
        return "public, max-age=604800, immutable" if names_run else "public, max-age=300"
    return "private, max-age=60"


def _http(err: ForecastError) -> HTTPException:
    return HTTPException(status_code=err.status, detail={"message": err.message, "reason": err.reason})


def add_forecast_routes(app: FastAPI, service: ForecastService, derived: Any | None = None) -> None:
    """Serve the forecast layers; layers computed by `derived` (if any) go through it instead."""

    prefix = f"{FORECAST_PREFIX}/cog"

    def _slots(layer: str, model: str, level: int) -> list[Slot]:
        if derived is not None and derived.has(layer):
            return derived.times(layer, model, level)
        return service.times(layer, model, level)

    @app.middleware("http")
    async def forecast_cache_headers(request: Request, call_next: Any) -> Response:
        """Say how long a browser may keep each forecast answer."""
        response = await call_next(request)
        if request.url.path.startswith(f"{FORECAST_PREFIX}/"):
            is_tile = request.url.path.startswith(f"{prefix}/tiles/")
            response.headers["Cache-Control"] = cache_control(
                response.status_code, is_tile=is_tile, names_run="run" in request.query_params
            )
        return response

    @app.get(f"{FORECAST_PREFIX}/times", tags=["Weather forecast"])
    def get_times(layer: str, model: str, level: int = 0) -> dict[str, Any]:
        try:
            slots = _slots(layer, model, level)
        except ForecastError as err:
            raise _http(err) from err
        return {"times": [{"time": f"{s.valid:{HOUR}}", "run": f"{s.run:{HOUR}}"} for s in slots]}

    def forecast_path(
        layer: Annotated[str, Query(description="A forecast layer id")],
        model: Annotated[str, Query(description="A forecast model id")],
        time: Annotated[str, Query(description="The time the forecast is for, UTC, as YYYYMMDDHH")],
        level: Annotated[int, Query(description="Pressure level in hPa; 0 is the surface")] = 0,
        run: Annotated[str | None, Query(description="The model run to take it from, UTC, as YYYYMMDDHH")] = None,
    ) -> str:
        """TiTiler opens only the file this names: a forecast the layer list knows, fetched if need be."""
        try:
            parsed_run = parse_hour(run) if run else None
            if derived is not None and derived.has(layer):
                return str(derived.file(layer, model, level, parse_hour(time), parsed_run))
            return str(service.file(layer, model, level, parse_hour(time), parsed_run))
        except ForecastError as err:
            raise _http(err) from err

    def forecast_colourmap(layer: Annotated[str, Query()]) -> dict[int, tuple[int, int, int, int]]:
        try:
            colours = derived.layer(layer).colours if derived is not None and derived.has(layer) else service.layer(layer).colours
            return ramp_colourmap(colours)
        except ForecastError as err:
            raise _http(err) from err

    tiler = TilerFactory(router_prefix=prefix, path_dependency=forecast_path, colormap_dependency=forecast_colourmap)
    app.include_router(tiler.router, prefix=prefix, tags=["Weather forecast"])
