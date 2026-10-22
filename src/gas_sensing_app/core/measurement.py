"""Instrument-neutral readings; missing quantities are never represented as zero."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    resistance: float | None = None
    voltage: float | None = None
    current: float | None = None
    status: str = "ok"
    resistance_range: float | None = None


def measured(value: str | float) -> float | None:
    number = float(value)
    return number if math.isfinite(number) and abs(number) < 9e36 else None
