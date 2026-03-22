"""Maps risk labels to whether human approval is required before changes ship."""

from __future__ import annotations


def requires_human_approval(risk_label: str) -> bool:
    """
    Return True when the labeled tier needs explicit human approval.

    Informational labels skip approval; all other tiers require it.
    """
    normalized = risk_label.strip().lower()
    if normalized in {"info", "informational"}:
        return False
    return True
