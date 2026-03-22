"""Tests for default-deny auto-apply rules on patch proposals."""

from __future__ import annotations

import pytest

from agents.cody.runtime.contracts import PatchProposal, RiskLevel
from agents.cody.runtime.patch_guard import PatchGuard


@pytest.fixture
def guard() -> PatchGuard:
    return PatchGuard()


def test_high_risk_auto_apply_blocked(guard: PatchGuard) -> None:
    p = PatchProposal(
        title="High-risk change",
        summary="Touches auth boundary.",
        risk_level=RiskLevel.HIGH,
        requests_auto_apply=True,
    )
    assert guard.allows_auto_apply(p) is False


def test_critical_risk_auto_apply_blocked(guard: PatchGuard) -> None:
    p = PatchProposal(
        title="Critical change",
        summary="Data migration.",
        risk_level=RiskLevel.CRITICAL,
        requests_auto_apply=True,
    )
    assert guard.allows_auto_apply(p) is False


def test_unsafe_flag_blocks_even_if_low_risk(guard: PatchGuard) -> None:
    p = PatchProposal(
        title="Unsafe edit",
        summary="Flagged by reviewer.",
        risk_level=RiskLevel.LOW,
        unsafe=True,
        requests_auto_apply=True,
    )
    assert guard.allows_auto_apply(p) is False


def test_no_auto_apply_request_is_not_allowed(guard: PatchGuard) -> None:
    p = PatchProposal(
        title="Manual workflow",
        summary="No automatic application requested.",
        risk_level=RiskLevel.LOW,
        requests_auto_apply=False,
    )
    assert guard.allows_auto_apply(p) is False
