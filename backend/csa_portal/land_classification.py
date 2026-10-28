"""Figures and charts for the land classification section, from the annual statistics.

Every number comes from backend/data/land_cover_annual.json, read through land_cover_stats. The
classes are the product's own and do not overlap, so a place's shares of its classified land add up
to a hundred. Shares say which land they are of: the land the data classified, or all the land.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .land_cover_stats import AnnualLandCoverStats, Place as StatsPlace, PlaceYear
from .places import COUNTRY_ID, Place

# The product's land classes: label, and the colour its map layer uses, so charts and map agree.
CLASSES = {
    "1": ("Water", "#419bdf"),
    "2": ("Trees", "#397d49"),
    "4": ("Flooded vegetation", "#7a87c6"),
    "5": ("Crops", "#e49635"),
    "7": ("Built area", "#c4281b"),
    "8": ("Bare ground", "#a59b8f"),
    "9": ("Snow/ice", "#a8ebff"),
    "11": ("Rangeland", "#e3e2c3"),
}
# The classes given a figure of their own, besides the most widespread one.
HEADLINE_CLASSES = ("5", "2", "7")
OF_CLASSIFIED = "of classified land"
OF_ALL = "of all land"
HECTARES_TO_ACRES = 2.47105
RANKING_LIMIT = 15
# Below this share of the land left unclassified, a place counts as fully classified.
COMPLETE_PCT = 99.5
# A share smaller than this is not worth a line of its own in the chart over time.
TREND_FLOOR_PCT = 0.5


def million_acres(hectares: float) -> float:
    return hectares * HECTARES_TO_ACRES / 1_000_000


def pct(value: float) -> str:
    """A percentage for a headline: whole numbers, except below 10 where one decimal is kept."""
    return f"{value:.1f}" if abs(value) < 10 else f"{value:.0f}"


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _figure(label: str, hectares: float, share: float | None = None, share_of: str = "") -> dict[str, Any]:
    figure: dict[str, Any] = {"label": label, "value": million_acres(hectares), "unit": "million acres"}
    if share is not None:
        figure |= {"share": round(share, 1), "share_of": share_of}
    return figure


def dominant(year: PlaceYear) -> str:
    """The class covering the most land; on a tie, the one listed first by the product."""
    return max(CLASSES, key=lambda code: (year.classes_ha.get(code, 0.0), -list(CLASSES).index(code)))


def _figures(year: PlaceYear) -> list[dict[str, Any]]:
    top = dominant(year)
    unclassified = year.cloud_ha + year.nodata_ha
    figures = [
        _figure("Land area", year.land_ha),
        _figure("Classified land", year.classified_ha, year.classified_ha / year.land_ha * 100, OF_ALL),
        _figure(
            f"Most widespread: {CLASSES[top][0]}", year.classes_ha[top], year.share_of_classified(top), OF_CLASSIFIED
        ),
    ]
    figures += [
        _figure(CLASSES[code][0], year.classes_ha[code], year.share_of_classified(code), OF_CLASSIFIED)
        for code in HEADLINE_CLASSES
        if code != top
    ]
    if unclassified / year.land_ha * 100 >= 100 - COMPLETE_PCT:
        figures.append(_figure("Not classified", unclassified, unclassified / year.land_ha * 100, OF_ALL))
    return figures


def _notes(name: str, year: PlaceYear) -> list[str]:
    """Only what changes how the figures read: land hidden by cloud, or land the data does not reach."""
    notes = []
    cloud = year.cloud_ha / year.land_ha * 100
    nodata = year.nodata_ha / year.land_ha * 100
    if cloud >= 100 - COMPLETE_PCT:
        notes.append(f"Cloud hid {pct(cloud)}% of {name} in {year.year}; shares are of the land that was classified.")
    if nodata >= 100 - COMPLETE_PCT:
        notes.append(f"The {year.year} classification has no data for {pct(nodata)}% of {name}.")
    return notes


def _composition(name: str, year: PlaceYear) -> dict[str, Any]:
    """The land the data classified, divided between the classes: a hundred squares."""
    shares = sorted(
        ((code, year.share_of_classified(code)) for code in CLASSES), key=lambda item: item[1], reverse=True
    )
    shares = [(code, share) for code, share in shares if share > 0]
    cells = [
        {"label": CLASSES[code][0], "colour": CLASSES[code][1], "share": round(share, 1), "exact": share}
        for code, share in shares
    ]
    for cell in cells:
        cell["squares"] = int(cell["exact"])
    # The squares left over after rounding down go to the classes that lost the most.
    spare = 100 - sum(cell["squares"] for cell in cells)
    for cell in sorted(cells, key=lambda c: c["exact"] - c["squares"], reverse=True)[:max(spare, 0)]:
        cell["squares"] += 1
    top_code, top_share = shares[0]
    return {
        "id": "land-cover-shares",
        "title": f"{CLASSES[top_code][0]} covered {pct(top_share)}% of {name}'s classified land in {year.year}",
        "kind": "shares", "unit": "%", "time": False, "categories": [], "series": [],
        "cells": [{key: value for key, value in cell.items() if key != "exact"} for cell in cells],
    }


def _trend(name: str, place: StatsPlace) -> dict[str, Any] | None:
    """Each class's share of the classified land in every year measured."""
    years = place.years
    if len(years) < 2:
        return None
    measured = [place.by_year[year] for year in years]
    shares = {code: [round(year.share_of_classified(code), 2) for year in measured] for code in CLASSES}
    shown = [code for code in CLASSES if max(shares[code]) >= TREND_FLOOR_PCT]
    moved = max(shown, key=lambda code: (abs(shares[code][-1] - shares[code][0]), -list(CLASSES).index(code)))
    first, last = shares[moved][0], shares[moved][-1]
    if round(first) == round(last):
        title = f"{name}'s classified land kept much the same make-up from {years[0]} to {years[-1]}"
    else:
        title = (
            f"{CLASSES[moved][0]} changed most, from {pct(first)}% to {pct(last)}% of "
            f"{name}'s classified land between {years[0]} and {years[-1]}"
        )
    return {
        "id": "land-cover-trend", "title": title, "kind": "line", "unit": "%", "time": True,
        "categories": years, "end_labels": True,
        "series": [
            {
                "name": CLASSES[code][0], "slot": number + 1, "values": shares[code], "colour": CLASSES[code][1],
                **({"emphasis": "strong"} if code == moved else {}),
            }
            for number, code in enumerate(shown)
        ],
    }


