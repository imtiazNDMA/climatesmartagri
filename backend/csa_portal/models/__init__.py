"""Pure functions that turn stacks of forecast values into agricultural indices."""

from __future__ import annotations

from typing import Any

from .frost import degree_hours_below

COMPUTES: dict[str, Any] = {
    "frost_degree_hours": degree_hours_below,
}
