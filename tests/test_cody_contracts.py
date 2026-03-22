"""Unit tests for Cody Pydantic contracts."""

from __future__ import annotations

from agents.cody.runtime.contracts import (
    PatchProposal,
    Recommendation,
    RiskLevel,
    TaskItem,
)


def test_recommendation_instantiation() -> None:
    r = Recommendation(
        title="Add tests",
        summary="Increase coverage on runtime contracts.",
        evidence="agents/cody/runtime/contracts.py",
        proposed_action="Add unit tests for model validation edge cases.",
        risk_level=RiskLevel.LOW,
        approval_required=True,
    )
    assert r.title == "Add tests"
    assert r.risk_level is RiskLevel.LOW
    assert r.approval_required is True


def test_patch_proposal_instantiation() -> None:
    p = PatchProposal(
        title="Refactor reporter",
        summary="Clarify markdown template boundaries.",
        diff="--- a/x\n+++ b/x\n",
        risk_level=RiskLevel.MEDIUM,
        requests_auto_apply=False,
    )
    assert p.diff.startswith("---")
    assert p.requests_auto_apply is False


def test_task_item_instantiation() -> None:
    t = TaskItem(id="1", title="Wire CI", description="Add workflow", done=False)
    assert t.id == "1"
    assert t.done is False


def test_risk_level_values() -> None:
    assert RiskLevel.HIGH.value == "high"
