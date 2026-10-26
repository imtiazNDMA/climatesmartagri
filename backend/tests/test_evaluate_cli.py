import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import evaluate  # noqa: E402
from csa_portal.ai.evals.cassettes import cassette_path, save_cassette  # noqa: E402
from csa_portal.ai.model import Completion  # noqa: E402

TINY = {"name": "tiny", "version": 1, "review_status": "draft", "cases": [
    {"id": "hello", "question": "Say hello", "expected_kind": "any", "required_terms": ["hello"]},
    {"id": "unrecorded", "question": "Say hello again", "expected_kind": "any", "required_terms": ["hello"]},
]}


@pytest.fixture
def tiny(tmp_path, monkeypatch, settings):
    datasets = tmp_path / "evaluations"
    datasets.mkdir()
    (datasets / "assistant_tiny.json").write_text(json.dumps(TINY), encoding="utf-8")
    save_cassette(cassette_path("tiny", "hello", datasets / "cassettes"), [Completion(text="hello there")])
    monkeypatch.setattr(evaluate, "DATASETS_DIR", datasets)
    monkeypatch.setattr(evaluate.Settings, "from_env", classmethod(lambda cls: settings))
    return datasets


def test_a_recorded_run_replays_cassettes_writes_the_report_and_passes_its_gate(tiny, tmp_path):
    report, baseline = tmp_path / "report.md", tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"tiny": 0.5}), encoding="utf-8")

    code = evaluate.main(["--dataset", "tiny", "--cassettes", str(tiny / "cassettes"), "--report", str(report),
                          "--gate", str(baseline)])

    assert code == 0
    text = report.read_text(encoding="utf-8")
    assert "- Passed every repeat (pass^1): 1/2 (50.0%)" in text
    assert "no answer: no-cassette" in text


def test_the_gate_fails_when_a_dataset_falls_below_its_baseline(tiny, tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"tiny": 1.0}), encoding="utf-8")

    code = evaluate.main(["--dataset", "tiny", "--cassettes", str(tiny / "cassettes"), "--gate", str(baseline)])

    assert code == 1
    assert "tiny: 50.0% is below the baseline of 100.0%" in capsys.readouterr().out


def test_write_baseline_keeps_each_datasets_recorded_pass_rate(tiny, tmp_path):
    baseline = tmp_path / "baseline.json"

    evaluate.main(["--dataset", "tiny", "--cassettes", str(tiny / "cassettes"), "--write-baseline", str(baseline)])

    assert json.loads(baseline.read_text(encoding="utf-8")) == {"tiny": 0.5}


def test_a_recorded_run_is_stored_only_when_asked(tiny, tmp_path):
    from csa_portal.ai.store import AiStore

    db = tmp_path / "ai.db"
    evaluate.main(["--dataset", "tiny", "--cassettes", str(tiny / "cassettes"), "--db", str(db)])
    assert not db.exists()

    evaluate.main(["--dataset", "tiny", "--cassettes", str(tiny / "cassettes"), "--db", str(db), "--store"])
    store = AiStore(db)
    [(run_id,)] = store._db.execute("SELECT id FROM eval_runs").fetchall()
    assert store.get_eval_run(run_id)[0].mode == "recorded"


def test_unknown_case_ids_are_refused(tiny):
    with pytest.raises(SystemExit):
        evaluate.main(["--dataset", "tiny", "--case", "nope"])


def test_the_gate_names_every_dataset_below_its_baseline():
    class Outcome:
        def __init__(self, rate):
            self.record = type("R", (), {"summary": {"pass_rate": rate}})()

    class Named:
        def __init__(self, name):
            self.name = name

    messages = evaluate.gate({"golden": 0.4, "adversarial": 0.9},
                             [(Named("golden"), Outcome(0.5)), (Named("adversarial"), Outcome(0.8))])

    assert messages == ["adversarial: 80.0% is below the baseline of 90.0%"]


def test_a_run_equal_to_its_written_baseline_passes_the_gate():
    class Outcome:
        record = type("R", (), {"summary": {"pass_rate": 28 / 52}})()

    class Named:
        name = "golden"

    # write-baseline stores 28/52 as 0.5385, just above the exact rate.
    assert evaluate.gate({"golden": 0.5385}, [(Named(), Outcome())]) == []
