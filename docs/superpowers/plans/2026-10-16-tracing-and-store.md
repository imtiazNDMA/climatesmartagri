# Tracing and the AI Store Implementation Plan (#29)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every assistant answer leaves a trace of spans (agent, llm, tool) in SQLite, the chat response carries its `trace_id`, and a configurable concurrency limit replaces the global lock.

**Architecture:** `ai/store.py` owns the SQLite file: migrations, writing a whole trace in one transaction, reading one back, deleting old live traces. `ai/tracing.py` keeps the current trace and span in `contextvars`; `span(...)` is a free function that any code (the agent loop, the traced model) calls, and it does nothing when no trace is being recorded. A `Tracer` starts traces and hands each finished one to the store and, optionally, to `ai/otlp.py`, which sends it to an OpenTelemetry collector. The assistant opens one trace per question; `main.py` builds the tracer from settings and reports its state in `/api/health`.

**Tech Stack:** Python 3.13 standard library (`sqlite3`, `contextvars`, `urllib`), FastAPI, pydantic v2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-16-ai-platform-core-design.md` (Tracing, Store, Architecture: Concurrency, Error handling; Rollout step 2)

## Global Constraints

- No new dependencies. OTLP export is JSON over `urllib`, not the OpenTelemetry SDK.
- Span attribute names follow OpenTelemetry GenAI: `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.agent.name`. Portal-specific attributes start with `csa.`.
- Span kinds are exactly `agent`, `llm`, `tool`, `workflow`. Span and trace status are `ok` or `error`. Trace source is `live` or `eval`.
- Trace ids are 32 lowercase hex characters and span ids 16 (OpenTelemetry sizes).
- `traces` and `spans` columns are exactly as the spec's Store table lists them (no `eval_runs`, `eval_results` or `labels` yet; those are #30 and #31).
- Question and answer text are stored only when `CSA_TRACE_CONTENT=1`; otherwise only `question_hash`, the SHA-256 hex of the question.
- Tool arguments are never stored or exported, only their names (the existing logging rule).
- A failed store write never fails an answer: it is logged as a warning, counted, and `/api/health` reports `tracing: degraded`.
- Settings: `CSA_AI_DB` (default `backend/ai.db`), `CSA_TRACE_CONTENT` (default off), `CSA_TRACE_RETENTION_DAYS` (default 30), `CSA_AI_CONCURRENCY` (default 1), `CSA_AI_QUEUE_SECONDS` (default 5), `CSA_OTLP_ENDPOINT` (default empty, off).
- `POST /api/assistant/chat` keeps every field it returns today and adds `trace_id`. The 429 reason stays `assistant-busy` with the message "The local AI model is answering another question".
- Settings built directly in tests (the `settings` fixture) have no AI database, so the test suite never writes to `backend/ai.db`.

## Review Focus

1. **Two readers ask at once with the default concurrency of 1.** Expect the second to wait up to `CSA_AI_QUEUE_SECONDS`, then get 429 `assistant-busy`, and with a concurrency of 2 both to be answered. Tests in Task 5.
2. **Two requests are traced at the same time in different threads.** Expect each trace to hold only its own spans. Test in Task 2.
3. **Code that opens spans runs with no trace** (the evaluation script, unit tests of the agent). Expect nothing to be recorded and nothing to fail. Test in Task 2.
4. **The database cannot be written** (locked, disk full, read-only). Expect the answer to be returned, the failure counted and `/api/health` to say `degraded`. Tests in Task 2 and Task 5.
5. **The model fails mid-answer** (LM Studio stopped). Expect the reader to get the same 503 as today and the trace to be stored with status `error` and reason `assistant-unavailable`. Test in Task 5.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `backend/csa_portal/ai/store.py` | `SpanRecord`, `TraceRecord`, `StoreError`, `AiStore` (migrations, write, read, retention) |
| `backend/csa_portal/ai/tracing.py` | `span()`, `Span`, `ActiveTrace`, `Tracer`, `TracedModel`, `traced()` |
| `backend/csa_portal/ai/otlp.py` | `otlp_body()`, `OtlpExporter` |
| `backend/csa_portal/ai/model.py` | `Completion` gains token counts; `LmStudioModel.complete` reads `usage` |
| `backend/csa_portal/ai/agent.py` | `agent` and `tool` spans around the loop |
| `backend/csa_portal/ai/agents/assistant.py` | one trace per question, `trace_id`, semaphore |
| `backend/csa_portal/settings.py` | the six settings |
| `backend/csa_portal/main.py` | `_build_tracer`, retention at startup, health fields, `tracer` parameter |
| `.gitignore`, `.env.example` | the database file; the new settings |
| `backend/tests/test_ai_store.py`, `test_tracing.py`, `test_otlp.py`, `test_assistant_tracing.py` | new tests |
| `backend/tests/test_ai_model.py`, `test_agent.py` | added tests |

---

### Task 0: Branch

**Files:** none changed.

- [ ] **Step 1: Branch from #28**

PR #35 (#28) may not be merged yet; branch from its head either way.

```bash
git fetch origin
git switch -c feat/29-tracing origin/feat/28-agent-runtime
```

- [ ] **Step 2: Confirm the suite is green before starting**

Run: `uv run pytest -q`
Expected: all pass (317 at the time of writing).

---

### Task 1: The AI store

**Files:**
- Create: `backend/csa_portal/ai/store.py`
- Test: `backend/tests/test_ai_store.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class SpanRecord: id: str; trace_id: str; parent_id: str | None; kind: str; name: str; started_at: datetime; duration_ms: float; status: str; attributes: dict[str, Any] = {}`
  - `@dataclass(frozen=True) class TraceRecord: id: str; source: str; agent: str; model: str; started_at: datetime; duration_ms: float; status: str; error_reason: str | None; input_tokens: int | None; output_tokens: int | None; question_hash: str; question_text: str | None; answer_text: str | None; eval_run_id: str | None = None; spans: list[SpanRecord] = []`
  - `class StoreError(Exception)`
  - `SCHEMA_VERSION = 1`
  - `class AiStore(path: Path)` with `write_trace(trace: TraceRecord) -> None`, `get_trace(trace_id: str) -> TraceRecord | None` (spans in start order), `delete_live_traces_before(cutoff: datetime) -> int`, `close() -> None`. The constructor raises `StoreError` when the file's schema version is newer than `SCHEMA_VERSION`.
  - All datetimes are timezone-aware UTC.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_ai_store.py`:

