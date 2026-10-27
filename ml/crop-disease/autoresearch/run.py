from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from autoresearch.prepare import KILL_AFTER_SECONDS
from crop_disease.tracking import configure_mlflow

METRIC_PATTERN = re.compile(r"^(val_macro_f1|peak_vram_mb):\s*([0-9]+(?:\.[0-9]+)?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Attempt:
    commit: str
    description: str


@dataclass(frozen=True)
class AttemptResult:
    commit: str
    val_macro_f1: float | None
    peak_vram_mb: float | None
    status: str
    description: str


def parse_metrics(output: str) -> tuple[float, float]:
    found: dict[str, float] = {}
    for name, value in METRIC_PATTERN.findall(output):
        found[name] = float(value)
    missing = {"val_macro_f1", "peak_vram_mb"} - found.keys()
    if missing:
        raise ValueError(f"training output is missing metrics: {sorted(missing)}")
    return found["val_macro_f1"], found["peak_vram_mb"]


def append_result(path: Path, result: AttemptResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        if is_new:
            writer.writerow(("commit", "val_macro_f1", "memory_gb", "status", "description"))
        writer.writerow((
            result.commit,
            "" if result.val_macro_f1 is None else f"{result.val_macro_f1:.6f}",
            "" if result.peak_vram_mb is None else f"{result.peak_vram_mb / 1024:.3f}",
            result.status,
            result.description,
        ))


def reset_candidate(project: Path, commit: str) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
    candidate = subprocess.check_output(["git", "rev-parse", commit], cwd=project, text=True).strip()
    if head != candidate:
        raise RuntimeError(f"refusing to reset: HEAD is {head}, candidate is {candidate}")
    subprocess.run(["git", "reset", "--hard", f"{candidate}^"], cwd=project, check=True)


def run_attempt(
    project: Path,
    attempt: Attempt,
    command: list[str],
    timeout_seconds: float = KILL_AFTER_SECONDS,
    baseline: float | None = None,
) -> AttemptResult:
    mlflow, _ = configure_mlflow(project, "autoresearch")
    active_run = mlflow.start_run(run_name=attempt.description)
    environment = os.environ.copy()
    environment["MLFLOW_RUN_ID"] = active_run.info.run_id
    environment["AUTORESEARCH_DESCRIPTION"] = attempt.description
    try:
        completed = subprocess.run(
            command,
            cwd=project / "autoresearch",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            env=environment,
        )
        if completed.returncode != 0:
            result = AttemptResult(attempt.commit, None, None, "crash", attempt.description)
        else:
            score, memory = parse_metrics(completed.stdout)
            status = "keep" if baseline is None or score > baseline else "discard"
            result = AttemptResult(attempt.commit, score, memory, status, attempt.description)
    except (subprocess.TimeoutExpired, ValueError) as error:
        output = getattr(error, "stdout", "") or str(error)
        result = AttemptResult(attempt.commit, None, None, "crash", attempt.description)
    else:
        output = completed.stdout

    append_result(project / "autoresearch" / "results.tsv", result)
    mlflow.set_tags({
        "commit": result.commit,
        "status": result.status,
        "description": result.description,
    })
    if result.val_macro_f1 is not None:
        mlflow.log_metric("val_macro_f1", result.val_macro_f1)
    if result.peak_vram_mb is not None:
        mlflow.log_metric("peak_vram_mb", result.peak_vram_mb)
    log_path = project / "autoresearch" / "run.log"
    log_path.write_text(output, encoding="utf-8")
    mlflow.log_artifact(str(log_path))
    mlflow.end_run(status="FINISHED" if result.status != "crash" else "FAILED")
    if result.status != "keep":
        reset_candidate(project, attempt.commit)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run and record one autoresearch candidate")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--baseline", type=float)
    parser.add_argument("--timeout", type=float, default=KILL_AFTER_SECONDS)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    result = run_attempt(
        project,
        Attempt(args.commit, args.description),
        ["uv", "run", "train.py"],
        timeout_seconds=args.timeout,
        baseline=args.baseline,
    )
    print(f"status={result.status} val_macro_f1={result.val_macro_f1}")


if __name__ == "__main__":
    main()
