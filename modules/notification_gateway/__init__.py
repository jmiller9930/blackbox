"""
BLACK BOX → phone notification gateway (SMS via Twilio or HTTPS webhook).

Priority tiers (SMS gating via BLACKBOX_NOTIFY_SMS_TIERS):
  1 — Trading / execution (notify_trade; optional routine → T3 if env allows)
  2 — System / availability (notify_system, notify_system_from_health)
  3 — General / agents (notify_training_milestone)

Env:
  BLACKBOX_NOTIFY_MODE=off|twilio|webhook
  BLACKBOX_NOTIFY_SMS_TIERS=1,2,3  — subset allowed to send SMS (default all)
  BLACKBOX_NOTIFY_TRADE_ROUTINE_TIER=3  — downgrade benign trade statuses to tier 3
  BLACKBOX_NOTIFY_PHONE_E164=+15551234567  — legacy single recipient
  BLACKBOX_NOTIFY_DISTRO=+1...,+1...  — comma-separated E.164 (overrides JSON)
  BLACKBOX_NOTIFY_RECIPIENTS_PATH=/path/to/recipients.json
  config/notification_recipients.local.json — optional gitignored distro (name + phone)
  BLACKBOX_NOTIFY_SYSTEM=1  — optional: SMS when DATA health writes an alert

Twilio: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER

Webhook: BLACKBOX_NOTIFY_WEBHOOK_URL, optional BLACKBOX_NOTIFY_WEBHOOK_SECRET
Webhook JSON includes optional \"tier\" (integer) for routing.
"""

from __future__ import annotations

import os

from .deliver import default_to_e164, delivery_mode, send_sms, send_sms_to_targets
from .messages import (
    format_system_notification,
    format_trade_notification,
    format_training_notification,
)
from .recipients import resolve_recipient_targets
from .tiers import NotificationTier, parse_sms_allowed_tiers, resolve_trade_tier, tier_allowed_sms

__all__ = [
    "notify_trade",
    "notify_system",
    "notify_system_from_health",
    "notify_training_milestone",
    "NotificationTier",
    "parse_sms_allowed_tiers",
    "resolve_trade_tier",
    "tier_allowed_sms",
    "format_trade_notification",
    "format_system_notification",
    "format_training_notification",
    "send_sms",
    "send_sms_to_targets",
    "delivery_mode",
    "default_to_e164",
    "resolve_recipient_targets",
]


def _targets_for_send(to_e164: str | None) -> list[tuple[str, str]]:
    if to_e164 and to_e164.strip():
        return [("direct", to_e164.strip())]
    return resolve_recipient_targets()


def _dispatch_sms(
    targets: list[tuple[str, str]],
    body: str,
    tier: int,
) -> tuple[bool, str]:
    if not tier_allowed_sms(tier):
        return False, f"sms_tier_filtered:tier={tier}"
    results = send_sms_to_targets(targets, body, tier=tier)
    ok_any = any(r[0] for r in results)
    summary_out = ";".join(f"{r[2]}:{r[1]}" for r in results)
    return ok_any, summary_out


def notify_trade(
    *,
    to_e164: str | None = None,
    lane: str = "paper",
    action: str = "?",
    symbol: str = "?",
    qty: str | None = None,
    price: str | None = None,
    venue: str | None = None,
    ref: str | None = None,
    status: str = "update",
    ts_utc: str | None = None,
    account: str | None = None,
    tier: int | None = None,
) -> tuple[bool, str]:
    targets = _targets_for_send(to_e164)
    if not targets:
        return False, "no_recipients_configure_distro_or_phone"
    t = resolve_trade_tier(status=status, tier_override=tier)
    body = format_trade_notification(
        lane=lane,
        action=action,
        symbol=symbol,
        qty=qty,
        price=price,
        venue=venue,
        ref=ref,
        status=status,
        ts_utc=ts_utc,
        account=account,
        tier=t,
    )
    return _dispatch_sms(targets, body, t)


def notify_system(
    *,
    to_e164: str | None = None,
    severity: str = "WARN",
    component: str = "system",
    summary: str = "",
    host: str | None = None,
    check: str | None = None,
    ts_utc: str | None = None,
    trace_id: str | None = None,
    source_agent: str | None = None,
    tier: int = 2,
) -> tuple[bool, str]:
    targets = _targets_for_send(to_e164)
    if not targets:
        return False, "no_recipients_configure_distro_or_phone"
    body = format_system_notification(
        severity=severity,
        component=component,
        summary=summary,
        host=host,
        check=check,
        ts_utc=ts_utc,
        trace_id=trace_id,
        source_agent=source_agent,
        tier=tier,
    )
    return _dispatch_sms(targets, body, tier)


def notify_training_milestone(
    *,
    to_e164: str | None = None,
    event_kind: str = "event",
    summary: str = "",
    detail: str | None = None,
    metric: str | None = None,
    ts_utc: str | None = None,
    tier: int = 3,
) -> tuple[bool, str]:
    """Anna training: graduation, improvement, completion — tier 3 by default."""
    targets = _targets_for_send(to_e164)
    if not targets:
        return False, "no_recipients_configure_distro_or_phone"
    body = format_training_notification(
        event_kind=event_kind,
        summary=summary,
        detail=detail,
        metric=metric,
        ts_utc=ts_utc,
        tier=tier,
    )
    return _dispatch_sms(targets, body, tier)


def notify_system_from_health(
    *,
    check_name: str,
    target: str,
    detail: str,
    source_agent: str,
    ts_utc: str,
    host_hint: str | None = None,
) -> tuple[bool, str]:
    """Called from DATA health workflow when an alert is raised (tier 2)."""
    if os.environ.get("BLACKBOX_NOTIFY_SYSTEM", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False, "notify_system_disabled"

    tier = int(NotificationTier.SYSTEM)
    targets = resolve_recipient_targets()
    if not targets:
        to = default_to_e164()
        if not to.strip():
            return False, "no_recipients_configure_distro_or_phone"
        targets = [("default", to.strip())]

    body = format_system_notification(
        severity="ERROR",
        component=check_name,
        summary=detail[:400],
        host=host_hint or target[:120],
        check=check_name,
        ts_utc=ts_utc,
        source_agent=source_agent,
        tier=tier,
    )
    return _dispatch_sms(targets, body, tier)