```python
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
        spans=[
            SpanRecord("2" * 16, trace_id, "1" * 16, "llm", "chat qwen", started_at + timedelta(milliseconds=5),
                       900.0, "ok", {"gen_ai.request.model": "qwen", "gen_ai.usage.input_tokens": 310}),
            SpanRecord("1" * 16, trace_id, None, "agent", "assistant", started_at, 1190.0, "ok",
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
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_ai_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.ai.store'`.

- [ ] **Step 3: Write the store**

`backend/csa_portal/ai/store.py`:

```python
"""The AI store: traces and their spans in one SQLite file, for monitoring and evaluation (CSA_AI_DB)."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# Migration N takes the database from version N-1 to N. Never change one that has shipped; add the next.
MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE traces (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            agent TEXT NOT NULL,
            model TEXT NOT NULL,
            started_at TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            status TEXT NOT NULL,
            error_reason TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            question_hash TEXT NOT NULL,
            question_text TEXT,
            answer_text TEXT,
            eval_run_id TEXT
        );
        CREATE INDEX traces_started_at ON traces (started_at);
        CREATE TABLE spans (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL REFERENCES traces (id),
            parent_id TEXT,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            status TEXT NOT NULL,
            attributes TEXT NOT NULL
        );
        CREATE INDEX spans_trace_id ON spans (trace_id);
    """,
}

_TRACE_COLUMNS = (
    "id, source, agent, model, started_at, duration_ms, status, error_reason, input_tokens, output_tokens, "
    "question_hash, question_text, answer_text, eval_run_id"
)
_SPAN_COLUMNS = "id, trace_id, parent_id, kind, name, started_at, duration_ms, status, attributes"


class StoreError(Exception):
    """The AI store cannot be used, with a message that says why and what to do."""


@dataclass(frozen=True)
class SpanRecord:
    id: str
    trace_id: str
    parent_id: str | None
    kind: str
    name: str
    started_at: datetime
    duration_ms: float
    status: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceRecord:
    id: str
    source: str
    agent: str
    model: str
    started_at: datetime
    duration_ms: float
    status: str
    error_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    question_hash: str
    question_text: str | None
    answer_text: str | None
    eval_run_id: str | None = None
    spans: list[SpanRecord] = field(default_factory=list)


class AiStore:
    """One SQLite connection in WAL mode; writes are serialised by a lock, one transaction per trace."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        try:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._migrate()
        except BaseException:
            self._db.close()
            raise

    def _migrate(self) -> None:
        with self._db:
            self._db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self._db.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._db.execute("INSERT INTO schema_version (version) VALUES (0)")
        version = 0 if row is None else int(row[0])
        if version > SCHEMA_VERSION:
            raise StoreError(
                f"{self.path} is at schema version {version}, newer than this code ({SCHEMA_VERSION}). "
                "Update the portal, or point CSA_AI_DB at another file."
            )
        for target in range(version + 1, SCHEMA_VERSION + 1):
            self._db.executescript(
                f"BEGIN;\n{MIGRATIONS[target]}\nUPDATE schema_version SET version = {target};\nCOMMIT;"
            )

    def write_trace(self, trace: TraceRecord) -> None:
        with self._lock, self._db:
            self._db.execute(
                f"INSERT INTO traces ({_TRACE_COLUMNS}) VALUES ({', '.join('?' * 14)})",
                (
                    trace.id, trace.source, trace.agent, trace.model, _stamp(trace.started_at), trace.duration_ms,
                    trace.status, trace.error_reason, trace.input_tokens, trace.output_tokens, trace.question_hash,
                    trace.question_text, trace.answer_text, trace.eval_run_id,
                ),
            )
            self._db.executemany(
                f"INSERT INTO spans ({_SPAN_COLUMNS}) VALUES ({', '.join('?' * 9)})",
                [
                    (
                        span.id, span.trace_id, span.parent_id, span.kind, span.name, _stamp(span.started_at),
                        span.duration_ms, span.status, json.dumps(span.attributes, ensure_ascii=False),
                    )
                    for span in trace.spans
                ],
            )

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        with self._lock:
            row = self._db.execute(f"SELECT {_TRACE_COLUMNS} FROM traces WHERE id = ?", (trace_id,)).fetchone()
            if row is None:
                return None
            spans = self._db.execute(
                f"SELECT {_SPAN_COLUMNS} FROM spans WHERE trace_id = ? ORDER BY started_at, id", (trace_id,)
            ).fetchall()
        return TraceRecord(
            id=row[0], source=row[1], agent=row[2], model=row[3], started_at=_time(row[4]), duration_ms=row[5],
            status=row[6], error_reason=row[7], input_tokens=row[8], output_tokens=row[9], question_hash=row[10],
            question_text=row[11], answer_text=row[12], eval_run_id=row[13],
            spans=[
                SpanRecord(s[0], s[1], s[2], s[3], s[4], _time(s[5]), s[6], s[7], json.loads(s[8])) for s in spans
            ],
        )

    def delete_live_traces_before(self, cutoff: datetime) -> int:
        """Delete live traces that started before `cutoff`, with their spans; evaluation traces are kept."""
        old = "SELECT id FROM traces WHERE source = 'live' AND started_at < ?"
        with self._lock, self._db:
            self._db.execute(f"DELETE FROM spans WHERE trace_id IN ({old})", (_stamp(cutoff),))
            return self._db.execute(
                "DELETE FROM traces WHERE source = 'live' AND started_at < ?", (_stamp(cutoff),)
            ).rowcount

    def close(self) -> None:
        self._db.close()


def _stamp(moment: datetime) -> str:
    # Always with microseconds, so stored times sort as text in the order they sort as times.
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _time(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests/test_ai_store.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/csa_portal/ai/store.py backend/tests/test_ai_store.py
git commit -m "feat: AI store for traces and spans in SQLite with migrations and retention (#29)"
```

