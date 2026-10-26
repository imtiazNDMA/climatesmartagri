"""How far the judge can be trusted: agreement between its faithfulness verdicts and people's labels.

Cohen's kappa is agreement corrected for chance: 1 is full agreement, 0 is what guessing would give. Below
MIN_LABELS labels, or below MIN_KAPPA, the judge's grades are shown but do not decide whether a run passed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

MIN_LABELS = 20
MIN_KAPPA = 0.6


def cohens_kappa(pairs: Sequence[tuple[bool, bool]]) -> float | None:
    """Kappa for (human, judge) yes/no pairs; None with no pairs, or when chance agreement is total."""
    n = len(pairs)
    if not n:
        return None
    observed = sum(human == judge for human, judge in pairs) / n
    human_yes = sum(human for human, _ in pairs) / n
    judge_yes = sum(judge for _, judge in pairs) / n
    chance = human_yes * judge_yes + (1 - human_yes) * (1 - judge_yes)
    if math.isclose(chance, 1.0):
        return None
    return (observed - chance) / (1 - chance)


def confusion(pairs: Sequence[tuple[bool, bool]]) -> dict[str, int]:
    return {
        "both_faithful": sum(human and judge for human, judge in pairs),
        "human_only": sum(human and not judge for human, judge in pairs),
        "judge_only": sum(judge and not human for human, judge in pairs),
        "neither": sum(not human and not judge for human, judge in pairs),
    }


@dataclass(frozen=True)
class Calibration:
    labels: int
    kappa: float | None
    confusion: dict[str, int]

    @property
    def calibrated(self) -> bool:
        return self.labels >= MIN_LABELS and self.kappa is not None and self.kappa >= MIN_KAPPA


def calibration(pairs: Sequence[tuple[bool, bool]]) -> Calibration:
    return Calibration(len(pairs), cohens_kappa(pairs), confusion(pairs))
