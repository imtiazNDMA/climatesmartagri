"""Figures, charts and map layers for each section, built from the prepared files in backend/data.

Every chart carries a headline that states its finding in a plain sentence, worked out from the
data, and nothing else above the plot.
"""

from __future__ import annotations

import json
import logging
import math
import re
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


def _num(value: float) -> str:
    """A number as people write it: thousands grouped, at most one decimal, no trailing zero."""
    return f"{value:,.1f}".rstrip("0").rstrip(".")


def _pct(value: float) -> str:
    """A percentage for a headline: whole numbers, except below 1 where one decimal is kept."""
    return f"{value:.1f}" if abs(value) < 1 else f"{value:.0f}"


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _figure(
    label: str, value: Any, unit: str = "", share: float | None = None, share_of: str = ""
) -> dict[str, Any]:
    """A figure for the panel. `share` is the part of a whole it makes up, in percent, and `share_of`
    names that whole in a few words ("of equipped land"); both are left out when there is none."""
    figure = {"label": label, "value": value, "unit": unit}
    if share is not None:
        figure |= {"share": share, "share_of": share_of}
    return figure


def _series(name: str, slot: int, values: list[Any], **extra: Any) -> dict[str, Any]:
    return {"name": name, "slot": slot, "values": values, **extra}


def _over_time(chart_id: str, title: str, kind: str, unit: str, years: list[int], series: list[dict], **extra: Any):
    return {
        "id": chart_id, "title": title, "kind": kind, "unit": unit, "time": True,
        "categories": years, "series": series, "end_labels": True, **extra,
    }


def _bars(chart_id: str, title: str, unit: str, categories: list[str], values: list[Any], **extra: Any):
    return {
        "id": chart_id, "title": title, "kind": "bar", "unit": unit, "time": False,
        "categories": categories, "series": [_series(extra.pop("series_name", "Value"), 1, values)], **extra,
    }


