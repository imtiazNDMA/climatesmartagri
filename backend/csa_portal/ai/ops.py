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
WINDOWS = {"24h": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}


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

    def metrics(self, window: str = "24h") -> dict[str, Any]:
        if window not in WINDOWS:
            raise ValueError(f"unknown window {window}")
        since = self.now() - WINDOWS[window]
        return {
            "window": window,
            "since": since.isoformat(),
            "live": self._live(since),
            "eval": self._evaluation(),
            "calibration": self.calibration(),
        }

    def _live(self, since: datetime) -> dict[str, Any]:
        rows = self.store.read(
            "SELECT started_at, duration_ms, status, error_reason, input_tokens, output_tokens FROM traces "
            "WHERE source = 'live' AND started_at >= ?", (_stamp(since),),
        )
        durations = sorted(row[1] for row in rows)
        errors = [row for row in rows if row[2] == "error"]
        days: dict[str, dict[str, Any]] = {}
        for started, _, status, *_ in rows:
            day = days.setdefault(started[:10], {"day": started[:10], "requests": 0, "errors": 0})
            day["requests"] += 1
            day["errors"] += status == "error"
        reasons = Counter(row[3] or "unknown" for row in errors)
        tool_rows = self.store.read(
            "SELECT s.name, s.status FROM spans s JOIN traces t ON t.id = s.trace_id "
            "WHERE t.source = 'live' AND t.started_at >= ? AND s.kind = 'tool'", (_stamp(since),),
        )
        tools: dict[str, dict[str, Any]] = {}
        for name, status in tool_rows:
            tool = tools.setdefault(name, {"tool": name, "calls": 0, "errors": 0})
            tool["calls"] += 1
            tool["errors"] += status == "error"
        return {
            "requests": len(rows),
            "errors": len(errors),
            "error_rate": len(errors) / len(rows) if rows else None,
            "p50_latency_ms": _percentile(durations, 0.5),
            "p95_latency_ms": _percentile(durations, 0.95),
            "input_tokens": _sum(row[4] for row in rows),
            "output_tokens": _sum(row[5] for row in rows),
            "by_day": [days[day] for day in sorted(days)],
            "error_reasons": [{"reason": r, "count": c} for r, c in sorted(reasons.items(), key=lambda i: (-i[1], i[0]))],
            "tools": sorted(tools.values(), key=lambda t: (-t["calls"], t["tool"])),
        }

    def _evaluation(self) -> dict[str, Any]:
        rows = self.store.read(
            "SELECT id, dataset, mode, model, judge_model, git_sha, started_at, status, summary FROM eval_runs "
            "ORDER BY started_at DESC, id DESC LIMIT 200"
        )
        history = []
        for run_id, dataset, mode, model, judge, sha, started, status, summary_text in reversed(rows):
            summary = json.loads(summary_text)
            history.append({
                "run_id": run_id, "dataset": dataset, "mode": mode, "model": model, "judge_model": judge,
                "git_sha": sha, "started_at": _time(started).isoformat(), "status": status,
                "pass_rate": summary.get("pass_rate"), "scorers": summary.get("scorers", {}), "judge": summary.get("judge"),
            })
        latest = []
        for dataset in sorted({run["dataset"] for run in history}):
            runs = [run for run in history if run["dataset"] == dataset]
            # The KPI follows live runs; a recorded replay counts only when a dataset has no live run yet.
            pool = [run for run in runs if run["mode"] == "live"] or runs
            previous = pool[-2]["pass_rate"] if len(pool) > 1 else None
            latest.append({**pool[-1], "previous_pass_rate": previous})
        return {"latest": latest, "history": history}

    def calibration(self) -> list[dict[str, Any]]:
        models = self.store.read(
            "SELECT DISTINCT judge_model FROM eval_runs WHERE judge_model IS NOT NULL ORDER BY judge_model"
        )
        states = []
        for (model,) in models:
            state = calibration(self.store.calibration_pairs(model))
            states.append({"judge_model": model, "labels": state.labels, "kappa": state.kappa,
                           "calibrated": state.calibrated, "confusion": state.confusion})
        return states

    def label_queue(self, limit: int = 20) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.store.unlabelled_results(limit)]

    def add_label(self, result_id: str, labeller: str, faithful: bool, helpful: int | None, note: str) -> str:
        label_id = secrets.token_hex(16)
        self.store.write_label(LabelRecord(label_id, result_id, labeller, faithful, helpful, note, self.now()))
        return label_id


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


def _percentile(values: list[float], q: float) -> float | None:
    """Nearest rank: the value at position ceil(q * n) of the sorted values."""
    return values[max(0, math.ceil(q * len(values)) - 1)] if values else None


def _sum(values: Any) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None
