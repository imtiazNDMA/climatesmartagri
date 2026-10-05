"""Figures, charts and map layers for each section, built from the prepared files in backend/data.

Every chart carries a headline that states its finding in a plain sentence, worked out from the
data, and a subtitle that says what is shown and how to read it.
"""

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
NO_UNIT = "The source spreadsheet gives no unit for these amounts."


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


def _num(value: float) -> str:
    """A number as people write it: thousands grouped, at most one decimal, no trailing zero."""
    return f"{value:,.1f}".rstrip("0").rstrip(".")


def _pct(value: float) -> str:
    """A percentage for a headline: whole numbers, except below 1 where one decimal is kept."""
    return f"{value:.1f}" if abs(value) < 1 else f"{value:.0f}"


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _figure(label: str, value: Any, unit: str = "") -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit}


def _series(name: str, slot: int, values: list[Any], **extra: Any) -> dict[str, Any]:
    return {"name": name, "slot": slot, "values": values, **extra}


def _over_time(chart_id: str, title: str, subtitle: str, kind: str, unit: str, years: list[int], series: list[dict], **extra: Any):
    return {
        "id": chart_id, "title": title, "subtitle": subtitle, "kind": kind, "unit": unit, "time": True,
        "categories": years, "series": series, "end_labels": True, **extra,
    }


def _bars(chart_id: str, title: str, subtitle: str, unit: str, categories: list[str], values: list[Any], **extra: Any):
    return {
        "id": chart_id, "title": title, "subtitle": subtitle, "kind": "bar", "unit": unit, "time": False,
        "categories": categories, "series": [_series(extra.pop("series_name", "Value"), 1, values)], **extra,
    }