---

### Task 2: Traces and spans

**Files:**
- Create: `backend/csa_portal/ai/tracing.py`
- Test: `backend/tests/test_tracing.py`

**Interfaces:**
- Consumes: `SpanRecord`, `TraceRecord` (Task 1).
- Produces:
  - `span(kind: Literal["agent", "llm", "tool", "workflow"], name: str, **attributes) -> ContextManager[Span | NoSpan]`. Outside a trace it yields a `NoSpan` that accepts `set(**attributes)` and `fail()` and keeps nothing. An exception inside marks the span `error` and is re-raised.
  - `class Span` with `id: str`, `set(**attributes) -> None`, `fail() -> None`.
  - `class ActiveTrace` with `id: str` and `answered(text: str) -> None`.
  - `class TraceSink(Protocol): def write_trace(self, trace: TraceRecord) -> None`
  - `class Tracer(sink: TraceSink | None = None, *, capture_content: bool = False, exporter: TraceSink | None = None, unavailable: str | None = None)` with `trace(agent: str, *, model: str, question: str, source: str = "live", eval_run_id: str | None = None) -> ContextManager[ActiveTrace]`, `failures: int`, `unavailable: str | None`, and `status -> "off" | "ok" | "degraded"`.
  - The trace's `error_reason` is the exception's `reason` attribute when it has one, else its class name.
  - The trace's token counts are the sums of `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` over its `llm` spans, or `None` when no span has them.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_tracing.py`:

```python
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
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.ai.tracing'`.

- [ ] **Step 3: Write the tracer**

`backend/csa_portal/ai/tracing.py`:

```python
"""Tracing: every AI answer leaves a trace of spans (agent, llm, tool, workflow) named after OpenTelemetry GenAI.

`span()` can be called from anywhere. It records into the trace the current request is answering, and does
nothing when there is none, so code that opens spans also runs untraced (tests, the evaluation script).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from .store import SpanRecord, TraceRecord

logger = logging.getLogger("uvicorn.error")

SpanKind = Literal["agent", "llm", "tool", "workflow"]
_TOKEN_ATTRIBUTES = ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens")


class TraceSink(Protocol):
    def write_trace(self, trace: TraceRecord) -> None: ...


class Span:
    """A span being recorded. `set` adds attributes; `fail` marks it as an error."""

    def __init__(self, trace_id: str, parent_id: str | None, kind: SpanKind, name: str, attributes: dict[str, Any]) -> None:
        self.id = secrets.token_hex(8)
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.kind = kind
        self.name = name
        self.attributes = dict(attributes)
        self.status = "ok"
        self.started_at = datetime.now(UTC)
        self.duration_ms = 0.0
        self._started = time.perf_counter()

    def set(self, **attributes: Any) -> None:
        self.attributes.update(attributes)

    def fail(self) -> None:
        self.status = "error"

    def finish(self) -> None:
        self.duration_ms = (time.perf_counter() - self._started) * 1000

    def record(self) -> SpanRecord:
        return SpanRecord(
            self.id, self.trace_id, self.parent_id, self.kind, self.name, self.started_at, self.duration_ms,
            self.status, dict(self.attributes),
        )


class NoSpan:
    """What `span` gives when no trace is being recorded: it accepts everything and keeps nothing."""

    id = None

    def set(self, **attributes: Any) -> None:
        pass

    def fail(self) -> None:
        pass


_NO_SPAN = NoSpan()


class ActiveTrace:
    """The trace one request is recording."""

    def __init__(self, agent: str, model: str, question: str, source: str, eval_run_id: str | None) -> None:
        self.id = secrets.token_hex(16)
        self.agent = agent
        self.model = model
        self.question = question
        self.source = source
        self.eval_run_id = eval_run_id
        self.answer: str | None = None
        self.status = "ok"
        self.error_reason: str | None = None
        self.spans: list[Span] = []
        self.started_at = datetime.now(UTC)
        self._started = time.perf_counter()

    def answered(self, text: str) -> None:
        self.answer = text

    def record(self, capture_content: bool) -> TraceRecord:
        llm = [s for s in self.spans if s.kind == "llm"]
        tokens = [_total(llm, name) for name in _TOKEN_ATTRIBUTES]
        return TraceRecord(
            id=self.id, source=self.source, agent=self.agent, model=self.model, started_at=self.started_at,
            duration_ms=(time.perf_counter() - self._started) * 1000, status=self.status,
            error_reason=self.error_reason, input_tokens=tokens[0], output_tokens=tokens[1],
            question_hash=hashlib.sha256(self.question.encode("utf-8")).hexdigest(),
            question_text=self.question if capture_content else None,
            answer_text=self.answer if capture_content else None,
            eval_run_id=self.eval_run_id, spans=[s.record() for s in self.spans],
        )


_trace: ContextVar[ActiveTrace | None] = ContextVar("csa_trace", default=None)
_span: ContextVar[Span | None] = ContextVar("csa_span", default=None)


@contextmanager
def span(kind: SpanKind, name: str, **attributes: Any) -> Iterator[Span | NoSpan]:
    active = _trace.get()
    if active is None:
        yield _NO_SPAN
        return
    parent = _span.get()
    current = Span(active.id, parent.id if parent else None, kind, name, attributes)
    active.spans.append(current)
    token = _span.set(current)
    try:
        yield current
    except BaseException:
        current.fail()
        raise
    finally:
        _span.reset(token)
        current.finish()


class Tracer:
    """Starts traces and hands each finished one to the store and the exporter.

    A store that cannot write never fails an answer: the failure is logged and counted, and `status` turns
    `degraded`. `unavailable` says why there is no store at all when one was configured.
    """

    def __init__(
        self,
        sink: TraceSink | None = None,
        *,
        capture_content: bool = False,
        exporter: TraceSink | None = None,
        unavailable: str | None = None,
    ) -> None:
        self.sink = sink
        self.capture_content = capture_content
        self.exporter = exporter
        self.unavailable = unavailable
        self.failures = 0
        self._lock = threading.Lock()

    @property
    def status(self) -> str:
        if self.unavailable or self.failures:
            return "degraded"
        return "off" if self.sink is None else "ok"

    @contextmanager
    def trace(
        self, agent: str, *, model: str, question: str, source: str = "live", eval_run_id: str | None = None
    ) -> Iterator[ActiveTrace]:
        active = ActiveTrace(agent, model, question, source, eval_run_id)
        trace_token = _trace.set(active)
        span_token = _span.set(None)
        try:
            yield active
        except BaseException as error:
            active.status = "error"
            active.error_reason = getattr(error, "reason", None) or type(error).__name__
            raise
        finally:
            _span.reset(span_token)
            _trace.reset(trace_token)
            self._finish(active.record(self.capture_content))

    def _finish(self, record: TraceRecord) -> None:
        if self.sink is not None:
            try:
                self.sink.write_trace(record)
            except Exception:
                with self._lock:
                    self.failures += 1
                logger.warning("Trace %s could not be stored", record.id, exc_info=True)
        if self.exporter is not None:
            self.exporter.write_trace(record)


def _total(spans: list[Span], attribute: str) -> int | None:
    values = [s.attributes[attribute] for s in spans if isinstance(s.attributes.get(attribute), int)]
    return sum(values) if values else None
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests/test_tracing.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/csa_portal/ai/tracing.py backend/tests/test_tracing.py
git commit -m "feat: traces and nested spans kept per request with contextvars (#29)"
```

