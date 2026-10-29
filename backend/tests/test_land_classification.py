"""The land classification section: one place in one year, from the annual statistics."""

import pytest

from csa_portal.land_classification import CLASSES, million_acres, provider_for
from csa_portal.land_cover_stats import AnnualLandCoverStats
from csa_portal.places import Place

CODES = list(CLASSES)


def year_of(land: float, cloud: float = 0.0, nodata: float = 0.0, **classes: float) -> dict:
    """A measurement with the named classes ("c5": crops ...) and every other class zero."""
    areas = {code: float(classes.get(f"c{code}", 0.0)) for code in CODES}
    classified = sum(areas.values())
    assert abs(classified + cloud + nodata - land) < 1e-6, "the test place must add up"
    return {
        "classes_ha": areas, "classified_ha": classified, "cloud_ha": cloud, "nodata_ha": nodata,
        "measured_ha": classified + cloud, "coverage_pct": round((classified + cloud) / land * 100, 2),
    }


def place(name: str, level: str, parent: str | None, area: float, by_year: dict) -> dict:
    return {"name": name, "level": level, "parent_id": parent, "area_ha": area, "by_year": by_year}


def build() -> AnnualLandCoverStats:
    places = {
        "PK": place("Pakistan", "national", None, 4000.0, {
            "2017": year_of(4000, c5=1000, c11=2600, c2=400),
            "2018": year_of(4000, c5=1200, c11=2400, c2=400),
            "2019": year_of(4000, c5=1400, c11=2200, c2=400),
        }),
        "p-a": place("Alpha", "province", "PK", 3000.0, {
            "2017": year_of(3000, c5=900, c11=1800, c2=300),
            "2018": year_of(3000, c5=1000, c11=1700, c2=300),
            "2019": year_of(3000, c5=1100, c11=1600, c2=300),
        }),
        "p-b": place("Beta", "province", "PK", 1000.0, {
            "2017": year_of(1000, c5=100, c11=800, c2=100),
            "2018": year_of(1000, c5=200, c11=700, c2=100),
            "2019": year_of(1000, c5=300, c11=600, c2=100),
        }),
        "d-cloudy": place("Cloudy", "district", "p-b", 500.0, {
            "2019": year_of(500, cloud=40, nodata=10, c5=150, c11=300),
        }),
        "d-gone": place("Gone", "district", "p-b", 500.0, {"2017": year_of(500, c5=50, c11=450)}),
    }
    # Twenty districts in Alpha, the last one with the least cropland.
    for n in range(20):
        crops = 100.0 - n * 4
        places[f"d-a{n:02}"] = place(f"Alpha {n:02}", "district", "p-a", 150.0, {
            "2019": year_of(150, c5=crops, c11=150 - crops - 5, c2=5),
        })
    return AnnualLandCoverStats({
        "schema_version": 1, "classes": CODES, "years": ["2017", "2018", "2019"], "method": "counted",
        "provenance": {"collection": "io-lulc-annual-v02", "cell_size_m": 80},
        "places": places,
    })


@pytest.fixture
def provider():
    return provider_for(build())


def at(place_id: str, name: str, level: str) -> Place:
    return Place(place_id, name, level, None, (0.0, 0.0, 1.0, 1.0))


def figures_of(body) -> dict:
    return {figure["label"]: figure for figure in body["figures"]}


def chart(body, chart_id) -> dict:
    return next(c for c in body["charts"] if c["id"] == chart_id)


def test_the_latest_observation_is_shown_when_no_year_is_asked_for(provider):
    latest = provider(at("PK", "Pakistan", "national"), None)
    asked = provider(at("PK", "Pakistan", "national"), 2019)

    assert latest == asked
    assert "2019" in chart(latest, "land-cover-shares")["title"]


def test_the_year_asked_for_is_the_year_shown(provider):
    body = provider(at("PK", "Pakistan", "national"), 2017)

    figures = figures_of(body)
    assert figures["Crops"]["value"] == pytest.approx(million_acres(1000))
    assert chart(body, "land-cover-shares")["title"] == "Rangeland covered 65% of Pakistan's classified land in 2017"


