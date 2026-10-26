"""Facts: what the portal holds for a section, place, year or forecast time, each value with its source.

The assistant, chart explanations and advisories read the portal's data through this module, and grounding
checks compare AI answers against the facts it returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from typing import Any, Protocol

from .catalogue import Catalogue
from .forecast import ForecastError, parse_hour
from .hazards import HazardRegistry
from .places import COUNTRY_ID, Place, PlaceIndex
from .sections import SectionDataProvider


class FactsError(Exception):
    """A question the portal cannot answer, with a short reason a caller can act on."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Fact:
    """One value the portal holds, with the place and time it is for and where it came from."""

    label: str
    value: float | int | str | None
    unit: str
    place: str
    when: str | None
    source: str
    # The chart the value is drawn in, or None for a figure.
    chart: str | None = None

    @property
    def source_id(self) -> str:
        """Stable public id for the source behind this fact, without exposing a filesystem path."""
        identity = "\x1f".join((self.source, self.label, str(self.value), self.unit, self.place, self.when or "", self.chart or ""))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        return f"fact:{digest}"


@dataclass(frozen=True)
class ChartSummary:
    title: str
    unit: str
    headline: str | None = None


@dataclass(frozen=True)
class SectionFacts:
    """A section's facts for the place and year it could answer for, which may differ from those asked."""

    place: Place
    year: int | None
    facts: list[Fact]
    notes: list[str] = field(default_factory=list)
    charts: list[ChartSummary] = field(default_factory=list)
    # Sentences about what changed, worked out by fixed rules; every number in them is also a fact.
    insights: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskFacts:
    """One hazard product's district risk at one valid time: the guidance, its bands and each district's value."""

    hazard: str
    title: str
    time: str
    run: str
    threshold_version: str
    disclaimer: str
    statistic: str
    risk: dict[str, str | None]
    facts: list[Fact]


class DistrictRisk(Protocol):
    """Where district risk comes from: the hazards module's service, or a stand-in in tests."""

    registry: HazardRegistry

    def calculate(self, hazard: str, model: str, level: int, valid: datetime, run: datetime) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SectionOutline:
    id: str
    title: str
    status: str
    summary: str
    years: tuple[int, int] | None
    place_levels: list[str]


@dataclass(frozen=True)
class LayerOutline:
    id: str
    title: str
    section_id: str


@dataclass(frozen=True)
class Outline:
    """What the portal has: its sections, in order, and the layers each can draw."""

    sections: list[SectionOutline]
    layers: list[LayerOutline]


class Facts:
    def __init__(
        self,
        catalogue: Catalogue,
        places: PlaceIndex,
        providers: Mapping[str, SectionDataProvider],
        district_risk: DistrictRisk | None = None,
    ) -> None:
        self._catalogue = catalogue
        self._risk = district_risk
        self._sections = {section.id: section for section in catalogue.sections}
        self._places = places
        self._providers = providers

    def portal(self) -> Outline:
        sections = [
            SectionOutline(
                s.id, s.title, s.status, s.summary,
                (s.years.first, s.years.last) if s.years else None, list(s.place_levels),
            )
            for s in sorted(self._catalogue.sections, key=lambda s: s.order)
        ]
        # Boundaries are how places are drawn, not something to ask about.
        layers = [
            LayerOutline(layer.id, layer.title, layer.section_id)
            for layer in self._catalogue.layers
            if layer.kind != "boundary" and layer.section_id
        ]
        return Outline(sections, layers)

    def find_place(self, name: str) -> list[Place]:
        """Places whose name matches, ignoring case, spaces and punctuation; exact matches first."""
        wanted = _plain(name)
        if not wanted:
            return []
        exact = [place for place in self._places.places if _plain(place.name) == wanted]
        partial = [place for place in self._places.places if wanted in _plain(place.name) and place not in exact]
        return exact + partial

    def district_risk(self, hazard: str, model: str, time: str, run: str, level: int = 0) -> RiskFacts:
        """Each district's value and risk band for a hazard product at a valid time (times as YYYYMMDDHH)."""
        if self._risk is None:
            raise FactsError("no-data", "Hazard guidance is not set up on this server")
        return _risk_facts(self._risk, hazard, model, time, run, level)

    def section(self, section_id: str, place_id: str, year: int | None = None) -> SectionFacts:
        section = self._sections.get(section_id)
        if section is None:
            raise FactsError("unknown-section", f"Unknown section '{section_id}'")
        place = self._places.by_id.get(place_id)
        if place is None:
            raise FactsError("unknown-place", f"Unknown place '{place_id}'")
        provider = self._providers.get(section_id)
        if provider is None:
            raise FactsError("no-data", f"{section.title} has no figures yet")
        if section.years is None:
            year = None
        elif year is None:
            year = section.years.last
        elif not section.years.first <= year <= section.years.last:
            raise FactsError(
                "year-out-of-range",
                f"{section.title} covers {section.years.first} to {section.years.last}, not {year}",
            )
        # A section without figures at this level answers for the nearest place above that has them.
        while place.level not in section.place_levels and place.parent_id in self._places.by_id:
            place = self._places.by_id[place.parent_id]
        if place.level not in section.place_levels:
            place = self._places.by_id[COUNTRY_ID]
        data: dict[str, Any] = provider(place, year)
        when = None if year is None else str(year)
        source = " / ".join(part for part in (section.title, place.name, when) if part)
        facts: list[Fact] = []
        for figure in data.get("figures", []):
            facts.append(Fact(figure["label"], figure["value"], figure.get("unit", ""), place.name, when, source))
            if figure.get("share") is not None:
                # "30.9% of equipped land" is a number an answer may quote, so it is a fact of its own.
                share_of = figure.get("share_of", "")
                label = f"{figure['label']}, share {share_of}" if share_of else f"{figure['label']}, share"
                facts.append(Fact(label, figure["share"], "%", place.name, when, source))
        for insight in data.get("insights", []):
            between = f"{insight['from_year']} to {insight['to_year']}"
            for value in insight.get("values", []):
                facts.append(Fact(value["label"], value["value"], value["unit"], place.name, between, source))
        charts = data.get("charts", [])
        for chart in charts:
            facts += _chart_facts(chart, place.name, when, f"{source} / {chart['title']}")
        summaries = [ChartSummary(chart["title"], chart.get("unit", ""), chart.get("headline")) for chart in charts]
        return SectionFacts(
            place, year, facts, list(data.get("notes", [])), summaries,
            [insight["text"] for insight in data.get("insights", [])],
        )


