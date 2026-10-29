import hashlib
import logging
import sqlite3
import threading

import pytest

from csa_portal.ai.model import ModelError
from csa_portal.ai.tracing import Tracer, span


class Sink:
    def __init__(self):
        self.traces = []

    def write_trace(self, trace):
        self.traces.append(trace)


def test_a_span_outside_any_trace_records_nothing_and_does_not_fail():
    with span("tool", "lookup", **{"gen_ai.tool.name": "lookup"}) as current:
        current.set(**{"csa.facts": 2})
        current.fail()


def test_spans_nest_under_the_span_they_were_opened_in():
    sink = Sink()
    with Tracer(sink).trace("assistant", model="qwen", question="Q") as active:
        with span("agent", "assistant") as agent:
            with span("llm", "chat qwen"):
                pass
            with span("tool", "lookup") as tool:
                tool.set(**{"gen_ai.tool.name": "lookup"})
        active.answered("A")

    [record] = sink.traces
    assert record.id == active.id and len(record.id) == 32
    assert [(s.kind, s.parent_id) for s in record.spans] == [("agent", None), ("llm", agent.id), ("tool", agent.id)]
    assert all(len(s.id) == 16 and s.trace_id == record.id and s.duration_ms >= 0 for s in record.spans)
    assert record.spans[2].attributes == {"gen_ai.tool.name": "lookup"}
    assert (record.status, record.error_reason, record.source, record.agent, record.model) == (
        "ok", None, "live", "assistant", "qwen",
    )


def test_an_exception_marks_its_span_and_trace_as_errors_and_still_stores_the_trace():
    sink = Sink()
    with pytest.raises(ModelError):
        with Tracer(sink).trace("assistant", model="qwen", question="Q"):
            with span("llm", "chat qwen"):
                raise ModelError(503, "assistant-unavailable", "The local AI model could not be reached")

    [record] = sink.traces
    assert (record.status, record.error_reason) == ("error", "assistant-unavailable")
    assert record.spans[0].status == "error"


def test_an_exception_without_a_reason_is_recorded_by_its_class_name():
    sink = Sink()
    with pytest.raises(KeyError):
        with Tracer(sink).trace("assistant", model="qwen", question="Q"):
            raise KeyError("x")

    assert sink.traces[0].error_reason == "KeyError"


def test_question_and_answer_text_are_kept_only_when_content_capture_is_on():
    question = "Where is frost worst?"
    for capture, expected in ((False, (None, None)), (True, (question, "In the north."))):
        sink = Sink()
        with Tracer(sink, capture_content=capture).trace("assistant", model="qwen", question=question) as active:
            active.answered("In the north.")
        record = sink.traces[0]
        assert record.question_hash == hashlib.sha256(question.encode("utf-8")).hexdigest()
        assert (record.question_text, record.answer_text) == expected


def test_tokens_are_summed_over_llm_spans_and_none_when_no_span_reports_them():
    sink = Sink()
    tracer = Tracer(sink)
    with tracer.trace("assistant", model="qwen", question="Q"):
        with span("llm", "chat qwen", **{"gen_ai.usage.input_tokens": 300, "gen_ai.usage.output_tokens": 10}):
            pass
        with span("llm", "chat qwen", **{"gen_ai.usage.input_tokens": 350, "gen_ai.usage.output_tokens": 40}):
            pass
    with tracer.trace("assistant", model="qwen", question="Q"):
        with span("tool", "lookup", **{"gen_ai.usage.input_tokens": 999}):
            pass

    assert (sink.traces[0].input_tokens, sink.traces[0].output_tokens) == (650, 50)
    assert (sink.traces[1].input_tokens, sink.traces[1].output_tokens) == (None, None)


def test_traces_recorded_at_the_same_time_in_two_threads_keep_their_own_spans():
    sink = Sink()
    tracer = Tracer(sink)
    both_inside = threading.Barrier(2)

    def answer(name):
        with tracer.trace("assistant", model="qwen", question=name):
            both_inside.wait()
            with span("tool", name):
                pass
            both_inside.wait()

    threads = [threading.Thread(target=answer, args=(name,)) for name in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted([s.name for s in record.spans] for record in sink.traces) == [["first"], ["second"]]


def test_a_store_that_cannot_write_is_counted_and_logged_and_the_answer_goes_on(caplog):
    class BrokenSink:
        def write_trace(self, trace):
            raise sqlite3.OperationalError("database is locked")

    tracer = Tracer(BrokenSink())
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        with tracer.trace("assistant", model="qwen", question="Q") as active:
            active.answered("Still answered.")

    assert tracer.failures == 1
    assert tracer.status == "degraded"
    assert any("could not be stored" in record.getMessage() for record in caplog.records)


def test_tracing_status_says_off_ok_or_degraded():
    assert Tracer().status == "off"
    assert Tracer(Sink()).status == "ok"
    assert Tracer(None, unavailable="ai.db is newer than this code").status == "degraded"


def test_finished_traces_also_go_to_the_exporter():
    sink, exporter = Sink(), Sink()
    with Tracer(sink, exporter=exporter).trace("assistant", model="qwen", question="Q"):
        pass

    assert [t.id for t in exporter.traces] == [t.id for t in sink.traces]


def test_a_traced_model_records_one_llm_span_per_call_with_its_usage():
    from csa_portal.ai.model import Completion, ScriptedModel, ToolCall
    from csa_portal.ai.tracing import traced

    sink = Sink()
    model = traced(ScriptedModel([
        Completion(tool_calls=[ToolCall("a", "lookup", {})], input_tokens=300, output_tokens=12),
        Completion(text="Done."),
    ]), "qwen")
    with Tracer(sink).trace("assistant", model="qwen", question="Q"):
        model.complete([{"role": "user", "content": "Q"}], tools=[])
        model.complete([{"role": "user", "content": "Q"}])

    first, second = sink.traces[0].spans
    assert (first.kind, first.name) == ("llm", "chat qwen")
    assert first.attributes == {
        "gen_ai.operation.name": "chat", "gen_ai.request.model": "qwen",
        "gen_ai.usage.input_tokens": 300, "gen_ai.usage.output_tokens": 12, "csa.tool_calls": 1,
    }
    assert "gen_ai.usage.input_tokens" not in second.attributes
    assert sink.traces[0].input_tokens == 300


def test_a_chat_only_model_stays_chat_only_when_traced():
    from csa_portal.ai.tracing import traced

    class ChatOnly:
        def chat(self, messages):
            return "Plain."

    model = traced(ChatOnly(), "fake")

    assert not hasattr(model, "complete")
    assert model.chat([]) == "Plain."


def test_an_exporter_that_cannot_send_is_counted_and_logged_and_the_answer_goes_on(caplog):
    class NoThreads:
        def write_trace(self, trace):
            raise RuntimeError("can't start new thread")

    sink = Sink()
    tracer = Tracer(sink, exporter=NoThreads())
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        with tracer.trace("assistant", model="qwen", question="Q") as active:
            active.answered("Still answered.")

    assert len(sink.traces) == 1
    assert (tracer.failures, tracer.status) == (1, "degraded")
    assert any("could not be exported" in record.getMessage() for record in caplog.records)


def test_evaluation_traces_keep_their_text_even_with_content_capture_off():
    sink = Sink()
    with Tracer(sink, capture_content=False).trace("assistant", model="qwen", question="Golden question", source="eval") as active:
        active.answered("Golden answer")

    assert (sink.traces[0].question_text, sink.traces[0].answer_text) == ("Golden question", "Golden answer")
