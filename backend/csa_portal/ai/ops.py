"""Read models for the AI Ops dashboard, computed from the AI store: live traffic, evaluation runs and their
comparison, traces, labels and judge calibration. The dashboard only draws what these return."""

from __future__ import annotations

import json
import math
import secrets
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from .evals.calibration import calibration
from .store import AiStore, LabelRecord, _stamp, _time

_TRACE_FIELDS = (
    "id", "source", "agent", "model", "started_at", "duration_ms", "status", "error_reason", "input_tokens",
    "output_tokens", "eval_run_id",
)
_RUN_FIELDS = (
    "id", "dataset", "dataset_version", "mode", "model", "judge_model", "git_sha", "started_at", "finished_at",
    "repeats", "status", "summary",
)


class OpsQueries:
    def __init__(self, store: AiStore, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.store = store
        self.now = now

    def traces(
        self, *, source: str | None = None, agent: str | None = None, status: str | None = None,
        before: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        """Traces newest first. `next` is the cursor for the page after this one: the last trace's start and id."""
        clauses, params = [], []
        for column, value in (("source", source), ("agent", agent), ("status", status)):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        if before:
            started, _, trace_id = before.partition("|")
            clauses.append("(started_at < ? OR (started_at = ? AND id < ?))")
            params += [started, started, trace_id]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.store.read(
            f"SELECT {', '.join(_TRACE_FIELDS)} FROM traces {where} ORDER BY started_at DESC, id DESC LIMIT ?",
            (*params, limit + 1),
        )
        page = rows[:limit]
        items = [{**dict(zip(_TRACE_FIELDS, row)), "started_at": _time(row[4]).isoformat()} for row in page]
        return {"traces": items, "next": f"{page[-1][4]}|{page[-1][0]}" if len(rows) > limit else None}

    def trace(self, trace_id: str) -> dict[str, Any] | None:
        record = self.store.get_trace(trace_id)
        return None if record is None else _jsonable(asdict(record))

    def eval_runs(self, dataset: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        where, params = ("WHERE dataset = ?", (dataset,)) if dataset else ("", ())
        rows = self.store.read(
            f"SELECT {', '.join(_RUN_FIELDS)} FROM eval_runs {where} ORDER BY started_at DESC, id DESC LIMIT ?",
            (*params, limit),
        )
        return [_run(row) for row in rows]

    def eval_run(self, run_id: str) -> dict[str, Any] | None:
        found = self.store.get_eval_run(run_id)
        if found is None:
            return None
        run, results = found
        return {"run": _jsonable(asdict(run)), "results": [asdict(result) for result in results]}

    def compare(self, a: str, b: str) -> dict[str, Any]:
        """Case by case, `a` (before) against `b` (after); a case passed when it passed every repeat."""
        found = {run_id: self.store.get_eval_run(run_id) for run_id in (a, b)}
        for run_id, value in found.items():
            if value is None:
                raise LookupError(run_id)
        (run_a, results_a), (run_b, results_b) = found[a], found[b]
        if run_a.dataset != run_b.dataset:
            raise ValueError("different-datasets")
        before, after = _pass_k(results_a), _pass_k(results_b)
        both = before.keys() & after.keys()
        return {
            "a": _jsonable(asdict(run_a)),
            "b": _jsonable(asdict(run_b)),
            "regressions": sorted(c for c in both if before[c] and not after[c]),
            "fixes": sorted(c for c in both if not before[c] and after[c]),
            "still_failing": sorted(c for c in both if not before[c] and not after[c]),
            "new_cases": sorted(after.keys() - before.keys()),
            "removed_cases": sorted(before.keys() - after.keys()),
        }


def _jsonable(node: Any) -> Any:
    if isinstance(node, datetime):
        return node.isoformat()
    if isinstance(node, dict):
        return {key: _jsonable(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_jsonable(item) for item in node]
    return node


def _run(row: tuple) -> dict[str, Any]:
    body = dict(zip(_RUN_FIELDS, row))
    body["started_at"] = _time(body["started_at"]).isoformat()
    body["finished_at"] = _time(body["finished_at"]).isoformat()
    body["summary"] = json.loads(body["summary"])
    return body


def _pass_k(results: list[Any]) -> dict[str, bool]:
    passed: dict[str, bool] = {}
    for result in results:
        passed[result.case_id] = passed.get(result.case_id, True) and result.passed
    return passed
