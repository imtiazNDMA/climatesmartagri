"""Frost severity from surface temperature: how far below zero, and for how long."""

from __future__ import annotations

import numpy as np


def degree_hours_below(stack: np.ndarray, step_hours: np.ndarray, params: dict[str, float]) -> np.ndarray:
    """Accumulated degree-hours below a base temperature over a window of times.

    `stack` is (times, rows, cols) of degrees Celsius; `step_hours` is (times,) of the
    hours each reading stands for. A place one degree below zero for six hours scores 6.
    """
    base = params.get("base_c", 0.0)
    cold = np.clip(base - stack, 0.0, None)
    return (cold * step_hours[:, None, None]).sum(axis=0)
