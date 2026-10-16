import dataclasses
import hashlib
import sqlite3
import threading
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from csa_portal.ai.model import Completion, ModelError, ScriptedModel, ToolCall
from csa_portal.ai.store import SCHEMA_VERSION, AiStore, TraceRecord
from csa_portal.ai.tracing import Tracer
from csa_portal.main import create_app
from csa_portal.settings import Settings


def test_an_answer_carries_its_trace_id_and_its_trace_is_stored_with_every_span(settings, tmp_path):
    store = AiStore(tmp_path / "ai.db")
    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("find", "find_place", {"name": "District One"})], input_tokens=300, output_tokens=9),
        Completion(text="District One is in the portal.", input_tokens=340, output_tokens=12),
    ])
    client = TestClient(create_app(settings, assistant_client=model, tracer=Tracer(store)))

    body = client.post("/api/assistant/chat", json={"question": "Find District One", "view": {}}).json()

    trace = store.get_trace(body["trace_id"])
    assert body["answer"] == "District One is in the portal."
    assert (trace.source, trace.agent, trace.status, trace.input_tokens, trace.output_tokens) == (
        "live", "assistant", "ok", 640, 21,
    )
    assert trace.model == settings.lm_studio_model
    assert [span.kind for span in trace.spans] == ["agent", "llm", "tool", "llm"]
    assert trace.question_hash == hashlib.sha256(b"Find District One").hexdigest()
    assert (trace.question_text, trace.answer_text) == (None, None)


def test_question_and_answer_are_stored_when_content_capture_is_on(settings, tmp_path):
    store = AiStore(tmp_path / "ai.db")
    model = ScriptedModel([Completion(text="An answer.")])
    client = TestClient(create_app(settings, assistant_client=model, tracer=Tracer(store, capture_content=True)))

    body = client.post("/api/assistant/chat", json={"question": "A question?", "view": {}}).json()

    trace = store.get_trace(body["trace_id"])
    assert (trace.question_text, trace.answer_text) == ("A question?", "An answer.")


def test_a_failed_model_still_leaves_an_error_trace_and_the_reader_gets_the_same_error(settings, tmp_path):
    class Down:
        def complete(self, messages, tools=None):
            raise ModelError(503, "assistant-unavailable", "The local AI model could not be reached")

        def chat(self, messages):
            raise AssertionError("not used")

    store = AiStore(tmp_path / "ai.db")
    client = TestClient(create_app(settings, assistant_client=Down(), tracer=Tracer(store)))

    response = client.post("/api/assistant/chat", json={"question": "Anything?", "view": {}})

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "assistant-unavailable"
    [row] = sqlite3.connect(tmp_path / "ai.db").execute("SELECT status, error_reason FROM traces").fetchall()
    assert row == ("error", "assistant-unavailable")


def test_an_unwritable_store_does_not_stop_answers_and_health_says_degraded(settings):
    class Locked:
        def write_trace(self, trace):
            raise sqlite3.OperationalError("database is locked")

    tracer = Tracer(Locked())
    client = TestClient(create_app(settings, assistant_client=ScriptedModel([Completion(text="Answered.")]), tracer=tracer))

    response = client.post("/api/assistant/chat", json={"question": "Q", "view": {}})

    assert response.status_code == 200
    health = client.get("/api/health").json()
    assert (health["tracing"], health["tracing_failures"]) == ("degraded", 1)


def test_health_says_tracing_is_off_without_a_database(client):
    health = client.get("/api/health").json()

    assert (health["tracing"], health["tracing_error"], health["tracing_failures"]) == ("off", None, 0)


def test_startup_deletes_live_traces_past_retention(settings, tmp_path):
    path = tmp_path / "ai.db"
    store = AiStore(path)
    old = datetime.now(UTC) - timedelta(days=31)
    for trace_id, started in (("a" * 32, old), ("b" * 32, datetime.now(UTC))):
        store.write_trace(TraceRecord(trace_id, "live", "assistant", "qwen", started, 1.0, "ok", None, None, None,
                                      "f" * 64, None, None))
    store.close()

    client = TestClient(create_app(dataclasses.replace(settings, ai_db_path=path, trace_retention_days=30)))

    assert client.get("/api/health").json()["tracing"] == "ok"
    reopened = AiStore(path)
    assert reopened.get_trace("a" * 32) is None
    assert reopened.get_trace("b" * 32) is not None


