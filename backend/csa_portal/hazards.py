"""Versioned agricultural hazard guidance and district-level risk screening."""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from rasterio.features import bounds as geometry_bounds, geometry_mask
from rasterio.windows import Window, from_bounds

from .catalogue import Identifier
from .forecast import ForecastError, ForecastService, parse_hour
from .hazard_models import DerivedService
from .places import PlaceIndex


class HazardBand(BaseModel):
    severity: str
    label: str
    threshold: float
    colour: str


class HazardProduct(BaseModel):
    id: Identifier
    title: str
    forecast_layer: Identifier
    unit: str
    direction: str
    summary: str
    district_percentile: float = Field(ge=0, le=100)
    bands: list[HazardBand] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> "HazardProduct":
        values = [band.threshold for band in self.bands]
        expected = sorted(values, reverse=self.direction == "below")
        if self.direction not in {"above", "below"} or values != expected:
            raise ValueError("hazard thresholds must follow their direction")
        return self


class HazardRegistry(BaseModel):
    classification: str
    threshold_version: str
    disclaimer: str
    products: list[HazardProduct]


def load_hazards(path: Path) -> HazardRegistry:
    return HazardRegistry.model_validate(json.loads(path.read_text(encoding="utf-8")))


def classify_risk(product: HazardProduct, value: float) -> str | None:
    """Map a physical forecast value to low, medium, high, or no highlighted risk."""
    matched: str | None = None
    last = len(product.bands) - 1
    for index, band in enumerate(product.bands):
        if (product.direction == "above" and value >= band.threshold) or (
            product.direction == "below" and value <= band.threshold
        ):
            matched = "high" if index == last else "low" if index == 0 else "medium"
    return matched


def risk_colours(product: HazardProduct) -> dict[str, str]:
    """Representative colours for the three map classes, even if guidance later adds more bands."""
    middle = product.bands[len(product.bands) // 2]
    return {
        "low": product.bands[0].colour,
        "medium": middle.colour,
        "high": product.bands[-1].colour,
    }


def district_values(path: Path, features: list[dict[str, Any]], percentile: float) -> list[tuple[str, str, float]]:
    """Read one tail percentile per district, using cells touched by its boundary."""
    results: list[tuple[str, str, float]] = []
    with rasterio.open(path) as source:
        if source.crs != rasterio.crs.CRS.from_epsg(4326):
            raise ForecastError(424, "bad-source", "District risk requires a WGS84 forecast grid")
        whole = Window(0, 0, source.width, source.height)
        for feature in features:
            geometry = feature.get("geometry")
            properties = feature.get("properties") or {}
            if not geometry or not properties.get("id"):
                continue
            try:
                window = from_bounds(*geometry_bounds(geometry), transform=source.transform).round_offsets().round_lengths()
                window = window.intersection(whole)
            except rasterio.errors.WindowError:
                continue
            data = source.read(1, window=window, masked=True)
            inside = geometry_mask(
                [geometry], out_shape=data.shape, transform=source.window_transform(window), invert=True, all_touched=True
            )
            usable = np.asarray(data[inside & ~np.ma.getmaskarray(data)], dtype="float64")
            usable = usable[np.isfinite(usable)]
            if usable.size:
                results.append((str(properties["id"]), str(properties.get("name") or ""), float(np.percentile(usable, percentile))))
    return results


class DistrictRiskService:
    """Aggregate forecast fields over districts and apply the configured guidance thresholds."""

    def __init__(
        self,
        registry: HazardRegistry,
        places: PlaceIndex,
        forecast: ForecastService | None,
        derived: DerivedService | None,
    ) -> None:
        self.registry = registry
        self._products = {product.id: product for product in registry.products}
        self._features = places.boundaries.get("district", {}).get("features", [])
        self._forecast = forecast
        self._derived = derived
        self._cache: OrderedDict[tuple[str, str, int, datetime, datetime], dict[str, Any]] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._locks: dict[tuple[str, str, int, datetime, datetime], threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def calculate(
        self, hazard: str, model: str, level: int, valid: datetime, run: datetime
    ) -> dict[str, Any]:
        product = self._products.get(hazard)
        if product is None:
            raise ForecastError(404, "not-found", f"Unknown hazard '{hazard}'")
        if not self._features:
            raise ForecastError(404, "no-data", "District boundaries are not loaded")
        provider: ForecastService | DerivedService | None = self._forecast
        if self._derived is not None and self._derived.has(product.forecast_layer):
            provider = self._derived
        if provider is None:
            raise ForecastError(501, "not-configured", "The forecast source is not set up on this server")
        key = (hazard, model, level, valid, run)
        with self._lock(key):
            with self._cache_lock:
                cached = self._cache.get(key)
            if cached is not None:
                return cached
            path = provider.value_file(product.forecast_layer, model, level, valid, run)
            percentile = product.district_percentile
            districts = [
                {"id": district_id, "name": name, "value": round(value, 2), "risk": classify_risk(product, value)}
                for district_id, name, value in district_values(path, self._features, percentile)
            ]
            result = {
                "hazard": product.id,
                "forecast_layer": product.forecast_layer,
                "time": valid.strftime("%Y%m%d%H"),
                "run": run.strftime("%Y%m%d%H"),
                "unit": product.unit,
                "threshold_version": self.registry.threshold_version,
                "statistic": {
                    "percentile": percentile,
                    "label": f"{percentile:g}th percentile of forecast cells intersecting each district",
                },
                "colours": risk_colours(product),
                "districts": districts,
            }
            with self._cache_lock:
                self._cache[key] = result
                self._cache.move_to_end(key)
                while len(self._cache) > 128:
                    self._cache.popitem(last=False)
            return result

    def _lock(self, key: tuple[str, str, int, datetime, datetime]) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())


def _http(err: ForecastError) -> HTTPException:
    return HTTPException(status_code=err.status, detail={"message": err.message, "reason": err.reason})


def add_hazard_routes(
    app: FastAPI,
    registry: HazardRegistry,
    places: PlaceIndex,
    forecast: ForecastService | None = None,
    derived: DerivedService | None = None,
) -> DistrictRiskService:
    """Serve hazard products and district risk; the service is returned so other modules share its cache."""
    district_risk = DistrictRiskService(registry, places, forecast, derived)

    @app.get("/api/hazards/products")
    def products() -> dict[str, object]:
        return registry.model_dump()

    @app.get("/api/hazards/district-risk")
    def risks(hazard: str, model: str, time: str, run: str, level: int = 0) -> dict[str, Any]:
        try:
            return district_risk.calculate(hazard, model, level, parse_hour(time), parse_hour(run))
        except ForecastError as err:
            raise _http(err) from err

    return district_risk