def _group(stats: AnnualLandCoverStats, place: StatsPlace) -> tuple[StatsPlace | None, list[StatsPlace]]:
    """The whole a ranking is about, and its parts: the provinces of the country, or the districts of
    the province in question."""
    scope_id = COUNTRY_ID if place.level == "national" else place.id if place.level == "province" else place.parent_id
    scope = stats.place(scope_id) if scope_id else None
    return scope, stats.children(scope_id) if scope_id else []


def _holders(stats: AnnualLandCoverStats, place: StatsPlace, year: int, code: str) -> dict[str, Any] | None:
    """Where the group's land of one class is, in the selected year, with how much of each place it is."""
    scope, parts = _group(stats, place)
    rows = [(part, part.year(year)) for part in parts]
    rows = [(part, measured) for part, measured in rows if measured is not None]
    total = sum(measured.classes_ha[code] for _, measured in rows)
    if scope is None or len(rows) < 2 or total <= 0:
        return None
    rows.sort(key=lambda row: (-row[1].classes_ha[code], row[0].name))
    selected = next((n for n, (part, _) in enumerate(rows) if part.id == place.id), None)
    shown = rows[:RANKING_LIMIT]
    shown_selected = selected
    if selected is not None and selected >= RANKING_LIMIT:
        shown = shown[:-1] + [rows[selected]]
        shown_selected = RANKING_LIMIT - 1
    held = [measured.classes_ha[code] / total * 100 for _, measured in shown]
    label = CLASSES[code][0].lower()
    kind = "districts" if parts[0].level == "district" else "provinces"
    if shown_selected is not None:
        # "0.0%" reads as a measurement error; a share that rounds to nothing is said in words.
        share = pct(held[shown_selected])
        amount = "almost none" if float(share) == 0 else f"{share}%"
        title = (
            f"{place.name} held {amount} of {scope.name}'s {label} in {year}, "
            f"{_ordinal(selected + 1)} of {len(rows)} {kind}"
        )
        highlights = [shown_selected]
    else:
        title = f"{shown[0][0].name} held {pct(held[0])}% of {scope.name}'s {label} in {year}"
        highlights = [0]
    return {
        "id": f"land-cover-{label.replace(' ', '-')}-ranking", "title": title, "kind": "bar",
        "unit": "million acres", "time": False,
        "categories": [part.name for part, _ in shown],
        "series": [{"name": CLASSES[code][0], "slot": 1, "values": [million_acres(m.classes_ha[code]) for _, m in shown]}],
        "horizontal": True, "bar_colours": [CLASSES[code][1]] * len(shown), "highlights": highlights,
        "hide_axis": True, "still": True,
        "bar_notes": [f"{pct(measured.share_of_land(code))}% of its land" for _, measured in shown],
    }


