"""
walk_forward.py

Purpose:
Phase 9 — deterministic train/validation splits for walk-forward research (anti-overfit).

Usage:
Split ordered bar rows or feature rows; train on prefix, validate on suffix.

Version:
v1.0

Change History:
- v1.0 Initial Phase 9 scaffold (phase8_to_11 pack).
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def split_data(data: list[T], split: float = 0.7) -> tuple[list[T], list[T]]:
    """
    Split a sequence at ``split`` fraction (default 70% train, 30% validation).
    """
    if not data:
        return [], []
    pivot = int(len(data) * split)
    pivot = max(0, min(pivot, len(data)))
    return data[:pivot], data[pivot:]
