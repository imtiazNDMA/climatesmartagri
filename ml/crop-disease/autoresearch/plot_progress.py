"""Chart the autoresearch loop: every experiment, the kept ones, the running best, and the seed re-checks.

    uv run python -m autoresearch.plot_progress

Reads `autoresearch/results.tsv` and, for the seed re-checks, the MLflow runs whose description
starts with "#69 confirm". Writes `runs/autoresearch-progress.png`.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT / "autoresearch" / "results.tsv"
OUTPUT = PROJECT / "runs" / "autoresearch-progress.png"
BASELINE = "ten-minute MobileNetV2 baseline corrected"
PYTORCH_BASELINE = 0.8304  # #67: full-length MobileNetV2 run
COLLAPSED_BELOW = 0.5

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8984"
GRID = "#e6e5e1"
KEPT = "#1baf7a"
DISCARDED = "#c9c8c2"
SEEDS = "#2a78d6"


def read_results(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    for number, row in enumerate(rows):
        row["number"] = number
        row["score"] = float(row["val_macro_f1"]) if row["val_macro_f1"] else None
    return rows


def read_seed_checks() -> list[tuple[str, list[float]]]:
    """Seed re-checks grouped by commit, in the order they were run."""
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    from crop_disease.tracking import configure_mlflow

    mlflow, _ = configure_mlflow(PROJECT, "autoresearch")
    client = mlflow.tracking.MlflowClient()
    experiment = client.get_experiment_by_name("autoresearch")
    runs = client.search_runs(
        [experiment.experiment_id], "tags.description LIKE '#69 confirm%'", order_by=["start_time ASC"]
    )
    groups: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        score = run.data.metrics.get("best_val_macro_f1")
        if score is not None:
            groups[run.data.tags["description"].split(" seed ")[0]].append(score)
    return [(name, scores) for name, scores in groups.items() if len(scores) >= 2]


def seed_label(name: str) -> str:
    return "fixed 25 epochs" if re.search(r"\bepochs\b", name) else "10-minute clock"


def plot(rows: list[dict], seed_checks: list[tuple[str, list[float]]], output: Path) -> None:
    start = next(row["number"] for row in rows if row["description"] == BASELINE)
    rows = [row for row in rows if row["number"] >= start]
    kept = [row for row in rows if row["status"] == "keep" or row["number"] == start]
    scored = [row for row in rows if row["score"] is not None and row["score"] >= COLLAPSED_BELOW]
    failed = [row for row in rows if row not in scored]
    best_line_x, best_line_y = [], []
    best = None
    for row in rows:
        if row in kept:
            best = row["score"]
        best_line_x.append(row["number"])
        best_line_y.append(best)
    last = rows[-1]["number"]

    fig, axis = plt.subplots(figsize=(14, 7), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    axis.set_facecolor("#fcfcfb")
    floor = 0.80
    axis.set_ylim(floor - 0.012, 0.94)
    axis.set_xlim(start - 1, last + 2 + 2.2 * len(seed_checks))

    axis.axhline(PYTORCH_BASELINE, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    axis.text(last, PYTORCH_BASELINE + 0.0015, "PyTorch baseline, full length (#67)",
              color=INK_SECONDARY, fontsize=8.5, ha="right", va="bottom")

    axis.scatter([r["number"] for r in scored if r not in kept], [r["score"] for r in scored if r not in kept],
                 s=22, color=DISCARDED, zorder=2, label="Discarded")
    axis.scatter([r["number"] for r in failed], [floor - 0.006] * len(failed), marker="x", s=30,
                 color=INK_MUTED, linewidths=1.5, zorder=2, clip_on=False,
                 label="Crashed or collapsed (F1 ≈ 0, pinned to axis)")
    axis.step(best_line_x, best_line_y, where="post", color=KEPT, linewidth=2, zorder=3, label="Running best")
    axis.scatter([r["number"] for r in kept], [r["score"] for r in kept], s=64, color=KEPT,
                 edgecolors="#fcfcfb", linewidths=2, zorder=4, label="Kept")
    for row in kept:
        text = "baseline" if row["number"] == start else row["description"]
        axis.annotate(text, (row["number"], row["score"]), xytext=(6, 6), textcoords="offset points",
                      rotation=28, fontsize=8.5, color=INK_SECONDARY, ha="left", va="bottom")

    for index, (name, scores) in enumerate(seed_checks):
        x = last + 2 + 2.2 * index
        mean = statistics.mean(scores)
        axis.vlines(x, min(scores), max(scores), color=SEEDS, linewidth=6, alpha=0.25, zorder=2)
        axis.scatter([x] * len(scores), scores, s=26, color=SEEDS, zorder=3,
                     label="Winner re-trained, 3 seeds" if index == 0 else None)
        axis.hlines(mean, x - 0.45, x + 0.45, color=SEEDS, linewidth=2, zorder=3)
        axis.text(x, max(scores) + 0.004, f"{seed_label(name)}\nmean {mean:.3f}", color=INK_SECONDARY,
                  fontsize=8.5, ha="center", va="bottom")
    if seed_checks:
        axis.axvline(last + 1, color=GRID, linewidth=1, zorder=0)

    shown = len(rows)
    axis.set_title(f"Autoresearch progress: {shown} experiments, {len(kept) - 1} kept improvements",
                   color=INK, fontsize=13, loc="left", pad=12)
    axis.set_xlabel("Experiment #", color=INK_SECONDARY)
    axis.set_ylabel("Validation macro F1 (higher is better)", color=INK_SECONDARY)
    axis.set_xticks(range(start, last + 1, 2))
    axis.tick_params(colors=INK_SECONDARY, labelsize=9)
    axis.grid(True, color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(INK_MUTED)
    legend = axis.legend(loc="upper left", fontsize=9, frameon=True)
    legend.get_frame().set_edgecolor(GRID)
    for text in legend.get_texts():
        text.set_color(INK_SECONDARY)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output, facecolor=fig.get_facecolor())
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--no-seeds", action="store_true", help="Leave out the MLflow seed re-checks")
    args = parser.parse_args()
    plot(read_results(args.results), [] if args.no_seeds else read_seed_checks(), args.output)


if __name__ == "__main__":
    main()
