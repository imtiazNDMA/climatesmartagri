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


def _jsonable(node: Any) -> Any:
    if isinstance(node, datetime):
        return node.isoformat()
    if isinstance(node, dict):
        return {key: _jsonable(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_jsonable(item) for item in node]
    return node
