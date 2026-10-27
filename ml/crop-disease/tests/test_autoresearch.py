from pathlib import Path
import subprocess

import pytest

from autoresearch.prepare import load_data
from autoresearch.run import Attempt, parse_metrics, run_attempt


def test_autoresearch_data_cannot_load_the_test_split(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "path,source_split,source_label,label,crop,category,sha256,dhash,group,status,split\n"
        "Train/A/a.jpg,Train,A,rust,Wheat,disease,a,00,g1,kept,train\n"
        "Validation/A/v.jpg,Validation,A,rust,Wheat,disease,b,11,g2,kept,val\n"
        "Validation/A/t.jpg,Validation,A,rust,Wheat,disease,c,22,g3,kept,test\n",
        encoding="utf-8",
    )

    prepared = load_data(tmp_path, manifest)

    assert [item.path for item in prepared.train.items] == ["Train/A/a.jpg"]
    assert [item.path for item in prepared.val.items] == ["Validation/A/v.jpg"]
    assert not hasattr(prepared, "test")
    with pytest.raises(TypeError):
        load_data(tmp_path, manifest, split="test")


def test_required_metrics_are_read_from_the_last_matching_lines():
    output = "val_macro_f1: 0.7000\nnotes\nval_macro_f1: 0.8123\npeak_vram_mb: 4096.0\n"

    assert parse_metrics(output) == (0.8123, 4096.0)


def test_crash_is_recorded_and_candidate_commit_is_reset(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "autoresearch.run.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout="SyntaxError: invalid syntax"),
    )
    monkeypatch.setattr("autoresearch.run.reset_candidate", lambda project, commit: calls.append((project, commit)))
    class FakeRun:
        class info:
            run_id = "run-1"

    class FakeMlflow:
        def start_run(self, **kwargs):
            return FakeRun()

        def set_tags(self, *args, **kwargs):
            pass

        def log_metric(self, *args, **kwargs):
            pass

        def log_artifact(self, *args, **kwargs):
            pass

        def end_run(self, *args, **kwargs):
            pass

    monkeypatch.setattr("autoresearch.run.configure_mlflow", lambda *args: (FakeMlflow(), "test"))

    result = run_attempt(
        project=tmp_path,
        attempt=Attempt("abc123", "broken syntax"),
        command=["python", "train.py"],
        timeout_seconds=2,
    )

    assert result.status == "crash"
    assert calls == [(tmp_path, "abc123")]
    assert (tmp_path / "autoresearch/results.tsv").read_text(encoding="utf-8").splitlines() == [
        "commit\tval_macro_f1\tmemory_gb\tstatus\tdescription",
        "abc123\t\t\tcrash\tbroken syntax",
    ]
