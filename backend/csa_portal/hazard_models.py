"""Forecast layers computed from other forecast layers: rolling windows over real values.

PMD hands out instantaneous fields; agricultural risks depend on how long conditions last.
A derived model reads the real-value files of its input layer over a window, runs a pure
function on the stack, and stores the result as colour positions exactly like any other
forecast layer, so tiles, times, and the frontend all work unchanged.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pydantic import BaseModel, Field, ValidationError, model_validator

from .catalogue import Identifier
from .forecast import (
    HOUR,
    ForecastError,
    ForecastLayer,
    ForecastService,
    Slot,
    write_positions,
)
from .models import COMPUTES

logger = logging.getLogger("uvicorn.error")

GROUP_ID = "hazard-models"
GROUP_TITLE = "Hazard models"


class DerivedRegistryError(ValueError):
    """The hazard model list is missing or invalid."""


def step_hours(valids: list[datetime]) -> np.ndarray:
    """How many hours each time's reading stands for: until the next, the last repeating the last gap."""
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(valids, valids[1:], strict=False)]
    return np.array([*gaps, gaps[-1]], dtype="float64")


class DerivedSpec(BaseModel):
    """One model computed from other forecast layers rather than fetched from PMD."""

    id: Identifier
    title: str
    group: str = GROUP_ID
    unit: str = ""
    colours: list[str] = Field(min_length=2)
    min: float
    max: float
    stops: list[float] | None = None
    hide_below: float | None = None
    # The layer whose real values feed the model, and at which level.
    input_layer: Identifier
    input_level: int = 0
    # How far back the window reaches, and the fewest input times it needs.
    window_hours: float = Field(gt=0)
    min_points: int = Field(ge=2, default=2)
    # The pure function to run, looked up by name, and its parameters.
    compute: str
    params: dict[str, float] = {}

    @model_validator(mode="after")
    def _consistent(self) -> DerivedSpec:
        if self.min >= self.max:
            raise ValueError(f"derived model '{self.id}' has an empty value range")
        if self.stops is not None:
            rising = all(a < b for a, b in zip(self.stops, self.stops[1:], strict=False))
            if len(self.stops) != len(self.colours) or not rising:
                raise ValueError(f"derived model '{self.id}' needs one rising stop per colour")
            if (self.stops[0], self.stops[-1]) != (self.min, self.max):
                raise ValueError(f"derived model '{self.id}': stops must run from min to max")
        if self.compute not in COMPUTES:
            raise ValueError(f"derived model '{self.id}' names unknown compute '{self.compute}'")
        return self

    def layer(self) -> ForecastLayer:
        """The model as the frontend sees it: an ordinary forecast layer."""
        return ForecastLayer(
            id=self.id, title=self.title, group=self.group, code=self.id, unit=self.unit,
            colours=self.colours, min=self.min, max=self.max, stops=self.stops,
            hide_below=self.hide_below,
        )


class DerivedModelFile(BaseModel):
    version: str
    models: list[DerivedSpec]


def load_hazard_models(path: Path) -> DerivedModelFile:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise DerivedRegistryError(f"Hazard model list not found: {path}") from err
    except json.JSONDecodeError as err:
        raise DerivedRegistryError(f"Hazard model list is not valid JSON: {path}: {err}") from err
    try:
        file = DerivedModelFile.model_validate(raw)
    except ValidationError as err:
        raise DerivedRegistryError(f"Hazard model list is invalid: {path}: {err}") from err
    seen: set[str] = set()
    for model in file.models:
        if model.id in seen:
            raise DerivedRegistryError(f"Hazard model list has a duplicate id '{model.id}': {path}")
        seen.add(model.id)
    return file


