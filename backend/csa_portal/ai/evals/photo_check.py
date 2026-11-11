"""The photo check's evaluation: a set of photos, the answers a model gave, and the bars that decide Auto (#93).

A live run asks the vision model about every photo and records each answer by the photo's hash. Scoring is a pure
function of the set and those answers, so CI, which has no model, replays the recording and checks the report.

Photos come in two parts. `tune` is for working on the prompt. `final` is scored once the prompt is frozen: its
five-crop photos are a sample of the crop disease model's locked test split.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from ...photo_check import QUESTION, SYSTEM_PROMPT, PhotoReading, outcome_of
from .datasets import DATASETS_DIR

EVALUATION_DIR = DATASETS_DIR / "photo_check"
MANIFEST = EVALUATION_DIR / "manifest.csv"
FIELDS = ("id", "part", "group", "crop", "label", "source", "path")

Group = Literal["crop", "other-plant", "not-plant", "poor"]
STOPPED = {"not-a-plant", "unsupported-crop"}


@dataclass(frozen=True)
class Case:
    """One photo. `id` is the SHA-256 of the file. `crop` and `label` are the truth for a five-crop photo; for
    another plant `label` names it. `path` is under the crop data folder for `source` val or test, and under the
    evaluation's own image folder otherwise."""

    id: str
    part: str
    group: str
    crop: str
    label: str
    source: str
    path: str


@dataclass(frozen=True)
class Bar:
    name: str
    value: float
    threshold: float
    at_least: bool
    met: bool


@dataclass
class Report:
    photos: dict[str, int]
    bars: list[Bar]
    ship: bool
    # Per true crop: how many photos were given the right crop, a wrong one, handed back, or refused.
    crop_outcomes: dict[str, dict[str, int]]
    # Wrong-crop answers as "true crop -> crop named".
    confusions: dict[str, int]
    quality_raised_on_poor: float | None
    quality_raised_on_clean: float | None
    hand_macro_f1: float | None = None
    auto_macro_f1: float | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2) + "\n"


@dataclass
class RecordedRun:
    model: str
    prompt_sha256: str
    readings: dict[str, PhotoReading]
    # Photo path -> the class the classifier named when the true crop was hand-picked.
    hand_predictions: dict[str, str] = field(default_factory=dict)
    # True for the run whose prompt the portal ships with.
    shipping: bool = False


def prompt_sha256() -> str:
    """Everything the model is told: the instructions, the question and the shape with its field descriptions."""
    shape = json.dumps(PhotoReading.model_json_schema(), sort_keys=True)
    return hashlib.sha256(f"{SYSTEM_PROMPT}\n---\n{QUESTION}\n---\n{shape}".encode()).hexdigest()


def load_cases(path: Path = MANIFEST) -> list[Case]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as file:
        return [Case(**{name: row[name] for name in FIELDS}) for row in csv.DictReader(file)]


def save_cases(cases: list[Case], path: Path = MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(case) for case in cases)


def load_readings(path: Path) -> RecordedRun:
    body = json.loads(path.read_text(encoding="utf-8"))
    return RecordedRun(
        model=body["model"], prompt_sha256=body["prompt_sha256"],
        readings={key: PhotoReading.model_validate(value) for key, value in body["readings"].items()},
        hand_predictions=body.get("hand_predictions", {}), shipping=body.get("shipping", False),
    )


def save_readings(path: Path, run: RecordedRun) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "model": run.model, "prompt_sha256": run.prompt_sha256, "shipping": run.shipping,
        "readings": {key: run.readings[key].model_dump() for key in sorted(run.readings)},
        "hand_predictions": dict(sorted(run.hand_predictions.items())),
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def macro_f1(truth: list[str], predicted: list[str]) -> float:
    """The mean F1 over the classes that occur in `truth`."""
    scores = []
    for name in sorted(set(truth)):
        hits = sum(t == name and p == name for t, p in zip(truth, predicted))
        named = sum(p == name for p in predicted)
        actual = sum(t == name for t in truth)
        scores.append(2 * hits / (named + actual) if hits else 0.0)
    return sum(scores) / len(scores)


