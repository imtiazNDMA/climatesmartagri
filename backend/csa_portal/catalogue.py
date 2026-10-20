"""The layer catalogue: every section and layer the portal knows about."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

SectionStatus = Literal["ready", "no-data", "coming-soon"]
# A forecast section takes its layers from the forecast layer list, not from this catalogue.
SectionKind = Literal["standard", "forecast", "crop-classification", "hazards"]
LayerStatus = Literal["ready", "no-data"]
LayerKind = Literal["raster", "vector", "geojson", "boundary"]
PlaceLevel = Literal["national", "province", "district"]

# Ids appear in the URL as `id:opacity,id:opacity`, so they must stay URL-safe.
Identifier = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]


class CatalogueError(ValueError):
    """The catalogue file is missing or invalid."""


class YearRange(BaseModel):
    first: int
    last: int
    available: list[int] | None = None

    @model_validator(mode="after")
    def _ordered(self) -> YearRange:
        if self.first > self.last:
            raise ValueError(f"year range {self.first}-{self.last} is reversed")
        if self.available is not None:
            if not self.available:
                raise ValueError("available years cannot be empty")
            if self.available != sorted(set(self.available)):
                raise ValueError("available years must be unique and in ascending order")
            if self.available[0] != self.first or self.available[-1] != self.last:
                raise ValueError("available years must start at first and end at last")
            if any(year < self.first or year > self.last for year in self.available):
                raise ValueError("available years must fall inside the year range")
        return self

    def observations(self) -> list[int]:
        """The years callers may select, including every year for legacy continuous ranges."""
        return self.available or list(range(self.first, self.last + 1))


class LegendItem(BaseModel):
    colour: str
    label: str
    # For a geojson layer: the feature property value this colour stands for.
    value: str | None = None


class ClassLegend(BaseModel):
    type: Literal["classes"]
    items: list[LegendItem] = Field(min_length=1)


class RampLegend(BaseModel):
    type: Literal["ramp"]
    colours: list[str] = Field(min_length=2)
    min: float
    max: float
    unit: str = ""
    # For a ramp with a neutral middle colour: the value that colour stands for, zero for a balance.
    mid: float | None = None
    # What each end of the ramp means, when the numbers alone do not say.
    min_label: str = ""
    max_label: str = ""


Legend = Annotated[ClassLegend | RampLegend, Field(discriminator="type")]


class RasterProduct(BaseModel):
    """Stable source semantics for a categorical raster product, independent of its files."""

    provider: str
    collection: str
    version: str
    resolution_metres: int = Field(gt=0)
    area_unit: str
    nodata_value: str


class Section(BaseModel):
    id: Identifier
    title: str
    icon: str
    order: int
    status: SectionStatus
    kind: SectionKind = "standard"
    summary: str = ""
    place_levels: list[PlaceLevel] = Field(min_length=1)
    years: YearRange | None = None


class Layer(BaseModel):
    id: Identifier
    section_id: str | None = None
    title: str
    kind: LayerKind
    status: LayerStatus
    legend: Legend | None = None
    # For a geojson layer: the feature property the legend colours.
    property: str | None = None
    # For a raster layer served by TiTiler: its converted file's name in the rasters folder.
    source: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+\.tif$")
    # The deepest zoom the data has detail for; the map stretches tiles beyond it.
    max_zoom: int | None = Field(default=None, ge=0, le=24)
    years: YearRange | None = None
    default_opacity: float = Field(default=1.0, ge=0, le=1)
    product: RasterProduct | None = None


class Catalogue(BaseModel):
    sections: list[Section]
    layers: list[Layer]

    @model_validator(mode="after")
    def _consistent(self) -> Catalogue:
        section_ids = [s.id for s in self.sections]
        sections_by_id = {section.id: section for section in self.sections}
        for section_id in section_ids:
            if section_ids.count(section_id) > 1:
                raise ValueError(f"duplicate section id '{section_id}'")
        layer_ids = [layer.id for layer in self.layers]
        for layer in self.layers:
            if layer_ids.count(layer.id) > 1:
                raise ValueError(f"duplicate layer id '{layer.id}'")
            if layer.kind == "boundary":
                continue
            if layer.section_id not in section_ids:
                raise ValueError(
                    f"layer '{layer.id}' names unknown section '{layer.section_id}'"
                )
            if layer.legend is None:
                raise ValueError(f"layer '{layer.id}' has no legend")
            if layer.kind == "geojson" and not layer.property:
                raise ValueError(f"geojson layer '{layer.id}' has no property")
            if layer.source and layer.kind != "raster":
                raise ValueError(f"layer '{layer.id}' has a raster source but is not a raster layer")
            if layer.product and layer.kind != "raster":
                raise ValueError(f"layer '{layer.id}' has raster product metadata but is not a raster layer")
            if layer.product and (not layer.years or not isinstance(layer.legend, ClassLegend)):
                raise ValueError(f"raster product layer '{layer.id}' needs years and a class legend")
            if layer.product and any(item.value is None for item in layer.legend.items):
                raise ValueError(f"raster product layer '{layer.id}' has a class without a value")
            if layer.product:
                values = [item.value for item in layer.legend.items]
                if len(values) != len(set(values)):
                    raise ValueError(f"raster product layer '{layer.id}' has duplicate class values")
            section = sections_by_id[layer.section_id]
            if layer.years and section.years:
                outside = set(layer.years.observations()) - set(section.years.observations())
                if outside:
                    raise ValueError(
                        f"layer '{layer.id}' has years unavailable in section '{section.id}': {sorted(outside)}"
                    )
        return self


def load_catalogue(path: Path) -> Catalogue:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise CatalogueError(f"Catalogue file not found: {path}") from err
    except json.JSONDecodeError as err:
        raise CatalogueError(f"Catalogue file is not valid JSON: {path}: {err}") from err
    try:
        return Catalogue.model_validate(raw)
    except ValidationError as err:
        raise CatalogueError(f"Catalogue file is invalid: {path}: {err}") from err
