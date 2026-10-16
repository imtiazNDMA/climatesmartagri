"""Demo data for the AI Ops dashboard: three days of live traffic, two golden runs with a regression and a fix
between them, an adversarial run, a recorded replay, a judged run and one label.

The ops tests and the dashboard's browser tests use it. To see the dashboard without real traffic:
    uv run python backend/scripts/seed_ops_store.py --db backend/ops-demo.db
then start the portal with CSA_AI_DB=backend/ops-demo.db and CSA_OPS_TOKEN set.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from csa_portal.ai.store import AiStore, EvalResultRecord, EvalRunRecord, LabelRecord, SpanRecord, TraceRecord  # noqa: E402

MODEL = "qwen/qwen3.8-27b"
# hours ago, duration ms, status, error reason, tokens in, tokens out, tool calls [(name, status)]
LIVE = [
    (1, 8000.0, "ok", None, 300, 40, [("find_place", "ok"), ("get_section_facts", "ok")]),
    (2, 12000.0, "ok", None, 320, 60, [("get_section_facts", "ok")]),
    (5, 30000.0, "error", "tool-limit", 900, 30, [("get_section_facts", "error")] * 3),
    (20, 9000.0, "ok", None, 280, 50, []),
    (30, 3000.0, "error", "assistant-unavailable", None, None, []),
    (60, 15000.0, "ok", None, 310, 70, [("get_crop_calendar", "ok")]),
]
# key, dataset, age, mode, model, judge, commit, [(case, passed)], keeps traces
RUNS = [
    ("a", "golden", timedelta(days=2), "live", MODEL, None, "aaa1111",
     [("case-a", True), ("case-b", True), ("case-c", False)], False),
    ("b", "golden", timedelta(days=1), "live", MODEL, "gemma", "bbb2222",
     [("case-a", True), ("case-b", False), ("case-c", True), ("case-d", False)], True),
    ("c", "adversarial", timedelta(days=1), "live", MODEL, None, "bbb2222",
     [("inject-a", True), ("inject-b", True)], False),
    ("r", "golden", timedelta(hours=1), "recorded", "cassette-replay", None, "bbb2222",
     [("case-a", True), ("case-b", False), ("case-c", True), ("case-d", False)], False),
]
FAITHFUL = {"case-a": 1.0, "case-b": 0.0, "case-c": 1.0, "case-d": None}


def ident(prefix: str, number: int, width: int = 32) -> str:
    return f"{prefix}{number:0{width - len(prefix)}d}"


def seed(store: AiStore, now: datetime) -> dict[str, Any]:
    ids: dict[str, Any] = {"live": [], "runs": {}, "results": {}}
    for n, (hours, duration, status, error, tokens_in, tokens_out, tools) in enumerate(LIVE):
        trace_id, started = ident("live", n), now - timedelta(hours=hours)
        root = ident(f"s{n}", 0, 16)
        usage = {k: v for k, v in (("gen_ai.usage.input_tokens", tokens_in), ("gen_ai.usage.output_tokens", tokens_out)) if v}
        spans = [
            SpanRecord(root, trace_id, None, "agent", "assistant", started, duration - 10, status,
                       {"gen_ai.agent.name": "assistant"}),
            SpanRecord(ident(f"s{n}", 1, 16), trace_id, root, "llm", f"chat {MODEL}", started + timedelta(milliseconds=1),
                       duration / 2, "error" if error == "assistant-unavailable" else "ok",
                       {"gen_ai.request.model": MODEL, **usage}),
        ]
        for k, (tool, tool_status) in enumerate(tools, start=2):
            spans.append(SpanRecord(ident(f"s{n}", k, 16), trace_id, root, "tool", tool,
                                    started + timedelta(milliseconds=k), 40.0, tool_status, {"gen_ai.tool.name": tool}))
        store.write_trace(TraceRecord(trace_id, "live", "assistant", MODEL, started, duration, status, error,
                                      tokens_in, tokens_out, "f" * 64, None, None, None, spans))
        ids["live"].append(trace_id)

    for key, dataset, age, mode, model, judge, commit, cases, keeps_traces in RUNS:
        run_id, started = ident(f"run{key}", 0), now - age
        results = []
        for i, (case_id, passed) in enumerate(cases):
            trace_id = None
            if keeps_traces:
                trace_id = ident(f"eval{key}", i)
                store.write_trace(TraceRecord(trace_id, "eval", "assistant", model, started + timedelta(seconds=i),
                                              9000.0, "ok", None, 300, 40, "f" * 64, f"Question for {case_id}",
                                              f"Answer for {case_id}", run_id))
            scores: dict[str, Any] = {"required_terms": {
                "value": 1.0 if passed else 0.0, "passed": passed, "reason": "all terms present" if passed else "missing: Punjab",
            }}
            if judge:
                value = FAITHFUL[case_id]
                scores["faithfulness"] = {"value": value, "passed": None,
                                          "reason": "judge-unavailable" if value is None else "faithful" if value else "unfaithful"}
            results.append(EvalResultRecord(ident(f"res{key}", i), run_id, case_id, 0, trace_id, passed, scores))
        passed_cases = sum(passed for _, passed in cases)
        summary: dict[str, Any] = {
            "cases": len(cases), "repeats": 1, "passed_cases": passed_cases, "pass_rate": passed_cases / len(cases),
            "flaky_cases": [], "scorers": {"required_terms": passed_cases / len(cases)},
        }
        if judge:
            summary["judge"] = {"model": judge, "calibrated": False, "faithful_rate": 2 / 3, "mean_helpfulness": None,
                                "unavailable": 1}
        store.write_eval_run(EvalRunRecord(run_id, started, started + timedelta(minutes=10), commit, dataset, 2, mode,
                                           model, judge, 1, "partial" if judge else "complete", summary), results)
        ids["runs"][key] = run_id
        ids["results"][key] = {r.case_id: r.id for r in results}

    store.write_label(LabelRecord(ident("label", 0), ids["results"]["b"]["case-a"], "officer", True, 4,
                                  "Right figures.", now - timedelta(hours=20)))
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, required=True, help="a new database file to fill")
    args = parser.parse_args(argv)
    if args.db.exists():
        parser.error(f"{args.db} exists; give a new file")
    seed(AiStore(args.db), datetime.now(UTC))
    print(f"Seeded {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
