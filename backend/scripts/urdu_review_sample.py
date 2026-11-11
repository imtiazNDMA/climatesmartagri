"""Write the review sheet a native Urdu reader fills in before #10 closes: a sample of recorded Urdu answers.

    uv run python backend/scripts/urdu_review_sample.py
    uv run python backend/scripts/urdu_review_sample.py --count 20 --output docs/evaluations/assistant-urdu-review.md

Answers come from the golden_ur cassettes (the first repeat of the last live recorded run). The sample takes one case
from each section or kind of answer in turn, so it covers every section, the unavailable and refusal answers and the
hazard disclaimer before it takes a second of anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from csa_portal.ai.evals.cassettes import CASSETTES_DIR, cassette_path, load_cassette  # noqa: E402
from csa_portal.ai.evals.datasets import Dataset, EvalCase, load_dataset  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "evaluations" / "assistant-urdu-review.md"
PANEL_TEXT = ROOT / "frontend" / "src" / "components" / "assistantLanguage.ts"

CHECKS = (
    "Reads as natural Urdu",
    "Agricultural and technical terms are correct",
    "Numbers, units and place names are easy to read",
    "Nothing misleading or unsafe (advice, warnings, refusals)",
)


def _group(case: EvalCase) -> str:
    return case.expected_section or case.expected_kind


def pick(cases: list[EvalCase], answered: set[str], count: int) -> list[EvalCase]:
    """Up to `count` answered cases, one from each group in turn, each group in dataset order."""
    groups: dict[str, list[EvalCase]] = {}
    for case in cases:
        if case.id in answered:
            groups.setdefault(_group(case), []).append(case)
    picked: list[EvalCase] = []
    while len(picked) < count and any(groups.values()):
        for members in groups.values():
            if members and len(picked) < count:
                picked.append(members.pop(0))
    return picked


def _answer(path: Path) -> str | None:
    turns = load_cassette(path) if path.exists() else []
    return next((turn.text for turn in reversed(turns) if turn.text), None)


def _panel_words() -> list[str]:
    """The panel's Urdu strings, as written in the frontend, so the reviewer checks those too."""
    if not PANEL_TEXT.exists():
        return []
    text = PANEL_TEXT.read_text(encoding="utf-8")
    urdu = text[text.index("  ur: {"):]
    return [line.strip().rstrip(",") for line in urdu.splitlines() if any("؀" <= ch <= "ۿ" for ch in line)]


def review_sheet(urdu: Dataset, english: Dataset, cassettes: Path, count: int) -> str:
    answers = {case.id: _answer(cassette_path(urdu.name, case.id, cassettes)) for case in urdu.cases}
    sample = pick(urdu.cases, {case_id for case_id, text in answers.items() if text}, count)
    questions = {case.id: case.question for case in english.cases}
    lines = [
        "# Urdu answers: native reader review",
        "",
        f"A sample of {len(sample)} answers from the portal guide in Urdu, for #10. They are the recorded answers of "
        f"the `{urdu.name}` evaluation set (version {urdu.version}) on the local model. For each answer, tick the "
        "checks that hold and note anything to change: wording, terms, or a figure that reads wrongly.",
        "",
        "Figures come from the portal's data; the evaluation has already checked that each number is one the "
        "portal holds. What needs a native reader is the language.",
        "",
        "- Reviewer:",
        "- Date:",
        "- Overall verdict (fit for readers / fit after the noted changes / not yet):",
        "",
        "## Answers",
        "",
    ]
    for number, case in enumerate(sample, 1):
        lines += [
            f"### {number}. `{case.id}` ({_group(case)})",
            "",
            f"**Question (Urdu):** {case.question}",
            "",
            f"**Question (English original):** {questions.get(case.id, '-')}",
            "",
            "**Answer:**",
            "",
            *[f"> {line}" if line else ">" for line in (answers[case.id] or "").splitlines()],
            "",
            *[f"- [ ] {check}" for check in CHECKS],
            "",
            "Notes:",
            "",
        ]
    words = _panel_words()
    if words:
        lines += ["## The panel's own words", "", "Labels and messages the panel shows around answers in Urdu.", ""]
        lines += [f"- {word}" for word in words]
        lines += ["", "- [ ] All of these read naturally", "", "Notes:", ""]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--cassettes", type=Path, default=CASSETTES_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    sheet = review_sheet(load_dataset("golden_ur"), load_dataset("golden"), args.cassettes, args.count)
    args.output.write_text(sheet, encoding="utf-8", newline="\n")
    print(f"{sheet.count(chr(10) + '### ')} answers written to {args.output}")


if __name__ == "__main__":
    main()
