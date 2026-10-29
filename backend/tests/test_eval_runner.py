from csa_portal.ai.agents.assistant import AssistantService
from csa_portal.ai.evals.cassettes import CassetteModel
from csa_portal.ai.evals.datasets import Dataset
from csa_portal.ai.evals.report import markdown_report
from csa_portal.ai.evals.runner import run_dataset
from csa_portal.ai.model import Completion, ModelError, ScriptedModel
from csa_portal.ai.store import AiStore
from csa_portal.ai.tracing import Tracer
from csa_portal.catalogue import load_catalogue
from csa_portal.facts import Facts
from csa_portal.places import load_places

DATASET = Dataset.model_validate({"name": "tiny", "version": 1, "review_status": "draft", "cases": [
    {"id": "steady", "question": "Say hello", "expected_kind": "any", "required_terms": ["hello"]},
    {"id": "wobbly", "question": "Say hello again", "expected_kind": "any", "required_terms": ["hello"]},
]})


def assistant(settings, model, store=None):
    catalogue = load_catalogue(settings.catalogue_path)
    places = load_places(settings.boundaries_dir)
    return AssistantService(catalogue, places, Facts(catalogue, places, {}), model, "test", tracer=Tracer(store))


def test_repeats_give_pass_k_flakiness_and_per_scorer_rates(settings):
    # Answers in order: steady x3, then wobbly x3, of which one forgets the word.
    answers = ["hello", "hello", "hello", "hello", "goodbye", "hello"]
    model = ScriptedModel([Completion(text=text) for text in answers])

    outcome = run_dataset(assistant(settings, model), DATASET, mode="live", model="qwen", repeats=3, git_sha="abc1234")

    summary = outcome.record.summary
    assert (summary["cases"], summary["passed_cases"], summary["pass_rate"]) == (2, 1, 0.5)
    assert summary["flaky_cases"] == ["wobbly"]
    assert summary["scorers"]["required_terms"] == 5 / 6
    assert summary["scorers"]["safety"] == 1.0
    assert [(r.case_id, r.repeat, r.passed) for r in outcome.results] == [
        ("steady", 0, True), ("steady", 1, True), ("steady", 2, True),
        ("wobbly", 0, True), ("wobbly", 1, False), ("wobbly", 2, True),
    ]
    assert (outcome.record.dataset, outcome.record.mode, outcome.record.repeats, outcome.record.git_sha) == (
        "tiny", "live", 3, "abc1234",
    )


def test_a_model_that_stops_fails_its_case_and_the_run_finishes_and_is_stored(settings, tmp_path):
    class StopsAfterOne:
        calls = 0

        def complete(self, messages, tools=None):
            self.calls += 1
            if self.calls > 1:
                raise ModelError(503, "assistant-unavailable", "The local AI model stopped answering")
            return Completion(text="hello")

    store = AiStore(tmp_path / "ai.db")
    outcome = run_dataset(assistant(settings, StopsAfterOne(), store), DATASET, mode="live", model="qwen", store=store)

    assert [r.passed for r in outcome.results] == [True, False]
    assert outcome.results[1].scores["required_terms"].reason == "no answer: assistant-unavailable"
    stored_run, stored_results = store.get_eval_run(outcome.record.id)
    assert stored_run == outcome.record
    assert [r.case_id for r in stored_results] == ["steady", "wobbly"]
    trace = store.get_trace(outcome.results[0].trace_id)
    assert (trace.source, trace.eval_run_id) == ("eval", outcome.record.id)


def test_a_case_without_a_cassette_fails_with_its_reason_and_the_others_still_run(settings):
    replay = CassetteModel()
    cassettes = {"steady": [Completion(text="hello")]}

    outcome = run_dataset(
        assistant(settings, replay), DATASET, mode="recorded", model="cassette-replay",
        before_case=lambda case, repeat: replay.load(cassettes.get(case.id)),
    )

    assert [r.passed for r in outcome.results] == [True, False]
    assert outcome.results[1].answer == "Evaluation error: no-cassette"


def test_the_report_summarises_each_dataset_and_shows_every_repeat(settings):
    model = ScriptedModel([Completion(text=text) for text in ["hello", "hello", "goodbye", "hello"]])
    outcome = run_dataset(assistant(settings, model), DATASET, mode="live", model="qwen", repeats=2)

    report = markdown_report([(DATASET, outcome)])

    assert report.startswith("# Assistant evaluation\n")
    assert "## tiny (version 1)" in report
    assert "- Passed every repeat (pass^2): 1/2 (50.0%)" in report
    assert "- Flaky: `wobbly`" in report
    assert "| Required Terms | 3/4 (75.0%) |" in report
    assert "| `wobbly` | fail pass | required_terms: missing: hello |" in report


