"""
Quantitative Evaluation Layer (QEL)

Authoritative sideline evaluation, survival checkpoints, lifecycle, and promotion
readiness use the **execution ledger** SQLite DB (not ``paper_trades.jsonl``).

Checkpoint control outputs are binary only: ``survive`` | ``drop``. When data is
insufficient for a checkpoint, that checkpoint is skipped for this run (no row).
"""

from __future__ import annotations

from .constants import (
    QEL_ENGINE_VERSION,
    QEL_SUBSYSTEM_NAME,
)
from .hypothesis_hash import normalized_hypothesis_hash
from .lifecycle import (
    apply_strategy_transition,
    create_survival_test,
    ensure_strategy_registered_for_qel,
    get_strategy_lifecycle_state,
    validate_experiment_to_test_prerequisites,
)
from .runtime import run_qel_survival_tick
from .survival_engine import run_survival_checkpoints_for_test

__all__ = [
    "QEL_ENGINE_VERSION",
    "QEL_SUBSYSTEM_NAME",
    "apply_strategy_transition",
    "create_survival_test",
    "ensure_strategy_registered_for_qel",
    "get_strategy_lifecycle_state",
    "normalized_hypothesis_hash",
    "run_qel_survival_tick",
    "run_survival_checkpoints_for_test",
    "validate_experiment_to_test_prerequisites",
]
