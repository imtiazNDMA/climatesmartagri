import dataclasses
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from csa_portal.ai.store import SCHEMA_VERSION, AiStore, SpanRecord, StoreError, TraceRecord

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def trace(trace_id: str = "a" * 32, *, source: str = "live", started_at: datetime = NOW) -> TraceRecord:
    return TraceRecord(
        id=trace_id, source=source, agent="assistant", model="qwen", started_at=started_at, duration_ms=1200.5,
        status="ok", error_reason=None, input_tokens=310, output_tokens=42, question_hash="f" * 64,
        question_text=None, answer_text=None,
        # Span ids are unique across the whole store, so they are made from the trace's id.
        spans=[
            SpanRecord(trace_id[:15] + "2", trace_id, trace_id[:15] + "1", "llm", "chat qwen", started_at + timedelta(milliseconds=5),
                       900.0, "ok", {"gen_ai.request.model": "qwen", "gen_ai.usage.input_tokens": 310}),
            SpanRecord(trace_id[:15] + "1", trace_id, None, "agent", "assistant", started_at, 1190.0, "ok",
                       {"gen_ai.agent.name": "assistant"}),
        ],
    )


def test_a_trace_and_its_spans_come_back_as_written_with_spans_in_start_order(tmp_path):
    store = AiStore(tmp_path / "ai.db")
    store.write_trace(trace())

    back = store.get_trace("a" * 32)

    assert back == dataclasses.replace(trace(), spans=sorted(trace().spans, key=lambda s: s.started_at))
    assert [span.kind for span in back.spans] == ["agent", "llm"]
    assert back.spans[1].attributes == {"gen_ai.request.model": "qwen", "gen_ai.usage.input_tokens": 310}
    assert store.get_trace("b" * 32) is None


def test_a_new_file_is_migrated_once_and_reopening_keeps_what_was_written(tmp_path):
    path = tmp_path / "ai.db"
    AiStore(path).write_trace(trace())

    reopened = AiStore(path)

    assert reopened.get_trace("a" * 32) is not None
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version FROM schema_version").fetchall() == [(SCHEMA_VERSION,)]
        assert db.execute("PRAGMA journal_mode").fetchone() == ("wal",)


def test_a_database_newer_than_the_code_is_refused_with_a_clear_message(tmp_path):
    path = tmp_path / "ai.db"
    AiStore(path).close()
    with sqlite3.connect(path) as db:
        db.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))

    with pytest.raises(StoreError, match="newer than this code"):
        AiStore(path)


def test_old_live_traces_are_deleted_with_their_spans_and_evaluation_traces_are_kept(tmp_path):
    store = AiStore(tmp_path / "ai.db")
    store.write_trace(trace("a" * 32, started_at=NOW - timedelta(days=40)))
    store.write_trace(trace("b" * 32, started_at=NOW - timedelta(days=1)))
    store.write_trace(trace("c" * 32, source="eval", started_at=NOW - timedelta(days=40)))

    deleted = store.delete_live_traces_before(NOW - timedelta(days=30))

    assert deleted == 1
    assert store.get_trace("a" * 32) is None
    assert store.get_trace("b" * 32) is not None
    assert store.get_trace("c" * 32) is not None
    with sqlite3.connect(tmp_path / "ai.db") as db:
        assert db.execute("SELECT COUNT(*) FROM spans WHERE trace_id = ?", ("a" * 32,)).fetchone() == (0,)


def test_times_on_either_side_of_a_whole_second_compare_correctly(tmp_path):
    """Stored times always carry microseconds, so they sort as text the way they sort as times."""
    store = AiStore(tmp_path / "ai.db")
    store.write_trace(trace("a" * 32, started_at=NOW))
    store.write_trace(trace("b" * 32, started_at=NOW + timedelta(microseconds=500)))

    assert store.delete_live_traces_before(NOW + timedelta(microseconds=1)) == 1
    assert store.get_trace("b" * 32) is not None
