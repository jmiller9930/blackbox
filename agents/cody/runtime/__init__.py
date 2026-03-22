"""
Python support layer for Cody (types, guardrails, CLI smoke).

IMPORTANT: This package does NOT define agent behavior. In OpenClaw, behavior
comes from SKILL.md, agent.md, and prompts; Python is for support logic only.
"""

from agents.cody.runtime.contracts import (
    PatchProposal,
    Recommendation,
    RiskLevel,
    TaskItem,
)
from agents.cody.runtime.patch_guard import PatchGuard

__version__ = "0.1.0"

__all__ = [
    "PatchGuard",
    "PatchProposal",
    "Recommendation",
    "RiskLevel",
    "TaskItem",
    "__version__",
]
