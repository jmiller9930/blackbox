"""
GT_DIRECTIVE_026AI — unified agent boundary (Student reasoning router; local primary, optional OpenAI review).

Existing modules stay in place; new router code lives here only.
"""

from __future__ import annotations

from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1 import load_reasoning_router_config_v1
from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_v1 import apply_unified_reasoning_router_v1

__all__ = [
    "apply_unified_reasoning_router_v1",
    "load_reasoning_router_config_v1",
]
