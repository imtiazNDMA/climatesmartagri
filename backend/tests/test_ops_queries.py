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


def test_evaluation_runs_come_newest_first_and_filter_by_dataset(seeded):
    ops, ids = seeded

    runs = ops.eval_runs()

    assert [r["id"] for r in runs] == [ids["runs"][k] for k in ("r", "c", "b", "a")]
    assert [r["id"] for r in ops.eval_runs(dataset="adversarial")] == [ids["runs"]["c"]]
    golden = next(r for r in runs if r["id"] == ids["runs"]["b"])
    assert (golden["judge_model"], golden["status"], golden["summary"]["pass_rate"]) == ("gemma", "partial", 0.5)
    assert golden["started_at"] == "2026-10-15T12:00:00+00:00"


def test_one_run_comes_with_its_results(seeded):
    ops, ids = seeded

    detail = ops.eval_run(ids["runs"]["b"])

    assert detail["run"]["id"] == ids["runs"]["b"]
    assert [(r["case_id"], r["passed"]) for r in detail["results"]] == [
        ("case-a", True), ("case-b", False), ("case-c", True), ("case-d", False),
    ]
    assert detail["results"][1]["scores"]["required_terms"]["reason"] == "missing: Punjab"
    assert ops.eval_run("x" * 32) is None


def test_comparing_two_runs_finds_regressions_fixes_and_new_cases(seeded):
    ops, ids = seeded

    diff = ops.compare(ids["runs"]["a"], ids["runs"]["b"])

    assert (diff["regressions"], diff["fixes"], diff["still_failing"]) == (["case-b"], ["case-c"], [])
    assert (diff["new_cases"], diff["removed_cases"]) == (["case-d"], [])
    assert (diff["a"]["id"], diff["b"]["id"]) == (ids["runs"]["a"], ids["runs"]["b"])


def test_a_case_counts_as_passed_in_a_comparison_only_when_every_repeat_passed(tmp_path):
    from csa_portal.ai.store import EvalResultRecord, EvalRunRecord

    store = AiStore(tmp_path / "ai.db")
    for key, repeats in (("1", [True, True]), ("2", [True, False])):
        run_id = key * 32
        store.write_eval_run(
            EvalRunRecord(run_id, NOW, NOW, "abc", "golden", 2, "live", "qwen", None, 2, "complete", {}),
            [EvalResultRecord(f"{key}{i}" * 16, run_id, "case-x", i, None, passed, {}) for i, passed in enumerate(repeats)],
        )

    assert OpsQueries(store).compare("1" * 32, "2" * 32)["regressions"] == ["case-x"]


def test_comparing_unknown_runs_or_different_datasets_is_refused(seeded):
    ops, ids = seeded

    with pytest.raises(LookupError):
        ops.compare(ids["runs"]["a"], "x" * 32)
    with pytest.raises(ValueError, match="different-datasets"):
        ops.compare(ids["runs"]["a"], ids["runs"]["c"])


def test_live_metrics_for_the_last_day(seeded):
    ops, _ = seeded

    live = ops.metrics("24h")["live"]

    assert (live["requests"], live["errors"], live["error_rate"]) == (4, 1, 0.25)
    assert (live["p50_latency_ms"], live["p95_latency_ms"]) == (9000.0, 30000.0)
    assert (live["input_tokens"], live["output_tokens"]) == (1800, 180)
    assert live["by_day"] == [{"day": "2026-10-15", "requests": 1, "errors": 0},
                              {"day": "2026-10-16", "requests": 3, "errors": 1}]
    assert live["error_reasons"] == [{"reason": "tool-limit", "count": 1}]
    assert live["tools"] == [{"tool": "get_section_facts", "calls": 5, "errors": 3},
                             {"tool": "find_place", "calls": 1, "errors": 0}]


def test_live_metrics_for_the_week_count_every_live_trace_and_no_evaluation_traces(seeded):
    ops, _ = seeded

    metrics = ops.metrics("7d")
    live = metrics["live"]

    assert metrics["window"] == "7d" and metrics["since"] == "2026-10-09T12:00:00+00:00"
    assert (live["requests"], live["errors"]) == (6, 2)
    assert (live["p50_latency_ms"], live["p95_latency_ms"]) == (9000.0, 30000.0)
    assert (live["input_tokens"], live["output_tokens"]) == (2110, 250)
    assert live["error_reasons"] == [{"reason": "assistant-unavailable", "count": 1}, {"reason": "tool-limit", "count": 1}]
    # Every day of the window is listed, quiet ones with zeros, so a chart shows an outage instead of skipping it.
    assert [d["day"] for d in live["by_day"]] == [f"2026-10-{day:02d}" for day in range(9, 17)]
    assert live["by_day"][1] == {"day": "2026-10-10", "requests": 0, "errors": 0}


def test_the_latest_live_run_is_compared_with_the_live_run_before_it(seeded):
    ops, ids = seeded

    evaluation = ops.metrics("24h")["eval"]

    golden, adversarial = sorted(evaluation["latest"], key=lambda r: r["dataset"], reverse=True)
    assert (golden["run_id"], golden["pass_rate"], golden["previous_pass_rate"]) == (ids["runs"]["b"], 0.5, 2 / 3)
    assert (adversarial["run_id"], adversarial["previous_pass_rate"]) == (ids["runs"]["c"], None)
    assert [r["run_id"] for r in evaluation["history"]] == [ids["runs"][k] for k in ("a", "b", "c", "r")]
    assert evaluation["history"][1]["judge"]["model"] == "gemma"


def test_an_unknown_window_is_refused(seeded):
    ops, _ = seeded

    with pytest.raises(ValueError):
        ops.metrics("1y")


def test_calibration_is_listed_per_judge_model(seeded):
    ops, _ = seeded

    assert ops.calibration() == [{
        "judge_model": "gemma", "labels": 1, "kappa": None, "calibrated": False,
        "confusion": {"both_faithful": 1, "human_only": 0, "judge_only": 0, "neither": 0},
    }]
    assert ops.metrics("24h")["calibration"] == ops.calibration()


def test_the_label_queue_lists_unlabelled_answers_and_a_new_label_leaves_it(seeded):
    ops, ids = seeded

    queue = ops.label_queue()
    assert [item["case_id"] for item in queue] == ["case-b", "case-c", "case-d"]
    assert queue[0]["answer"] == "Answer for case-b"

    label_id = ops.add_label(ids["results"]["b"]["case-b"], "officer", False, 2, "Invented a figure.")

    assert len(label_id) == 32
    assert [item["case_id"] for item in ops.label_queue()] == ["case-c", "case-d"]
    assert ops.calibration()[0]["labels"] == 2
    with pytest.raises(ValueError):
        ops.add_label("x" * 32, "officer", True, None, "")