class DerivedService:
    """Serves the layers that are computed from other forecast layers."""

    def __init__(self, forecast: ForecastService, models: DerivedModelFile) -> None:
        self._forecast = forecast
        self._models = {model.id: model for model in models.models}
        self._locks: dict[Any, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        for spec in self._models.values():
            try:
                forecast.layer(spec.input_layer)
            except ForecastError as err:
                raise DerivedRegistryError(
                    f"derived model '{spec.id}' names unknown input layer '{spec.input_layer}'"
                ) from err

    @property
    def configured(self) -> bool:
        return self._forecast.configured

    def has(self, layer_id: str) -> bool:
        return layer_id in self._models

    def spec(self, layer_id: str) -> DerivedSpec:
        model = self._models.get(layer_id)
        if model is None:
            raise ForecastError(404, "not-found", f"Unknown forecast layer '{layer_id}'")
        return model

    def layer(self, layer_id: str) -> ForecastLayer:
        return self.spec(layer_id).layer()

    def describe(self) -> dict[str, Any]:
        """The derived layers and their group, to be appended to the forecast description."""
        layers = []
        for spec in self._models.values():
            source = self._forecast.layer(spec.input_layer)
            levels = {
                model_id: [spec.input_level]
                for model_id, offered in source.levels.items()
                if spec.input_level in offered
            }
            layers.append(
                {
                    "id": spec.id,
                    "title": spec.title,
                    "group": spec.group,
                    "unit": spec.unit,
                    "colours": spec.colours,
                    "min": spec.min,
                    "max": spec.max,
                    "ranges": {},
                    "model_ranges": {},
                    "stops": spec.stops,
                    "levels": levels,
                }
            )
        return {
            "groups": [{"id": GROUP_ID, "title": GROUP_TITLE}],
            "layers": layers,
        }

    def times(self, layer_id: str, model_id: str, level: int) -> list[Slot]:
        """Every time the model can be shown for: the input times with a full window behind them."""
        spec = self._choice(layer_id, level)
        slots = self._forecast.times(spec.input_layer, model_id, spec.input_level)
        usable = []
        for slot in slots:
            if self._window(model_id, slot.run, slot.valid, spec):
                usable.append(Slot(valid=slot.valid, run=slot.run, path=f"derived:{spec.id}:{slot.run:{HOUR}}"))
        return usable

    def file(self, layer_id: str, model_id: str, level: int, valid: datetime, run: datetime | None = None) -> Path:
        """The stored file for a derived model at a time, computed if this is the first request for it."""
        spec = self._choice(layer_id, level)
        slots = self.times(layer_id, model_id, level)
        if run is None:
            slot = next((s for s in slots if s.valid == valid), None)
            if slot is None:
                raise ForecastError(404, "no-data", f"No forecast for {valid:%d %b %H:%M} UTC")
            run = slot.run
        elif not any(s.valid == valid and s.run == run for s in slots):
            raise ForecastError(404, "no-data", f"No forecast for {valid:%d %b %H:%M} UTC from that run")
        window = self._window(model_id, run, valid, spec)
        if not window:
            raise ForecastError(404, "no-data", f"Not enough forecast steps behind {valid:%d %b %H:%M} UTC")
        layer = spec.layer()
        folder = self._forecast.cache_dir / "_derived" / layer_id / model_id / str(level)
        scale = "_".join(f"{value:g}" for value in layer.colour_values(level, model_id))
        path = folder / f"{valid:{HOUR}}_{run:{HOUR}}_{scale}.tif"
        if path.is_file():
            return path
        with self._lock(path):
            if path.is_file():
                return path
            stack, transform = self._stack(model_id, run, window, spec)
            result = COMPUTES[spec.compute](stack, step_hours(window), spec.params)
            write_positions(np.ma.masked_invalid(result), transform, path, layer, level, model_id)
        self._forecast.prune()
        return path

    def _choice(self, layer_id: str, level: int) -> DerivedSpec:
        spec = self.spec(layer_id)
        if level != spec.input_level:
            raise ForecastError(404, "not-found", f"'{spec.title}' is only offered at level {spec.input_level}")
        if not self._forecast.configured:
            raise ForecastError(501, "not-configured", "The forecast source is not set up on this server")
        return spec

    def _window(self, model_id: str, run: datetime, valid: datetime, spec: DerivedSpec) -> list[datetime]:
        """The input times ending at `valid` from `run`, or [] if the window is too thin."""
        cutoff = valid - timedelta(hours=spec.window_hours)
        offered = self._forecast.known_valids(spec.input_layer, model_id, spec.input_level, run)
        window = [v for v in offered if cutoff < v <= valid]
        return window if len(window) >= spec.min_points else []

    def _stack(
        self, model_id: str, run: datetime, window: list[datetime], spec: DerivedSpec
    ) -> tuple[np.ndarray, Any]:
        """The input times' real values as one array, with the grid they share."""
        bands = []
        transform = None
        for valid in window:
            path = self._forecast.value_file(spec.input_layer, model_id, spec.input_level, valid, run)
            with rasterio.open(path) as stored:
                if transform is None:
                    transform = stored.transform
                bands.append(stored.read(1, masked=True).astype("float64"))
        return np.stack(bands), transform

    def _lock(self, key: Any) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())
