import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import label_answers  # noqa: E402
from csa_portal.ai.store import AiStore, EvalResultRecord, EvalRunRecord, TraceRecord  # noqa: E402

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def seeded(path, answers=2):
    store = AiStore(path)
    results = []
    for index in range(answers):
        trace_id = f"{'t' * 30}{index:02d}"
        store.write_trace(TraceRecord(trace_id, "eval", "assistant", "qwen", NOW, 1.0, "ok", None, None, None, "f" * 64,
                                      f"Question {index}", f"Answer {index}", "r" * 32))
        results.append(EvalResultRecord(f"{'x' * 30}{index:02d}", "r" * 32, f"case-{index}", 0, trace_id, True,
                                        {"faithfulness": {"value": 1.0, "passed": None, "reason": "faithful"}}))
    store.write_eval_run(EvalRunRecord("r" * 32, NOW, NOW, "abc", "golden", 2, "live", "qwen", "gemma", 1, "complete", {}),
                         results)
    return store, [r.id for r in results]


def scripted(*answers):
    replies = list(answers)
    return lambda prompt="": replies.pop(0)


def test_a_labeller_labels_answers_until_they_quit(tmp_path):
    store, results = seeded(tmp_path / "ai.db")
    said = []

    code = label_answers.main(["--labeller", "officer", "--db", str(tmp_path / "ai.db"), "--judge-model", "gemma"],
                              ask=scripted("y", "4", "Clear and right.", "q"), say=said.append)

    assert code == 0
    [only] = AiStore(tmp_path / "ai.db").labels(results[0])
    assert (only.labeller, only.faithful, only.helpful, only.note) == ("officer", True, 4, "Clear and right.")
    assert AiStore(tmp_path / "ai.db").labels(results[1]) == []
    assert any("Answer 0" in line for line in said)
    assert any("Judge gemma: 1 labels, uncalibrated" in line for line in said)


def test_unexpected_input_is_asked_again_and_skipping_writes_nothing(tmp_path):
    store, results = seeded(tmp_path / "ai.db")
    said = []

    label_answers.main(["--labeller", "officer", "--db", str(tmp_path / "ai.db")],
                       ask=scripted("maybe", "n", "7", "", "", "s"), say=said.append)

    reopened = AiStore(tmp_path / "ai.db")
    [only] = reopened.labels(results[0])
    assert (only.faithful, only.helpful) == (False, None)
    assert reopened.labels(results[1]) == []
    assert sum("Please answer" in line for line in said) == 2


def test_nothing_to_label_says_so(tmp_path):
    AiStore(tmp_path / "ai.db")
    said = []

    assert label_answers.main(["--labeller", "officer", "--db", str(tmp_path / "ai.db")], ask=scripted(), say=said.append) == 0
    assert said[-1] == "Nothing to label. Run a live evaluation (npm run eval:live) first."
