import pytest

from csa_portal.ai.evals.cassettes import CassetteModel, RecordingModel, cassette_path, load_cassette, save_cassette
from csa_portal.ai.model import Completion, ModelError, ScriptedModel, ToolCall

TURNS = [
    Completion(tool_calls=[ToolCall("call-1", "find_place", {"name": "Lahore"})], input_tokens=300, output_tokens=12),
    Completion(text="Lahore is a district in Punjab.", input_tokens=340, output_tokens=9),
]


def test_a_cassette_is_saved_under_its_dataset_and_case_and_reads_back_the_same(tmp_path):
    path = cassette_path("golden", "land-punjab", tmp_path)

    save_cassette(path, TURNS)

    assert path == tmp_path / "golden" / "land-punjab.json"
    assert load_cassette(path) == TURNS


def test_recording_passes_every_reply_through_and_keeps_it():
    recorder = RecordingModel(ScriptedModel(list(TURNS)))

    replies = [recorder.complete([{"role": "user", "content": "Q"}], tools=[]) for _ in TURNS]
    assert replies == TURNS and recorder.turns == TURNS
    recorder.start()
    assert recorder.turns == []


def test_replay_gives_the_turns_back_then_says_it_has_run_out():
    replay = CassetteModel()
    replay.load(list(TURNS))

    assert [replay.complete([], tools=[]) for _ in TURNS] == TURNS
    with pytest.raises(ModelError) as raised:
        replay.complete([], tools=[])
    assert raised.value.reason == "cassette-exhausted"


def test_replay_without_a_cassette_fails_with_its_own_reason():
    replay = CassetteModel()
    replay.load(None)

    with pytest.raises(ModelError) as raised:
        replay.complete([])
    assert raised.value.reason == "no-cassette"


def test_a_recorded_assistant_answer_replays_to_the_same_answer_and_steps(settings):
    from csa_portal.ai.agents.assistant import AssistantChatRequest, AssistantService
    from csa_portal.catalogue import load_catalogue
    from csa_portal.facts import Facts
    from csa_portal.places import load_places

    catalogue = load_catalogue(settings.catalogue_path)
    places = load_places(settings.boundaries_dir)

    def assistant(model):
        return AssistantService(catalogue, places, Facts(catalogue, places, {}), model, "test")

    question = AssistantChatRequest(question="Where is Lahore?")
    recorder = RecordingModel(ScriptedModel(list(TURNS)))
    live = assistant(recorder).answer_in_detail(question)
    replay = CassetteModel()
    replay.load(recorder.turns)
    replayed = assistant(replay).answer_in_detail(question)

    assert replayed.body["answer"] == live.body["answer"]
    assert replayed.steps == live.steps