---

### Task 3: Token counts, the traced model and agent spans

**Files:**
- Modify: `backend/csa_portal/ai/model.py` (`Completion`, `LmStudioModel.complete`)
- Modify: `backend/csa_portal/ai/tracing.py` (add `TracedModel`, `traced`)
- Modify: `backend/csa_portal/ai/agent.py` (`Agent.run`)
- Test: `backend/tests/test_ai_model.py`, `backend/tests/test_tracing.py`, `backend/tests/test_agent.py`

**Interfaces:**
- Consumes: `span`, `Tracer` (Task 2).
- Produces:
  - `Completion` gains `input_tokens: int | None = None` and `output_tokens: int | None = None`, read by `LmStudioModel.complete` from the response's `usage.prompt_tokens` / `usage.completion_tokens`.
  - `traced(model: Any, model_name: str) -> Any`: a wrapper that opens an `llm` span named `chat <model_name>` around every `complete` and `chat` call, with `gen_ai.operation.name = "chat"`, `gen_ai.request.model`, the usage attributes when the reply has them, and `csa.tool_calls`. A model with no `complete` method gets a wrapper with no `complete` method, so the agent's chat-only path still applies. `stream` is passed through untraced (streaming is traced with #6).
  - `Agent.run` opens an `agent` span (`gen_ai.operation.name = "invoke_agent"`, `gen_ai.agent.name`, and at the end `csa.tool_calls`) and one `tool` span per call (`gen_ai.operation.name = "execute_tool"`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `csa.tool.argument_names` as a comma-separated string, `csa.facts`), failed when the tool's result has an `error`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_ai_model.py`:

```python
def test_lm_studio_token_counts_come_from_the_response_usage():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from csa_portal.ai.model import LmStudioModel

    replies = [
        {"choices": [{"message": {"content": "Answer"}}], "usage": {"prompt_tokens": 312, "completion_tokens": 41}},
        {"choices": [{"message": {"content": "Answer"}}]},
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps(replies.pop(0)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        model = LmStudioModel(f"http://127.0.0.1:{server.server_port}", "qwen-test", timeout=2)
        with_usage = model.complete([{"role": "user", "content": "Q"}])
        without_usage = model.complete([{"role": "user", "content": "Q"}])
    finally:
        server.shutdown()

    assert (with_usage.input_tokens, with_usage.output_tokens) == (312, 41)
    assert (without_usage.input_tokens, without_usage.output_tokens) == (None, None)
```

Append to `backend/tests/test_tracing.py`:

```python
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
```

Append to `backend/tests/test_agent.py`:

```python
def test_a_traced_run_records_the_agent_its_model_calls_and_its_tools():
    from csa_portal.ai.tracing import Tracer, traced

    class Sink:
        traces = []

        def write_trace(self, trace):
            self.traces.append(trace)

    sink = Sink()
    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("a", "lookup", {"place_id": "PK101"}), ToolCall("b", "lookup", {"place_id": "nowhere"})]),
        Completion(text="District One has 175."),
    ])
    agent = agent_for(model)
    agent.model = traced(model, "qwen")
    with Tracer(sink).trace("assistant", model="qwen", question="Q"):
        agent.run(QUESTION)

    spans = sink.traces[0].spans
    root = spans[0]
    assert (root.kind, root.name, root.parent_id) == ("agent", "assistant", None)
    assert root.attributes == {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "assistant", "csa.tool_calls": 2}
    assert [(s.kind, s.parent_id) for s in spans[1:]] == [("llm", root.id), ("tool", root.id), ("tool", root.id), ("llm", root.id)]
    found, missing = spans[2], spans[3]
    assert found.attributes == {
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "lookup", "gen_ai.tool.call.id": "a",
        "csa.tool.argument_names": "place_id", "csa.facts": 1,
    }
    assert (found.status, missing.status) == ("ok", "error")
    assert "PK101" not in str(found.attributes)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_ai_model.py backend/tests/test_tracing.py backend/tests/test_agent.py -q`
