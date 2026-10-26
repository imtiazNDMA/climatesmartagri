"""The published annual land-classification statistics, read and checked.

The file is written by backend/scripts/prepare_land_cover_stats.py. Everything that shows the
figures reads them through here, so a broken or unexpected file is refused in one place.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "land_cover_annual.json"
LEVELS = ("national", "province", "district")
_AREAS = ("classified_ha", "cloud_ha", "nodata_ha", "measured_ha")


class LandCoverStatsError(RuntimeError):
    """The published statistics cannot be read."""


@dataclass(frozen=True)
class PlaceYear:
    """What one place looked like in one year, in hectares."""

    year: int
    land_ha: float
    classes_ha: dict[str, float]
    classified_ha: float
    cloud_ha: float
    nodata_ha: float
    measured_ha: float
    coverage_pct: float

    def share_of_classified(self, code: str) -> float:
        """The class's share of the land the data classified, clouds and no data left out."""
        if self.classified_ha <= 0:
            return 0.0
        return self.classes_ha.get(code, 0.0) / self.classified_ha * 100

    def share_of_land(self, code: str) -> float:
        """The class's share of the place's whole administrative land area."""
        if self.land_ha <= 0:
            return 0.0
        return self.classes_ha.get(code, 0.0) / self.land_ha * 100


@dataclass(frozen=True)
class Place:
    """A place, with what is known about it and what it looked like each year."""

    id: str
    name: str
    level: str
    parent_id: str | None
    area_ha: float
    by_year: Mapping[int, PlaceYear]

    def year(self, year: int | str) -> PlaceYear | None:
        """What this place looked like in that year, if it was measured."""
        try:
            return self.by_year.get(int(year))
        except (TypeError, ValueError):
            return None

    @property
    def years(self) -> list[int]:
        return sorted(self.by_year)


class AnnualLandCoverStats:
    """The published statistics, read once and answered from."""

    def __init__(self, document: Mapping[str, Any]):
        if not isinstance(document, Mapping):
            raise LandCoverStatsError("the statistics are not an object")
        version = document.get("schema_version")
        if version != SCHEMA_VERSION:
            raise LandCoverStatsError(f"unsupported statistics schema version {version!r}")
        self._classes = _strings(document.get("classes"), "classes")
        try:
            self._years = sorted(int(year) for year in _strings(document.get("years"), "years"))
        except ValueError as error:
            raise LandCoverStatsError("the statistics list a year that is not a number") from error
        self._document = document
        self._places = _read_places(document, self._classes, self._years)

    @classmethod
    def load(cls, path: Path | None = None) -> AnnualLandCoverStats:
        source = Path(path or DEFAULT_PATH)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LandCoverStatsError(f"cannot read {source}") from error
        return cls(document)

    @property
    def years(self) -> list[int]:
        return list(self._years)

    @property
    def classes(self) -> list[str]:
        return list(self._classes)

    @property
    def method(self) -> str:
        return str(self._document.get("method", ""))

    @property
    def provenance(self) -> dict[str, Any]:
        return dict(self._document.get("provenance") or {})

    def places(self) -> dict[str, Place]:
        return dict(self._places)

    def place(self, place_id: str) -> Place | None:
        return self._places.get(place_id)

    def year(self, place_id: str, year: int | str) -> PlaceYear | None:
        place = self._places.get(place_id)
        return place.year(year) if place else None

    def children(self, place_id: str) -> list[Place]:
        return [place for place in self._places.values() if place.parent_id == place_id]


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise LandCoverStatsError(f"the statistics list no {name}")
    return [str(item) for item in value]


def _area(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise LandCoverStatsError(f"{where} is not an area")
    return float(value)


def _read_places(document: Mapping[str, Any], classes: list[str], years: list[int]) -> dict[str, Place]:
    places = document.get("places")
    if not isinstance(places, dict) or not places:
        raise LandCoverStatsError("the statistics hold no places")
    read: dict[str, Place] = {}
    for place_id, entry in places.items():
        if not isinstance(entry, dict):
            raise LandCoverStatsError(f"place {place_id} is malformed")
        level = entry.get("level")
        if level not in LEVELS:
            raise LandCoverStatsError(f"place {place_id} has an unknown level {level!r}")
        area = _area(entry.get("area_ha"), f"place {place_id} land area")
        by_year: dict[int, PlaceYear] = {}
        for year, measurement in (entry.get("by_year") or {}).items():
            where = f"place {place_id} year {year}"
            if not isinstance(measurement, dict):
                raise LandCoverStatsError(f"{where} is malformed")
            if not str(year).isdigit() or int(year) not in years:
                raise LandCoverStatsError(f"{where} is not a published year")
            found = measurement.get("classes_ha")
            if not isinstance(found, dict):
                raise LandCoverStatsError(f"{where} has no class areas")
            if set(found) != set(classes):
                raise LandCoverStatsError(f"{where} does not hold exactly the published classes")
            coverage = _area(measurement.get("coverage_pct"), f"{where} coverage")
            if coverage > 100:
                raise LandCoverStatsError(f"{where} coverage is above 100%")
            areas = {name: _area(measurement.get(name), f"{where} {name}") for name in _AREAS}
            by_year[int(year)] = PlaceYear(
                year=int(year),
                land_ha=area,
                classes_ha={code: _area(found[code], f"{where} class {code}") for code in classes},
                coverage_pct=coverage,
                **areas,
            )
        read[place_id] = Place(
            id=place_id,
            name=str(entry.get("name", place_id)),
            level=level,
            parent_id=entry.get("parent_id"),
            area_ha=area,
            by_year=by_year,
        )
    for place in read.values():
        if place.parent_id is not None and place.parent_id not in read:
            raise LandCoverStatsError(f"place {place.id} belongs to an unknown place {place.parent_id}")
    return read
