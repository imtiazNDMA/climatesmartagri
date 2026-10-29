import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prepare_data import parse_calendar, read_crop_calendar  # noqa: E402

SCRIPT = """const records = [
  {
    province: 'Punjab',
    crop: 'Wheat',
    traditional: 'Oct–Dec sowing → Mar–Apr harvest',
    adjusted: 'Oct–Nov sowing → Mar–Apr harvest',
    reason: 'Rising temperatures can reduce yield; timely sowing helps.'
  },
  {
    province: 'KP',
    crop: 'Maize',
    traditional: 'Feb–Apr / Jun–Jul',
    adjusted: 'Feb–Mar / Jun–Jul',
    reason: 'Heat during reproductive stages can reduce grain formation.'
  },
  {
    province: 'Baluchistan',
    crop: 'Orchards',
    traditional: 'Traditional regional schedule',
    adjusted: 'Climate-risk adjusted',
    reason: 'Warmer winters may affect chilling requirements.'
  }
];

const provinceOrder = ['All', 'Punjab'];
"""


def test_a_sowing_and_harvest_calendar_becomes_month_ranges():
    calendar = parse_calendar("Oct–Dec sowing → Mar–Apr harvest")
    assert calendar == {
        "text": "Oct–Dec sowing → Mar–Apr harvest",
        "sowing": [[9.0, 12.0]],
        "harvest": [[2.0, 4.0]],
    }


def test_months_without_the_words_sowing_and_harvest_read_the_same_way():
    assert parse_calendar("May–Jul → Sep–Oct")["sowing"] == [[4.0, 7.0]]
    assert parse_calendar("May–Jul → Sep–Oct")["harvest"] == [[8.0, 10.0]]


def test_a_single_month_and_a_part_month():
    assert parse_calendar("Jun → Sep–Oct")["sowing"] == [[5.0, 6.0]]
    assert parse_calendar("Jun–early Jul → Sep–Oct")["sowing"] == [[5.0, 6.5]]
    assert parse_calendar("Nov–early Dec → Mar–Apr")["sowing"] == [[10.0, 11.5]]
    assert parse_calendar("late Jun–Jul → Sep")["sowing"] == [[5.5, 7.0]]


def test_either_month_takes_the_wider_range():
    assert parse_calendar("Apr–May → Aug–Oct/Nov")["harvest"] == [[7.0, 11.0]]


def test_two_planting_seasons_with_no_harvest_given():
    calendar = parse_calendar("Feb–Mar / Sep–Oct")
    assert calendar["sowing"] == [[1.0, 3.0], [8.0, 10.0]]
    assert calendar["harvest"] == []


def test_a_range_that_runs_over_the_new_year_is_split():
    assert parse_calendar("Nov–Feb → May")["sowing"] == [[10.0, 12.0], [0.0, 2.0]]


def test_wording_with_no_months_keeps_its_text_and_has_no_ranges():
    calendar = parse_calendar("Traditional regional schedule")
    assert calendar == {"text": "Traditional regional schedule", "sowing": [], "harvest": []}


@pytest.mark.parametrize("text", ["Oct-Dec → Mar-Apr", "Oct – Dec → Mar – Apr", "oct–dec -> mar–apr"])
def test_plain_hyphens_spacing_case_and_ascii_arrows_are_accepted(text):
    assert parse_calendar(text)["sowing"] == [[9.0, 12.0]]
    assert parse_calendar(text)["harvest"] == [[2.0, 4.0]]


def test_read_crop_calendar_reads_the_records_from_the_calendar_app(tmp_path):
    path = tmp_path / "script.js"
    path.write_text(SCRIPT, encoding="utf-8")
    records = read_crop_calendar(path)

    assert [(r["province_id"], r["province"], r["crop"]) for r in records] == [
        ("p-punjab", "Punjab", "Wheat"),
        ("p-khyber-pakhtunkhwa", "Khyber Pakhtunkhwa", "Maize"),
        ("p-balochistan", "Balochistan", "Orchards"),
    ]
    wheat = records[0]
    assert wheat["traditional"]["sowing"] == [[9.0, 12.0]]
    assert wheat["adjusted"]["sowing"] == [[9.0, 11.0]]
    assert wheat["reason"] == "Rising temperatures can reduce yield; timely sowing helps."
    assert wheat["changed"] is True
    assert wheat["sown_earlier"] is True
    maize = records[1]
    assert maize["sown_earlier"] is True
    orchards = records[2]
    assert orchards["changed"] is True
    assert orchards["sown_earlier"] is False


def test_an_unchanged_calendar_is_marked_unchanged(tmp_path):
    path = tmp_path / "script.js"
    path.write_text(SCRIPT.replace("'Oct–Nov sowing → Mar–Apr harvest'", "'Oct–Dec sowing → Mar–Apr harvest'"), encoding="utf-8")
    wheat = read_crop_calendar(path)[0]
    assert (wheat["changed"], wheat["sown_earlier"]) == (False, False)


def test_a_file_without_the_records_is_reported(tmp_path):
    path = tmp_path / "script.js"
    path.write_text("const nothing = [];", encoding="utf-8")
    with pytest.raises(ValueError, match="records"):
        read_crop_calendar(path)


def test_the_real_calendar_app_parses_completely():
    from prepare_data import CROP_CALENDAR_FILE

    records = read_crop_calendar(CROP_CALENDAR_FILE)
    assert len(records) == 20
    assert {r["province"] for r in records} == {"Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan"}
    # Every calendar except the orchards entry, which names no months, has a sowing range.
    without_months = [r["crop"] for r in records if not r["traditional"]["sowing"]]
    assert without_months == ["Orchards"]
    punjab = [r for r in records if r["province"] == "Punjab"]
    assert sorted(r["crop"] for r in punjab if r["sown_earlier"]) == ["Cotton", "Maize – Kharif", "Rice", "Wheat"]
