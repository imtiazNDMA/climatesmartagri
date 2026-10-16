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
        # Span ids are unique across the whole store, so they are made from the trace's id.
        spans=[
            SpanRecord(trace_id[:15] + "2", trace_id, trace_id[:15] + "1", "llm", "chat qwen", started_at + timedelta(milliseconds=5),
                       900.0, "ok", {"gen_ai.request.model": "qwen", "gen_ai.usage.input_tokens": 310}),
            SpanRecord(trace_id[:15] + "1", trace_id, None, "agent", "assistant", started_at, 1190.0, "ok",
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


def test_an_evaluation_run_and_its_results_come_back_as_written(tmp_path):
    from csa_portal.ai.store import EvalResultRecord, EvalRunRecord

    store = AiStore(tmp_path / "ai.db")
    run = EvalRunRecord("r" * 32, NOW, NOW + timedelta(minutes=9), "abc1234", "golden", 2, "live", "qwen", None, 3,
                        "complete", {"pass_rate": 0.25, "flaky_cases": ["land-punjab"]})
    results = [
        EvalResultRecord("1" * 32, "r" * 32, "land-punjab", 0, "a" * 32, True,
                         {"safety": {"value": 1.0, "passed": True, "reason": "safe"}}),
        EvalResultRecord("2" * 32, "r" * 32, "land-punjab", 1, None, False,
                         {"safety": {"value": 0.0, "passed": False, "reason": "said: PWNED"}}),
    ]

    store.write_eval_run(run, results)

    assert store.get_eval_run("r" * 32) == (run, results)
    assert store.get_eval_run("x" * 32) is None


def test_an_evaluation_run_and_its_results_are_one_transaction(tmp_path):
    from csa_portal.ai.store import EvalResultRecord, EvalRunRecord

    path = tmp_path / "ai.db"
    store = AiStore(path)
    run = EvalRunRecord("r" * 32, NOW, NOW, "abc1234", "golden", 2, "recorded", "qwen", None, 1,
                        "complete", {})
    results = [
        EvalResultRecord("1" * 32, run.id, "first", 0, None, True, {}),
        EvalResultRecord("2" * 32, "x" * 32, "orphan", 0, None, False, {}),
    ]

    with pytest.raises(sqlite3.IntegrityError):
        store.write_eval_run(run, results)

    assert store.get_eval_run(run.id) is None
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM eval_results").fetchone() == (0,)


def test_a_version_1_database_is_upgraded_and_keeps_its_traces(tmp_path, monkeypatch):
    import csa_portal.ai.store as store_module

    path = tmp_path / "ai.db"
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", 1)
    AiStore(path).write_trace(trace())
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", 2)

    upgraded = AiStore(path)

    assert upgraded.get_trace("a" * 32) is not None
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version FROM schema_version").fetchone() == (2,)
        assert db.execute("SELECT COUNT(*) FROM eval_runs").fetchone() == (0,)


def judged_run(store, run_id, judge_model, verdicts, *, started=NOW):
    """A stored run whose results carry judge verdicts (True/False/None) and traces with text."""
    from csa_portal.ai.store import EvalResultRecord, EvalRunRecord

    results = []
    for index, verdict in enumerate(verdicts):
        trace_id = f"{run_id[:30]}{index:02d}"
        store.write_trace(TraceRecord(trace_id, "eval", "assistant", "qwen", started, 1.0, "ok", None, None, None,
                                      "f" * 64, f"Question {index}", f"Answer {index}", run_id))
        scores = {} if verdict is None else {"faithfulness": {"value": 1.0 if verdict else 0.0, "passed": None, "reason": ""}}
        results.append(EvalResultRecord(f"{run_id[:30]}{index:02d}", run_id, f"case-{index}", 0, trace_id, True, scores))
    store.write_eval_run(EvalRunRecord(run_id, started, started, "abc", "golden", 2, "live", "qwen", judge_model, 1,
                                       "complete", {}), results)
    return [r.id for r in results]


def label(result_id, faithful, *, labeller="officer", helpful=4):
    from csa_portal.ai.store import LabelRecord

    return LabelRecord(f"{result_id}-{labeller}", result_id, labeller, faithful, helpful, "", NOW)


def test_labels_are_kept_per_result_and_a_result_can_be_labelled_by_several_people(tmp_path):
    store = AiStore(tmp_path / "ai.db")
    [result] = judged_run(store, "r" * 32, "gemma", [True])

    store.write_label(label(result, True, labeller="first"))
    store.write_label(label(result, False, labeller="second", helpful=None))

    assert [(l.labeller, l.faithful, l.helpful) for l in store.labels(result)] == [("first", True, 4), ("second", False, None)]
    assert store.calibration_pairs("gemma") == [(True, True), (False, True)]


def test_a_label_for_an_unknown_result_or_with_helpfulness_out_of_range_is_refused(tmp_path):
    store = AiStore(tmp_path / "ai.db")
    [result] = judged_run(store, "r" * 32, "gemma", [True])

    with pytest.raises(ValueError, match="unknown result"):
        store.write_label(label("x" * 32, True))
    with pytest.raises(ValueError, match="1 to 5"):
        store.write_label(label(result, True, helpful=7))


def test_unlabelled_results_come_newest_run_first_with_their_question_and_answer(tmp_path):
    store = AiStore(tmp_path / "ai.db")
    older = judged_run(store, "o" * 32, "gemma", [True], started=NOW - timedelta(days=1))
    newer = judged_run(store, "n" * 32, "gemma", [True, False])
    store.write_label(label(newer[0], True))

    unlabelled = store.unlabelled_results()

    assert [(u.result_id, u.question, u.answer) for u in unlabelled] == [
        (newer[1], "Question 1", "Answer 1"), (older[0], "Question 0", "Answer 0"),
    ]
    assert store.unlabelled_results(limit=1)[0].result_id == newer[1]


def test_calibration_pairs_belong_to_one_judge_and_skip_results_it_did_not_grade(tmp_path):
    store = AiStore(tmp_path / "ai.db")
    gemma = judged_run(store, "g" * 32, "gemma", [True, None])
    glm = judged_run(store, "m" * 32, "glm", [False])
    for result in [*gemma, *glm]:
        store.write_label(label(result, True))

    assert store.calibration_pairs("gemma") == [(True, True)]
    assert store.calibration_pairs("glm") == [(True, False)]
