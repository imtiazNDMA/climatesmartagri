"""Facts: what the portal holds for a section, place, year or forecast time, each value with its source."""

from pathlib import Path

import pytest

from csa_portal.catalogue import load_catalogue
from csa_portal.facts import Facts, FactsError
from csa_portal.places import load_places

FIXTURES = Path(__file__).parent / "fixtures"


def irrigation(place, year):
    return {
        "figures": [{"label": "Land equipped for irrigation", "value": 41.33, "unit": "million acres"}],
        "notes": ["Figures are for the latest survey."],
        "charts": [],
    }


def yearly(place, year):
    return {"figures": [{"label": "Food needed", "value": year - 1830, "unit": ""}], "notes": [], "charts": []}


@pytest.fixture
def facts():
    return Facts(
        load_catalogue(FIXTURES / "test_catalogue.json"),
        load_places(FIXTURES / "boundaries"),
        {"alpha-section": yearly, "beta-section": irrigation},
    )


def test_a_section_without_figures_for_a_district_answers_for_the_country(facts):
    answer = facts.section("beta-section", "PK101")

    assert answer.place.name == "Pakistan"
    assert answer.year is None
    assert [(f.label, f.value, f.unit, f.place, f.source) for f in answer.facts] == [
        ("Land equipped for irrigation", 41.33, "million acres", "Pakistan", "Beta section / Pakistan"),
    ]
    assert answer.notes == ["Figures are for the latest survey."]
    assert answer.facts[0].source_id.startswith("fact:")
    assert answer.facts[0].source_id == facts.section("beta-section", "PK").facts[0].source_id


def test_a_section_with_years_answers_for_its_latest_year_unless_asked_for_another(facts):
    latest = facts.section("alpha-section", "PK101")
    assert (latest.place.name, latest.year) == ("District One", 2010)
    assert [(f.value, f.when, f.source) for f in latest.facts] == [(180, "2010", "Alpha section / District One / 2010")]
    assert facts.section("alpha-section", "PK101", 2004).facts[0].value == 174


def test_unknown_or_unanswerable_questions_say_why(facts):
    for args, reason in [
        (("ghost", "PK"), "unknown-section"),
        (("beta-section", "XX9"), "unknown-place"),
        (("alpha-section", "PK", 1999), "year-out-of-range"),
        (("empty-section", "PK"), "no-data"),
    ]:
        with pytest.raises(FactsError) as error:
            facts.section(*args)
        assert error.value.reason == reason, args


def charted(place, year):
    return {"figures": [], "notes": [], "charts": [
        {"title": "Food needs rise", "kind": "line", "unit": "Mt", "time": True, "categories": [2009, 2010],
         "series": [{"name": "Food needed", "values": [178, 180]}]},
        {"title": "Methane grew most", "kind": "bar", "unit": "times", "time": False, "categories": ["Methane"],
         "series": [{"name": "Growth", "values": [2.5]}]},
        {"title": "How the land is classified", "kind": "shares", "unit": "%", "time": False,
         "categories": [], "series": [], "cells": [{"label": "Forest", "share": 6.3, "colour": "#000", "squares": 6}]},
        {"title": "Where water comes from", "kind": "diverging", "unit": "%", "time": False,
         "categories": [], "series": [],
         "sides": [{"label": "Groundwater", "colour": "#000"}, {"label": "Surface water", "colour": "#000"}],
         "splits": [{"name": "Sindh", "left": 4.1, "right": 95.9, "weight": 1, "highlight": False}]},
        {"title": "Sprinkler is recommended most", "kind": "counts", "unit": "", "time": False,
         "categories": [], "series": [], "total": 558, "items": [{"name": "Sprinkler irrigation", "value": 480}]},
        {"title": "Sow wheat earlier", "kind": "calendar", "unit": "", "time": False, "categories": [], "series": [],
         "rows": [{"crop": "Wheat", "traditional": {"text": "Oct–Dec sowing"}, "adjusted": {"text": "Oct–Nov sowing"},
                   "reason": "Terminal heat"}]},
    ]}


