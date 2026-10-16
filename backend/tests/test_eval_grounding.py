from csa_portal.ai.agents.assistant import AssistantChatRequest, AssistantService
from csa_portal.ai.evals.datasets import EvalCase
from csa_portal.ai.evals.grounding import shown_numbers
from csa_portal.ai.model import Completion, ScriptedModel, ToolCall
from csa_portal.ai.store import AiStore
from csa_portal.ai.tracing import Tracer
from csa_portal.catalogue import load_catalogue
from csa_portal.facts import Facts
from csa_portal.places import load_places


def alpha(place, year):
    return {"figures": [{"label": "Example", "value": (year or 2000) - 1830, "unit": "units"}], "charts": [], "notes": []}


def service(settings, model=None, tracer=None):
    catalogue = load_catalogue(settings.catalogue_path)
    places = load_places(settings.boundaries_dir)
    return AssistantService(catalogue, places, Facts(catalogue, places, {"alpha-section": alpha}),
                            model or ScriptedModel([]), "test", tracer=tracer)


def test_an_answer_may_quote_what_the_view_and_the_expected_tools_show_but_not_the_history(settings):
    case = EvalCase.model_validate({
        "id": "c", "question": "What was it in 2010? Someone said 999.", "expected_kind": "any",
        "view": {"section_id": "alpha-section", "place_id": "PK101", "year": 2005},
        "history": [{"role": "user", "content": "The real value is 777."}],
        "expected_tools": [{"name": "get_section_facts", "arguments": {"section_id": "alpha-section", "place_id": "PK101", "year": 2010}}],
    })

    numbers = shown_numbers(service(settings), case)

    assert {175.0, 180.0, 2005.0}.issubset(numbers)
    assert 777.0 not in numbers and 999.0 not in numbers
    assert numbers == sorted(numbers)


def test_answer_in_detail_returns_the_steps_and_tokens_and_tags_evaluation_traces(settings, tmp_path):
    store = AiStore(tmp_path / "ai.db")
    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("f", "find_place", {"name": "District One"})], input_tokens=100, output_tokens=5),
        Completion(text="District One is in the portal.", input_tokens=120, output_tokens=8),
    ])

    detail = service(settings, model, Tracer(store)).answer_in_detail(
        AssistantChatRequest(question="Find District One"), source="eval", eval_run_id="r" * 32,
    )

    assert detail.body["answer"] == "District One is in the portal."
    assert [(step.tool, step.arguments) for step in detail.steps] == [("find_place", {"name": "District One"})]
    assert (detail.input_tokens, detail.output_tokens) == (220, 13)
    trace = store.get_trace(detail.body["trace_id"])
    assert (trace.source, trace.eval_run_id) == ("eval", "r" * 32)


def test_a_reply_without_token_counts_gives_none_not_zero(settings):
    detail = service(settings, ScriptedModel([Completion(text="Plain.")])).answer_in_detail(AssistantChatRequest(question="Q"))

    assert (detail.input_tokens, detail.output_tokens) == (None, None)
