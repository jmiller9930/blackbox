"""
Backward-compatible entry point for RMv2.

Implementation is organized under ``agent_lab/rmv2/`` (engine + memory_index).
Prefer: ``from rmv2 import ReasoningModule, RMConfig``.
"""

from __future__ import annotations

from rmv2 import (
    RMConfig,
    RMDecision,
    RMState,
    ReasoningModule,
    apply_guard_rails,
    compute_r_multiple,
    compute_stop_target,
    run_llm_test,
    run_self_test,
)
from rmv2.engine import main

__all__ = [
    "RMConfig",
    "RMDecision",
    "RMState",
    "ReasoningModule",
    "apply_guard_rails",
    "compute_r_multiple",
    "compute_stop_target",
    "run_llm_test",
    "run_self_test",
    "main",
]
