"""Grounding helpers shared by the assistant and its evaluation: the numbers an answer states, and whether each
one is among the facts it was given."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingScore:
    numbers: tuple[float, ...]
    unsupported: tuple[float, ...]

    @property
    def passed(self) -> bool:
        return not self.unsupported


_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w)")
# "1.", "2)" or "(3)" opening a line numbers a list; it is not a figure.
_LIST_MARKER = re.compile(r"(?m)^[ \t]*(?:\d{1,2}[.)]|\(\d{1,2}\))[ \t]+")
# A number in the first cell of a Markdown table is a row ordinal, not a factual claim.
_TABLE_ORDINAL = re.compile(r"(?m)^[ \t]*\|[ \t]*\d{1,2}[ \t]*\|")


def answer_numbers(answer: str) -> tuple[float, ...]:
    """Numbers a reader sees, excluding digits embedded in words such as CO2 or model names, and list numbering."""
    text = _TABLE_ORDINAL.sub("|", _LIST_MARKER.sub("", answer))
    return tuple(float(match.group().replace(",", "")) for match in _NUMBER.finditer(text))


def score_grounding(answer: str, fact_values: Sequence[float], *, relative_tolerance: float = 0.015) -> GroundingScore:
    """Require every number in an answer to occur among supplied facts, allowing ordinary display rounding."""
    numbers = answer_numbers(answer)
    unsupported = tuple(
        number
        for number in numbers
        if not any(math.isclose(number, fact, rel_tol=relative_tolerance, abs_tol=0.051) for fact in fact_values)
    )
    return GroundingScore(numbers, unsupported)
