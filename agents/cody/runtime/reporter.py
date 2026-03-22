"""Serializes `Recommendation` models to Markdown using Jinja2 templates."""

from __future__ import annotations

from jinja2 import Template

from agents.cody.runtime.contracts import Recommendation

_RECOMMENDATION_MD = Template(
    """## {{ title }}

**Summary:** {{ summary }}

**Evidence:** {{ evidence }}

**Proposed action:** {{ proposed_action }}

**Risk:** {{ risk_level.value }}
**Approval required:** {{ approval_required }}
"""
)


def recommendation_to_markdown(rec: Recommendation) -> str:
    """Render a recommendation as review-ready Markdown."""
    return _RECOMMENDATION_MD.render(
        title=rec.title,
        summary=rec.summary,
        evidence=rec.evidence,
        proposed_action=rec.proposed_action,
        risk_level=rec.risk_level,
        approval_required="yes" if rec.approval_required else "no",
    )