def _emissions(data: dict[str, Any]) -> SectionDataProvider:
    years, unit = data["years"], data["unit"]
    gases = [("Carbon dioxide", "co2", 1), ("Methane", "ch4", 2), ("Nitrous oxide", "n2o", 3)]
    first, last = years[0], years[-1]
    growth = [round(data[key][-1] / data[key][0], 1) for _, key, _ in gases]
    fastest = max(range(len(gases)), key=lambda n: data[gases[n][1]][-1] / data[gases[n][1]][0])

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        i = _index(years, year)
        total = data["total"][i]
        shares = [round(data[key][i] / total * 100, 1) for _, key, _ in gases]
        top = max(range(len(gases)), key=lambda n: data[gases[n][1]][i])
        return {
            "figures": [
                _figure("Total emissions", total, unit),
                _figure("Carbon dioxide (CO2)", data["co2"][i], unit),
                _figure("Methane (CH4)", data["ch4"][i], unit),
                _figure("Nitrous oxide (N2O)", data["n2o"][i], unit),
            ],
            "notes": [],
            "charts": [
                _over_time(
                    "emissions-by-gas",
                    f"Pakistan's annual emissions more than tripled since {first}",
                    "stacked-area", unit, years,
                    [_series(name, slot, data[key]) for name, key, slot in gases],
                ),
                _bars(
                    "emissions-growth",
                    f"{gases[fastest][0]} grew fastest: {_num(growth[fastest])} times its {first} level",
                    "times", [name for name, _, _ in gases], growth,
                    horizontal=True, bar_slots=[slot for _, _, slot in gases], series_name=f"Growth {first} to {last}",
                ),
                _bars(
                    "emissions-share",
                    f"In {years[i]}, {gases[top][0].lower()} made up {_pct(shares[top])}% of emissions",
                    "%", [name for name, _, _ in gases], shares,
                    horizontal=True, bar_slots=[slot for _, _, slot in gases], series_name="Share of total",
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
    # More efficiency leaves more water in every year: the plain finding, when the figures bear it out.
    ordered = all(
        balance[low][n] < balance[high][n]
        for (low, _), (high, _) in zip(levels, levels[1:]) for n in range(len(years))
    )
    buffer_chart = {
        "id": "water-buffer", "kind": "balance", "unit": "", "time": True, "categories": years,
        "title": "Higher efficiency protects the water buffer" if ordered else need_title,
        "series": [_series(f"{level}% efficiency", slot, balance[level]) for level, slot in levels],
        "balance": {
            "available": availability, "needed": [data["requirement"][level] for level, _ in levels],
            "negative": "Water deficit", "positive": "Water buffer", "zero": "Water limit",
            "negative_word": "deficit", "positive_word": "buffer",
            "caption": "Water balance = available water − crop water requirement",
        },
    }
    first, last = years[0], years[-1]

    # In the source, need times efficiency is the same at every level it lists: what a crop must receive
    # does not change, only how much must be supplied to deliver it. The two charts below work the
    # balance out at any efficiency by that rule, which is only as good as the levels agreeing.
    base_level = levels[0][0]
    base_need = data["requirement"][base_level]
    proportional = all(
        abs(need * int(level) - base * int(base_level)) <= 1e-6 * base * int(base_level)
        for level, _ in levels for need, base in zip(data["requirement"][level], base_need)
    )
    # The efficiency at which the water crops need would exactly equal the water available.
    breakeven = [round(need * int(base_level) / available, 1) for need, available in zip(base_need, availability)]
    given = [int(level) for level, _ in levels]
    choice = {"min": min(given), "max": max(given), "base": int(base_level), "start": 45, "given": given}
    note = "Efficiencies other than " + ", ".join(f"{g}%" for g in given[:-1]) + f" and {given[-1]}% are calculated from the source's figures, not given in it."
    series = [_series("Water available", 1, availability), _series(f"Water crops need at {base_level}% efficiency", 2, base_need)]
    enough = max(breakeven)
    explorer_chart = _over_time(
        "water-explorer",
        f"Water stays enough to {last} only if irrigation efficiency reaches {_pct(enough)}%",
        "explorer", "", years, series, efficiency=choice, note=note,
    )
    direction = "climbs from" if breakeven[-1] > breakeven[0] else "falls from" if breakeven[-1] < breakeven[0] else "stays at"
    grid_chart = _over_time(
        "water-grid",
        f"The efficiency that breaks even {direction} {_pct(breakeven[0])}% in {first} to {_pct(breakeven[-1])}% in {last}"
        if breakeven[-1] != breakeven[0] else f"The efficiency that breaks even stays at {_pct(breakeven[0])}%",
        "grid", "", years, series, efficiency=choice, note=note,
    )
    extra_charts = [explorer_chart, grid_chart] if proportional else []

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
            "notes": [],
            "charts": [buffer_chart, *extra_charts],
        }

    return provider


def _food_security(data: dict[str, Any]) -> SectionDataProvider:
    years = data["years"]
    last = years[-1]

    gain = data["csa_availability"][-1] - data["traditional_availability"][-1]
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
            "notes": [],
            "charts": [
                # One chart for need, the two supplies and the two spaces between them: the gap that
                # remains with climate smart agriculture, and what it adds over traditional farming.
                _over_time(
                    "food-outlook",
                    f"By {last} {csa} adds {_num(gain)} over {traditional}, "
                    f"yet {_num(data['csa_gap'][-1])} of the food needed is unmet",
                    "outlook", "", years,
                    [
                        _series("Food needed", 1, data["demand"]),
                        _series("With climate smart agriculture", 3, data["csa_availability"]),
                        _series("With traditional farming", 2, data["traditional_availability"]),
                        _series("Population", 4, data["population"]),
                    ],
                ),
                _over_time(
                    "food-population",
                    f"Population grows from {data['population'][0]:.0f} to {data['population'][-1]:.0f} million by {last}",
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


def _irrigation(data: dict[str, Any], practice: dict[str, Any] | None = None) -> SectionDataProvider:
    places = data["places"]
    # Each tehsil that has a recommendation: its id and the practices recommended for it.
    tehsils = [
        (str(f["properties"].get("id", "")), [c.strip() for c in str(f["properties"]["practice"]).split(",")])
        for f in (practice or {}).get("features", []) if f["properties"].get("practice")
    ]

    unit = "million acres"

    def area(hectares: Any) -> Any:
        return None if hectares is None else _million_acres(hectares)

    def group(place_id: str, entry: dict[str, Any]) -> tuple[str, str, list[tuple[str, dict[str, Any]]]]:
        """The places a chart compares: the provinces for the country, otherwise the districts of the
        province in question, largest first. With them, that whole's name and what its parts are called."""
        if entry["level"] == "national":
            scope, level = COUNTRY_ID, "province"
        else:
            scope, level = (place_id if entry["level"] == "province" else entry["parent_id"]), "district"
        rows = [
            (pid, p) for pid, p in places.items()
            if p["level"] == level and p["parent_id"] == scope and p["equipped"]
        ]
        rows.sort(key=lambda row: row[1]["equipped"], reverse=True)
        return places.get(scope, {}).get("name", "its province"), level, rows

    def shown_rows(rows: list, place_id: str) -> tuple[list, int | None]:
        """The largest rows that fit, always with the selected place among them, and where it sits."""
        selected = next((n for n, row in enumerate(rows) if row[0] == place_id), None)
        shown = rows[:RANKING_LIMIT]
        if selected is not None and selected >= RANKING_LIMIT:
            shown[-1] = rows[selected]
            selected = RANKING_LIMIT - 1
        return shown, selected

    def water_source(place_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
        """Each place's equipped land by where its water comes from: groundwater one way, surface the other."""
        whole, level, rows = group(place_id, entry)
        rows = [(pid, p) for pid, p in rows if p["groundwater"] is not None and p["surface"] is not None]
        if not rows:
            return None
        shown, selected = shown_rows(rows, place_id)
        ground = [_share(p["groundwater"], p["equipped"]) or 0 for _, p in shown]
        surface = [_share(p["surface"], p["equipped"]) or 0 for _, p in shown]
        if selected is not None:
            source, share = ("surface water", surface[selected]) if surface[selected] >= ground[selected] else ("groundwater", ground[selected])
            title = f"{entry['name']} takes {_pct(share)}% of its irrigation water from {source}"
            leads = [selected]
        else:
            # With no place chosen the chart singles none out: which provinces matter is the reader's to
            # judge, and any rule for picking some (the largest shares, or those among places above a
            # size) puts a claim in the headline that the figures do not make.
            title = f"Where each {level}'s irrigation water comes from"
            if level == "district":
                title += f" in {whole}"
            leads = []
        return {
            "id": "irrigation-source", "title": title, "kind": "diverging", "unit": "%", "time": False,
            "categories": [], "series": [],
            # The two sides wear the colours of the two ends of the irrigation balance map.
            "sides": [
                {"label": "Groundwater", "colour": BALANCE_ENDS[0]},
                {"label": "Surface water", "colour": BALANCE_ENDS[1]},
            ],
            "splits": [
                {
                    "name": p["name"], "left": ground[n], "right": surface[n],
                    "weight": area(p["equipped"]), "highlight": n in leads,
                }
                for n, (_, p) in enumerate(shown)
            ],
        }

    def tehsils_of(place_id: str) -> list[list[str]]:
        """The recommendations of the tehsils inside a province or district. A tehsil's id opens with the
        names of its province and district, as theirs do after the first two letters."""
        stem = TEHSIL_STEMS.get(place_id, place_id[2:])
        return [codes for tehsil_id, codes in tehsils if tehsil_id.startswith(f"t-{stem}-")]

    def practice_counts(place_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
        """In how many tehsils each practice is recommended. A tehsil can be recommended several."""
        if entry["level"] == "national":
            where, rows = None, [codes for _, codes in tehsils]
        else:
            where, rows = entry["name"], tehsils_of(place_id)
            if not rows and entry["level"] == "district":
                # The tehsil map names some districts differently; their province is the nearest match.
                where, rows = places.get(entry["parent_id"], {}).get("name"), tehsils_of(entry["parent_id"])
        if not rows:
            return None
        counts = sorted(
            ((code, sum(1 for codes in rows if code in codes)) for code in PRACTICE_GUIDE),
            key=lambda item: item[1], reverse=True,
        )
        (top, most), (low, least) = counts[0], next((c for c in reversed(counts) if c[1] > 0), counts[0])
        noun = "tehsil" if len(rows) == 1 else "tehsils"
        title = f"{PRACTICE_GUIDE[top][1]} is recommended in {most} of {len(rows)} {noun}"
        if where:
            title += f" in {where}"
        elif 0 < least < most:
            title += f"; {PRACTICE_GUIDE[low][1].lower()} in only {least}"
        return {
            "id": "irrigation-practices", "title": title, "kind": "counts", "unit": noun, "time": False,
            "categories": [], "series": [], "total": len(rows),
            "items": [
                {"icon": PRACTICE_GUIDE[code][0], "name": PRACTICE_GUIDE[code][1], "value": count, "highlight": code == top}
                for code, count in counts
            ],
        }

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        entry = places.get(place.id)
        if entry is None:
            return {
                "figures": [], "charts": [],
                "notes": [f"No irrigation figures are reported for {place.name}."],
            }
        name = entry["name"]
        figures = [
            _figure("Land equipped for irrigation", area(entry["equipped"]), unit),
            _figure(
                "Served by groundwater", area(entry["groundwater"]), unit,
                _share(entry["groundwater"], entry["equipped"]), "of equipped land",
            ),
            _figure(
                "Served by surface water", area(entry["surface"]), unit,
                _share(entry["surface"], entry["equipped"]), "of equipped land",
            ),
            _figure("Land actually irrigated", area(entry["irrigated"]), unit),
        ]
        used = _share(entry["irrigated"], entry["equipped"])
        if used is not None:
            figures.append(_figure("Share of equipped land irrigated", used, "%"))

        charts = [water_source(place.id, entry), practice_counts(place.id, entry)]
        charts = [chart for chart in charts if chart is not None]
        return {"figures": figures, "notes": [], "charts": charts}

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
    "bare": ("Others", "#bcaaa4"),
    "irrigated": ("Irrigated cropland", "#2a78d6"),
    "rainfed": ("Rainfed cropland", "#eda100"),
}

HECTARES_TO_ACRES = 2.47105
MILLION = 1_000_000


def _million_acres(hectares: float) -> float:
    return hectares * HECTARES_TO_ACRES / MILLION


NOT_MAPPED = ("Not mapped", "#d9d8d2")
# A place counts towards a headline about its group only if it holds at least this share of the group's total,
# so a very small territory with an extreme share does not become the story.
HEADLINE_FLOOR = 2.0


def _squares(parts: list[tuple[str, str, float]]) -> list[dict[str, Any]]:
    """A hundred squares shared out between the parts by their percentages, largest first.

    What the parts leave uncovered becomes "Not mapped". Parts that overlap and add up to more than the
    whole are scaled back to fit, and keep their true percentage beside the squares.
    """
    total = sum(share for _, _, share in parts)
    scale = 100 / total if total > 100 else 1.0
    cells = [
        {"label": label, "colour": colour, "share": share, "exact": share * scale}
        for label, colour, share in sorted(parts, key=lambda part: part[2], reverse=True)
    ]
    if total < 99.5:
        cells.append({"label": NOT_MAPPED[0], "colour": NOT_MAPPED[1], "share": round(100 - total, 1), "exact": 100 - total})
    for cell in cells:
        cell["squares"] = int(cell["exact"])
    # The squares left over after rounding down go to the parts that lost the most.
    spare = 100 - sum(cell["squares"] for cell in cells)
    for cell in sorted(cells, key=lambda c: c["exact"] - c["squares"], reverse=True)[:spare]:
        cell["squares"] += 1
    return [{k: v for k, v in cell.items() if k != "exact"} for cell in cells]


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _land_cover(data: dict[str, Any]) -> SectionDataProvider:
    places = data["places"]
    classes = [c for c in LAND_COVER if c in data["classes"]]
    missing = [LAND_COVER[c][0] for c in LAND_COVER if c not in data["classes"]]

    def group(place_id: str, entry: dict[str, Any]) -> tuple[str, str, list[tuple[str, dict[str, Any]]]]:
        """The places a chart compares: the provinces for the country, otherwise the districts of the
        province in question. With them, that whole's name and what its parts are called."""
        if entry["level"] == "national":
            scope, level = COUNTRY_ID, "province"
        else:
            scope, level = (place_id if entry["level"] == "province" else entry["parent_id"]), "district"
        rows = [(pid, p) for pid, p in places.items() if p["level"] == level and p["parent_id"] == scope]
        return places.get(scope, {}).get("name", "its province"), level, rows

    def shown_rows(rows: list, place_id: str) -> tuple[list, int | None]:
        """The largest rows that fit, always with the selected place among them, and where it sits."""
        selected = next((n for n, row in enumerate(rows) if row[0] == place_id), None)
        shown = rows[:RANKING_LIMIT]
        if selected is not None and selected >= RANKING_LIMIT:
            shown[-1] = rows[selected]
            selected = RANKING_LIMIT - 1
        return shown, selected

    def cover_squares(entry: dict[str, Any], measured: list[str]) -> dict[str, Any]:
        shares = {c: _share(entry[c], entry["area_ha"]) or 0 for c in measured}
        # The strip and bars show the proportions; the headline carries no percentages.
        return {
            "id": "land-cover-shares", "title": f"How {entry['name']}'s land is classified", "kind": "shares",
            "unit": "%", "time": False,
            "categories": [], "series": [],
            "cells": _squares([(LAND_COVER[c][0], LAND_COVER[c][1], shares[c]) for c in measured]),
        }

    def rain_dependence(place_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
        """Cropland in each place of the group, split into irrigated and rainfed: how much is farmed,
        and how much of it waits on rain."""
        whole, level, rows = group(place_id, entry)
        rows = [
            (pid, p, p["irrigated"] + p["rainfed"]) for pid, p in rows
            if p.get("irrigated") is not None and p.get("rainfed") is not None and p["irrigated"] + p["rainfed"] > 0
        ]
        if not rows:
            return None
        rows.sort(key=lambda row: row[2], reverse=True)
        total = sum(row[2] for row in rows)
        shown, selected = shown_rows(rows, place_id)
        rainfed = [_share(p["rainfed"], crop) or 0 for _, p, crop in shown]
        if selected is not None:
            title = f"{_pct(rainfed[selected])}% of {entry['name']}'s cropland depends on rain"
            highlights = [selected]
        else:
            weighty = [n for n, (_, _, crop) in enumerate(shown) if crop / total * 100 >= HEADLINE_FLOOR]
            ranked = sorted(weighty or range(len(shown)), key=lambda n: rainfed[n], reverse=True)
            mostly = [n for n in ranked if rainfed[n] > 50][:2]
            if len(mostly) == 2:
                title = f"{_and([shown[n][1]['name'] for n in mostly])} farm mostly on rain"
                highlights = mostly
            else:
                lead = ranked[0]
                verb = "farms mostly on rain" if rainfed[lead] > 50 else "depends most on rain"
                title = f"{shown[lead][1]['name']} {verb}: {_pct(rainfed[lead])}% of its cropland is rainfed"
                highlights = [lead]
        return {
            "id": "land-cover-cropland", "title": title, "kind": "bar", "unit": "million acres", "time": False,
            "categories": [p["name"] for _, p, _ in shown],
            "series": [
                _series("Irrigated cropland", 1, [_million_acres(p["irrigated"]) for _, p, _ in shown],
                        colour=LAND_COVER["irrigated"][1]),
                _series("Rainfed cropland", 4, [_million_acres(p["rainfed"]) for _, p, _ in shown],
                        colour=LAND_COVER["rainfed"][1]),
            ],
            "horizontal": True, "stacked": True, "highlights": highlights, "hide_axis": True, "still": True,
            "bar_notes": [f"{_pct(share)}% rainfed" for share in rainfed],
        }

    def forest_holders(place_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
        """Where the group's forest is: forest area in each place, with how forested that place is."""
        if "forest" not in classes:
            return None
        whole, level, rows = group(place_id, entry)
        rows = [(pid, p) for pid, p in rows if p.get("forest") is not None]
        total = sum(p["forest"] for _, p in rows)
        if not rows or total <= 0:
            return None
        rows.sort(key=lambda row: row[1]["forest"], reverse=True)
        shown, selected = shown_rows(rows, place_id)
        held = [p["forest"] / total * 100 for _, p in shown]
        if selected is not None:
            rank = next(n for n, (pid, _) in enumerate(rows) if pid == place_id) + 1
            title = (
                f"{entry['name']} holds {_pct(held[selected])}% of {whole}'s forest, "
                f"{_ordinal(rank)} of {len(rows)} districts"
            )
            highlights = [selected]
        elif len(shown) >= 3:
            title = f"{_and([p['name'] for _, p in shown[:2]])} hold {_pct(held[0] + held[1])}% of {whole}'s forest"
            highlights = [0, 1]
        else:
            title = f"{shown[0][1]['name']} holds {_pct(held[0])}% of {whole}'s forest"
            highlights = [0]
        chart = _bars(
            "land-cover-forest-ranking", title,
            "million acres", [p["name"] for _, p in shown], [_million_acres(p["forest"]) for _, p in shown],
            horizontal=True, series_name="Forest", bar_colours=[LAND_COVER["forest"][1]] * len(shown),
            highlights=highlights, hide_axis=True, still=True,
            bar_notes=[f"{_pct(_share(p['forest'], p['area_ha']) or 0)}% of its land" for _, p in shown],
        )
        # The place that is a large part of the land and a small part of the forest, when there is one.
        land = sum(p["area_ha"] for _, p in rows)
        bare = [(p, p["area_ha"] / land * 100, p["forest"] / total * 100) for _, p in rows]
        bare = [row for row in bare if row[1] >= 20 and row[2] < 5]
        if bare:
            p, of_land, of_forest = max(bare, key=lambda row: row[1])
            chart["note"] = (
                f"{p['name']} is {_pct(of_land)}% of {whole}'s land and holds {_pct(of_forest)}% of its forest."
            )
        return chart

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        entry = places.get(place.id)
        if entry is None:
            return {
                "figures": [], "charts": [],
                "notes": [f"No land-cover figures are available for {place.name}."],
            }
        name = entry["name"]
        measured = [c for c in classes if entry.get(c) is not None]
        figures = [_figure("Land area", _million_acres(entry["area_ha"]), "million acres")]
        figures += [
            _figure(
                LAND_COVER[c][0], _million_acres(entry[c]), "million acres",
                _share(entry[c], entry["area_ha"]), "of all land",
            )
            for c in measured
        ]
        if not measured:
            return {
                "figures": figures, "charts": [],
                "notes": [f"The land-cover maps do not reach {name}."],
            }

        notes: list[str] = []
        if missing:
            notes.append(f"Not measured yet: {', '.join(missing)}.")

        charts = [cover_squares(entry, measured)]
        if "irrigated" in classes and "rainfed" in classes:
            charts.append(rain_dependence(place.id, entry))
        charts.append(forest_holders(place.id, entry))
        return {"figures": figures, "notes": notes, "charts": [chart for chart in charts if chart is not None]}

    return provider


# Each irrigation practice a tehsil can be recommended: a picture for it, its name, what it is,
# where it suits, and how it helps. Words to pick out in colour are wrapped in markers:
# {+a benefit+}, {!a drawback!} and {~a condition the method depends on~}.
PRACTICE_GUIDE = {
    "Drip": (
        "drip", "Drip irrigation",
        "Feeds water drop by drop at the roots of each plant.",
        "Orchards, vegetables and row crops where {~water is scarce~}.",
        "{+Very little is lost+} to evaporation or runoff, and {+weeds get less water+}.",
    ),
    "SP": (
        "sprinkler", "Sprinkler irrigation",
        "Sprays water over the crop like rain.",
        "{~Sandy or uneven land~} where flooding wastes water.",
        "It {+spreads water evenly+} without levelling the field and {+uses less than flooding+}.",
    ),
    "AWD": (
        "paddy", "Alternate wetting and drying",
        "The field is left to dry between floodings instead of staying under water.",
        "{~Rice~}.",
        "It {+saves water and pumping cost+} without lowering the yield, and paddies release {+less methane+}.",
    ),
    "FI": (
        "flood", "Flood irrigation",
        "Covers a level field with canal water.",
        "Places with a {~plentiful canal supply~}.",
        "It is {+simple and cheap+} and can wash salts down out of the soil, but it {!uses the most water!}.",
    ),
}

_HIGHLIGHT = re.compile(r"\{([+!~])(.+?)\1\}")
_TONES = {"+": "benefit", "!": "caution", "~": "condition"}


def _highlighted(marked: str) -> dict[str, Any]:
    """A marked sentence as its plain text, plus that text cut where the highlighted words begin and end."""
    parts: list[dict[str, str]] = []
    at = 0
    for match in _HIGHLIGHT.finditer(marked):
        if match.start() > at:
            parts.append({"text": marked[at:match.start()]})
        parts.append({"text": match.group(2), "tone": _TONES[match.group(1)]})
        at = match.end()
    if at < len(marked):
        parts.append({"text": marked[at:]})
    return {"text": "".join(part["text"] for part in parts), "parts": parts}


def _practice_row(code: str) -> dict[str, Any]:
    icon, name, what, suits, helps = PRACTICE_GUIDE[code]
    return {
        "icon": icon, "name": name,
        "points": [
            _highlighted(what),
            {"label": "Suits", "tone": "condition", **_highlighted(suits)},
            {"label": "Helps by", "tone": "benefit", **_highlighted(helps)},
        ],
    }


def _with_practice_tables(collection: dict[str, Any]) -> dict[str, Any]:
    """The practice layer with, on each tehsil, a table of its recommended practices for the popup."""
    features = []
    for feature in collection["features"]:
        props = dict(feature["properties"])
        codes = [code.strip() for code in str(props.get("practice") or "").split(",") if code.strip()]
        rows = [_practice_row(code) for code in codes if code in PRACTICE_GUIDE]
        if rows:
            props["table"] = {
                "title": f"Recommended for {props.get('name', 'this')} tehsil",
                "columns": ["Irrigation type", "Why it is needed and how it helps"],
                "rows": rows,
            }
        features.append({**feature, "properties": props})
    return {**collection, "features": features}


# How many districts at each end of the irrigation balance the map picks out.
BALANCE_EXTREMES = 5
# The colours of the two ends of the irrigation balance map: more groundwater, more surface water.
BALANCE_ENDS = ("#3b4cc0", "#b40426")
# Places the tehsil map files under a different name from the district map.
TEHSIL_STEMS = {"p-federal-capital": "islamabad"}


def _amount(value: float) -> str:
    """A figure for a label: at most two decimals, or its first two digits when it is too small for that."""
    if value == 0:
        return "0"
    if abs(value) >= 0.1:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{value:.{1 - math.floor(math.log10(abs(value)))}f}".rstrip("0")


def _water_balance_label(balance: float) -> str:
    """Which source waters more land in a district, and by how much, from the balance in million acres."""
    if abs(balance) < 0.5 * HECTARES_TO_ACRES / MILLION:
        return "Surface water and groundwater irrigate the same area"
    more, less = ("Surface water", "groundwater") if balance > 0 else ("Groundwater", "surface water")
    return f"{more} irrigates {_amount(abs(balance))} million acres more than {less}"


def _district_layer(
    boundaries: dict[str, Any], places: dict[str, Any], title: str, value_of: Callable[[dict], Any], unit: str,
    describe: Callable[[float], str] | None = None, extremes: int = 0,
) -> GeoJsonProvider:
    """One shape per district with its value and a label. With `extremes`, that many districts furthest
    above zero are marked "high" and that many furthest below are marked "low", for the map to pick out."""
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
            merged["label"] = describe(value) if describe else f"{title}: {_amount(value)}{unit}"
        features.append({"type": "Feature", "geometry": feature["geometry"], "properties": merged})
    if extremes > 0:
        valued = sorted((f["properties"] for f in features if "value" in f["properties"]), key=lambda p: p["value"])
        for props in [p for p in valued if p["value"] < 0][:extremes]:
            props["extreme"] = "low"
        for props in [p for p in valued if p["value"] > 0][-extremes:]:
            props["extreme"] = "high"
    collection = {"type": "FeatureCollection", "features": features}
    return lambda: collection


def build_providers(
    data_dir: Path, boundaries_dir: Path
) -> tuple[dict[str, SectionDataProvider], dict[str, GeoJsonProvider]]:
    """Providers for every section and layer whose prepared files exist."""
    data_dir, boundaries_dir = Path(data_dir), Path(boundaries_dir)
    sections: dict[str, SectionDataProvider] = {}
    layers: dict[str, GeoJsonProvider] = {}

    practice = _read(data_dir / "irrigation_practice.geojson")
    builders = {
        "emissions": ("emissions.json", _emissions),
        "water-balance": ("water_balance.json", _water_balance),
        "food-security": ("food_security.json", _food_security),
        "irrigation": ("irrigation.json", lambda data: _irrigation(data, practice)),
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
        except (KeyError, TypeError, IndexError, ZeroDivisionError, AttributeError) as err:
            logger.error("%s does not have the expected contents: %r", filename, err)

    if practice is not None:
        try:
            practice = _with_practice_tables(practice)
        except (KeyError, TypeError, AttributeError) as err:
            logger.error("irrigation_practice.geojson does not have the expected contents: %r", err)
        layers["irrigation-practice"] = lambda: practice

    districts = _read(boundaries_dir / "districts.geojson")
    if districts is not None and "irrigation" in loaded:
        places = loaded["irrigation"]["places"]

        def area(hectares: Any) -> Any:
            return None if hectares is None else _million_acres(hectares)

        layers["equipped-area"] = _district_layer(
            districts, places, "Area equipped for irrigation", lambda e: area(e["equipped"]), " million acres"
        )
        layers["irrigated-share"] = _district_layer(
            districts, places, "Share of equipped area irrigated", lambda e: _share(e["irrigated"], e["equipped"]), "%"
        )
        layers["surface-water-area"] = _district_layer(
            districts, places, "Surface water irrigation", lambda e: area(e["surface"]), " million acres"
        )
        layers["groundwater-area"] = _district_layer(
            districts, places, "Groundwater irrigation", lambda e: area(e["groundwater"]), " million acres"
        )
        layers["irrigation-balance"] = _district_layer(
            districts, places, "Irrigation balance",
            lambda e: (
                None if e["surface"] is None or e["groundwater"] is None
                else _million_acres(e["surface"] - e["groundwater"])
            ),
            " million acres", describe=_water_balance_label, extremes=BALANCE_EXTREMES,
        )
        layers["groundwater-share"] = _district_layer(
            districts, places, "Share equipped with groundwater", lambda e: _share(e["groundwater"], e["equipped"]), "%"
        )
    return sections, layers
