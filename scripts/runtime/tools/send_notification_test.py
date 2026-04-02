#!/usr/bin/env python3
"""
Send one test SMS via the notification gateway (Twilio or webhook).

Requires BLACKBOX_NOTIFY_MODE=twilio (or webhook) and credentials. Recipients come
from config/notification_recipients.local.json, BLACKBOX_NOTIFY_DISTRO, or
BLACKBOX_NOTIFY_PHONE_E164 — see modules/notification_gateway/__init__.py.

Easiest (one system SMS with the standard test sentence):
  python3 scripts/runtime/tools/send_notification_test.py --ping

With Twilio env set (same as above, actually sends):
  BLACKBOX_NOTIFY_MODE=twilio TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... TWILIO_FROM_NUMBER=... \\
    python3 scripts/runtime/tools/send_notification_test.py --ping

Other examples:
  python3 scripts/runtime/tools/send_notification_test.py --who john --dry-run
  python3 scripts/runtime/tools/send_notification_test.py --list-sms-tiers
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Single sentence for --ping (shows in SMS body summary line).
PING_SUMMARY = "This is a system test from the BLACK BOX engine."


def main() -> int:
    ap = argparse.ArgumentParser(description="Send a test BLACKBOX SMS.")
    ap.add_argument(
        "--who",
        choices=("john", "sean", "all"),
        default="john",
        help="Named recipient from distro, or all.",
    )
    ap.add_argument(
        "--kind",
        choices=("system", "trade", "training"),
        default="system",
        help="Which template to send.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print body only; do not send (still loads recipients).",
    )
    ap.add_argument(
        "--list-sms-tiers",
        action="store_true",
        help="Print effective BLACKBOX_NOTIFY_SMS_TIERS (which priority levels may SMS).",
    )
    ap.add_argument(
        "--trade-status",
        default="test",
        metavar="STATUS",
        help="For --kind trade: status string (affects tier if BLACKBOX_NOTIFY_TRADE_ROUTINE_TIER is on).",
    )
    ap.add_argument(
        "--ping",
        action="store_true",
        help=f"Send one tier-2 system SMS with this text: {PING_SUMMARY!r} (ignores --kind).",
    )
    args = ap.parse_args()

    if args.list_sms_tiers:
        from modules.notification_gateway import parse_sms_allowed_tiers

        tiers = sorted(parse_sms_allowed_tiers())
        print("SMS allowed tiers:", ",".join(str(t) for t in tiers))
        print("(Set BLACKBOX_NOTIFY_SMS_TIERS=1,2 to drop tier-3 agent/training SMS.)")
        return 0

    from modules.notification_gateway import (
        notify_system,
        notify_trade,
        notify_training_milestone,
    )
    from modules.notification_gateway.recipients import resolve_recipient_targets

    targets = resolve_recipient_targets()
    if not targets:
        print(
            "No recipients: add config/notification_recipients.local.json, "
            "or set BLACKBOX_NOTIFY_DISTRO / BLACKBOX_NOTIFY_PHONE_E164.",
            file=sys.stderr,
        )
        return 2

    to_e164: str | None
    if args.who == "all":
        to_e164 = None
    else:
        want = args.who.lower()
        match = [t for t in targets if t[0].lower() == want]
        if not match:
            names = ", ".join(t[0] for t in targets)
            print(f"No recipient named {args.who!r}. Available: {names}", file=sys.stderr)
            return 2
        to_e164 = match[0][1]

    mode = (os.environ.get("BLACKBOX_NOTIFY_MODE") or "off").strip().lower()
    if args.dry_run:
        from modules.notification_gateway.messages import (
            format_system_notification,
            format_trade_notification,
            format_training_notification,
        )

        if args.ping or args.kind == "system":
            body = format_system_notification(
                severity="INFO",
                component="blackbox_engine",
                summary=PING_SUMMARY if args.ping else "Dry-run test message from send_notification_test.py",
                host=os.environ.get("BLACKBOX_HOST_LABEL"),
                check="manual",
                source_agent="operator",
            )
        elif not args.ping and args.kind == "trade":
            from modules.notification_gateway.tiers import resolve_trade_tier

            rt = resolve_trade_tier(status=args.trade_status, tier_override=None)
            body = format_trade_notification(
                lane="paper",
                action="BUY",
                symbol="TEST",
                qty="1",
                price="0",
                status=args.trade_status,
                tier=rt,
            )
        else:
            body = format_training_notification(
                event_kind="TEST",
                summary="Dry-run Anna training notification",
                detail="No SMS sent",
            )
        print(body)
        return 0

    if mode in ("0", "off", "false", "no"):
        print(
            "BLACKBOX_NOTIFY_MODE is off. Set BLACKBOX_NOTIFY_MODE=twilio and TWILIO_* "
            "to send, or use --dry-run.",
            file=sys.stderr,
        )
        return 3

    if args.ping:
        ok, msg = notify_system(
            to_e164=to_e164,
            severity="INFO",
            component="blackbox_engine",
            summary=PING_SUMMARY,
            host=os.environ.get("BLACKBOX_HOST_LABEL"),
            check="manual",
            source_agent="operator",
        )
    elif args.kind == "system":
        ok, msg = notify_system(
            to_e164=to_e164,
            severity="INFO",
            component="notify_test",
            summary="Test message from send_notification_test.py",
            host=os.environ.get("BLACKBOX_HOST_LABEL"),
            check="manual",
            source_agent="operator",
        )
    elif args.kind == "trade":
        ok, msg = notify_trade(
            to_e164=to_e164,
            lane="paper",
            action="BUY",
            symbol="TEST",
            qty="1",
            price="0",
            status=args.trade_status,
        )
    else:
        ok, msg = notify_training_milestone(
            to_e164=to_e164,
            event_kind="TEST",
            summary="Test Anna training notification from send_notification_test.py",
            detail="If you see this, training SMS path works.",
        )

    print("ok" if ok else "failed", "-", msg)
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