def test_every_value_a_chart_draws_is_a_fact_naming_its_chart():
    facts = Facts(
        load_catalogue(FIXTURES / "test_catalogue.json"), load_places(FIXTURES / "boundaries"), {"alpha-section": charted}
    )
    answer = facts.section("alpha-section", "PK", 2010)

    assert [(c.title, c.unit) for c in answer.charts] == [
        ("Food needs rise", "Mt"), ("Methane grew most", "times"), ("How the land is classified", "%"),
        ("Where water comes from", "%"), ("Sprinkler is recommended most", ""), ("Sow wheat earlier", ""),
    ]
    assert {f.chart for f in answer.facts} == {c.title for c in answer.charts}
    assert [(f.label, f.value, f.unit, f.when, f.source) for f in answer.facts] == [
        # A chart over time is not tied to the selected year, so its source does not name it.
        ("Food needed", 178, "Mt", "2009", "Alpha section / Pakistan / Food needs rise"),
        ("Food needed", 180, "Mt", "2010", "Alpha section / Pakistan / Food needs rise"),
        ("Growth, Methane", 2.5, "times", "2010", "Alpha section / Pakistan / 2010 / Methane grew most"),
        ("Forest", 6.3, "%", "2010", "Alpha section / Pakistan / 2010 / How the land is classified"),
        ("Sindh, Groundwater", 4.1, "%", "2010", "Alpha section / Pakistan / 2010 / Where water comes from"),
        ("Sindh, Surface water", 95.9, "%", "2010", "Alpha section / Pakistan / 2010 / Where water comes from"),
        ("Sprinkler irrigation", 480, "of 558", "2010", "Alpha section / Pakistan / 2010 / Sprinkler is recommended most"),
        ("Wheat, traditional", "Oct–Dec sowing", "", "2010", "Alpha section / Pakistan / 2010 / Sow wheat earlier"),
        ("Wheat, adjusted", "Oct–Nov sowing", "", "2010", "Alpha section / Pakistan / 2010 / Sow wheat earlier"),
        ("Wheat, why", "Terminal heat", "", "2010", "Alpha section / Pakistan / 2010 / Sow wheat earlier"),
    ]


def test_a_place_is_found_by_name_however_it_is_typed(facts):
    names = lambda query: [place.name for place in facts.find_place(query)]  # noqa: E731
    assert names("district one") == ["District One"]
    assert names("District-One") == ["District One"]
    assert names("  ALPHA ") == ["Alpha"]
    # A part of a name finds every place it fits, exact matches first.
    assert names("district") == ["District One", "District Three", "District Two"]
    assert names("Atlantis") == []


def test_the_portal_outline_lists_sections_with_what_they_cover_and_their_layers(facts):
    outline = facts.portal()

    alpha = outline.sections[0]
    assert (alpha.id, alpha.title, alpha.status, alpha.years, alpha.place_levels) == (
        "alpha-section", "Alpha section", "ready", (2000, 2010), ["national", "province", "district"],
    )
    later = next(s for s in outline.sections if s.id == "later-section")
    assert (later.status, later.summary, later.years) == ("coming-soon", "Will show things later.", None)
    # Boundaries are how places are drawn, not something to ask about.
    assert [(layer.id, layer.section_id) for layer in outline.layers] == [
        ("fake-yearly", "alpha-section"), ("fake-static", "beta-section"), ("fake-shapes", "beta-section"),
        ("fake-empty", "empty-section"), ("fake-later", "later-section"),
    ]


class FakeRisk:
    """Stands in for the district risk service, which needs forecast files."""

    def __init__(self):
        from csa_portal.hazards import HazardRegistry

        self.registry = HazardRegistry.model_validate({
            "classification": "guidance", "threshold_version": "provisional-test",
            "disclaimer": "Model-derived agricultural guidance. This is not an official warning.",
            "products": [{
                "id": "frost", "title": "Frost risk", "forecast_layer": "frost-degree-hours", "unit": "°C·h",
                "direction": "above", "summary": "Cold below 0 °C.", "district_percentile": 90,
                "bands": [{"severity": "advisory", "label": "Light frost", "threshold": 3, "colour": "#facc15"},
                          {"severity": "severe", "label": "Severe frost", "threshold": 24, "colour": "#dc2626"}],
            }],
        })
        self.asked = []

    def calculate(self, hazard, model, level, valid, run):
        from csa_portal.forecast import ForecastError

        self.asked.append((hazard, model, level, valid, run))
        if hazard != "frost":
            raise ForecastError(404, "not-found", f"Unknown hazard '{hazard}'")
        return {"hazard": "frost", "unit": "°C·h", "time": "2026101506", "run": "2026101500",
                "statistic": {"percentile": 90, "label": "90th percentile of forecast cells intersecting each district"},
                "districts": [{"id": "PK101", "name": "District One", "value": 30.5, "risk": "high"},
                              {"id": "PK102", "name": "District Two", "value": 0.0, "risk": None}]}


