import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from csa_portal.ai.evals.datasets import Dataset, EvalCase, dataset_path, dump_dataset, load_dataset

BACKEND = Path(__file__).resolve().parents[1]


def test_both_datasets_load_with_their_names_and_versions():
    golden, adversarial = load_dataset("golden"), load_dataset("adversarial")

    assert (golden.name, golden.version, len(golden.cases)) == ("golden", 3, 60)
    assert (adversarial.name, adversarial.version) == ("adversarial", 2)
    assert len(adversarial.cases) >= 18


def test_the_urdu_golden_set_asks_the_english_questions_in_urdu_with_the_same_checks():
    english, urdu = load_dataset("golden"), load_dataset("golden_ur")

    assert (urdu.name, urdu.language, english.language) == ("golden_ur", "ur", "en")
    assert [case.id for case in urdu.cases] == [case.id for case in english.cases]
    for en, ur in zip(english.cases, urdu.cases, strict=True):
        same = ("view", "expected_kind", "expected_section", "fact_values", "forbidden_values", "expected_tools",
                "requires_hazard_disclaimer", "max_tool_calls")
        assert {key: getattr(ur, key) for key in same} == {key: getattr(en, key) for key in same}, en.id
        assert any("؀" <= ch <= "ۿ" for ch in ur.question), en.id
    assert dump_dataset(urdu) == dataset_path("golden_ur").read_text(encoding="utf-8")


def test_every_case_points_at_real_sections_places_and_tools():
    from csa_portal.ai.agents.assistant import assistant_tools
    from csa_portal.catalogue import load_catalogue
    from csa_portal.places import load_places

    sections = {section.id for section in load_catalogue(BACKEND / "catalogue.json").sections}
    places = load_places(BACKEND / "boundaries").by_id
    # set_portal_view is registered beside the fact tools, once the catalogue and places are known.
    tools = {tool.name for tool in assistant_tools(None).tools} | {"set_portal_view"}
    for dataset in (load_dataset("golden"), load_dataset("adversarial")):
        for case in dataset.cases:
            assert case.view.section_id is None or case.view.section_id in sections, case.id
            assert case.view.place_id is None or case.view.place_id in places, case.id
            for tool in case.expected_tools:
                assert tool.name in tools, case.id
                for key in ("section_id",):
                    if key in tool.arguments:
                        assert tool.arguments[key] in sections, case.id
                if "place_id" in tool.arguments:
                    assert tool.arguments["place_id"] in places, case.id


def test_the_golden_set_asks_about_other_views_and_names_the_tools_for_them():
    cross_view = [case for case in load_dataset("golden").cases if case.expected_tools]

    assert len(cross_view) >= 8
    # Questions about another view, and requests to change the view.
    assert all(case.id.startswith(("cross-", "view-")) for case in cross_view)


def test_the_adversarial_set_covers_injection_warnings_invented_figures_and_off_topic():
    ids = [case.id for case in load_dataset("adversarial").cases]

    for prefix in ("inject-", "warning-", "invent-", "offtopic-"):
        assert sum(case_id.startswith(prefix) for case_id in ids) >= 3, prefix
    assert any(case.history for case in load_dataset("adversarial").cases)


def test_a_misspelt_field_is_an_error_not_a_skipped_check():
    with pytest.raises(ValidationError, match="expected_tool"):
        EvalCase.model_validate({
            "id": "x", "question": "Q", "expected_kind": "any", "expected_tool": [{"name": "find_place"}],
        })


def test_grounded_cases_must_name_their_section_and_ids_must_be_unique():
    with pytest.raises(ValidationError, match="expected_section"):
        EvalCase.model_validate({"id": "x", "question": "Q", "expected_kind": "grounded"})
    case = {"id": "same", "question": "Q", "expected_kind": "any"}
    with pytest.raises(ValidationError, match="duplicate case ids: same"):
        Dataset.model_validate({"name": "t", "version": 1, "review_status": "draft", "cases": [case, case]})


def test_a_dataset_written_back_reads_the_same_and_leaves_defaults_out():
    golden = load_dataset("golden")

    text = dump_dataset(golden)

    assert Dataset.model_validate(json.loads(text)) == golden
    assert '"max_tool_calls"' not in text
    assert text.count("\n    {") == len(golden.cases)