def test_a_database_newer_than_the_code_leaves_the_portal_running_without_traces(settings, tmp_path):
    path = tmp_path / "ai.db"
    AiStore(path).close()
    with sqlite3.connect(path) as db:
        db.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))

    client = TestClient(create_app(dataclasses.replace(settings, ai_db_path=path),
                                   assistant_client=ScriptedModel([Completion(text="Answered.")])))

    assert client.post("/api/assistant/chat", json={"question": "Q", "view": {}}).status_code == 200
    health = client.get("/api/health").json()
    assert health["tracing"] == "degraded"
    assert "newer than this code" in health["tracing_error"]


class Blocking:
    """A model that holds its answer until released, so a second question finds every slot busy."""

    def __init__(self):
        self.started = threading.Semaphore(0)
        self.release = threading.Event()

    def complete(self, messages, tools=None):
        self.started.release()
        self.release.wait(5)
        return Completion(text="Answered.")


def service(settings, model, **options):
    from csa_portal.ai.agents.assistant import AssistantService
    from csa_portal.catalogue import load_catalogue
    from csa_portal.facts import Facts
    from csa_portal.places import load_places

    catalogue = load_catalogue(settings.catalogue_path)
    places = load_places(settings.boundaries_dir)
    return AssistantService(catalogue, places, Facts(catalogue, places, {}), model, "test", **options)


def ask(assistant, results):
    from csa_portal.ai.agents.assistant import AssistantChatRequest

    try:
        results.append(assistant.answer(AssistantChatRequest(question="Q"))["answer"])
    except ModelError as error:
        results.append(error.reason)


def test_with_one_slot_a_second_question_waits_then_is_told_the_model_is_busy(settings):
    model = Blocking()
    assistant = service(settings, model, concurrency=1, queue_seconds=0.1)
    results = []
    first = threading.Thread(target=ask, args=(assistant, results))
    first.start()
    assert model.started.acquire(timeout=5)

    ask(assistant, results)
    model.release.set()
    first.join()

    assert results == ["assistant-busy", "Answered."]


def test_with_two_slots_two_questions_are_answered_at_once(settings):
    model = Blocking()
    assistant = service(settings, model, concurrency=2, queue_seconds=0.1)
    results = []
    threads = [threading.Thread(target=ask, args=(assistant, results)) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert model.started.acquire(timeout=5) and model.started.acquire(timeout=5)
    model.release.set()
    for thread in threads:
        thread.join()

    assert results == ["Answered.", "Answered."]


def test_ai_settings_are_read_from_the_environment():
    settings = Settings._from({
        "CSA_AI_DB": "elsewhere/ai.db", "CSA_TRACE_CONTENT": "1", "CSA_TRACE_RETENTION_DAYS": "7",
        "CSA_AI_CONCURRENCY": "3", "CSA_AI_QUEUE_SECONDS": "2.5", "CSA_OTLP_ENDPOINT": "http://collector:4318",
    })
    defaults = Settings._from({})

    assert (settings.ai_db_path.as_posix(), settings.trace_content, settings.trace_retention_days) == (
        "elsewhere/ai.db", True, 7,
    )
    assert (settings.ai_concurrency, settings.ai_queue_seconds, settings.otlp_endpoint) == (3, 2.5, "http://collector:4318")
    assert (defaults.ai_db_path.name, defaults.trace_content, defaults.trace_retention_days) == ("ai.db", False, 30)
    assert (defaults.ai_concurrency, defaults.ai_queue_seconds, defaults.otlp_endpoint) == (1, 5, "")
    assert Settings._from({"CSA_AI_CONCURRENCY": "0"}).ai_concurrency == 1
    assert Settings._from({"CSA_AI_DB": ""}).ai_db_path is None


def test_a_database_that_cannot_be_written_at_startup_leaves_the_portal_running_without_traces(
    settings, tmp_path, monkeypatch
):
    """Opening can succeed on a read-only or locked file; the retention delete is then the first write."""
    def cannot_write(self, cutoff):
        raise sqlite3.OperationalError("attempt to write a readonly database")

    monkeypatch.setattr(AiStore, "delete_live_traces_before", cannot_write)

    client = TestClient(create_app(dataclasses.replace(settings, ai_db_path=tmp_path / "ai.db"),
                                   assistant_client=ScriptedModel([Completion(text="Answered.")])))

    assert client.post("/api/assistant/chat", json={"question": "Q", "view": {}}).status_code == 200
    health = client.get("/api/health").json()
    assert health["tracing"] == "degraded"
    assert "readonly" in health["tracing_error"]