from csa_portal.ai.evals.judge import Judge, JudgeVerdict  # noqa: E402

ONE = Dataset.model_validate({"name": "one", "version": 1, "review_status": "draft", "cases": [
    {"id": "hello", "question": "Say hello", "expected_kind": "any", "required_terms": ["hello"]},
]})
UNFAITHFUL = JudgeVerdict(faithful=False, unsupported_claims=["a made-up figure"], helpfulness=2, reason="Invented.")


def judged(settings, verdicts, *, gates):
    judge = Judge(ScriptedModel([Completion(data=verdict) for verdict in verdicts]), "gemma")
    model = ScriptedModel([Completion(text="hello") for _ in verdicts])
    return run_dataset(assistant(settings, model), ONE, mode="live", model="qwen", judge=judge, judge_gates=gates)


def test_an_uncalibrated_judge_is_recorded_but_an_unfaithful_verdict_does_not_fail_the_case(settings):
    outcome = judged(settings, [UNFAITHFUL], gates=False)

    [result] = outcome.results
    assert result.passed is True
    assert result.scores["faithfulness"].value == 0.0 and result.scores["faithfulness"].passed is None
    assert (outcome.record.judge_model, outcome.record.status) == ("gemma", "complete")
    assert outcome.record.summary["judge"] == {
        "model": "gemma", "calibrated": False, "faithful_rate": 0.0, "mean_helpfulness": 2.0, "unavailable": 0,
    }


def test_a_calibrated_judge_fails_a_case_its_deterministic_checks_passed(settings):
    [result] = judged(settings, [UNFAITHFUL], gates=True).results

    assert result.passed is False


def test_a_judge_that_cannot_answer_leaves_the_deterministic_result_and_marks_the_run_partial(settings):
    class Unloaded:
        def complete(self, messages, tools=None, output=None):
            raise ModelError(404, "assistant-misconfigured", "Model not loaded")

    model = ScriptedModel([Completion(text="hello")])
    outcome = run_dataset(assistant(settings, model), ONE, mode="live", model="qwen",
                          judge=Judge(Unloaded(), "gemma"), judge_gates=True)

    [result] = outcome.results
    assert result.passed is True
    assert result.scores["faithfulness"].reason == "judge-unavailable"
    assert outcome.record.status == "partial"
    assert outcome.record.summary["judge"]["unavailable"] == 1


def test_the_judge_is_not_asked_about_a_run_that_has_no_answer(settings):
    class Down:
        def complete(self, messages, tools=None):
            raise ModelError(503, "assistant-unavailable", "down")

    judge_model = ScriptedModel([])
    outcome = run_dataset(assistant(settings, Down()), ONE, mode="live", model="qwen",
                          judge=Judge(judge_model, "gemma"))

    assert outcome.results[0].scores["faithfulness"].reason == "no answer"
    assert judge_model.sent == []


def test_the_report_names_the_judge_and_whether_it_is_calibrated(settings):
    outcome = judged(settings, [UNFAITHFUL], gates=False)

    report = markdown_report([(ONE, outcome)])

    assert "- Judge `gemma` (uncalibrated): faithful 0.0%, mean helpfulness 2.0/5, unavailable 0" in report


def test_the_judge_grades_with_the_context_and_facts_the_assistant_was_shown(settings):
    import json as json_module

    judge_model = ScriptedModel([Completion(data=JudgeVerdict(faithful=True, helpfulness=5, reason="Fine."))])
    model = ScriptedModel([Completion(text="hello")])

    run_dataset(assistant(settings, model), ONE, mode="live", model="qwen", judge=Judge(judge_model, "gemma"))

    data = json_module.loads(judge_model.sent[0][1]["content"])
    assert data["context"]["portal"]["title"] == "Climate Smart Agriculture Portal"
    assert "current_view" in data["context"]


def test_an_urdu_dataset_asks_every_question_for_an_urdu_answer(settings):
    urdu = DATASET.model_copy(update={"language": "ur"})
    model = ScriptedModel([Completion(text="hello"), Completion(text="hello")])

    run_dataset(assistant(settings, model), urdu, mode="live", model="qwen")

    assert all("ANSWER LANGUAGE:" in sent[-1]["content"] for sent in model.sent)
    assert "Language: Urdu" in markdown_report([(urdu, run_dataset(
        assistant(settings, ScriptedModel([Completion(text="hello")] * 2)), urdu, mode="live", model="qwen"))])