def test_district_risk_gives_each_district_its_value_and_band_with_the_guidance_disclaimer():
    from datetime import datetime

    risk = FakeRisk()
    facts = Facts(load_catalogue(FIXTURES / "test_catalogue.json"), load_places(FIXTURES / "boundaries"), {}, risk)
    answer = facts.district_risk("frost", "ECMWF", "2026101506", "2026101500")

    assert risk.asked == [("frost", "ECMWF", 0, datetime(2026, 10, 15, 6), datetime(2026, 10, 15, 0))]
    assert answer.disclaimer == "Model-derived agricultural guidance. This is not an official warning."
    assert (answer.title, answer.threshold_version) == ("Frost risk", "provisional-test")
    assert answer.risk == {"District One": "high", "District Two": None}
    source = "Hazards / Frost risk / ECMWF run 2026101500"
    assert [(f.label, f.value, f.unit, f.place, f.when, f.source) for f in answer.facts] == [
        ("Light frost threshold", 3, "°C·h", "Pakistan", None, source),
        ("Severe frost threshold", 24, "°C·h", "Pakistan", None, source),
        ("Frost risk", 30.5, "°C·h", "District One", "2026101506", source),
        ("Frost risk", 0.0, "°C·h", "District Two", "2026101506", source),
    ]


def test_district_risk_says_why_it_cannot_answer():
    places = load_places(FIXTURES / "boundaries")
    catalogue = load_catalogue(FIXTURES / "test_catalogue.json")
    for facts, args, reason in [
        (Facts(catalogue, places, {}, FakeRisk()), ("hail", "ECMWF", "2026101506", "2026101500"), "unknown-hazard"),
        (Facts(catalogue, places, {}, FakeRisk()), ("frost", "ECMWF", "tomorrow", "2026101500"), "bad-time"),
        (Facts(catalogue, places, {}), ("frost", "ECMWF", "2026101506", "2026101500"), "no-data"),
    ]:
        with pytest.raises(FactsError) as error:
            facts.district_risk(*args)
        assert error.value.reason == reason, args


def test_a_figure_that_is_a_share_of_a_whole_gives_its_share_as_a_fact_too():
    def shared(place, year):
        return {"figures": [{"label": "Served by groundwater", "value": 12.78, "unit": "million acres",
                             "share": 30.9, "share_of": "of equipped land"}], "notes": [], "charts": []}

    facts = Facts(load_catalogue(FIXTURES / "test_catalogue.json"), load_places(FIXTURES / "boundaries"),
                  {"beta-section": shared})
    answer = facts.section("beta-section", "PK")
    assert [(f.label, f.value, f.unit, f.chart) for f in answer.facts] == [
        ("Served by groundwater", 12.78, "million acres", None),
        ("Served by groundwater, share of equipped land", 30.9, "%", None),
    ]


def test_a_value_over_time_keeps_its_source_id_whichever_year_is_selected():
    def trend(place, year):
        return {"figures": [{"label": "Crops", "value": year - 1990, "unit": "million acres"}], "charts": [{
            "id": "trend", "title": "Crops grew", "kind": "line", "unit": "%", "time": True,
            "categories": [2004, 2007, 2010], "series": [{"name": "Crops", "values": [10.0, 11.0, 12.0]}],
        }]}

    facts = Facts(load_catalogue(FIXTURES / "test_catalogue.json"), load_places(FIXTURES / "boundaries"),
                  {"alpha-section": trend})
    def series(year):
        return {(f.label, f.when): f for f in facts.section("alpha-section", "PK", year).facts if f.chart}

    in_2010, in_2004 = series(2010), series(2004)

    assert sorted(in_2010) == [("Crops", "2004"), ("Crops", "2007"), ("Crops", "2010")]
    assert all(in_2010[key].source_id == in_2004[key].source_id for key in in_2010)
    assert in_2010[("Crops", "2007")].source == "Alpha section / Pakistan / Crops grew"
    # A figure is for the selected year, so its source still names it.
    figure = next(f for f in facts.section("alpha-section", "PK", 2004).facts if f.chart is None)
    assert figure.source == "Alpha section / Pakistan / 2004"


def test_a_section_says_where_its_figures_come_from_when_its_provider_does():
    def sourced(place, year):
        return {"figures": [], "provenance": "Survey of 2004, 10 m cells."}

    facts = Facts(load_catalogue(FIXTURES / "test_catalogue.json"), load_places(FIXTURES / "boundaries"),
                  {"alpha-section": sourced, "beta-section": irrigation})

    assert facts.section("alpha-section", "PK", 2004).provenance == "Survey of 2004, 10 m cells."
    assert facts.section("beta-section", "PK").provenance is None
