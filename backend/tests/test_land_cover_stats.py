"""The published annual land-classification statistics, read and checked."""

import copy
import json

import pytest

from csa_portal.land_cover_stats import AnnualLandCoverStats, LandCoverStatsError

CLASSES = ["1", "2", "5"]


def measurement(**overrides) -> dict:
    base = {
        "classes_ha": {"1": 0.0, "2": 300.0, "5": 600.0},
        "classified_ha": 900.0,
        "cloud_ha": 50.0,
        "nodata_ha": 50.0,
        "measured_ha": 950.0,
        "coverage_pct": 95.0,
    }
    base.update(overrides)
    return base


def document(**overrides) -> dict:
    base = {
        "schema_version": 1,
        "collection": "io-lulc-annual-v02",
        "classes": CLASSES,
        "years": ["2019", "2020"],
        "method": "counted",
        "provenance": {"collection": "io-lulc-annual-v02"},
        "places": {
            "PK": {
                "name": "Pakistan",
                "level": "national",
                "parent_id": None,
                "area_ha": 1000.0,
                "by_year": {"2019": measurement()},
            },
            "PK1": {"name": "Punjab", "level": "province", "parent_id": "PK", "area_ha": 500.0, "by_year": {}},
        },
    }
    base.update(overrides)
    return base


def with_place(change) -> dict:
    changed = copy.deepcopy(document())
    change(changed["places"]["PK"])
    return changed


def test_the_years_classes_and_places_are_read():
    stats = AnnualLandCoverStats(document())

    assert stats.years == [2019, 2020]
    assert stats.classes == CLASSES
    assert stats.method == "counted"
    assert set(stats.places()) == {"PK", "PK1"}
    assert stats.place("PK").name == "Pakistan"
    assert stats.place("PK").years == [2019]
    assert stats.place("PK1").parent_id == "PK"
    assert [place.id for place in stats.children("PK")] == ["PK1"]
    assert stats.place("nowhere") is None


def test_a_year_is_read_with_its_areas_and_coverage():
    stats = AnnualLandCoverStats(document())

    year = stats.year("PK", 2019)
    assert year.classes_ha == {"1": 0.0, "2": 300.0, "5": 600.0}
    assert (year.classified_ha, year.cloud_ha, year.nodata_ha, year.measured_ha) == (900.0, 50.0, 50.0, 950.0)
    assert year.coverage_pct == 95.0
    assert stats.year("PK", "2019") == year
    assert stats.year("PK", 2020) is None  # published, but not measured here
    assert stats.year("nowhere", 2019) is None


def test_shares_of_classified_land_and_of_all_land_are_kept_apart():
    year = AnnualLandCoverStats(document()).year("PK", 2019)

    assert year.share_of_classified("5") == pytest.approx(66.667, abs=0.001)
    assert year.share_of_land("5") == pytest.approx(60.0)
    assert year.share_of_classified("1") == 0.0


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (document(schema_version=2), "schema version"),
        (document(classes=[]), "no classes"),
        (document(years="2019"), "no years"),
        (document(places={}), "no places"),
        (document(places={"PK": "nonsense"}), "malformed"),
        (with_place(lambda place: place.update(level="county")), "unknown level"),
        (with_place(lambda place: place.update(area_ha=-1)), "not an area"),
        (with_place(lambda place: place.update(parent_id="PX")), "unknown place"),
        (with_place(lambda place: place["by_year"].update({"2021": measurement()})), "not a published year"),
        (with_place(lambda place: place["by_year"]["2019"].pop("classes_ha")), "no class areas"),
        (with_place(lambda place: place["by_year"]["2019"]["classes_ha"].pop("1")), "exactly the published classes"),
        (with_place(lambda place: place["by_year"]["2019"]["classes_ha"].update({"5": "lots"})), "not an area"),
        (with_place(lambda place: place["by_year"]["2019"].update(cloud_ha=float("nan"))), "not an area"),
        (with_place(lambda place: place["by_year"]["2019"].update(coverage_pct=101)), "above 100%"),
    ],
)
def test_a_file_of_the_wrong_shape_is_refused(broken, message):
    with pytest.raises(LandCoverStatsError, match=message):
        AnnualLandCoverStats(broken)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(LandCoverStatsError, match="cannot read"):
        AnnualLandCoverStats.load(tmp_path / "nowhere.json")


def test_a_file_on_disk_is_read(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps(document()), encoding="utf-8")

    stats = AnnualLandCoverStats.load(path)

    assert stats.years == [2019, 2020]
    assert stats.provenance["collection"] == "io-lulc-annual-v02"
