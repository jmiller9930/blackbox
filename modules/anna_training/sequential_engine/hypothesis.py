"""Hypothesis = pattern + test binding; uses QEL-compatible canonical hash."""

from __future__ import annotations

from typing import Any

from modules.anna_training.quantitative_evaluation_layer.hypothesis_hash import normalized_hypothesis_hash


def hypothesis_hash(hypothesis: dict[str, Any]) -> str:
    return normalized_hypothesis_hash(hypothesis)