def score(cases: list[Case], readings: dict[str, PhotoReading], hand_predictions: dict[str, str] | None = None) -> Report:
    """The report for `cases`. Every case must have a reading. `hand_predictions`, when given, adds what the
    classifier scores through Auto beside what it scores when the true crop is hand-picked."""
    missing = [case.id for case in cases if case.id not in readings]
    if missing:
        raise KeyError(f"{len(missing)} photos have no recorded answer, the first being {missing[0]}")
    outcomes = {case.id: outcome_of(readings[case.id]) for case in cases}
    by_group = {group: [c for c in cases if c.group == group] for group in ("crop", "other-plant", "not-plant", "poor")}

    def kind(case: Case) -> str:
        outcome = outcomes[case.id]
        if outcome.status in STOPPED:
            return "stopped"
        if outcome.status == "crop-unclear":
            return "unclear"
        return "right" if outcome.identified_crop == case.crop else "wrong-crop"

    crops = by_group["crop"]
    kinds = {case.id: kind(case) for case in crops}
    crop_outcomes: dict[str, dict[str, int]] = {}
    for case in crops:
        crop_outcomes.setdefault(case.crop, {"right": 0, "wrong-crop": 0, "unclear": 0, "stopped": 0})[kinds[case.id]] += 1
    confusions = Counter(
        f"{case.crop} -> {outcomes[case.id].identified_crop}" for case in crops if kinds[case.id] == "wrong-crop"
    )

    def share(group: list[Case], test) -> float | None:
        return sum(test(case) for case in group) / len(group) if group else None

    def stopped(case: Case) -> bool:
        return outcomes[case.id].status in STOPPED

    bars: list[Bar] = []

    def add(name: str, value: float | None, threshold: float, at_least: bool) -> None:
        if value is not None:
            bars.append(Bar(name, round(value, 4), threshold, at_least, value >= threshold if at_least else value <= threshold))

    add("crop-identification", share(crops, lambda c: kinds[c.id] == "right"), 0.97, True)
    add("false-stops", share(crops, stopped), 0.02, False)
    add("non-plant-stopped", share(by_group["not-plant"], stopped), 0.95, True)
    add("unsupported-plant-stopped", share(by_group["other-plant"], stopped), 0.85, True)

    hand_f1 = auto_f1 = None
    scored = [case for case in crops if hand_predictions and case.path in hand_predictions]
    if scored:
        truth = [case.label for case in scored]
        hand = [hand_predictions[case.path] for case in scored]
        # Through Auto: the right crop or a reader-named one gets the same classifier answer; the wrong
        # classifier can only name another crop's class, and a stopped photo gets no answer at all.
        auto = [
            hand_predictions[case.path] if kinds[case.id] in {"right", "unclear"} else f"({kinds[case.id]})"
            for case in scored
        ]
        hand_f1, auto_f1 = round(macro_f1(truth, hand), 4), round(macro_f1(truth, auto), 4)
        add("auto-macro-f1-drop", hand_f1 - auto_f1, 0.02, False)

    def flagged(case: Case) -> bool:
        return bool(outcomes[case.id].quality)

    return Report(
        photos={group: len(members) for group, members in by_group.items()},
        bars=bars,
        # Auto needs every bar, and the classifier comparison cannot be left out.
        ship=bool(bars) and all(bar.met for bar in bars) and hand_f1 is not None,
        crop_outcomes=crop_outcomes,
        confusions=dict(sorted(confusions.items())),
        quality_raised_on_poor=share(by_group["poor"], flagged),
        quality_raised_on_clean=share(crops, flagged),
        hand_macro_f1=hand_f1,
        auto_macro_f1=auto_f1,
    )
