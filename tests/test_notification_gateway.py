"""Notification gateway — message shape, tiers, and length (no live SMS in CI)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.notification_gateway.messages import (
    format_system_notification,
    format_trade_notification,
    format_training_notification,
)
from modules.notification_gateway.recipients import normalize_to_e164


def test_trade_message_compact() -> None:
    t = format_trade_notification(
        lane="paper",
        action="SELL",
        symbol="SOL-PERP",
        qty="0.5",
        price="142.30",
        venue="drift",
        ref="apr-test-1",
        status="submitted",
        ts_utc="2026-04-02T12:00:00+00:00",
        account="user_prod_1234",
        tier=1,
    )
    assert "BLACKBOX · T1 · TRADE · paper" in t
    assert "SELL" in t and "SOL" in t
    assert "When:" in t
    assert len(t) < 600


def test_system_message_compact() -> None:
    s = format_system_notification(
        severity="WARN",
        component="gateway",
        summary="connection refused",
        host="https://example/gw/",
        check="gateway",
        ts_utc="2026-04-02T12:00:00+00:00",
        trace_id="tr-abc",
        source_agent="DATA",
        tier=2,
    )
    assert "BLACKBOX · T2 · ALERT · WARN" in s
    assert "Who: DATA" in s
    assert "Where:" in s
    assert len(s) < 600


def test_training_message_compact() -> None:
    t = format_training_notification(
        event_kind="GRADUATION",
        summary="Phase 2 complete",
        detail="All gates passed",
        metric="score 0.94",
        ts_utc="2026-04-02T12:00:00+00:00",
        tier=3,
    )
    assert "BLACKBOX · T3 · ANNA · TRAINING" in t
    assert "GRADUATION" in t
    assert "Metric:" in t
    assert len(t) < 600


def test_normalize_e164_us() -> None:
    assert normalize_to_e164("4807203454") == "+14807203454"
    assert normalize_to_e164("480-720-8491") == "+14807208491"
    assert normalize_to_e164("+14807208491") == "+14807208491"


def test_deliver_mode_off_no_crash(monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_NOTIFY_MODE", "off")
    from modules.notification_gateway.deliver import send_sms

    ok, reason = send_sms("+15550001", "test", tier=1)
    assert not ok
    assert "off" in reason.lower() or "notify" in reason.lower()


def test_tier_three_filtered_when_sms_tiers_exclude_it(monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_NOTIFY_SMS_TIERS", "1,2")
    monkeypatch.setenv("BLACKBOX_NOTIFY_DISTRO", "+15550001")
    from modules.notification_gateway import notify_training_milestone

    ok, msg = notify_training_milestone(summary="phase done")
    assert not ok
    assert "sms_tier_filtered" in msg


def test_trade_routine_downgrades_to_t3_when_env_on(monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_NOTIFY_TRADE_ROUTINE_TIER", "yes")
    from modules.notification_gateway.tiers import resolve_trade_tier

    assert resolve_trade_tier(status="filled", tier_override=None) == 3
    assert resolve_trade_tier(status="reject loss", tier_override=None) == 1


def test_parse_sms_tiers_default(monkeypatch) -> None:
    monkeypatch.delenv("BLACKBOX_NOTIFY_SMS_TIERS", raising=False)
    from modules.notification_gateway.tiers import parse_sms_allowed_tiers

    assert parse_sms_allowed_tiers() == {1, 2, 3}
