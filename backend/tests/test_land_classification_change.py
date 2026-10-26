"""Net class-area change against the previous observation and the 2017 baseline."""

import re

import pytest

from csa_portal.land_classification import CLASSES, provider_for, thousand_acres
from csa_portal.land_cover_stats import AnnualLandCoverStats
from csa_portal.places import Place

CODES = list(CLASSES)


def year_of(land: float, cloud: float = 0.0, nodata: float = 0.0, **classes: float) -> dict:
    areas = {code: float(classes.get(f"c{code}", 0.0)) for code in CODES}
    classified = sum(areas.values())
    assert abs(classified + cloud + nodata - land) < 1e-6, "the test place must add up"
    return {
        "classes_ha": areas, "classified_ha": classified, "cloud_ha": cloud, "nodata_ha": nodata,
        "measured_ha": classified + cloud, "coverage_pct": round((classified + cloud) / land * 100, 2),
    }


def build(**places_by_year) -> AnnualLandCoverStats:
    places = {
        place_id: {"name": place_id.title(), "level": "national" if place_id == "PK" else "district",
                   "parent_id": None if place_id == "PK" else "PK", "area_ha": 10_000.0,
                   "by_year": {str(year): measured for year, measured in by_year.items()}}
        for place_id, by_year in places_by_year.items()
    }
    return AnnualLandCoverStats({
        "schema_version": 1, "classes": CODES, "years": ["2017", "2018", "2019", "2020"], "places": places,
    })


GROWING = {
    2017: year_of(10_000, c5=3000, c11=6000, c2=900, c7=100),
    2018: year_of(10_000, c5=3200, c11=5800, c2=900, c7=100),
    2019: year_of(10_000, c5=3500, c11=5300, c2=1000, c7=200),
    2020: year_of(10_000, c5=3500, c11=5300, c2=1000, c7=200),
}


def body_for(stats, year, place_id="PK", level="national"):
    return provider_for(stats)(Place(place_id, place_id.title(), level, None, (0, 0, 1, 1)), year)


def rules(body, comparison=None):
    return [(i["comparison"], i["rule"], i.get("class")) for i in body["insights"]
            if comparison is None or i["comparison"] == comparison]


def chart_ids(body):
    return [chart["id"] for chart in body["charts"]]


def test_the_baseline_year_has_nothing_to_compare():
    body = body_for(build(PK=GROWING), 2017)

    assert body["insights"] == []
    assert not any(cid.startswith("land-cover-change") for cid in chart_ids(body))


def test_the_year_after_the_baseline_is_compared_once():
    body = body_for(build(PK=GROWING), 2018)

    assert {i["comparison"] for i in body["insights"]} == {"baseline"}
    assert {(i["from_year"], i["to_year"]) for i in body["insights"]} == {(2017, 2018)}
    assert "land-cover-change-baseline" in chart_ids(body)
    assert "land-cover-change-previous" not in chart_ids(body)


def test_a_later_year_is_compared_with_the_previous_observation_and_the_baseline():
    body = body_for(build(PK=GROWING), 2019)

    assert rules(body, "previous") == [
        ("previous", "largest-gain", "5"),
        ("previous", "largest-decline", "11"),
        ("previous", "material-change", "2"),
        ("previous", "material-change", "7"),
    ]
    assert rules(body, "baseline")[:2] == [("baseline", "largest-gain", "5"), ("baseline", "largest-decline", "11")]
    assert rules(body, "baseline")[-1] == ("baseline", "dominant-kept", "11")
    assert chart_ids(body)[1:3] == ["land-cover-change-previous", "land-cover-change-baseline"]


def test_the_previous_observation_is_the_last_one_measured_not_the_year_before():
    patchy = {2017: GROWING[2017], 2018: GROWING[2018], 2020: GROWING[2019]}
    body = body_for(build(PK=patchy), 2020)

    previous = [i for i in body["insights"] if i["comparison"] == "previous"]
    assert {i["from_year"] for i in previous} == {2018}


def test_the_numbers_are_absolute_and_in_points_with_both_years_stated():
    body = body_for(build(PK=GROWING), 2019)

    gain = next(i for i in body["insights"] if i["comparison"] == "baseline" and i["rule"] == "largest-gain")
    assert gain["text"] == (
        "Land in Pk classified as crops rose by 1.2 thousand acres from 2017 to 2019, "
        "a net class-area change of +5.0 points of classified land."
    )
    assert gain["values"] == [
        {"label": "Crops, net class-area change", "value": round(thousand_acres(500), 1), "unit": "thousand acres"},
        {"label": "Crops, change in share of classified land", "value": 5.0, "unit": "percentage points"},
    ]


