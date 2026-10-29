"""The AI Ops API (/api/ops) the dashboard reads. Every route needs an X-Ops-Token header equal to CSA_OPS_TOKEN;
without CSA_OPS_TOKEN set, main.py does not mount these routes at all."""

# No `from __future__ import annotations` here: FastAPI must see the route annotations (the local `Ops`
# dependency alias) as real objects, not strings it would look up in the module.
import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .ops import OpsQueries
from .store import AiStore


class LabelIn(BaseModel):
    result_id: str = Field(min_length=1, max_length=64)
    labeller: str = Field(min_length=1, max_length=80)
    faithful: bool
    helpful: int | None = Field(default=None, ge=1, le=5)
    note: str = Field(default="", max_length=1000)


def _error(status: int, reason: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"reason": reason, "message": message})


def add_ops_routes(
    app: FastAPI, token: str, store: AiStore | None, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> None:
    queries = OpsQueries(store, now) if store is not None else None

    def ops(x_ops_token: Annotated[str | None, Header()] = None) -> OpsQueries:
        # Checked before anything else, in constant time, so a wrong token learns nothing.
        if x_ops_token is None or not hmac.compare_digest(x_ops_token.encode(), token.encode()):
            raise _error(401, "ops-unauthorized", "A valid X-Ops-Token header is required")
        if queries is None:
            raise _error(503, "no-ai-store", "The AI store is not available; see /api/health")
        return queries

    Ops = Annotated[OpsQueries, Depends(ops)]
    router = APIRouter(prefix="/api/ops", tags=["AI Ops"])

    @router.get("/metrics")
    def metrics(ops: Ops, window: Literal["24h", "7d", "30d"] = "24h") -> dict[str, Any]:
        return ops.metrics(window)

    @router.get("/eval-runs")
    def eval_runs(ops: Ops, dataset: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict[str, Any]:
        return {"runs": ops.eval_runs(dataset, limit)}

    # Declared before /eval-runs/{run_id}, which would otherwise take "compare" as a run id.
    @router.get("/eval-runs/compare")
    def compare(ops: Ops, a: str, b: str) -> dict[str, Any]:
        try:
            return ops.compare(a, b)
        except LookupError as error:
            raise _error(404, "unknown-run", f"No evaluation run {error}") from error
        except ValueError as error:
            raise _error(422, "different-datasets", "Only runs of the same dataset can be compared") from error

    @router.get("/eval-runs/{run_id}")
    def eval_run(ops: Ops, run_id: str) -> dict[str, Any]:
        found = ops.eval_run(run_id)
        if found is None:
            raise _error(404, "unknown-run", f"No evaluation run {run_id}")
        return found

    @router.get("/traces")
    def traces(
        ops: Ops,
        source: Literal["live", "eval"] | None = None,
        agent: str | None = None,
        status: Literal["ok", "error"] | None = None,
        before: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, Any]:
        return ops.traces(source=source, agent=agent, status=status, before=before, limit=limit)

    @router.get("/traces/{trace_id}")
    def trace(ops: Ops, trace_id: str) -> dict[str, Any]:
        found = ops.trace(trace_id)
        if found is None:
            raise _error(404, "unknown-trace", f"No trace {trace_id}")
        return found

    @router.get("/labels/queue")
    def label_queue(ops: Ops, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict[str, Any]:
        return {"queue": ops.label_queue(limit)}

    @router.post("/labels", status_code=201)
    def add_label(ops: Ops, body: LabelIn) -> dict[str, str]:
        try:
            return {"id": ops.add_label(body.result_id, body.labeller, body.faithful, body.helpful, body.note)}
        except ValueError as error:
            if "unknown result" in str(error):
                raise _error(404, "unknown-result", str(error)) from error
            raise _error(422, "bad-label", str(error)) from error

    @router.get("/calibration")
    def judge_calibration(ops: Ops) -> dict[str, Any]:
        return {"judges": ops.calibration()}

    app.include_router(router)
