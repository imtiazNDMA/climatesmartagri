"""Evaluation datasets: versioned JSON in backend/evaluations, one file per dataset, one case per line."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATASETS_DIR = Path(__file__).resolve().parents[3] / "evaluations"


class _Strict(BaseModel):
    # A misspelt field would otherwise be dropped and its check silently skipped.
    model_config = ConfigDict(extra="forbid")


class ExpectedTool(_Strict):
    """A tool call the agent should make. Each listed argument must match what the agent sent: a string matches
    ignoring case as part of the sent value ("Faisalabad" matches "Faisalabad district"); a number by value."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class CaseMessage(_Strict):
    role: Literal["user", "assistant"]
    content: str


class CaseView(_Strict):
    section_id: str | None = None
    place_id: str | None = None
    year: int | None = None
    active_layer_ids: list[str] = Field(default_factory=list)


class EvalCase(_Strict):
    id: str
    question: str
    view: CaseView = Field(default_factory=CaseView)
    # Earlier turns of the conversation, as the panel would send them (untrusted).
    history: list[CaseMessage] = Field(default_factory=list)
    # grounded: answers from portal facts; unavailable: says the portal does not hold it; refusal: declines;
    # any: no particular kind of answer, only grounding and safety matter.
    expected_kind: Literal["grounded", "unavailable", "refusal", "any"]
    expected_section: str | None = None
    # Numbers the answer may quote; filled from what the agent is shown by backend/scripts/fill_eval_facts.py.
    fact_values: list[float] = Field(default_factory=list)
    forbidden_values: list[float] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    requires_hazard_disclaimer: bool = False
    expected_tools: list[ExpectedTool] = Field(default_factory=list)
    max_tool_calls: int = 4

    @model_validator(mode="after")
    def grounded_cases_name_their_section(self) -> EvalCase:
        if self.expected_kind == "grounded" and not self.expected_section:
            raise ValueError("grounded cases require expected_section")
        return self


class Dataset(_Strict):
    name: str
    version: int
    review_status: str
    # The language the assistant is asked to answer in for every case.
    language: Literal["en", "ur"] = "en"
    cases: list[EvalCase]

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> Dataset:
        ids = [case.id for case in self.cases]
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        if duplicates:
            raise ValueError("duplicate case ids: " + ", ".join(duplicates))
        return self


def dataset_path(name: str, directory: Path = DATASETS_DIR) -> Path:
    return directory / f"assistant_{name}.json"


def load_dataset(name: str, directory: Path = DATASETS_DIR) -> Dataset:
    return Dataset.model_validate(json.loads(dataset_path(name, directory).read_text(encoding="utf-8")))


def dump_dataset(dataset: Dataset) -> str:
    """The dataset as JSON with one case per line and defaults left out, so a diff shows one line per case."""
    head = {key: getattr(dataset, key) for key in ("name", "version", "review_status")}
    if dataset.language != "en":
        head["language"] = dataset.language
    lines = [json.dumps(case.model_dump(mode="json", exclude_defaults=True), ensure_ascii=False) for case in dataset.cases]
    body = ",\n".join(f"    {line}" for line in lines)
    fields = ",\n".join(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}" for key, value in head.items())
    return f"{{\n{fields},\n  \"cases\": [\n{body}\n  ]\n}}\n"
