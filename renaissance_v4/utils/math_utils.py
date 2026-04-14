"""
math_utils.py

Purpose:
Provide reusable deterministic math helpers for RenaissanceV4 feature calculations.

Usage:
Imported by the feature engine and regime classifier.

Version:
v1.0

Change History:
- v1.0 Initial Phase 2 implementation.
"""

from __future__ import annotations

from typing import Iterable


def safe_mean(values: Iterable[float]) -> float:
    """
    Return the arithmetic mean of the provided values.
    Returns 0.0 when the iterable is empty.
    """
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def safe_stddev(values: Iterable[float]) -> float:
    """
    Return a simple population standard deviation.
    Returns 0.0 when the iterable has fewer than 2 items.
    """
    items = list(values)
    if len(items) < 2:
        return 0.0
    mean_value = safe_mean(items)
    variance = sum((item - mean_value) ** 2 for item in items) / len(items)
    return variance**0.5


def ema(values: list[float], period: int) -> float:
    """
    Compute a simple exponential moving average for the provided list.
    Uses the full input list and returns the last EMA value.
    Returns 0.0 when there is no data.
    """
    if not values:
        return 0.0

    multiplier = 2 / (period + 1)
    ema_value = values[0]

    for value in values[1:]:
        ema_value = ((value - ema_value) * multiplier) + ema_value

    return ema_value
