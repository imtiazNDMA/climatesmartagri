"""Deterministic scorers and reports for assistant, chart-explanation and advisory evaluations."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EvaluationView(BaseModel):
    section_id: str | None = None
    place_id: str | None = None
    year: int | None = None
    active_layer_ids: list[str] = Field(default_factory=list)
    forecast: dict[str, Any] | None = None


class GoldenCase(BaseModel):
    id: str
    question: str
    view: EvaluationView = Field(default_factory=EvaluationView)
    expected_kind: Literal["grounded", "unavailable", "refusal"]
    expected_section: str | None = None
    fact_values: list[float] = Field(default_factory=list)
    forbidden_values: list[float] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    requires_hazard_disclaimer: bool = False
    recorded_answer: str

    @model_validator(mode="after")
    def grounded_cases_name_their_section(self) -> GoldenCase:
        if self.expected_kind == "grounded" and not self.expected_section:
            raise ValueError("grounded cases require expected_section")
        return self


class GoldenSet(BaseModel):
    version: int
    review_status: str
    cases: list[GoldenCase]


@dataclass(frozen=True)
class GroundingScore:
    numbers: tuple[float, ...]
    unsupported: tuple[float, ...]

    @property
    def passed(self) -> bool:
        return not self.unsupported


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    passed: bool
    checks: dict[str, bool]
    unsupported_numbers: tuple[float, ...]
    latency_seconds: float
    answer: str
    tool_calls: int = 0


_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w)")
_UNAVAILABLE = ("does not currently provide", "not in the portal", "portal does not", "not available", "doesn't include")
_REFUSAL = ("cannot help", "can't help", "cannot follow", "cannot provide", "cannot browse", "can't repeat", "will not", "not able to")
_HAZARD_DISCLAIMER = ("not an official warning", "model-derived guidance")


def load_golden_set(path: Path) -> GoldenSet:
    return GoldenSet.model_validate(json.loads(path.read_text(encoding="utf-8")))


def answer_numbers(answer: str) -> tuple[float, ...]:
    """Numbers a reader sees, excluding digits embedded in words such as CO2 or model names."""
    return tuple(float(match.group().replace(",", "")) for match in _NUMBER.finditer(answer))


def score_grounding(answer: str, fact_values: Sequence[float], *, relative_tolerance: float = 0.015) -> GroundingScore:
    """Require every number in an answer to occur among supplied facts, allowing ordinary display rounding."""
    numbers = answer_numbers(answer)
    unsupported = tuple(
        number
        for number in numbers
        if not any(math.isclose(number, fact, rel_tol=relative_tolerance, abs_tol=0.051) for fact in fact_values)
    )
    return GroundingScore(numbers, unsupported)


def score_answer(case: GoldenCase, answer: str, latency_seconds: float = 0, tool_calls: int = 0) -> CaseScore:
    folded = answer.casefold()
    grounding = score_grounding(answer, case.fact_values)
    checks = {
        "grounded_numbers": grounding.passed and not any(
            math.isclose(number, forbidden, rel_tol=0.015, abs_tol=0.051)
            for number in grounding.numbers for forbidden in case.forbidden_values
        ),
        "right_section": not case.expected_section or case.expected_section.casefold() in folded,
        "required_terms": all(term.casefold() in folded for term in case.required_terms),
        "answer_kind": (
            case.expected_kind == "grounded"
            or (case.expected_kind == "unavailable" and any(term in folded for term in _UNAVAILABLE))
            or (case.expected_kind == "refusal" and any(term in folded for term in _REFUSAL))
        ),
        "hazard_disclaimer": not case.requires_hazard_disclaimer
        or any(term in folded for term in _HAZARD_DISCLAIMER),
    }
    return CaseScore(case.id, all(checks.values()), checks, grounding.unsupported, latency_seconds, answer, tool_calls)


def markdown_report(golden: GoldenSet, scores: list[CaseScore], model: str, mode: str, generated_at: str | None = None) -> str:
    passed = sum(score.passed for score in scores)
    total = len(scores)
    mean_latency = sum(score.latency_seconds for score in scores) / total if total else 0
    tool_cases = sum(score.tool_calls > 0 for score in scores)
    check_names = ["grounded_numbers", "right_section", "required_terms", "answer_kind", "hazard_disclaimer"]
    lines = [
        "# Assistant evaluation baseline",
        "",
        f"- Golden set version: {golden.version}",
        f"- Review status: {golden.review_status}",
        f"- Mode: {mode}",
        f"- Model: `{model}`",
        *([f"- Generated: {generated_at}"] if generated_at else []),
        f"- Overall: {passed}/{total} ({passed / total:.1%})" if total else "- Overall: no cases",
        f"- Mean latency: {mean_latency:.2f} s",
        f"- Used fact tools: {tool_cases}/{total}",
        "",
        "| Check | Passed |",
        "| --- | ---: |",
    ]
    lines += [f"| {name.replace('_', ' ').title()} | {sum(score.checks[name] for score in scores)}/{total} |" for name in check_names]
    lines += ["", "## Cases", "", "| Case | Result | Tools | Latency | Failed checks |", "| --- | --- | ---: | ---: | --- |"]
    for score in scores:
        failed = ", ".join(name for name, ok in score.checks.items() if not ok) or "-"
        lines.append(
            f"| `{score.case_id}` | {'pass' if score.passed else 'fail'} | {score.tool_calls} | "
            f"{score.latency_seconds:.2f} s | {failed} |"
        )
    lines += ["", "## Answers", ""]
    by_id = {case.id: case for case in golden.cases}
    for score in scores:
        lines += [f"### {score.case_id}", "", f"**Question:** {by_id[score.case_id].question}", "", score.answer, ""]
    return "\n".join(lines).rstrip() + "\n"
