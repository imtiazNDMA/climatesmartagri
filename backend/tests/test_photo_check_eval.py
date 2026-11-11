"""Scoring the photo check against the bars that decide whether Auto may be switched on (#93)."""

import hashlib
import json

import pytest

from csa_portal.ai.evals.photo_check import (
    EVALUATION_DIR, Case, load_cases, load_readings, macro_f1, prompt_sha256, score,
)
from csa_portal.photo_check import PhotoReading


def case(number, group="crop", crop="Maize", label="maize_healthy", part="final"):
    return Case(id=f"{group}-{number}", part=part, group=group, crop=crop, label=label, source="test", path=f"{number}.jpg")


def read(crop="Maize", **fields):
    return PhotoReading(**{"is_plant": True, "crop": crop, **fields})


def bar(report, name):
    return next(b for b in report.bars if b.name == name)


def test_crop_identification_counts_only_the_right_crop_and_false_stops_only_refusals():
    cases = [case(n) for n in range(10)]
    readings = {c.id: read() for c in cases[:6]}
    readings[cases[6].id] = read("Sugarcane")                          # sent to the wrong classifier
    readings[cases[7].id] = read("Unclear")                            # handed back to the reader
    readings[cases[8].id] = read("Other", other_plant="Bamboo")        # refused
    readings[cases[9].id] = read("Other", is_plant=False)              # refused

    report = score(cases, readings)

    assert bar(report, "crop-identification").value == 0.6
    assert bar(report, "false-stops").value == 0.2
    assert report.crop_outcomes == {"Maize": {"right": 6, "wrong-crop": 1, "unclear": 1, "stopped": 2}}
    assert not bar(report, "crop-identification").met and not bar(report, "false-stops").met


def test_photos_that_should_be_stopped_count_as_stopped_only_when_no_crop_and_no_question_follows():
    not_plants = [case(n, "not-plant", "", "") for n in range(4)]
    others = [case(n, "other-plant", "", "Tomato") for n in range(4)]
    readings = {
        not_plants[0].id: read("Other", is_plant=False), not_plants[1].id: read("Other", is_plant=False),
        not_plants[2].id: read("Unclear"),   # the reader would be asked to pick a crop for a non-plant
        not_plants[3].id: read("Wheat"),
        others[0].id: read("Other", other_plant="Tomato"), others[1].id: read("Other", other_plant="Potato"),
        others[2].id: read("Other", is_plant=False), others[3].id: read("Cotton"),
    }

    report = score(not_plants + others, readings)

    assert bar(report, "non-plant-stopped").value == 0.5
    assert bar(report, "unsupported-plant-stopped").value == 0.75


def test_quality_warnings_are_reported_and_never_hold_auto_back():
    poor = [case(n, "poor") for n in range(4)]
    clean = [case(n) for n in range(4)]
    readings = {c.id: read() for c in poor + clean}
    readings[poor[0].id] = read(blurred=True)
    readings[poor[1].id] = read(too_dark=True)
    readings[clean[0].id] = read(several_leaves=True)

    report = score(poor + clean, readings)

    assert (report.quality_raised_on_poor, report.quality_raised_on_clean) == (0.5, 0.25)
    assert all(b.name != "quality" for b in report.bars)


def test_the_classifier_score_through_auto_loses_misrouted_and_stopped_photos_but_not_unclear_ones():
    cases = [case(n, label="maize_healthy") for n in range(4)] + [case(n + 4, label="maize_rust") for n in range(4)]
    hand = {c.path: c.label for c in cases}      # the classifier is right on every photo when the crop is hand-picked
    readings = {c.id: read() for c in cases}
    readings[cases[0].id] = read("Unclear")      # the reader names the crop: nothing lost
    readings[cases[4].id] = read("Sugarcane")    # misrouted: lost
    readings[cases[5].id] = read("Other", is_plant=False)  # stopped: lost

    report = score(cases, readings, hand)

    assert report.hand_macro_f1 == 1.0
    assert report.auto_macro_f1 == pytest.approx((1.0 + 2 * 0.5 * 1.0 / 1.5) / 2, abs=1e-4)  # rust recall 2/4
    assert not bar(report, "auto-macro-f1-drop").met


def test_auto_ships_only_when_every_bar_is_met():
    cases = [case(n) for n in range(100)] + [case(n, "not-plant", "", "") for n in range(20)] + [
        case(n, "other-plant", "", "Tomato") for n in range(20)
    ]
    readings = {c.id: read() if c.group == "crop" else read("Other", is_plant=c.group == "other-plant") for c in cases}
    hand = {c.path: c.label for c in cases if c.group == "crop"}

    assert score(cases, readings, hand).ship is True
    readings[cases[0].id] = readings[cases[1].id] = readings[cases[2].id] = readings[cases[3].id] = read("Wheat")
    assert score(cases, readings, hand).ship is False


def test_a_photo_with_no_recorded_answer_is_an_error_not_a_silent_gap():
    with pytest.raises(KeyError, match="crop-1"):
        score([case(0), case(1)], {"crop-0": read()})


def test_macro_f1_is_the_mean_over_the_true_classes():
    assert macro_f1(["a", "a", "b", "b"], ["a", "b", "b", "b"]) == pytest.approx((2 / 3 + 0.8) / 2)


@pytest.mark.parametrize("part", ["tune", "final"])
def test_the_recorded_answers_give_the_committed_report(part):
    """CI has no vision model: it replays the answers a live run recorded and checks the report still follows."""
    recorded = sorted((EVALUATION_DIR / "readings").glob(f"*-{part}.json"))
    if not recorded:
        pytest.skip(f"no {part} run has been recorded yet")
    cases = [c for c in load_cases() if c.part == part]
    for path in recorded:
        run = load_readings(path)
        report = score(cases, run.readings, run.hand_predictions)
        committed = json.loads(path.with_suffix(".report.json").read_text(encoding="utf-8"))
        assert json.loads(report.to_json()) == committed, f"{path.name} no longer gives its committed report"


def test_the_final_answers_were_recorded_with_the_prompt_the_portal_uses():
    for path in sorted((EVALUATION_DIR / "readings").glob("*-final.json")):
        if json.loads(path.read_text(encoding="utf-8")).get("shipping"):
            assert load_readings(path).prompt_sha256 == prompt_sha256(), (
                "The photo check prompt changed after its final evaluation: re-run evaluate_photo_check.py"
            )


def test_the_committed_set_has_no_photo_in_both_parts_and_names_every_photo_by_its_hash():
    cases = load_cases()
    if not cases:
        pytest.skip("the set has not been built yet")
    assert len({c.id for c in cases}) == len(cases)
    assert all(len(c.id) == len(hashlib.sha256().hexdigest()) for c in cases)
    assert {c.part for c in cases} == {"tune", "final"}
    assert {c.group for c in cases} == {"crop", "other-plant", "not-plant", "poor"}