def test_national_figures_carry_the_dominant_class_and_their_denominators(provider):
    figures = figures_of(provider(at("PK", "Pakistan", "national"), 2019))

    assert list(figures) == ["Land area", "Classified land", "Most widespread: Rangeland", "Crops", "Trees", "Built area"]
    assert figures["Land area"]["value"] == pytest.approx(million_acres(4000))
    assert "share" not in figures["Land area"]
    assert figures["Classified land"]["share"] == 100.0
    assert figures["Classified land"]["share_of"] == "of all land"
    assert figures["Most widespread: Rangeland"]["share"] == 55.0
    assert figures["Crops"]["share"] == 35.0
    assert figures["Crops"]["share_of"] == "of classified land"


def test_a_class_with_no_land_is_a_zero_not_a_gap(provider):
    figures = figures_of(provider(at("PK", "Pakistan", "national"), 2019))

    assert figures["Built area"]["value"] == 0.0
    assert figures["Built area"]["share"] == 0.0


def test_cloud_and_no_data_are_told_apart_and_shares_are_of_classified_land(provider):
    body = provider(at("d-cloudy", "Cloudy", "district"), 2019)

    figures = figures_of(body)
    assert figures["Classified land"]["share"] == 90.0
    assert figures["Not classified"]["value"] == pytest.approx(million_acres(50))
    assert figures["Not classified"]["share"] == 10.0
    assert figures["Crops"]["share"] == pytest.approx(33.3)  # 150 of 450 classified, not of 500
    assert body["notes"] == [
        "Cloud hid 8.0% of Cloudy in 2019; shares are of the land that was classified.",
        "The 2019 classification has no data for 2.0% of Cloudy.",
    ]


def test_a_fully_classified_place_has_no_notes_and_no_unclassified_figure(provider):
    body = provider(at("p-a", "Alpha", "province"), 2019)

    assert body["notes"] == []
    assert "Not classified" not in figures_of(body)


def test_a_year_the_data_does_not_reach_is_unavailable_not_zero(provider):
    body = provider(at("d-gone", "Gone", "district"), 2019)

    assert body["figures"] == []
    assert body["notes"] == ["The 2019 land classification does not reach Gone."]


def test_a_year_that_is_not_published_says_so(provider):
    body = provider(at("PK", "Pakistan", "national"), 2016)

    assert body["figures"] == []
    assert body["notes"] == ["No land classification is published for 2016."]


def test_a_place_with_no_statistics_says_so(provider):
    body = provider(at("d-nowhere", "Nowhere", "district"), 2019)

    body.pop("provenance")
    assert body == {"figures": [], "charts": [], "notes": ["No land classification is available for Nowhere."]}


def test_the_composition_is_of_mutually_exclusive_classes_and_fills_exactly_a_hundred_squares(provider):
    shares = chart(provider(at("d-cloudy", "Cloudy", "district"), 2019), "land-cover-shares")

    assert shares["kind"] == "shares"
    assert [cell["label"] for cell in shares["cells"]] == ["Rangeland", "Crops"]
    assert sum(cell["squares"] for cell in shares["cells"]) == 100
    assert sum(cell["share"] for cell in shares["cells"]) == pytest.approx(100.0, abs=0.1)
    assert all(cell["label"] != "Not mapped" for cell in shares["cells"])


def test_the_chart_over_time_holds_every_measured_year(provider):
    trend = chart(provider(at("PK", "Pakistan", "national"), 2018), "land-cover-trend")

    assert trend["time"] is True
    assert trend["categories"] == [2017, 2018, 2019]
    series = {s["name"]: s for s in trend["series"]}
    assert set(series) == {"Trees", "Crops", "Rangeland"}  # classes that never reach 0.5% are left out
    assert series["Crops"]["values"] == [25.0, 30.0, 35.0]
    assert series["Crops"]["colour"] == CLASSES["5"][1]
    assert series["Crops"]["emphasis"] == "strong"  # tied with Rangeland; the product lists crops first
    assert trend["title"] == "Crops changed most, from 25% to 35% of Pakistan's classified land between 2017 and 2019"


