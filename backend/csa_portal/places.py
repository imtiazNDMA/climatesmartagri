"""Provinces and districts, read from the boundary GeoJSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COUNTRY_ID = "PK"
COUNTRY_NAME = "Pakistan"
# Used only when no province boundaries are loaded.
FALLBACK_BBOX = (60.87, 23.69, 77.84, 37.10)
LEVEL_FILES = {"province": "provinces.geojson", "district": "districts.geojson"}

Bbox = tuple[float, float, float, float]


class BoundaryError(ValueError):
    """A boundary file exists but cannot be used."""


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    level: str
    parent_id: str | None
    bbox: Bbox

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "parent_id": self.parent_id,
            "bbox": list(self.bbox),
        }


@dataclass
class PlaceIndex:
    places: list[Place]
    boundaries: dict[str, dict[str, Any]]
    loaded: bool
    by_id: dict[str, Place] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {place.id: place for place in self.places}


def _bbox(geometry: dict[str, Any]) -> Bbox:
    xs: list[float] = []
    ys: list[float] = []

    def walk(coords: Any) -> None:
        if coords and isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
        else:
            for item in coords:
                walk(item)

    walk(geometry.get("coordinates", []))
    if not xs:
        raise ValueError("geometry has no coordinates")
    return (min(xs), min(ys), max(xs), max(ys))


def _union(boxes: list[Bbox]) -> Bbox:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _read_level(path: Path, level: str) -> tuple[list[Place], dict[str, Any]]:
    try:
        collection = json.loads(path.read_text(encoding="utf-8"))
        features = collection["features"]
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        raise BoundaryError(f"{path.name} is not a GeoJSON FeatureCollection: {err}") from err
    if not isinstance(features, list):
        raise BoundaryError(f"{path.name}: 'features' is not a list")

    places: list[Place] = []
    kept: list[dict[str, Any]] = []
    for number, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise BoundaryError(f"{path.name}: feature {number} is not an object")
        props = feature.get("properties") or {}
        if not props.get("id") or not props.get("name"):
            raise BoundaryError(f"{path.name}: feature {number} has no 'id' or 'name' property")
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            bbox = _bbox(geometry)
        except (ValueError, TypeError, IndexError) as err:
            raise BoundaryError(f"{path.name}: feature {number} has bad geometry: {err}") from err
        parent_id = COUNTRY_ID if level == "province" else props.get("parent_id")
        places.append(Place(str(props["id"]), str(props["name"]), level, parent_id, bbox))
        kept.append(feature)
    return places, {"type": "FeatureCollection", "features": kept}


def no_places() -> PlaceIndex:
    """The index used when no boundaries can be loaded: the country alone."""
    country = Place(COUNTRY_ID, COUNTRY_NAME, "national", None, FALLBACK_BBOX)
    return PlaceIndex(places=[country], boundaries={}, loaded=False)


def load_places(boundaries_dir: Path) -> PlaceIndex:
    boundaries_dir = Path(boundaries_dir)
    by_level: dict[str, list[Place]] = {}
    boundaries: dict[str, dict[str, Any]] = {}
    for level, filename in LEVEL_FILES.items():
        path = boundaries_dir / filename
        if path.is_file():
            by_level[level], boundaries[level] = _read_level(path, level)

    provinces = sorted(by_level.get("province", []), key=lambda p: p.name)
    districts = sorted(by_level.get("district", []), key=lambda p: p.name)

    seen: set[str] = {COUNTRY_ID}
    for place in [*provinces, *districts]:
        if place.id in seen:
            raise BoundaryError(f"duplicate place id '{place.id}'")
        seen.add(place.id)

    if "province" in by_level:
        province_ids = {p.id for p in provinces}
        for district in districts:
            if district.parent_id not in province_ids:
                raise BoundaryError(
                    f"district '{district.id}' names unknown province '{district.parent_id}'"
                )

    country_bbox = _union([p.bbox for p in provinces]) if provinces else FALLBACK_BBOX
    country = Place(COUNTRY_ID, COUNTRY_NAME, "national", None, country_bbox)
    return PlaceIndex(
        places=[country, *provinces, *districts],
        boundaries=boundaries,
        loaded=len(boundaries) == len(LEVEL_FILES),
    )
