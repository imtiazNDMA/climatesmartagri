"""Figures, charts and map layers for each section, built from the prepared files in backend/data."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .places import COUNTRY_ID, Place

logger = logging.getLogger("uvicorn.error")

SectionDataProvider = Callable[[Place, int | None], dict[str, Any]]
GeoJsonProvider = Callable[[], dict[str, Any]]

RANKING_LIMIT = 15


def _read(path: Path) -> Any | None:
    """A prepared file's contents, or None if it is missing or unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as err:
        logger.error("Could not read %s: %s", path, err)
        return None


def _index(years: list[int], year: int | None) -> int:
    return years.index(year) if year in years else len(years) - 1


def _figure(label: str, value: Any, unit: str = "") -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit}


def _series(name: str, slot: int, values: list[Any], **extra: Any) -> dict[str, Any]:
    return {"name": name, "slot": slot, "values": values, **extra}


def _time_chart(chart_id: str, title: str, kind: str, unit: str, years: list[int], series: list[dict], **extra: Any):
    return {
        "id": chart_id, "title": title, "kind": kind, "unit": unit, "time": True,
        "categories": years, "series": series, **extra,
    }


def _emissions(data: dict[str, Any]) -> SectionDataProvider:
    years, unit = data["years"], data["unit"]

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        i = _index(years, year)
        status = (
            f"{years[i]} is an official inventory year."
            if data["official"][i]
            else f"{years[i]} is an interpolated estimate, not an official inventory value."
        )
        return {
            "figures": [
                _figure("Total emissions", data["total"][i], unit),
                _figure("Carbon dioxide (CO2)", data["co2"][i], unit),
                _figure("Methane (CH4)", data["ch4"][i], unit),
                _figure("Nitrous oxide (N2O)", data["n2o"][i], unit),
            ],
            "notes": [
                status,
                f"Source: {data['source']}. All gases are in CO2-equivalent ({unit}, million tonnes).",
            ],
            "charts": [
                _time_chart("emissions-by-gas", "Emissions by gas", "stacked-area", unit, years, [
                    _series("CO2", 1, data["co2"]),
                    _series("CH4", 2, data["ch4"]),
                    _series("N2O", 3, data["n2o"]),
                ]),
                _time_chart(
                    "emissions-total", "Total emissions", "line", unit, years,
                    [_series("Total", 1, data["total"], points=[n for n, ok in enumerate(data["official"]) if ok])],
                    note="Dots mark official inventory years; the line between them is interpolated.",
                ),
            ],
        }

    return provider


def _water_balance(data: dict[str, Any]) -> SectionDataProvider:
    years, availability = data["years"], data["availability"]
    levels = [("35", 2), ("50", 3), ("70", 4)]
    balance = {
        level: [round(a - r, 4) for a, r in zip(availability, data["requirement"][level])] for level, _ in levels
    }

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        i = _index(years, year)
        return {
            "figures": [
                _figure("Water availability", availability[i]),
                *[_figure(f"Requirement at {level}% efficiency", data["requirement"][level][i]) for level, _ in levels],
                *[_figure(f"Balance at {level}% efficiency", balance[level][i]) for level, _ in levels],
            ],
            "notes": [
                "Balance is water availability minus crop water requirement; a negative balance is a shortfall.",
                "The source spreadsheet gives no unit for these values.",
            ],
            "charts": [
                _time_chart(
                    "water-availability-requirement", "Water availability and crop water requirement", "line", "",
                    years,
                    [
                        _series("Water availability", 1, availability),
                        *[_series(f"Requirement at {level}%", slot, data["requirement"][level]) for level, slot in levels],
                    ],
                ),
                _time_chart(
                    "water-balance", "Water balance by irrigation efficiency", "line", "", years,
                    [_series(f"Balance at {level}%", slot, balance[level]) for level, slot in levels],
                    zero_line=True,
                ),
            ],
        }

    return provider


def _food_security(data: dict[str, Any]) -> SectionDataProvider:
    years = data["years"]

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        i = _index(years, year)
        return {
            "figures": [
                _figure("Food demand", data["demand"][i]),
                _figure("Availability with CSA", data["csa_availability"][i]),
                _figure("Food gap with CSA", data["csa_gap"][i]),
                _figure("Availability with traditional practice", data["traditional_availability"][i]),
                _figure("Food gap with traditional practice", data["traditional_gap"][i]),
                _figure("Population", data["population"][i]),
            ],
            "notes": [
                "Food gap is demand minus availability.",
                "The source spreadsheet gives no unit for these values.",
            ],
            "charts": [
                _time_chart("food-demand-availability", "Food demand and availability", "line", "", years, [
                    _series("Food demand", 1, data["demand"]),
                    _series("Availability with CSA", 3, data["csa_availability"]),
                    _series("Availability with traditional practice", 2, data["traditional_availability"]),
                ]),
                _time_chart("food-gap", "Food gap", "line", "", years, [
                    _series("With CSA", 3, data["csa_gap"]),
                    _series("With traditional practice", 2, data["traditional_gap"]),
                ]),
                _time_chart("food-population", "Population", "line", "", years, [
                    _series("Population", 1, data["population"]),
                ]),
            ],
        }

    return provider


def _share(part: Any, whole: Any) -> float | None:
    if part is None or not whole:
        return None
    return round(part / whole * 100, 1)