def test_a_place_measured_once_has_no_chart_over_time(provider):
    body = provider(at("d-cloudy", "Cloudy", "district"), 2019)

    assert "land-cover-trend" not in [c["id"] for c in body["charts"]]


def test_the_national_ranking_compares_provinces_in_the_selected_year(provider):
    ranking = chart(provider(at("PK", "Pakistan", "national"), 2017), "land-cover-crops-ranking")

    assert ranking["categories"] == ["Alpha", "Beta"]
    assert ranking["series"][0]["values"] == pytest.approx([million_acres(900), million_acres(100)])
    assert ranking["title"] == "Alpha held 90% of Pakistan's crops in 2017"
    assert ranking["bar_labels"] == ["2.22k acres", "247"]
    assert ranking["bar_details"] == ["2.22k acres\n30% of Alpha's land", "247 acres\n10% of Beta's land"]
    assert "bar_notes" not in ranking


def test_a_district_ranking_keeps_the_selected_district_when_capped(provider):
    ranking = chart(provider(at("d-a19", "Alpha 19", "district"), 2019), "land-cover-crops-ranking")

    assert len(ranking["categories"]) == 15
    assert ranking["categories"][0] == "Alpha 00"
    assert ranking["categories"][-1] == "Alpha 19"
    assert ranking["highlights"] == [14]
    assert ranking["title"].startswith("Alpha 19 held 1.9% of Alpha's crops in 2019, 20th of 20 districts")


def test_a_share_that_rounds_to_nothing_is_said_as_almost_none():
    stats = AnnualLandCoverStats({
        "schema_version": 1, "classes": CODES, "years": ["2019"], "method": "counted",
        "places": {
            "PK": place("Pakistan", "national", None, 2000.0, {"2019": year_of(2000, c2=1000.1, c5=999.9)}),
            "p-a": place("Alpha", "province", "PK", 2000.0, {"2019": year_of(2000, c2=1000.1, c5=999.9)}),
            "d-wood": place("Wood", "district", "p-a", 1000.0, {"2019": year_of(1000, c2=1000)}),
            "d-field": place("Field", "district", "p-a", 1000.0, {"2019": year_of(1000, c2=0.1, c5=999.9)}),
        },
    })

    ranking = chart(provider_for(stats)(at("d-field", "Field", "district"), 2019), "land-cover-trees-ranking")

    assert ranking["title"] == "Field held almost none of Alpha's trees in 2019, 2nd of 2 districts"


def test_a_province_ranks_its_own_districts(provider):
    body = provider(at("p-a", "Alpha", "province"), 2019)

    assert chart(body, "land-cover-crops-ranking")["categories"][0] == "Alpha 00"
    assert chart(body, "land-cover-crops-ranking")["title"].startswith("Alpha 00 held")


def test_no_ranking_when_only_one_place_was_measured(provider):
    # Gone was not measured in 2019, so only Cloudy remains of Beta's districts.
    body = provider(at("p-b", "Beta", "province"), 2019)

    assert "land-cover-crops-ranking" not in [c["id"] for c in body["charts"]]


def test_nothing_says_converted(provider):
    for place_id, level in (("PK", "national"), ("p-a", "province"), ("d-cloudy", "district")):
        body = provider(at(place_id, place_id, level), 2019)
        assert "convert" not in str(body).lower()


def test_every_answer_says_which_product_it_comes_from_and_how_it_was_measured(provider):
    measured = provider(at("PK", "Pakistan", "national"), 2019)
    unpublished = provider(at("PK", "Pakistan", "national"), 2016)
    missing = provider(at("d-nowhere", "Nowhere", "district"), 2019)

    for body in (measured, unpublished, missing):
        assert "io-lulc-annual-v02" in body["provenance"]
        assert "80 m" in body["provenance"]
        assert "converted" not in body["provenance"]
