"""Enforces default-deny rules for automatic application of patch proposals."""

from __future__ import annotations

from agents.cody.runtime.contracts import PatchProposal, RiskLevel


class PatchGuard:
    """Evaluates whether a patch may be auto-applied; defaults to deny."""

    def allows_auto_apply(self, proposal: PatchProposal) -> bool:
        if proposal.unsafe:
            return False
        if proposal.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return False
        if not proposal.requests_auto_apply:
            return False
        return False
