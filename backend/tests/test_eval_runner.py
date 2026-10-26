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
