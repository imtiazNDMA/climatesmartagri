from pathlib import Path
import subprocess

import pytest

from autoresearch.prepare import load_data
from autoresearch.run import Attempt, parse_metrics, reset_candidate, run_attempt, validate_candidate


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
    candidate = git_candidate(tmp_path, "ml/crop-disease/autoresearch/train.py")
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
        attempt=Attempt(candidate, "broken syntax"),
        command=["python", "train.py"],
        timeout_seconds=2,
        execute=lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="SyntaxError: invalid syntax"
        ),
    )

    assert result.status == "crash"
    assert (tmp_path / "autoresearch/results.tsv").read_text(encoding="utf-8").splitlines() == [
        "commit\tval_macro_f1\tmemory_gb\tstatus\tdescription",
        f"{candidate}\t\t\tcrash\tbroken syntax",
    ]


def test_reset_accepts_an_abbreviated_candidate_sha(tmp_path):
    candidate = git_candidate(tmp_path, "file.txt")[:7]

    reset_candidate(tmp_path, candidate)

    assert (tmp_path / "file.txt").read_text(encoding="utf-8") == "base"


def test_reset_refuses_to_delete_tracked_uncommitted_work(tmp_path):
    candidate = git_candidate(tmp_path, "file.txt")
    (tmp_path / "file.txt").write_text("important work", encoding="utf-8")

    with pytest.raises(RuntimeError, match="dirty tracked worktree"):
        reset_candidate(tmp_path, candidate)

    assert (tmp_path / "file.txt").read_text(encoding="utf-8") == "important work"


def test_candidate_may_change_only_the_editable_training_file(tmp_path):
    candidate = git_candidate(tmp_path, "ml/crop-disease/autoresearch/prepare.py")

    with pytest.raises(RuntimeError, match="must change only"):
        validate_candidate(tmp_path, candidate)


def git_candidate(root: Path, changed_path: str) -> str:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    path = root / changed_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", changed_path], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "switch", "-c", "autoresearch/test"], cwd=root, check=True, capture_output=True)
    path.write_text("candidate", encoding="utf-8")
    subprocess.run(["git", "commit", "-am", "candidate"], cwd=root, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