# A class's net change counts as material only when its share of classified land moves by at least
# this many percentage points; built area is small everywhere, so it has a lower bar of its own.
MATERIAL_PP = 0.5
MATERIAL_PP_BY_CLASS = {"7": 0.1}
# And only when its area moves by at least this share of what it was, so a large class drifting by a
# rounding error is not news.
MATERIAL_RELATIVE = 0.01
# Two years are compared like for like when the share of the place classified differs by less than
# this many points; up to SUPPRESS_GAP_PP they are compared with a warning; beyond it, not at all.
QUALIFY_GAP_PP = 0.5
SUPPRESS_GAP_PP = 5.0


def thousand_acres(hectares: float) -> float:
    return hectares * HECTARES_TO_ACRES / 1_000


def _signed(value: float) -> str:
    return f"{value:+.1f}"


@dataclass(frozen=True)
class ClassChange:
    code: str
    before_ha: float
    after_ha: float
    before_pct: float
    after_pct: float

    @property
    def change_ha(self) -> float:
        return self.after_ha - self.before_ha

    @property
    def change_pp(self) -> float:
        return self.after_pct - self.before_pct

    @property
    def material(self) -> bool:
        if abs(self.change_pp) < MATERIAL_PP_BY_CLASS.get(self.code, MATERIAL_PP):
            return False
        return self.before_ha <= 0 or abs(self.change_ha) / self.before_ha >= MATERIAL_RELATIVE


@dataclass(frozen=True)
class Comparison:
    """Net class-area change between two observations of one place. It says how much land was classified
    as each class in each year, not what any piece of land became."""

    kind: str  # "previous" or "baseline"
    before: PlaceYear
    after: PlaceYear
    changes: tuple[ClassChange, ...]

    @property
    def coverage_gap_pp(self) -> float:
        def classified(year: PlaceYear) -> float:
            return year.classified_ha / year.land_ha * 100

        return abs(classified(self.after) - classified(self.before))

    @property
    def status(self) -> str:
        if self.coverage_gap_pp > SUPPRESS_GAP_PP:
            return "suppressed"
        return "qualified" if self.coverage_gap_pp > QUALIFY_GAP_PP else "like-for-like"

    def change(self, code: str) -> ClassChange:
        return next(change for change in self.changes if change.code == code)


