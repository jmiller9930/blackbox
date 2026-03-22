"""Builds `Recommendation` instances for tests, demos, and tooling.

Support layer only — not agent behavior. Recommendation rules live in SKILL.md / prompts.
"""

from __future__ import annotations

from agents.cody.runtime.contracts import Recommendation, RiskLevel


def sample_recommendation() -> Recommendation:
    """Return a minimal valid `Recommendation` for integration tests and demos."""
    return Recommendation(
        title="Standardize recommendation format",
        summary="Route substantive outputs through `recommendation_format.md` for consistent review.",
        evidence="agents/cody/prompts/recommendation_format.md",
        proposed_action="Use the shared fields (title, summary, evidence, action, risk, approval) for new docs.",
        risk_level=RiskLevel.LOW,
        approval_required=False,
    )