def test_every_number_in_an_insight_is_one_of_its_values_or_years():
    body = body_for(build(PK=GROWING), 2019)

    for insight in body["insights"]:
        quoted = {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.?\d*", insight["text"])}
        allowed = {abs(v["value"]) for v in insight["values"]} | {insight["from_year"], insight["to_year"], 0.5}
        assert quoted <= allowed, insight["text"]


def test_a_change_too_small_to_matter_is_not_a_story():
    still = {2017: year_of(10_000, c5=3000, c11=7000), 2018: year_of(10_000, c5=3020, c11=6980)}
    body = body_for(build(PK=still), 2018)

    assert rules(body) == [("baseline", "no-material-change", None), ("baseline", "dominant-kept", "11")]
    change = next(c for c in body["charts"] if c["id"] == "land-cover-change-baseline")
    assert change["title"] == "No class in Pk changed materially from 2017 to 2018"


def test_a_large_class_drifting_slightly_is_not_material_but_built_area_has_a_lower_bar():
    built = {2017: year_of(10_000, c5=3000, c11=6980, c7=20), 2018: year_of(10_000, c5=3000, c11=6960, c7=40)}
    body = body_for(build(PK=built), 2018)

    assert ("baseline", "largest-gain", "7") in rules(body)


def test_ties_are_broken_by_the_products_class_order():
    tied = {2017: year_of(10_000, c1=1000, c2=1000, c11=8000), 2018: year_of(10_000, c1=1500, c2=1500, c11=7000)}
    body = body_for(build(PK=tied), 2018)

    assert rules(body)[0] == ("baseline", "largest-gain", "1")


def test_the_most_widespread_class_changing_is_said():
    flipped = {2017: year_of(10_000, c5=4000, c11=6000), 2018: year_of(10_000, c5=6000, c11=4000)}
    body = body_for(build(PK=flipped), 2018)

    dominant = next(i for i in body["insights"] if i["rule"] == "dominant-changed")
    assert dominant["text"] == "Crops replaced rangeland as the most widespread class in Pk between 2017 and 2018."


def test_a_small_coverage_difference_qualifies_the_comparison():
    cloudy = {2017: GROWING[2017], 2018: year_of(10_000, cloud=200, c5=3000, c11=5800, c2=900, c7=100)}
    body = body_for(build(PK=cloudy), 2018)

    first = body["insights"][0]
    assert first["rule"] == "coverage-differs"
    assert first["text"] == "The share of Pk classified differs by 2.0 points between 2017 and 2018, so these changes are approximate."


def test_a_large_coverage_difference_suppresses_the_comparison():
    gappy = {2017: GROWING[2017], 2018: year_of(10_000, nodata=1000, c5=2700, c11=5400, c2=810, c7=90)}
    body = body_for(build(PK=gappy), 2018)

    assert rules(body) == [("baseline", "not-comparable", None)]
    assert "land-cover-change-baseline" not in chart_ids(body)


def test_the_change_chart_has_a_zero_line_and_shows_both_years():
    body = body_for(build(PK=GROWING), 2019)

    change = next(c for c in body["charts"] if c["id"] == "land-cover-change-baseline")
    assert change["zero_line"] is True and change["colour_by_sign"] is True
    assert change["series"][0]["name"] == "Net class-area change, 2017 to 2019"
    assert change["categories"][0] == "Crops" and change["categories"][-1] == "Rangeland"
    assert change["series"][0]["values"][0] == pytest.approx(round(thousand_acres(500), 1))
    assert change["bar_notes"][0] == "+5.0 pts"
    assert change["title"] == "Land classified as rangeland lost most in Pk, 2017 to 2019"


def test_the_wording_never_claims_conversion_and_the_output_is_deterministic():
    stats = build(PK=GROWING)

    first, again = body_for(stats, 2019), body_for(stats, 2019)

    assert first == again
    text = " ".join(i["text"] for i in first["insights"]).lower()
    assert "convert" not in text and " became " not in text and " into " not in text
    assert "classified as" in text and "net class-area change" in text