def compare(kind: str, before: PlaceYear, after: PlaceYear) -> Comparison:
    return Comparison(kind, before, after, tuple(
        ClassChange(
            code, before.classes_ha[code], after.classes_ha[code],
            before.share_of_classified(code), after.share_of_classified(code),
        )
        for code in CLASSES
    ))


def comparisons(stats: AnnualLandCoverStats, place: StatsPlace, year: int) -> list[Comparison]:
    """The selected year against the observation before it, and against the first year published.
    When those are the same year, there is one comparison."""
    after = place.year(year)
    if after is None:
        return []
    found = []
    first = stats.years[0]
    earlier = [y for y in place.years if y < year]
    if earlier and earlier[-1] != first:
        found.append(compare("previous", place.by_year[earlier[-1]], after))
    if first < year and place.year(first) is not None:
        found.append(compare("baseline", place.by_year[first], after))
    return found


def _class_sentence(name: str, change: ClassChange, before: int, after: int) -> tuple[str, list[dict[str, Any]]]:
    label = CLASSES[change.code][0]
    area = round(thousand_acres(change.change_ha), 1)
    points = round(change.change_pp, 1)
    verb = "rose" if area > 0 else "fell"
    text = (
        f"Land in {name} classified as {label.lower()} {verb} by {abs(area):,.1f} thousand acres from {before} "
        f"to {after}, a net class-area change of {_signed(points)} points of classified land."
    )
    values = [
        {"label": f"{label}, net class-area change", "value": area, "unit": "thousand acres"},
        {"label": f"{label}, change in share of classified land", "value": points, "unit": "percentage points"},
    ]
    return text, values


def insights(name: str, comparison: Comparison, *, with_dominant: bool) -> list[dict[str, Any]]:
    """What changed, in plain sentences worked out by fixed rules, each with the numbers it quotes."""
    before, after = comparison.before.year, comparison.after.year
    base = {"comparison": comparison.kind, "from_year": before, "to_year": after}
    gap = round(comparison.coverage_gap_pp, 1)
    gap_value = [{"label": "Difference in share of land classified", "value": gap, "unit": "percentage points"}]
    if comparison.status == "suppressed":
        return [{
            **base, "rule": "not-comparable", "values": gap_value,
            "text": f"{before} and {after} are not compared for {name}: the share of its land classified "
                    f"differs by {gap:.1f} points between them.",
        }]
    found: list[dict[str, Any]] = []
    if comparison.status == "qualified":
        found.append({
            **base, "rule": "coverage-differs", "values": gap_value,
            "text": f"The share of {name} classified differs by {gap:.1f} points between {before} and {after}, "
                    "so these changes are approximate.",
        })
    material = [change for change in comparison.changes if change.material]
    order = list(CLASSES)
    gains = sorted((c for c in material if c.change_ha > 0), key=lambda c: (-c.change_ha, order.index(c.code)))
    losses = sorted((c for c in material if c.change_ha < 0), key=lambda c: (c.change_ha, order.index(c.code)))
    told: list[ClassChange] = []
    for rule, picked in (("largest-gain", gains[:1]), ("largest-decline", losses[:1])):
        for change in picked:
            text, values = _class_sentence(name, change, before, after)
            found.append({**base, "rule": rule, "class": change.code, "text": text, "values": values})
            told.append(change)
    for code in HEADLINE_CLASSES:
        change = comparison.change(code)
        if change.material and change not in told:
            text, values = _class_sentence(name, change, before, after)
            found.append({**base, "rule": "material-change", "class": code, "text": text, "values": values})
    if not material:
        found.append({
            **base, "rule": "no-material-change", "values": [],
            "text": f"No class's share of {name}'s classified land moved by {MATERIAL_PP} points or more "
                    f"from {before} to {after}.",
        })
    was, now = dominant(comparison.before), dominant(comparison.after)
    if was != now:
        found.append({
            **base, "rule": "dominant-changed", "class": now, "values": [],
            "text": f"{CLASSES[now][0]} replaced {CLASSES[was][0].lower()} as the most widespread class in {name} "
                    f"between {before} and {after}.",
        })
    elif with_dominant:
        found.append({
            **base, "rule": "dominant-kept", "class": now, "values": [],
            "text": f"{CLASSES[now][0]} was the most widespread class in {name} in both {before} and {after}.",
        })
    return found


