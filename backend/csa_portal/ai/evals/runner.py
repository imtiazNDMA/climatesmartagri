"""Runs a dataset against the assistant: every case, every repeat, scored, summarised and stored."""

from __future__ import annotations

import math
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..agents.assistant import AssistantChatRequest, AssistantMessage, AssistantService, AssistantView
from ..model import ModelError
from ..store import AiStore, EvalResultRecord, EvalRunRecord
from .datasets import Dataset, EvalCase
from .scorers import GATING, CaseRun, Score, case_passed, score_case


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    repeat: int
    trace_id: str | None
    passed: bool
    scores: dict[str, Score]
    answer: str


@dataclass(frozen=True)
class RunOutcome:
    record: EvalRunRecord
    results: list[CaseResult]


def run_case(service: AssistantService, case: EvalCase, run_id: str) -> CaseRun:
    request = AssistantChatRequest(
        question=case.question,
        history=[AssistantMessage(role=m.role, content=m.content) for m in case.history],
        view=AssistantView(**case.view.model_dump()),
    )
    started = time.perf_counter()
    try:
        detail = service.answer_in_detail(request, source="eval", eval_run_id=run_id)
    except ModelError as error:
        return CaseRun("", error.reason, [], time.perf_counter() - started, None, None, None)
    return CaseRun(
        detail.body["answer"], None, detail.steps, time.perf_counter() - started,
        detail.input_tokens, detail.output_tokens, detail.body["trace_id"],
    )


def run_dataset(
    service: AssistantService,
    dataset: Dataset,
    *,
    mode: str,
    model: str,
    repeats: int = 1,
    git_sha: str = "unknown",
    before_case: Callable[[EvalCase, int], None] | None = None,
    after_case: Callable[[EvalCase, int], None] | None = None,
    store: AiStore | None = None,
) -> RunOutcome:
    run_id = secrets.token_hex(16)
    started = datetime.now(UTC)
    results: list[CaseResult] = []
    for case in dataset.cases:
        for repeat in range(repeats):
            if before_case is not None:
                before_case(case, repeat)
            run = run_case(service, case, run_id)
            if after_case is not None:
                after_case(case, repeat)
            scores = score_case(case, run)
            answer = run.answer if run.error is None else f"Evaluation error: {run.error}"
            results.append(CaseResult(case.id, repeat, run.trace_id, case_passed(scores), scores, answer))
    record = EvalRunRecord(
        run_id, started, datetime.now(UTC), git_sha, dataset.name, dataset.version, mode, model, None, repeats,
        "complete", summarise(results, repeats),
    )
    if store is not None:
        store.write_eval_run(record, [
            EvalResultRecord(
                secrets.token_hex(16), run_id, r.case_id, r.repeat, r.trace_id, r.passed,
                {name: score.as_dict() for name, score in r.scores.items()},
            )
            for r in results
        ])
    return RunOutcome(record, results)


def summarise(results: list[CaseResult], repeats: int) -> dict[str, Any]:
    by_case: dict[str, list[CaseResult]] = {}
    for result in results:
        by_case.setdefault(result.case_id, []).append(result)
    passed_cases = sum(all(r.passed for r in runs) for runs in by_case.values())
    flaky = sorted(case_id for case_id, runs in by_case.items() if any(r.passed for r in runs) and not all(r.passed for r in runs))
    latencies = sorted(r.scores["latency"].value for r in results if r.scores["latency"].value is not None)
    return {
        "cases": len(by_case),
        "repeats": repeats,
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / len(by_case) if by_case else 0.0,
        "flaky_cases": flaky,
        "scorers": {
            name: sum(r.scores[name].passed is True for r in results) / len(results) if results else 0.0
            for name in GATING
        },
        "mean_latency_seconds": sum(latencies) / len(latencies) if latencies else None,
        "p95_latency_seconds": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        "tokens": _sum(r.scores["tokens"].value for r in results),
    }


def _sum(values: Any) -> int | None:
    known = [int(value) for value in values if value is not None]
    return sum(known) if known else None