Expected: 4 FAIL: the usage test with `AttributeError: 'Completion' object has no attribute 'input_tokens'`, the two tracing tests with `ImportError: cannot import name 'traced'`, and the agent test with `ImportError: cannot import name 'traced'`.

- [ ] **Step 3: Read token counts in the model seam**

In `backend/csa_portal/ai/model.py`, change `Completion` to:

```python
@dataclass(frozen=True)
class Completion:
    """What the model gave back: words, tool calls to run before it can answer, or an object of the asked shape.
    Token counts are the server's own, when it reports them."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    data: Any = None
    input_tokens: int | None = None
    output_tokens: int | None = None
```

In `LmStudioModel.complete`, replace

```python
        message = self._message(self._post(payload))
        calls = [_tool_call(call) for call in message.get("tool_calls") or []]
        content = message.get("content")
        text = content.strip() if isinstance(content, str) and content.strip() else None
        return Completion(text=text, tool_calls=calls)
```

with

```python
        body = self._post(payload)
        message = self._message(body)
        calls = [_tool_call(call) for call in message.get("tool_calls") or []]
        content = message.get("content")
        text = content.strip() if isinstance(content, str) and content.strip() else None
        return Completion(text=text, tool_calls=calls, **_token_counts(body))
```

and add this function after `_tool_call`:

```python
def _token_counts(body: Any) -> dict[str, int]:
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return {}
    counts = {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}
    return {name: value for name, value in counts.items() if isinstance(value, int)}
```

- [ ] **Step 4: Add the traced model**

Append to `backend/csa_portal/ai/tracing.py`:

```python
class _TracedChat:
    """A model that can only chat, with each call an `llm` span."""

    def __init__(self, inner: Any, model_name: str) -> None:
        self.inner = inner
        self.model_name = model_name

    def _attributes(self) -> dict[str, Any]:
        return {"gen_ai.operation.name": "chat", "gen_ai.request.model": self.model_name}

    def chat(self, messages: list[dict[str, Any]]) -> str:
        with span("llm", f"chat {self.model_name}", **self._attributes()):
            return self.inner.chat(messages)


class TracedModel(_TracedChat):
    """A language model whose every `complete` and `chat` call is an `llm` span with request and usage attributes."""

    def complete(self, messages: list[dict[str, Any]], tools: Any = None, output: Any = None) -> Any:
        with span("llm", f"chat {self.model_name}", **self._attributes()) as current:
            reply = (
                self.inner.complete(messages, tools=tools)
                if output is None
                else self.inner.complete(messages, tools=tools, output=output)
            )
            usage = {"gen_ai.usage.input_tokens": reply.input_tokens, "gen_ai.usage.output_tokens": reply.output_tokens}
            current.set(**{name: value for name, value in usage.items() if value is not None})
            current.set(**{"csa.tool_calls": len(reply.tool_calls)})
            return reply

    def stream(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        # Streaming is traced with #6; a span cannot safely stay open across a generator's yields here.
        return self.inner.stream(messages)


def traced(model: Any, model_name: str) -> Any:
    """`model` with its calls traced. A chat-only model stays chat-only, so callers can still tell."""
    return TracedModel(model, model_name) if hasattr(model, "complete") else _TracedChat(model, model_name)
```

- [ ] **Step 5: Open spans in the agent loop**

In `backend/csa_portal/ai/agent.py`, add `from .tracing import span` to the imports, and replace the whole `run` method with:

```python
    def run(self, messages: list[dict[str, Any]]) -> AgentResult:
        """Answer the conversation in `messages`; the system prompt is added here and `messages` is left as it was."""
        attributes = {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": self.name}
        with span("agent", self.name, **attributes) as agent_span:
            result = self._run(messages)
            agent_span.set(**{"csa.tool_calls": len(result.steps)})
            return result

    def _run(self, messages: list[dict[str, Any]]) -> AgentResult:
        conversation: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}, *messages]
        if not hasattr(self.model, "complete"):
            # A model that can only chat answers without tools.
            return AgentResult(self.model.chat(conversation))
        facts: list[Fact] = []
        steps: list[AgentStep] = []
        last = self.policy.max_rounds - 1
        for round_number in range(self.policy.max_rounds):
            reply = self.model.complete(conversation, tools=self.registry.tools if round_number < last else None)
            if reply.text:
                return AgentResult(reply.text, facts, steps)
            if not reply.tool_calls:
                raise ModelError(502, "bad-model-response", "The AI model returned neither an answer nor a tool call")
            if round_number == last:
                break
            conversation.append({
                "role": "assistant", "content": "", "tool_calls": [
                    {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}
                    for call in reply.tool_calls
                ],
            })
            for call in reply.tool_calls:
                with span("tool", call.name, **{
                    "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": call.name,
                    "gen_ai.tool.call.id": call.id, "csa.tool.argument_names": ",".join(sorted(call.arguments)),
                }) as tool_span:
                    output = self.registry.run(call)
                    tool_span.set(**{"csa.facts": len(output.facts)})
                    if "error" in output.result:
                        tool_span.fail()
                facts.extend(output.facts)
                steps.append(AgentStep(call.name, dict(call.arguments), output.result.get("error"), len(output.facts)))
                logger.info(
                    "%s fact tool %s argument_names=%s returned=%d facts",
                    self.name.capitalize(), call.name, sorted(call.arguments), len(output.facts),
                )
                conversation.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(output.result, ensure_ascii=True)}
                )
        raise ModelError(502, "tool-limit", f"The AI model did not answer within {self.policy.max_rounds} tool rounds")
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest -q`
Expected: all PASS (the 4 new tests included; every earlier agent and assistant test unchanged).

- [ ] **Step 7: Commit**

