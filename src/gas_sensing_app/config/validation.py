"""Reject invalid experiment inputs before opening instruments."""

import math


def finite(value, name, minimum=0.0, maximum=float("inf")):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(
            f"{name} must be a finite number between {minimum} and {maximum}"
        )
    return float(value)


def flows(raw, ranges):
    if not isinstance(raw, dict):
        raise ValueError("Gas flows must be a channel-to-sccm mapping")
    result = dict.fromkeys(ranges, 0.0)
    for key, value in raw.items():
        channel = int(key)
        if channel not in ranges:
            raise ValueError(f"Unknown gas channel: {channel}")
        result[channel] = finite(value, f"flow {channel}", 0, ranges[channel])
    return result
