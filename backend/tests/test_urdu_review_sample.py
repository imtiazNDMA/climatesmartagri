import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from csa_portal.ai.evals.datasets import Dataset  # noqa: E402
from urdu_review_sample import pick, review_sheet  # noqa: E402


def dataset(name, language, questions):
    return Dataset.model_validate({"name": name, "version": 1, "review_status": "draft", "language": language, "cases": [
        {"id": case_id, "question": question, "expected_kind": kind, **({"expected_section": section} if section else {})}
        for case_id, question, kind, section in questions
    ]})


CASES = [
    ("land-a", "زمین الف؟", "grounded", "Land"), ("land-b", "زمین ب؟", "grounded", "Land"),
    ("land-c", "زمین ج؟", "grounded", "Land"), ("water-a", "پانی؟", "grounded", "Water"),
    ("hazard-a", "خطرہ؟", "grounded", "Hazards"), ("soil", "مٹی؟", "unavailable", None),
    ("inject", "نظرانداز کریں", "refusal", None),
]


def test_the_sample_takes_each_section_and_kind_in_turn_before_a_second_of_any():
    picked = pick(dataset("golden_ur", "ur", CASES).cases, {case[0] for case in CASES}, 5)

    assert [case.id for case in picked] == ["land-a", "water-a", "hazard-a", "soil", "inject"]
    assert [case.id for case in pick(dataset("golden_ur", "ur", CASES).cases, {c[0] for c in CASES}, 6)][-1] == "land-b"


def test_cases_without_a_recorded_answer_are_not_sampled():
    picked = pick(dataset("golden_ur", "ur", CASES).cases, {"land-b", "soil"}, 20)

    assert [case.id for case in picked] == ["land-b", "soil"]


def test_the_sheet_shows_both_questions_the_answer_the_checks_and_the_panel_words(tmp_path):
    urdu = dataset("golden_ur", "ur", CASES[:1])
    english = dataset("golden", "en", [("land-a", "Land A?", "grounded", "Land")])
    cassette = tmp_path / "golden_ur" / "land-a.json"
    cassette.parent.mkdir()
    cassette.write_text(json.dumps([
        {"text": None, "tool_calls": [{"id": "1", "name": "find_place", "arguments": {}}], "input_tokens": 1, "output_tokens": 1},
        {"text": "پنجاب (Punjab) میں 30.5 ملین ایکڑ۔", "tool_calls": [], "input_tokens": 1, "output_tokens": 1},
    ], ensure_ascii=False), encoding="utf-8")

    sheet = review_sheet(urdu, english, tmp_path, 20)

    assert "### 1. `land-a` (Land)" in sheet
    assert "زمین الف؟" in sheet and "Land A?" in sheet
    assert "پنجاب (Punjab) میں 30.5 ملین ایکڑ۔" in sheet
    assert sheet.count("- [ ] ") >= 4
    assert "ذرائع:" in sheet and "Reviewer:" in sheet
    assert "1 answers" in sheet
