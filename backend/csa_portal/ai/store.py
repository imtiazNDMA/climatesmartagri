"""The AI store: traces and their spans in one SQLite file, for monitoring and evaluation (CSA_AI_DB)."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3

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
    2: """
        CREATE TABLE eval_runs (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            git_sha TEXT NOT NULL,
            dataset TEXT NOT NULL,
            dataset_version INTEGER NOT NULL,
            mode TEXT NOT NULL,
            model TEXT NOT NULL,
            judge_model TEXT,
            repeats INTEGER NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL
        );
        CREATE INDEX eval_runs_started_at ON eval_runs (started_at);
        CREATE TABLE eval_results (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES eval_runs (id),
            case_id TEXT NOT NULL,
            repeat INTEGER NOT NULL,
            trace_id TEXT,
            passed INTEGER NOT NULL,
            scores TEXT NOT NULL
        );
        CREATE INDEX eval_results_run_id ON eval_results (run_id);
    """,
    3: """
        CREATE TABLE labels (
            id TEXT PRIMARY KEY,
            result_id TEXT NOT NULL REFERENCES eval_results (id),
            labeller TEXT NOT NULL,
            faithful INTEGER NOT NULL,
            helpful INTEGER,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX labels_result_id ON labels (result_id);
    """,
}

_TRACE_COLUMNS = (
    "id, source, agent, model, started_at, duration_ms, status, error_reason, input_tokens, output_tokens, "
    "question_hash, question_text, answer_text, eval_run_id"
)
_SPAN_COLUMNS = "id, trace_id, parent_id, kind, name, started_at, duration_ms, status, attributes"
_RUN_COLUMNS = (
    "id, started_at, finished_at, git_sha, dataset, dataset_version, mode, model, judge_model, repeats, status, summary"
)
_RESULT_COLUMNS = "id, run_id, case_id, repeat, trace_id, passed, scores"


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


@dataclass(frozen=True)
class EvalRunRecord:
    id: str
    started_at: datetime
    finished_at: datetime
    git_sha: str
    dataset: str
    dataset_version: int
    mode: str
    model: str
    judge_model: str | None
    repeats: int
    status: str
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalResultRecord:
    id: str
    run_id: str
    case_id: str
    repeat: int
    trace_id: str | None
    passed: bool
    scores: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class LabelRecord:
    """A person's judgement of one evaluated answer, which the judge is calibrated against."""

    id: str
    result_id: str
    labeller: str
    faithful: bool
    helpful: int | None
    note: str
    created_at: datetime


@dataclass(frozen=True)
class UnlabelledResult:
    result_id: str
    run_id: str
    case_id: str
    question: str
    answer: str


class AiStore:
    """One SQLite connection in WAL mode; writes are serialised by a lock, one transaction per trace."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        try:
            self._db.execute("PRAGMA foreign_keys=ON")
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

    def write_eval_run(self, run: EvalRunRecord, results: list[EvalResultRecord]) -> None:
        with self._lock, self._db:
            self._db.execute(
                f"INSERT INTO eval_runs ({_RUN_COLUMNS}) VALUES ({', '.join('?' * 12)})",
                (
                    run.id, _stamp(run.started_at), _stamp(run.finished_at), run.git_sha, run.dataset,
                    run.dataset_version, run.mode, run.model, run.judge_model, run.repeats, run.status,
                    json.dumps(run.summary, ensure_ascii=False),
                ),
            )
            self._db.executemany(
                f"INSERT INTO eval_results ({_RESULT_COLUMNS}) VALUES ({', '.join('?' * 7)})",
                [
                    (
                        result.id, result.run_id, result.case_id, result.repeat, result.trace_id, int(result.passed),
                        json.dumps(result.scores, ensure_ascii=False),
                    )
                    for result in results
                ],
            )

    def get_eval_run(self, run_id: str) -> tuple[EvalRunRecord, list[EvalResultRecord]] | None:
        with self._lock:
            row = self._db.execute(f"SELECT {_RUN_COLUMNS} FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            results = self._db.execute(
                f"SELECT {_RESULT_COLUMNS} FROM eval_results WHERE run_id = ? ORDER BY rowid", (run_id,)
            ).fetchall()
        run = EvalRunRecord(
            row[0], _time(row[1]), _time(row[2]), row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10],
            json.loads(row[11]),
        )
        return run, [
            EvalResultRecord(result[0], result[1], result[2], result[3], result[4], bool(result[5]), json.loads(result[6]))
            for result in results
        ]

    def write_label(self, label: LabelRecord) -> None:
        if label.helpful is not None and not 1 <= label.helpful <= 5:
            raise ValueError("helpful must be from 1 to 5, or left out")
        with self._lock, self._db:
            if self._db.execute("SELECT 1 FROM eval_results WHERE id = ?", (label.result_id,)).fetchone() is None:
                raise ValueError(f"unknown result {label.result_id}")
            self._db.execute(
                "INSERT INTO labels (id, result_id, labeller, faithful, helpful, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (label.id, label.result_id, label.labeller, int(label.faithful), label.helpful, label.note,
                 _stamp(label.created_at)),
            )

    def labels(self, result_id: str) -> list[LabelRecord]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, result_id, labeller, faithful, helpful, note, created_at FROM labels "
                "WHERE result_id = ? ORDER BY rowid", (result_id,),
            ).fetchall()
        return [LabelRecord(r[0], r[1], r[2], bool(r[3]), r[4], r[5], _time(r[6])) for r in rows]

    def unlabelled_results(self, limit: int = 20, judge_model: str | None = None) -> list[UnlabelledResult]:
        """Answers waiting for a person's label, newest run first: only from runs a judge graded (a label pairs with
        a verdict), each distinct answer to a case once, and none whose text was already labelled for that case, so
        twenty labels are twenty different answers rather than one answer's repeats."""
        judged = "u.judge_model = ?" if judge_model else "u.judge_model IS NOT NULL"
        with self._lock:
            rows = self._db.execute(
                "SELECT r.id, r.run_id, r.case_id, t.question_text, t.answer_text FROM eval_results r "
                "JOIN eval_runs u ON u.id = r.run_id JOIN traces t ON t.id = r.trace_id "
                f"WHERE t.answer_text IS NOT NULL AND {judged} AND NOT EXISTS ("
                "  SELECT 1 FROM labels l JOIN eval_results r2 ON r2.id = l.result_id JOIN traces t2 ON t2.id = r2.trace_id"
                "  WHERE r2.case_id = r.case_id AND t2.answer_text = t.answer_text"
                ") ORDER BY u.started_at DESC, r.rowid",
                (judge_model,) if judge_model else (),
            ).fetchall()
        seen: set[tuple[str, str]] = set()
        pending = []
        for row in rows:
            if (row[2], row[4]) in seen:
                continue
            seen.add((row[2], row[4]))
            pending.append(UnlabelledResult(*row))
        return pending[:limit] if limit > 0 else []

    def calibration_pairs(self, judge_model: str) -> list[tuple[bool, bool]]:
        """(person said faithful, judge said faithful) for every label on an answer this judge graded."""
        with self._lock:
            rows = self._db.execute(
                "SELECT l.faithful, r.scores FROM labels l JOIN eval_results r ON r.id = l.result_id "
                "JOIN eval_runs u ON u.id = r.run_id WHERE u.judge_model = ? ORDER BY l.rowid", (judge_model,),
            ).fetchall()
        pairs = []
        for faithful, scores in rows:
            value = json.loads(scores).get("faithfulness", {}).get("value")
            if value is not None:
                pairs.append((bool(faithful), value >= 0.5))
        return pairs

    def close(self) -> None:
        self._db.close()


def _stamp(moment: datetime) -> str:
    # Always with microseconds, so stored times sort as text in the order they sort as times.
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _time(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)