```bash
git add backend/csa_portal/ai/model.py backend/csa_portal/ai/tracing.py backend/csa_portal/ai/agent.py backend/tests/test_ai_model.py backend/tests/test_tracing.py backend/tests/test_agent.py
git commit -m "feat: llm, agent and tool spans with token usage from the model (#29)"
```

---

### Task 4: OTLP export

**Files:**
- Create: `backend/csa_portal/ai/otlp.py`
- Test: `backend/tests/test_otlp.py`

**Interfaces:**
- Consumes: `TraceRecord`, `SpanRecord` (Task 1); used as a `TraceSink` by `Tracer` (Task 2).
- Produces:
  - `otlp_body(trace: TraceRecord) -> dict[str, Any]`: an OTLP/HTTP JSON `ExportTraceServiceRequest`.
  - `class OtlpExporter(endpoint: str, timeout: float = 2.0)` with `url` (`<endpoint>/v1/traces`), `write_trace(trace)` (sends in a daemon thread) and `send(trace)` (sends now; logs a warning and returns on any network failure).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_otlp.py`:

```python
import json
import logging
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from csa_portal.ai.otlp import OtlpExporter, otlp_body
from csa_portal.ai.store import SpanRecord, TraceRecord

START = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TRACE = TraceRecord(
    id="a" * 32, source="live", agent="assistant", model="qwen", started_at=START, duration_ms=1000.0, status="error",
    error_reason="tool-limit", input_tokens=300, output_tokens=20, question_hash="f" * 64, question_text=None,
    answer_text=None,
    spans=[
        SpanRecord("1" * 16, "a" * 32, None, "agent", "assistant", START, 1000.0, "error", {"gen_ai.agent.name": "assistant"}),
        SpanRecord("2" * 16, "a" * 32, "1" * 16, "llm", "chat qwen", START, 250.5, "ok",
                   {"gen_ai.usage.input_tokens": 300, "csa.ratio": 0.5, "csa.cached": False}),
    ],
)


def test_a_trace_becomes_an_otlp_json_request_with_one_span_per_record():
    body = otlp_body(TRACE)

    resource = body["resourceSpans"][0]
    assert resource["resource"]["attributes"] == [{"key": "service.name", "value": {"stringValue": "csa-portal"}}]
    agent, llm = resource["scopeSpans"][0]["spans"]
    assert (agent["traceId"], agent["spanId"], agent["name"], agent["kind"]) == ("a" * 32, "1" * 16, "assistant", 1)
    assert "parentSpanId" not in agent
    assert agent["status"] == {"code": 2}
    assert (llm["parentSpanId"], llm["kind"], llm["status"]) == ("1" * 16, 3, {"code": 1})
    start = int(START.timestamp() * 1_000_000_000)
    assert (llm["startTimeUnixNano"], llm["endTimeUnixNano"]) == (str(start), str(start + 250_500_000))
    assert {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "300"}} in llm["attributes"]
    assert {"key": "csa.ratio", "value": {"doubleValue": 0.5}} in llm["attributes"]
    assert {"key": "csa.cached", "value": {"boolValue": False}} in llm["attributes"]
    assert {"key": "csa.span.kind", "value": {"stringValue": "llm"}} in llm["attributes"]


def test_a_trace_is_posted_to_the_collector():
    received = {}

    class Collector(BaseHTTPRequestHandler):
        def do_POST(self):
            received["path"] = self.path
            received["type"] = self.headers["Content-Type"]
            received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        OtlpExporter(f"http://127.0.0.1:{server.server_port}/").send(TRACE)
    finally:
        server.shutdown()

    assert (received["path"], received["type"]) == ("/v1/traces", "application/json")
    assert received["body"] == otlp_body(TRACE)


def test_an_unreachable_collector_is_logged_and_does_not_raise(caplog):
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        OtlpExporter("http://127.0.0.1:1", timeout=0.2).send(TRACE)

    assert any("could not be exported" in record.getMessage() for record in caplog.records)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_otlp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.ai.otlp'`.

- [ ] **Step 3: Write the exporter**

`backend/csa_portal/ai/otlp.py`:

```python
"""Sends finished traces to an OpenTelemetry collector as OTLP/HTTP JSON, when CSA_OTLP_ENDPOINT is set.

This lets Langfuse, Phoenix or any OTLP collector show the portal's traces without the portal depending on them.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from typing import Any

from .store import SpanRecord, TraceRecord

logger = logging.getLogger("uvicorn.error")

_SPAN_KIND_INTERNAL = 1
_SPAN_KIND_CLIENT = 3
_STATUS = {"ok": 1, "error": 2}


def otlp_body(trace: TraceRecord) -> dict[str, Any]:
    return {
        "resourceSpans": [{
            "resource": {"attributes": [_attribute("service.name", "csa-portal")]},
            "scopeSpans": [{"scope": {"name": "csa_portal.ai"}, "spans": [_span(span) for span in trace.spans]}],
        }],
    }


def _span(span: SpanRecord) -> dict[str, Any]:
    start = int(span.started_at.timestamp() * 1_000_000_000)
    body: dict[str, Any] = {
        "traceId": span.trace_id,
        "spanId": span.id,
        "name": span.name,
        "kind": _SPAN_KIND_CLIENT if span.kind == "llm" else _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + round(span.duration_ms * 1_000_000)),
        "attributes": [_attribute(key, value) for key, value in span.attributes.items()]
        + [_attribute("csa.span.kind", span.kind)],
        "status": {"code": _STATUS.get(span.status, 0)},
    }
    if span.parent_id:
        body["parentSpanId"] = span.parent_id
    return body


def _attribute(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        typed: dict[str, Any] = {"boolValue": value}
    elif isinstance(value, int):
        typed = {"intValue": str(value)}
    elif isinstance(value, float):
        typed = {"doubleValue": value}
    else:
        typed = {"stringValue": str(value)}
    return {"key": key, "value": typed}


class OtlpExporter:
    def __init__(self, endpoint: str, timeout: float = 2.0) -> None:
        self.url = endpoint.rstrip("/") + "/v1/traces"
        self.timeout = timeout

    def write_trace(self, trace: TraceRecord) -> None:
        # Sent out of the request's way: a slow or absent collector must not slow an answer.
        threading.Thread(target=self.send, args=(trace,), daemon=True).start()

    def send(self, trace: TraceRecord) -> None:
        request = urllib.request.Request(
            self.url, data=json.dumps(otlp_body(trace)).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=self.timeout).close()
        except (OSError, ValueError):
            logger.warning("Trace %s could not be exported to %s", trace.id, self.url, exc_info=True)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests/test_otlp.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/csa_portal/ai/otlp.py backend/tests/test_otlp.py
git commit -m "feat: optional OTLP/HTTP export of finished traces (#29)"
```

