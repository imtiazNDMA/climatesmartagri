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
