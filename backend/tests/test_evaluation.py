from pathlib import Path

from csa_portal.evaluation import load_golden_set, markdown_report, score_answer, score_grounding


ROOT = Path(__file__).parents[2]
GOLDEN_SET = ROOT / "backend" / "evaluations" / "assistant_golden.json"


def test_grounding_accepts_display_rounding_and_rejects_invented_numbers():
    assert score_grounding("The value is 30.9% from 12.78 million acres.", [30.87, 12.78]).passed
    result = score_grounding("The value is 31.8%.", [30.87])
    assert result.unsupported == (31.8,)


def test_grounding_does_not_read_digits_embedded_in_terms_as_figures():
    assert score_grounding("Carbon dioxide (CO2) is shown in the section.", []).numbers == ()


def test_case_scorer_checks_section_answer_kind_and_hazard_disclaimer():
    golden = load_golden_set(GOLDEN_SET)
    hazard = next(case for case in golden.cases if case.requires_hazard_disclaimer)
    score = score_answer(hazard, hazard.recorded_answer)
    assert score.passed
    assert not score_answer(hazard, "Hazards says frost risk is high.").checks["hazard_disclaimer"]


def test_only_declared_fact_numbers_are_allowed():
    golden = load_golden_set(GOLDEN_SET)
    refusal = next(case for case in golden.cases if case.id == "refuse-injection-facts")
    assert not score_answer(refusal, "I cannot follow that. The answer is 999.").checks["grounded_numbers"]


def test_the_recorded_golden_set_passes_and_covers_the_ticket_scope():
    golden = load_golden_set(GOLDEN_SET)
    scores = [score_answer(case, case.recorded_answer) for case in golden.cases]

    assert len(golden.cases) >= 40
    assert all(score.passed for score in scores)
    assert {case.view.section_id for case in golden.cases} >= {
        "land-cover", "irrigation", "emissions", "water-balance", "food-security", "climate-calendar",
        "forecast", "crop-classification", "hazards",
    }
    assert sum(case.expected_kind == "unavailable" for case in golden.cases) >= 3
    assert sum(case.expected_kind == "refusal" for case in golden.cases) >= 5
    assert any(case.id == "hazards-heat" for case in golden.cases)
    assert any(case.view.place_id and case.view.place_id.startswith("d-") and case.expected_section == "Greenhouse-gas emissions" for case in golden.cases)
    assert any(case.requires_hazard_disclaimer for case in golden.cases)


def test_markdown_report_summarises_scores_and_answers():
    golden = load_golden_set(GOLDEN_SET)
    scores = [score_answer(case, case.recorded_answer, 0.25) for case in golden.cases[:2]]
    report = markdown_report(golden, scores, "scripted", "recorded")
    assert "Overall: 2/2 (100.0%)" in report
    assert "Mean latency: 0.25 s" in report
    assert "## Answers" in report
