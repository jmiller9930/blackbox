"""Structured types for the Cody support layer: RiskLevel, Recommendation, PatchProposal.

Optional: TaskItem — small struct used by `planner.py` for ordered steps.

Support layer only — agent behavior is defined in SKILL.md, agent.md, and prompts.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class RiskLevel(str, Enum):
    """Risk tier for recommendations and patch proposals."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Recommendation(BaseModel):
    """Engineering recommendation (align fields with `recommendation_format.md`)."""

    title: str
    summary: str
    evidence: str = ""
    proposed_action: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    approval_required: bool = True


class PatchProposal(BaseModel):
    """Patch intent for human review; not auto-applied by default."""

    title: str
    summary: str
    diff: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    requests_auto_apply: bool = False
    unsafe: bool = False
    notes: str = ""


class TaskItem(BaseModel):
    """One row in a simple task list (used by `planner.get_next_steps`)."""

    id: str
    title: str
    description: str = ""
    done: bool = False