def _irrigation(data: dict[str, Any]) -> SectionDataProvider:
    places = data["places"]

    def ranking(place_id: str, entry: dict[str, Any]) -> dict[str, Any]:
        if entry["level"] == "national":
            scope, title, level = COUNTRY_ID, "Area equipped for irrigation by province", "province"
        else:
            scope = place_id if entry["level"] == "province" else entry["parent_id"]
            title = f"Area equipped for irrigation by district, {places.get(scope, {}).get('name', '')}"
            level = "district"
        rows = [
            (pid, p) for pid, p in places.items()
            if p["level"] == level and p["parent_id"] == scope and p["equipped"] is not None
        ]
        rows.sort(key=lambda item: item[1]["equipped"], reverse=True)
        selected = next((n for n, (pid, _) in enumerate(rows) if pid == place_id), None)
        shown = rows[:RANKING_LIMIT]
        if selected is not None and selected >= RANKING_LIMIT:
            shown[-1] = rows[selected]
            selected = RANKING_LIMIT - 1
        return {
            "id": "irrigation-ranking", "title": title, "kind": "bar", "unit": "ha", "time": False,
            "horizontal": True, "highlight": selected,
            "categories": [p["name"] for _, p in shown],
            "series": [_series("Area equipped", 1, [p["equipped"] for _, p in shown])],
        }

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        entry = places.get(place.id)
        if entry is None:
            return {
                "figures": [], "charts": [],
                "notes": [f"No irrigation figures are reported for {place.name}."],
            }
        figures = [
            _figure("Area equipped for irrigation", entry["equipped"], "ha"),
            _figure("Equipped with groundwater", entry["groundwater"], "ha"),
            _figure("Equipped with surface water", entry["surface"], "ha"),
            _figure("Area actually irrigated", entry["irrigated"], "ha"),
        ]
        share = _share(entry["irrigated"], entry["equipped"])
        if share is not None:
            figures.append(_figure("Share of equipped area irrigated", share, "%"))
        notes: list[str] = []
        if entry["level"] != "district":
            notes.append(f"Totals from {entry['districts_reported']} districts reported in the spreadsheet.")
        if entry["level"] == "national" and data.get("unmatched"):
            names = ", ".join(data["unmatched"])
            notes.append(
                f"{len(data['unmatched'])} spreadsheet districts could not be matched to the map and are "
                f"counted in totals only: {names}."
            )
        return {
            "figures": figures,
            "notes": notes,
            "charts": [
                {
                    "id": "irrigation-source", "title": "Water source of the equipped area", "kind": "bar",
                    "unit": "ha", "time": False, "categories": ["Groundwater", "Surface water"],
                    "series": [_series("Area equipped", 1, [entry["groundwater"], entry["surface"]])],
                },
                ranking(place.id, entry),
            ],
        }

    return provider


def _district_layer(
    boundaries: dict[str, Any], places: dict[str, Any], title: str, value_of: Callable[[dict], Any], unit: str
) -> GeoJsonProvider:
    features = []
    for feature in boundaries["features"]:
        props = feature["properties"]
        entry = places.get(props["id"])
        value = value_of(entry) if entry else None
        merged = {"id": props["id"], "name": props["name"]}
        if value is None:
            merged["label"] = f"{title}: no figures reported"
        else:
            merged["value"] = value
            merged["label"] = f"{title}: {value:,.0f}{unit}"
        features.append({"type": "Feature", "geometry": feature["geometry"], "properties": merged})
    collection = {"type": "FeatureCollection", "features": features}
    return lambda: collection


def build_providers(
    data_dir: Path, boundaries_dir: Path
) -> tuple[dict[str, SectionDataProvider], dict[str, GeoJsonProvider]]:
    """Providers for every section and layer whose prepared files exist."""
    data_dir, boundaries_dir = Path(data_dir), Path(boundaries_dir)
    sections: dict[str, SectionDataProvider] = {}
    layers: dict[str, GeoJsonProvider] = {}

    builders = {
        "emissions": ("emissions.json", _emissions),
        "water-balance": ("water_balance.json", _water_balance),
        "food-security": ("food_security.json", _food_security),
        "irrigation": ("irrigation.json", _irrigation),
    }
    loaded: dict[str, Any] = {}
    for section_id, (filename, build) in builders.items():
        data = _read(data_dir / filename)
        if data is None:
            continue
        try:
            sections[section_id] = build(data)
            loaded[section_id] = data
        except (KeyError, TypeError, IndexError) as err:
            logger.error("%s does not have the expected contents: %r", filename, err)

    practice = _read(data_dir / "irrigation_practice.geojson")
    if practice is not None:
        layers["irrigation-practice"] = lambda: practice

    districts = _read(boundaries_dir / "districts.geojson")
    if districts is not None and "irrigation" in loaded:
        places = loaded["irrigation"]["places"]
        layers["equipped-area"] = _district_layer(
            districts, places, "Area equipped for irrigation", lambda e: e["equipped"], " ha"
        )
        layers["irrigated-share"] = _district_layer(
            districts, places, "Share of equipped area irrigated", lambda e: _share(e["irrigated"], e["equipped"]), "%"
        )
        layers["groundwater-share"] = _district_layer(
            districts, places, "Share equipped with groundwater", lambda e: _share(e["groundwater"], e["equipped"]), "%"
        )
    return sections, layers
