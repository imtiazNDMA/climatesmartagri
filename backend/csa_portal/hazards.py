"""Versioned agricultural hazard guidance derived from PMD forecast quantities."""

from pathlib import Path
import json

from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator

from .catalogue import Identifier


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


def add_hazard_routes(app: FastAPI, registry: HazardRegistry) -> None:
    @app.get("/api/hazards/products")
    def products() -> dict[str, object]:
        return registry.model_dump()