def _emissions(data: dict[str, Any]) -> SectionDataProvider:
    years, unit = data["years"], data["unit"]
    gases = [("Carbon dioxide", "co2", 1), ("Methane", "ch4", 2), ("Nitrous oxide", "n2o", 3)]
    first, last = years[0], years[-1]
    growth = [round(data[key][-1] / data[key][0], 1) for _, key, _ in gases]
    fastest = max(range(len(gases)), key=lambda n: data[gases[n][1]][-1] / data[gases[n][1]][0])
    official_years = sum(data["official"])

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        i = _index(years, year)
        total = data["total"][i]
        shares = [round(data[key][i] / total * 100, 1) for _, key, _ in gases]
        top = max(range(len(gases)), key=lambda n: data[gases[n][1]][i])
        status = (
            f"{years[i]} is an official inventory year."
            if data["official"][i]
            else f"{years[i]} is an interpolated estimate, not an official inventory value."
        )
        return {
            "figures": [
                _figure("Total emissions", total, unit),
                _figure("Carbon dioxide (CO2)", data["co2"][i], unit),
                _figure("Methane (CH4)", data["ch4"][i], unit),
                _figure("Nitrous oxide (N2O)", data["n2o"][i], unit),
            ],
            "notes": [
                status,
                f"Source: {data['source']}. All gases are in CO2-equivalent ({unit}, million tonnes).",
            ],
            "charts": [
                _over_time(
                    "emissions-by-gas",
                    f"Pakistan's yearly emissions grew {_num(data['total'][-1] / data['total'][0])} times "
                    f"between {first} and {last}",
                    "Greenhouse gases released each year, in million tonnes of CO2-equivalent. "
                    "CO2-equivalent is a common unit that lets different gases be added together. "
                    "The height of each band is that gas; the top edge is the total.",
                    "stacked-area", unit, years,
                    [_series(name, slot, data[key]) for name, key, slot in gases],
                ),
                _bars(
                    "emissions-growth",
                    f"{gases[fastest][0]} grew fastest: {_num(growth[fastest])} times its {first} level",
                    f"How many times larger each gas was in {last} than in {first}. "
                    "A value of 2 means it doubled.",
                    "times", [name for name, _, _ in gases], growth,
                    horizontal=True, bar_slots=[slot for _, _, slot in gases], series_name=f"Growth {first} to {last}",
                ),
                _bars(
                    "emissions-share",
                    f"In {years[i]}, {gases[top][0].lower()} made up {_pct(shares[top])}% of emissions",
                    f"Each gas as a share of total emissions in {years[i]}. "
                    "Move the year slider to see another year.",
                    "%", [name for name, _, _ in gases], shares,
                    horizontal=True, bar_slots=[slot for _, _, slot in gases], series_name="Share of total",
                ),
                _over_time(
                    "emissions-official",
                    f"Only {official_years} of the {len(years)} years shown are official measurements",
                    "Total emissions per year. Dots are officially reported inventory years. "
                    "The line between dots is an estimate, drawn straight from one official year to the next.",
                    "line", unit, years,
                    [_series("Total emissions", 1, data["total"], points=[n for n, ok in enumerate(data["official"]) if ok])],
                    end_labels=False,
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
    short_years = sum(1 for value in balance["35"] if value < 0)
    if short_years == len(years):
        need_title = f"At 35% efficiency, crops need more water than is available in every year to {years[-1]}"
    else:
        need_title = (
            f"At 35% efficiency, crops need more water than is available in {short_years} of {len(years)} years"
        )
    start, end = balance["50"][0], balance["50"][-1]
    if start > end > 0:
        trend_title = f"The water to spare at 50% efficiency shrinks from {_num(start)} to {_num(end)} by {years[-1]}"
    else:
        trend_title = "Water to spare, or missing, at each efficiency level"

    def describe(level: str, value: float) -> str:
        return f"short by {_num(-value)} at {level}%" if value < 0 else f"{_num(value)} to spare at {level}%"

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        i = _index(years, year)
        now = {level: balance[level][i] for level, _ in levels}
        return {
            "figures": [
                _figure("Water available", availability[i]),
                *[
                    _figure(f"Water crops need at {level}% efficiency", data["requirement"][level][i])
                    for level, _ in levels
                ],
                *[
                    _figure(
                        f"{'Shortfall' if now[level] < 0 else 'Water to spare'} at {level}% efficiency",
                        round(abs(now[level]), 4),
                    )
                    for level, _ in levels
                ],
            ],
            "notes": [
                "Irrigation efficiency is the share of water that actually reaches the crop. "
                "Water to spare is water available minus the water crops need.",
                NO_UNIT,
            ],
            "charts": [
                _over_time(
                    "water-need-vs-supply", need_title,
                    "The dark line is the water available each year. The other lines are the water crops "
                    "need at three levels of irrigation efficiency. Where a line sits above the dark line, "
                    "there is not enough water.",
                    "line", "", years,
                    [
                        _series("Water available", 1, availability, emphasis="strong"),
                        *[
                            _series(f"Needed at {level}% efficiency", slot, data["requirement"][level])
                            for level, slot in levels
                        ],
                    ],
                ),
                _bars(
                    "water-balance-year",
                    f"In {years[i]}: {describe('35', now['35'])} efficiency, {describe('50', now['50'])}",
                    f"Water available minus water needed in {years[i]}, at each efficiency level. "
                    "Bars below zero are a shortfall. Move the year slider to see another year.",
                    "", [f"{level}% efficiency" for level, _ in levels], [now[level] for level, _ in levels],
                    colour_by_sign=True, zero_line=True, series_name="Water to spare",
                ),
                _over_time(
                    "water-balance", trend_title,
                    "Water available minus water needed, year by year. Above the zero line there is "
                    "water to spare; below it there is not enough.",
                    "line", "", years,
                    [_series(f"Balance at {level}% efficiency", slot, balance[level]) for level, slot in levels],
                    zero_line=True,
                ),
            ],
        }

    return provider


def _food_security(data: dict[str, Any]) -> SectionDataProvider:
    years = data["years"]
    last = years[-1]

    def rise(values: list[float]) -> float:
        return (values[-1] - values[0]) / values[0] * 100

    saved = (data["traditional_gap"][-1] - data["csa_gap"][-1]) / data["traditional_gap"][-1] * 100
    csa, traditional = "climate smart agriculture", "traditional farming"

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        i = _index(years, year)
        return {
            "figures": [
                _figure("Food needed", data["demand"][i]),
                _figure(f"Food available with {csa}", data["csa_availability"][i]),
                _figure(f"Food gap with {csa}", data["csa_gap"][i]),
                _figure(f"Food available with {traditional}", data["traditional_availability"][i]),
                _figure(f"Food gap with {traditional}", data["traditional_gap"][i]),
                _figure("Population", data["population"][i], "million"),
            ],
            "notes": [
                "The food gap is the food needed minus the food available.",
                "The source spreadsheet gives no unit for the food amounts.",
            ],
            "charts": [
                _over_time(
                    "food-demand-availability",
                    f"Food needs rise {_pct(rise(data['demand']))}% by {last}, while supply with {csa} "
                    f"rises {_pct(rise(data['csa_availability']))}%",
                    "The dark line is the food the country needs. The other two lines are the food "
                    "available under each way of farming. The space between them is the food gap.",
                    "line", "", years,
                    [
                        _series("Food needed", 1, data["demand"], emphasis="strong"),
                        _series(f"Available with {csa}", 3, data["csa_availability"]),
                        _series(f"Available with {traditional}", 2, data["traditional_availability"]),
                    ],
                ),
                _over_time(
                    "food-gap",
                    f"By {last}, {csa} makes the food gap {_pct(saved)}% smaller than {traditional}",
                    "The food gap is how far the food needed exceeds the food available. Lower is better.",
                    "line", "", years,
                    [
                        _series(f"With {csa}", 3, data["csa_gap"]),
                        _series(f"With {traditional}", 2, data["traditional_gap"]),
                    ],
                ),
                _over_time(
                    "food-population",
                    f"Population grows from {data['population'][0]:.0f} to {data['population'][-1]:.0f} million by {last}",
                    "Projected number of people, in millions. More people is the main reason food needs rise.",
                    "line", "million", years,
                    [_series("Population", 1, data["population"])],
                    end_labels=False,
                ),
            ],
        }

    return provider


def _share(part: Any, whole: Any) -> float | None:
    if part is None or not whole:
        return None
    return round(part / whole * 100, 1)


def _irrigation(data: dict[str, Any]) -> SectionDataProvider:
    places = data["places"]

    def ranking(place_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
        if entry["level"] == "national":
            scope, level, where = COUNTRY_ID, "province", "of any province"
        else:
            scope = place_id if entry["level"] == "province" else entry["parent_id"]
            level, where = "district", f"in {places.get(scope, {}).get('name', 'its province')}"
        rows = [
            (pid, p) for pid, p in places.items()
            if p["level"] == level and p["parent_id"] == scope and p["equipped"] is not None
        ]
        if not rows:
            return None
        rows.sort(key=lambda item: item[1]["equipped"], reverse=True)
        selected = next((n for n, (pid, _) in enumerate(rows) if pid == place_id), None)
        if selected is None:
            title = f"{rows[0][1]['name']} has the most irrigation-ready land {where}"
        else:
            title = (
                f"{entry['name']} ranks {_ordinal(selected + 1)} of {len(rows)} districts "
                f"{where} for irrigation-ready land"
            )
        shown = rows[:RANKING_LIMIT]
        if selected is not None and selected >= RANKING_LIMIT:
            shown[-1] = rows[selected]
            selected = RANKING_LIMIT - 1
        more = f" The {RANKING_LIMIT} largest are shown." if len(rows) > RANKING_LIMIT else ""
        return _bars(
            "irrigation-ranking", title,
            f"Land equipped for irrigation in each {level}, largest first.{more}",
            "ha", [p["name"] for _, p in shown], [p["equipped"] for _, p in shown],
            horizontal=True, highlight=selected, series_name="Land equipped for irrigation",
        )

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        entry = places.get(place.id)
        if entry is None:
            return {
                "figures": [], "charts": [],
                "notes": [f"No irrigation figures are reported for {place.name}."],
            }
        name = entry["name"]
        figures = [
            _figure("Land equipped for irrigation", entry["equipped"], "ha"),
            _figure("Served by groundwater", entry["groundwater"], "ha"),
            _figure("Served by surface water", entry["surface"], "ha"),
            _figure("Land actually irrigated", entry["irrigated"], "ha"),
        ]
        used = _share(entry["irrigated"], entry["equipped"])
        if used is not None:
            figures.append(_figure("Share of equipped land irrigated", used, "%"))
        notes: list[str] = [
            "Land equipped for irrigation has canals, wells or other infrastructure. "
            "Not all of it is irrigated in practice."
        ]
        if entry["level"] != "district":
            notes.append(f"Totals from {entry['districts_reported']} districts reported in the spreadsheet.")
        if entry["level"] == "national" and data.get("unmatched"):
            names = ", ".join(data["unmatched"])
            notes.append(
                f"{len(data['unmatched'])} spreadsheet districts could not be matched to the map and are "
                f"counted in totals only: {names}."
            )

        charts: list[dict[str, Any]] = []
        if used is not None:
            charts.append(_bars(
                "irrigation-use",
                f"{_pct(used)}% of {name}'s irrigation-ready land is actually irrigated",
                "Land that has irrigation infrastructure, next to the land that is irrigated in practice.",
                "ha", ["Equipped for irrigation", "Actually irrigated"], [entry["equipped"], entry["irrigated"]],
                series_name="Land",
            ))
        ground, surface = _share(entry["groundwater"], entry["equipped"]), _share(entry["surface"], entry["equipped"])
        if ground is not None and surface is not None:
            lead, lead_share = ("Surface water", surface) if surface >= ground else ("Groundwater", ground)
            charts.append(_bars(
                "irrigation-source",
                f"{lead} serves {_pct(lead_share)}% of the irrigation-ready land in {name}",
                "Where the water for irrigation-ready land comes from: wells that pump groundwater, "
                "or canals and rivers that carry surface water.",
                "%", ["Groundwater", "Surface water"], [ground, surface],
                series_name="Share of equipped land",
            ))
        ranked = ranking(place.id, entry)
        if ranked is not None:
            charts.append(ranked)
        return {"figures": figures, "notes": notes, "charts": charts}

    return provider


def _crop_calendar(data: dict[str, Any]) -> SectionDataProvider:
    by_province: dict[str, list[dict[str, Any]]] = {}
    for record in data["records"]:
        by_province.setdefault(record["province_id"], []).append(record)

    def chart(province_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        province = records[0]["province"]
        earlier = sum(1 for r in records if r["sown_earlier"])
        title = (
            f"In {province}, {earlier} of {len(records)} crops should be sown earlier than before"
            if earlier
            else f"In {province}, crop calendars keep their traditional sowing dates"
        )
        return {
            "id": f"calendar-{province_id.removeprefix('p-')}", "title": title, "kind": "calendar",
            "subtitle": (
                "Each crop has two lines: its traditional calendar on top and its climate-smart calendar below. "
                "Green is sowing and amber is harvest. A shorter or earlier green bar means sow sooner."
            ),
            "unit": "", "time": False, "categories": [], "series": [],
            "rows": [
                {
                    "crop": r["crop"], "traditional": r["traditional"], "adjusted": r["adjusted"],
                    "changed": r["changed"], "sown_earlier": r["sown_earlier"], "reason": r["reason"],
                }
                for r in records
            ],
        }

    def counts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            _figure("Crops with a calendar", len(records)),
            _figure("Calendars adjusted for climate", sum(1 for r in records if r["changed"])),
            _figure("Crops to sow earlier", sum(1 for r in records if r["sown_earlier"])),
        ]

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        if place.level == "national":
            return {
                "figures": [_figure("Provinces with a calendar", len(by_province)), *counts(data["records"])],
                "notes": [],
                "charts": [chart(province_id, records) for province_id, records in by_province.items()],
            }
        records = by_province.get(place.id)
        if not records:
            return {
                "figures": [], "charts": [],
                "notes": [f"No crop calendar is available for {place.name}."],
            }
        return {"figures": counts(records), "notes": [], "charts": [chart(place.id, records)]}

    return provider


# Land-cover classes: label, and the colour its map layer uses, so charts and map agree.
LAND_COVER = {
    "forest": ("Forest", "#2e7d32"),
    "shrub": ("Shrub land", "#9ccc65"),
    "bare": ("Bare land", "#bcaaa4"),
    "irrigated": ("Irrigated cropland", "#2a78d6"),
    "rainfed": ("Rainfed cropland", "#eda100"),
}


def _land_cover(data: dict[str, Any]) -> SectionDataProvider:
    places = data["places"]
    classes = [c for c in LAND_COVER if c in data["classes"]]
    missing = [LAND_COVER[c][0] for c in LAND_COVER if c not in data["classes"]]

    def forest_ranking(place_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
        if "forest" not in classes:
            return None
        if entry["level"] == "national":
            scope, level, where = COUNTRY_ID, "province", "of any province"
        else:
            scope = place_id if entry["level"] == "province" else entry["parent_id"]
            level, where = "district", f"in {places.get(scope, {}).get('name', 'its province')}"
        rows = [
            (pid, p, _share(p["forest"], p["area_ha"])) for pid, p in places.items()
            if p["level"] == level and p["parent_id"] == scope and p.get("forest") is not None
        ]
        rows = [row for row in rows if row[2] is not None]
        if not rows:
            return None
        rows.sort(key=lambda row: row[2], reverse=True)
        selected = next((n for n, row in enumerate(rows) if row[0] == place_id), None)
        if selected is None:
            title = f"{rows[0][1]['name']} has the largest share of forest {where}"
        else:
            title = f"{entry['name']} ranks {_ordinal(selected + 1)} of {len(rows)} districts {where} for forest cover"
        shown = rows[:RANKING_LIMIT]
        if selected is not None and selected >= RANKING_LIMIT:
            shown[-1] = rows[selected]
            selected = RANKING_LIMIT - 1
        more = f" The {RANKING_LIMIT} highest are shown." if len(rows) > RANKING_LIMIT else ""
        return _bars(
            "land-cover-forest-ranking", title,
            f"Forest as a share of all land in each {level}, highest first.{more}",
            "%", [row[1]["name"] for row in shown], [row[2] for row in shown],
            horizontal=True, highlight=selected, series_name="Forest share of land",
            bar_colours=[LAND_COVER["forest"][1]] * len(shown),
        )

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        entry = places.get(place.id)
        if entry is None:
            return {
                "figures": [], "charts": [],
                "notes": [f"No land-cover figures are available for {place.name}."],
            }
        name = entry["name"]
        measured = [c for c in classes if entry.get(c) is not None]
        figures = [_figure("Land area", entry["area_ha"], "ha")]
        figures += [_figure(LAND_COVER[c][0], entry[c], "ha") for c in measured]
        if not measured:
            return {
                "figures": figures, "charts": [],
                "notes": [f"The land-cover maps do not reach {name}."],
            }

        notes: list[str] = []
        if missing:
            notes.append(f"Not measured yet: {', '.join(missing)}.")

        shares = [_share(entry[c], entry["area_ha"]) for c in measured]
        top = max(range(len(measured)), key=lambda n: shares[n] or 0)
        charts = [_bars(
            "land-cover-shares",
            f"{LAND_COVER[measured[top]][0]} covers {_pct(shares[top] or 0)}% of {name}",
            f"Each kind of land cover as a share of all land in {name}. "
            "The colours match the map layers.",
            "%", [LAND_COVER[c][0] for c in measured], shares,
            horizontal=True, series_name="Share of land", bar_colours=[LAND_COVER[c][1] for c in measured],
        )]
        cropland = (entry.get("irrigated") or 0) + (entry.get("rainfed") or 0)
        if "irrigated" in measured and "rainfed" in measured and cropland > 0:
            split = [_share(entry["irrigated"], cropland), _share(entry["rainfed"], cropland)]
            charts.append(_bars(
                "land-cover-cropland",
                f"{_pct(split[0] or 0)}% of the cropland in {name} is irrigated",
                "Cropland that gets water from canals or wells, next to cropland that depends on rain. "
                "Rainfed land is the more exposed to drought.",
                "%", ["Irrigated", "Rainfed"], split,
                series_name="Share of cropland",
                bar_colours=[LAND_COVER["irrigated"][1], LAND_COVER["rainfed"][1]],
            ))
        ranked = forest_ranking(place.id, entry)
        if ranked is not None:
            charts.append(ranked)
        return {"figures": figures, "notes": notes, "charts": charts}

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
        "land-cover": ("land_cover.json", _land_cover),
        "climate-calendar": ("crop_calendar.json", _crop_calendar),
    }
    loaded: dict[str, Any] = {}
    for section_id, (filename, build) in builders.items():
        data = _read(data_dir / filename)
        if data is None:
            continue
        try:
            sections[section_id] = build(data)
            loaded[section_id] = data
        except (KeyError, TypeError, IndexError, ZeroDivisionError) as err:
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