def _risk_facts(risk: DistrictRisk, hazard: str, model: str, time: str, run: str, level: int) -> RiskFacts:
    product = next((p for p in risk.registry.products if p.id == hazard), None)
    if product is None:
        raise FactsError("unknown-hazard", f"Unknown hazard '{hazard}'")
    try:
        result = risk.calculate(hazard, model, level, parse_hour(time), parse_hour(run))
    except ForecastError as err:
        raise FactsError("bad-time" if err.reason == "bad-time" else "no-data", err.message) from err
    source = f"Hazards / {product.title} / {model} run {result['run']}"
    facts = [
        Fact(f"{band.label} threshold", band.threshold, product.unit, "Pakistan", None, source) for band in product.bands
    ]
    facts += [
        Fact(product.title, district["value"], product.unit, district["name"], result["time"], source)
        for district in result["districts"]
    ]
    return RiskFacts(
        product.id, product.title, result["time"], result["run"], risk.registry.threshold_version,
        risk.registry.disclaimer, result["statistic"]["label"],
        {district["name"]: district["risk"] for district in result["districts"]}, facts,
    )


def _plain(name: str) -> str:
    return "".join(ch for ch in name.casefold() if ch.isalnum())


def _chart_facts(chart: dict[str, Any], place: str, when: str | None, source: str) -> list[Fact]:
    """Every value a chart draws, whatever its kind, labelled so it reads on its own."""
    unit = chart.get("unit", "")

    def fact(label: str, value: Any, unit: str = unit, at: str | None = when) -> Fact:
        return Fact(label, value, unit, place, at, source, chart["title"])

    found: list[Fact] = []
    for series in chart.get("series", []):
        if not isinstance(series, dict) or "values" not in series:
            continue  # not a series this module can read; the chart's other values still count
        for category, value in zip(chart.get("categories", []), series["values"]):
            if chart.get("time"):
                found.append(fact(series["name"], value, at=str(category)))
            else:
                found.append(fact(f"{series['name']}, {category}", value))
    for cell in chart.get("cells", []):
        found.append(fact(cell["label"], cell["share"]))
    sides = chart.get("sides", [])
    for split in chart.get("splits", []):
        found += [fact(f"{split['name']}, {sides[0]['label']}", split["left"]),
                  fact(f"{split['name']}, {sides[1]['label']}", split["right"])]
    for item in chart.get("items", []):
        found.append(fact(item["name"], item["value"], f"of {chart['total']}" if chart.get("total") else unit))
    for row in chart.get("rows", []):
        found += [fact(f"{row['crop']}, traditional", row["traditional"]["text"], ""),
                  fact(f"{row['crop']}, adjusted", row["adjusted"]["text"], ""),
                  fact(f"{row['crop']}, why", row["reason"], "")]
    return found
