"""Pydantic models for Cody recommendations, patch proposals, tasks, and risk levels.

Support layer only — agent behavior is defined in SKILL.md, agent.md, and prompts.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk tier for recommendations and patch proposals."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskItem(BaseModel):
    """One actionable unit in a development plan."""

    id: str
    title: str
    description: str = ""
    done: bool = False


class Recommendation(BaseModel):
    """Engineering recommendation aligned with `recommendation_format.md`."""

    title: str
    summary: str
    evidence: str = ""
    proposed_action: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    approval_required: bool = True


class PatchProposal(BaseModel):
    """Describes an intended patch for review; not auto-applied unless policy allows."""

    title: str
    summary: str
    diff: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    requests_auto_apply: bool = False
    unsafe: bool = False
    notes: str = Field(default="", description="Optional reviewer notes.")