---

### Task 5: Settings, the assistant and the app

**Files:**
- Modify: `backend/csa_portal/settings.py`
- Modify: `backend/csa_portal/ai/agents/assistant.py` (`AssistantService.__init__`, `answer`)
- Modify: `backend/csa_portal/main.py` (imports, `_build_tracer`, `create_app`, `/api/health`)
- Modify: `.gitignore`, `.env.example`, `frontend/playwright.config.ts` (the e2e backend's `env`)
- Test: `backend/tests/test_assistant_tracing.py`

**Interfaces:**
- Consumes: `AiStore`, `StoreError` (Task 1); `Tracer` (Task 2); `traced` (Task 3); `OtlpExporter` (Task 4).
- Produces:
  - `Settings` fields `ai_db_path: Path | None = None`, `trace_content: bool = False`, `trace_retention_days: int = 30`, `ai_concurrency: int = 1`, `ai_queue_seconds: float = 5`, `otlp_endpoint: str = ""`. `Settings.from_env()` defaults `ai_db_path` to `backend/ai.db`; the dataclass default stays `None` so directly built settings have no database.
  - `AssistantService(..., tracer: Tracer | None = None, concurrency: int = 1, queue_seconds: float = 5)`; `answer` returns `trace_id`.
  - `create_app(..., tracer: Tracer | None = None)`; `/api/health` adds `tracing` (`off`/`ok`/`degraded`), `tracing_error` and `tracing_failures`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_assistant_tracing.py`:

```python
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
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_assistant_tracing.py -q`
Expected: FAIL, most with `TypeError: create_app() got an unexpected keyword argument 'tracer'`, the health test with `KeyError: 'tracing'`, and the settings test with `AttributeError: 'Settings' object has no attribute 'ai_db_path'`.

- [ ] **Step 3: Add the settings**

In `backend/csa_portal/settings.py`, add after `positive_float`:

```python
def positive_int(value: str, fallback: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


def optional_path(value: str) -> Path | None:
    """A path, or None for an empty value: an empty CSA_AI_DB turns the AI store off (the browser tests do this)."""
    return Path(value) if value else None
```

Add to the `Settings` fields, after `lm_studio_timeout: float = 60`:

```python
    # The AI store and tracing. Without a database (the default when built directly, as tests do) answers are
    # still traced in memory, but nothing is kept.
    ai_db_path: Path | None = None
    trace_content: bool = False
    trace_retention_days: int = 30
    ai_concurrency: int = 1
    ai_queue_seconds: float = 5
    otlp_endpoint: str = ""
```

Add to the `cls(...)` call in `_from`, after `lm_studio_timeout=...`:

```python
            ai_db_path=optional_path(environ.get("CSA_AI_DB", str(BACKEND_DIR / "ai.db"))),
            trace_content=environ.get("CSA_TRACE_CONTENT", "") == "1",
            trace_retention_days=positive_int(environ.get("CSA_TRACE_RETENTION_DAYS", "30"), 30),
            ai_concurrency=positive_int(environ.get("CSA_AI_CONCURRENCY", "1"), 1),
            ai_queue_seconds=positive_float(environ.get("CSA_AI_QUEUE_SECONDS", "5"), 5),
            otlp_endpoint=environ.get("CSA_OTLP_ENDPOINT", ""),
```

- [ ] **Step 4: One trace per question in the assistant**

In `backend/csa_portal/ai/agents/assistant.py`, add `from ..tracing import Tracer, traced` to the imports.

Add three keyword parameters to `AssistantService.__init__` after `local_model: bool = True,`:

```python
        tracer: Tracer | None = None,
        concurrency: int = 1,
        queue_seconds: float = 5,
```

In the body, replace

```python
        self._agent = Agent("assistant", SYSTEM_PROMPT, assistant_tools(facts), client)
        self._generation_lock = threading.Lock()
```

with

```python
        self.tracer = tracer or Tracer()
        self.queue_seconds = queue_seconds
        self._agent = Agent("assistant", SYSTEM_PROMPT, assistant_tools(facts), traced(client, model))
        # Questions the model may answer at once; a question waits up to queue_seconds for a slot.
        self._slots = threading.BoundedSemaphore(concurrency)
```

Rename the current `answer` method to `_answer`, give it a second parameter, and use the slots. Its first line changes from

```python
    def answer(self, request: AssistantChatRequest) -> dict[str, Any]:
```

to

```python
    def _answer(self, request: AssistantChatRequest, trace: Any) -> dict[str, Any]:
```

replace

```python
        if not self._generation_lock.acquire(blocking=False):
            raise AssistantError(429, "assistant-busy", "The local AI model is answering another question")
        try:
            result = self._agent.run(messages)
        finally:
            self._generation_lock.release()
```

with

```python
        if not self._slots.acquire(timeout=self.queue_seconds):
            raise AssistantError(429, "assistant-busy", "The local AI model is answering another question")
        try:
            result = self._agent.run(messages)
        finally:
            self._slots.release()
```

and in its returned dict, after `"tool_calls": tool_calls,` add `"trace_id": trace.id,`, and just before the `return` add `trace.answered(answer)`.

Then add the new `answer` above `_answer`:

```python
    def answer(self, request: AssistantChatRequest) -> dict[str, Any]:
        """Answer one question; every answer, and every failure to answer, leaves a trace."""
        with self.tracer.trace("assistant", model=self.model, question=request.question) as trace:
            return self._answer(request, trace)
```

- [ ] **Step 5: Build the tracer in the app and report it in health**

In `backend/csa_portal/main.py`, add to the standard-library imports at the top (beside `import functools` and `import logging`, before `use_bundled_proj` is imported):

```python
import sqlite3
from datetime import UTC, datetime, timedelta
```

and beside the other `.ai` imports (after `use_bundled_proj()` has run):

```python
from .ai.otlp import OtlpExporter  # noqa: E402
from .ai.store import AiStore, StoreError  # noqa: E402
from .ai.tracing import Tracer  # noqa: E402
```

Add this function above `create_app`:

```python
def _build_tracer(settings: Settings) -> Tracer:
    """The tracer the settings ask for. A store that cannot be opened leaves the portal answering without one."""
    exporter = OtlpExporter(settings.otlp_endpoint) if settings.otlp_endpoint else None
    if settings.ai_db_path is None:
        return Tracer(None, capture_content=settings.trace_content, exporter=exporter)
    try:
        store = AiStore(settings.ai_db_path)
    except (StoreError, sqlite3.Error, OSError) as err:
        logger.error("The AI store could not be opened; answering without traces: %s", err)
        return Tracer(None, capture_content=settings.trace_content, exporter=exporter, unavailable=str(err))
    cutoff = datetime.now(UTC) - timedelta(days=settings.trace_retention_days)
    removed = store.delete_live_traces_before(cutoff)
    if removed:
        logger.info("Deleted %d live traces older than %d days", removed, settings.trace_retention_days)
    return Tracer(store, capture_content=settings.trace_content, exporter=exporter)
```

Add the parameter `tracer: Tracer | None = None,` to `create_app` after `assistant_client: AssistantClient | None = None,`, and just after `settings = settings or Settings.from_env()` add:

```python
    tracer = tracer or _build_tracer(settings)
```

In the `AssistantService(...)` call, after `local_model=...,` add:

```python
            tracer=tracer,
            concurrency=settings.ai_concurrency,
            queue_seconds=settings.ai_queue_seconds,
```

In `health()`, after `"assistant_model": settings.lm_studio_model,` add:

```python
            "tracing": tracer.status,
            "tracing_error": tracer.unavailable,
            "tracing_failures": tracer.failures,
```

- [ ] **Step 6: Ignore the database and document the settings**

Append to `.gitignore`, after the `backend/forecast/` block:

```gitignore

# The AI store: traces and evaluation results (CSA_AI_DB), with SQLite's WAL files.
backend/ai.db*
```

Append to `.env.example`:

```bash

# AI store, tracing and limits
CSA_AI_DB=backend/ai.db
# 1 keeps question and answer text in traces; otherwise only a hash of the question.
CSA_TRACE_CONTENT=
CSA_TRACE_RETENTION_DAYS=30
CSA_AI_CONCURRENCY=1
CSA_AI_QUEUE_SECONDS=5
# Optional OpenTelemetry collector, e.g. http://127.0.0.1:4318
CSA_OTLP_ENDPOINT=
```

In `frontend/playwright.config.ts`, add to the backend server's `env` block, after `CSA_BASEMAP_STYLE_URL: 'https://basemap.test/style.json',`:

```ts
        // No AI store for browser tests: answers are traced in memory and nothing is written to backend/ai.db.
        CSA_AI_DB: '',
```

- [ ] **Step 7: Run every backend test**

Run: `uv run pytest -q`
Expected: all PASS, including `backend/tests/test_assistant.py` unedited.

- [ ] **Step 8: Run the full check and the browser tests**

Run: `npm run check` then `npm run test:e2e`
Expected: lint clean; all backend, frontend and browser tests pass. Then confirm nothing was written to the real database: `ls backend/ai.db* 2>/dev/null || echo "no ai.db"` prints `no ai.db`. If a file appears, the e2e backend's `CSA_AI_DB: ''` is missing; delete the file and fix the config.

- [ ] **Step 9: Commit**

```bash
git add backend/csa_portal backend/tests/test_assistant_tracing.py .gitignore .env.example frontend/playwright.config.ts
git commit -m "feat: trace every assistant answer, return its trace id, and limit concurrent answers (#29)"
```

---

### Task 6: Pull request

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin feat/29-tracing
gh pr create --base feat/28-agent-runtime --title "feat: tracing and the AI store" --body "Closes #29

> Stacked on #35. After #35 merges, change this PR's base to \`feat/portal-data\`.

- \`ai/store.py\`: traces and spans in SQLite (\`CSA_AI_DB\`), WAL mode, numbered migrations, a database newer than the code is refused with a clear message, live traces past \`CSA_TRACE_RETENTION_DAYS\` deleted at startup.
- \`ai/tracing.py\`: one trace per question with agent, llm and tool spans named after OpenTelemetry GenAI; tokens from the model's own usage counts.
- \`ai/otlp.py\`: optional OTLP/HTTP export when \`CSA_OTLP_ENDPOINT\` is set.
- \`POST /api/assistant/chat\` returns \`trace_id\`; question and answer text are kept only with \`CSA_TRACE_CONTENT=1\`.
- A store that cannot write never fails an answer; \`/api/health\` reports \`tracing\`, \`tracing_error\`, \`tracing_failures\`.
- \`CSA_AI_CONCURRENCY\` (default 1) and \`CSA_AI_QUEUE_SECONDS\` (default 5) replace the global lock. **Behaviour change:** with every slot busy, a question now waits up to 5 s before the 429, where before it got the 429 at once.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 2: Wait for CI**

Run: `gh pr checks --watch`
Expected: `quality` and `e2e` pass.
