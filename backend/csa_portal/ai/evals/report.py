"""The markdown report of one evaluation: a section per dataset, with its summary, scorer rates and cases."""

from __future__ import annotations

from .datasets import Dataset
from .runner import CaseResult, RunOutcome
from .scorers import GATING


def markdown_report(outcomes: list[tuple[Dataset, RunOutcome]]) -> str:
    lines = ["# Assistant evaluation", ""]
    for dataset, outcome in outcomes:
        record, summary = outcome.record, outcome.record.summary
        total = len(outcome.results)
        lines += [
            f"## {dataset.name} (version {dataset.version})",
            "",
            f"- Review status: {dataset.review_status}",
            f"- Mode: {record.mode}, model `{record.model}`, commit `{record.git_sha}`",
            f"- Generated: {record.finished_at.isoformat(timespec='seconds')}",
            f"- Passed every repeat (pass^{record.repeats}): {summary['passed_cases']}/{summary['cases']} "
            f"({summary['pass_rate']:.1%})",
            f"- Flaky: {', '.join(f'`{case_id}`' for case_id in summary['flaky_cases']) or 'none'}",
            f"- Mean latency: {_seconds(summary['mean_latency_seconds'])}, p95: {_seconds(summary['p95_latency_seconds'])}",
            "",
            "| Scorer | Runs passed |",
            "| --- | ---: |",
        ]
        for name in GATING:
            passed = round(summary["scorers"][name] * total)
            lines.append(f"| {name.replace('_', ' ').title()} | {passed}/{total} ({summary['scorers'][name]:.1%}) |")
        lines += ["", "| Case | Repeats | First failure |", "| --- | --- | --- |"]
        by_case: dict[str, list[CaseResult]] = {}
        for result in outcome.results:
            by_case.setdefault(result.case_id, []).append(result)
        for case_id, runs in by_case.items():
            marks = " ".join("pass" if r.passed else "fail" for r in runs)
            lines.append(f"| `{case_id}` | {marks} | {_first_failure(runs)} |")
        lines += ["", "### Answers (first repeat)", ""]
        questions = {case.id: case.question for case in dataset.cases}
        for case_id, runs in by_case.items():
            lines += [f"#### {case_id}", "", f"**Question:** {questions[case_id]}", "", runs[0].answer, ""]
    return "\n".join(lines).rstrip() + "\n"


def _first_failure(runs: list[CaseResult]) -> str:
    for run in runs:
        for name in GATING:
            if run.scores[name].passed is False:
                return f"{name}: {run.scores[name].reason}"
    return "-"


def _seconds(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f} s"
