"""
RMv2 (Reasoning Module v2) — self-contained package under ``agent_lab/rmv2``.

- ``engine``: LangGraph pipeline, ToT, guard rails, ``ReasoningModule`` API.
- ``memory_index``: SQLite learning-memory index and optional context snapshots.

Import::

    from rmv2 import ReasoningModule, RMConfig
"""

from rmv2.engine import (
    ReasoningModule,
    RMConfig,
    RMDecision,
    RMState,
    apply_guard_rails,
    compute_r_multiple,
    compute_stop_target,
    node_feature_extraction,
    node_guard_rails,
    node_quality_retrieval,
    node_tot_reasoning,
    run_llm_test,
    run_self_test,
)

__all__ = [
    "ReasoningModule",
    "RMConfig",
    "RMDecision",
    "RMState",
    "apply_guard_rails",
    "compute_r_multiple",
    "compute_stop_target",
    "node_feature_extraction",
    "node_guard_rails",
    "node_quality_retrieval",
    "node_tot_reasoning",
    "run_llm_test",
    "run_self_test",
]
