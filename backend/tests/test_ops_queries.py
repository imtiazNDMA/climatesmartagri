import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from seed_ops_store import seed  # noqa: E402

from csa_portal.ai.ops import OpsQueries  # noqa: E402
from csa_portal.ai.store import AiStore  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def seeded(tmp_path):
    store = AiStore(tmp_path / "ai.db")
    ids = seed(store, NOW)
    return OpsQueries(store, now=lambda: NOW), ids


def test_traces_come_newest_first_with_their_summary_fields(seeded):
    ops, ids = seeded

    page = ops.traces()

    assert len(page["traces"]) == 10 and page["next"] is None
    first = page["traces"][0]
    assert first["id"] == ids["live"][0]
    assert (first["source"], first["status"], first["duration_ms"], first["input_tokens"]) == ("live", "ok", 8000.0, 300)
    assert first["started_at"] == "2026-10-16T11:00:00+00:00"
    assert set(first) == {"id", "source", "agent", "model", "started_at", "duration_ms", "status", "error_reason",
                          "input_tokens", "output_tokens", "eval_run_id"}


def test_traces_filter_by_source_status_and_agent(seeded):
    ops, _ = seeded

    assert len(ops.traces(source="live")["traces"]) == 6
    assert len(ops.traces(source="eval")["traces"]) == 4
    errors = ops.traces(status="error")["traces"]
    assert [t["error_reason"] for t in errors] == ["tool-limit", "assistant-unavailable"]
    assert ops.traces(agent="nobody")["traces"] == []


def test_paging_with_the_cursor_visits_every_trace_once(seeded):
    ops, _ = seeded
    seen, cursor = [], None
    while True:
        page = ops.traces(limit=3, before=cursor)
        seen += [t["id"] for t in page["traces"]]
        cursor = page["next"]
        if cursor is None:
            break

    assert seen == [t["id"] for t in ops.traces()["traces"]]
    assert len(set(seen)) == 10


def test_paging_does_not_skip_traces_that_started_at_the_same_moment(tmp_path):
    from csa_portal.ai.store import TraceRecord

    store = AiStore(tmp_path / "ai.db")
    for n in range(4):
        store.write_trace(TraceRecord(f"{n:032d}", "live", "assistant", "qwen", NOW, 1.0, "ok", None, None, None,
                                      "f" * 64, None, None))
    ops = OpsQueries(store, now=lambda: NOW)

    first = ops.traces(limit=2)
    second = ops.traces(limit=2, before=first["next"])

    assert [t["id"] for t in first["traces"] + second["traces"]] == [f"{n:032d}" for n in (3, 2, 1, 0)]


def test_a_trace_comes_with_its_spans_in_start_order(seeded):
    ops, ids = seeded

    trace = ops.trace(ids["live"][0])

    assert [(s["kind"], s["name"]) for s in trace["spans"]] == [
        ("agent", "assistant"), ("llm", "chat qwen/qwen3.8-27b"), ("tool", "find_place"), ("tool", "get_section_facts"),
    ]
    assert trace["spans"][2]["parent_id"] == trace["spans"][0]["id"]
    assert (trace["question_text"], trace["answer_text"]) == (None, None)
    assert ops.trace("x" * 32) is None