def _change_chart(name: str, comparison: Comparison) -> dict[str, Any] | None:
    """Net class-area change of every class present in either year, gains right and losses left."""
    if comparison.status == "suppressed":
        return None
    shown = [c for c in comparison.changes if c.before_ha > 0 or c.after_ha > 0]
    shown.sort(key=lambda c: (-c.change_ha, list(CLASSES).index(c.code)))
    before, after = comparison.before.year, comparison.after.year
    biggest = max(shown, key=lambda c: (abs(c.change_ha), -list(CLASSES).index(c.code)))
    if biggest.material:
        verb = "gained" if biggest.change_ha > 0 else "lost"
        title = f"Land classified as {CLASSES[biggest.code][0].lower()} {verb} most in {name}, {before} to {after}"
    else:
        title = f"No class in {name} changed materially from {before} to {after}"
    return {
        "id": f"land-cover-change-{comparison.kind}", "title": title, "kind": "bar",
        "unit": "thousand acres", "time": False,
        "categories": [CLASSES[c.code][0] for c in shown],
        "series": [{
            "name": f"Net class-area change, {before} to {after}", "slot": 1,
            "values": [round(thousand_acres(c.change_ha), 1) for c in shown],
        }],
        "horizontal": True, "colour_by_sign": True, "zero_line": True, "still": True,
        "bar_notes": [f"{_signed(round(c.change_pp, 1))} pts" for c in shown],
    }


def _provenance(stats: AnnualLandCoverStats) -> str:
    """Which product the figures come from and how they were measured, for whoever quotes them."""
    provenance = stats.provenance
    collection = provenance.get("collection", "io-lulc-annual-v02")
    cell = provenance.get("cell_size_m")
    how = f", measured on its {cell} m overview" if cell else ""
    return (
        f"Impact Observatory's 10 m annual land use and land cover ({collection}, Microsoft Planetary "
        f"Computer){how}. Figures are each year's net class areas; the product does not say which land "
        "moved between classes, or why."
    )


def provider_for(stats: AnnualLandCoverStats):
    """The section's provider: one place in one year, the latest when no year is asked for."""
    provenance = _provenance(stats)

    def provider(place: Place, year: int | None) -> dict[str, Any]:
        return {**answer(place, year), "provenance": provenance}

    def answer(place: Place, year: int | None) -> dict[str, Any]:
        found = stats.place(place.id)
        if found is None or not found.years:
            return {"figures": [], "charts": [], "notes": [f"No land classification is available for {place.name}."]}
        chosen = year if year is not None else stats.years[-1]
        measured = found.year(chosen)
        if measured is None:
            trend = _trend(found.name, found)
            reason = (
                f"The {chosen} land classification does not reach {found.name}."
                if chosen in stats.years
                else f"No land classification is published for {chosen}."
            )
            return {"figures": [], "charts": [trend] if trend else [], "notes": [reason]}
        compared = comparisons(stats, found, chosen)
        charts = [
            _composition(found.name, measured),
            *(_change_chart(found.name, comparison) for comparison in compared),
            _trend(found.name, found),
            _holders(stats, found, chosen, "5"),
            _holders(stats, found, chosen, "2"),
        ]
        said = [
            insight
            for comparison in compared
            for insight in insights(found.name, comparison, with_dominant=comparison is compared[-1])
        ]
        return {
            "figures": _figures(measured),
            "notes": _notes(found.name, measured),
            "insights": said,
            "charts": [chart for chart in charts if chart is not None],
        }

    return provider
