"""Deliver SMS via Twilio REST, Textbelt REST, or generic webhook — no extra pip deps."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def delivery_mode() -> str:
    """off | twilio | webhook | textbelt"""
    return _env("BLACKBOX_NOTIFY_MODE", "off").lower()


def default_to_e164() -> str:
    return _env("BLACKBOX_NOTIFY_PHONE_E164", "")


def send_sms(
    to_e164: str,
    body: str,
    *,
    tier: int | None = None,
) -> tuple[bool, str]:
    """
    Send one SMS-sized message. Respects BLACKBOX_NOTIFY_MODE.

    Twilio env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER (E.164).

    Webhook env: BLACKBOX_NOTIFY_WEBHOOK_URL.
    Optional: BLACKBOX_NOTIFY_WEBHOOK_SECRET (sent as X-Notify-Secret).
    Optional: BLACKBOX_NOTIFY_WEBHOOK_FORMAT=slack — POST ``{\"text\": \"...\"}`` for Slack Incoming Webhooks
    (recommended primary channel when SMS is off). Multicast sends **one** Slack message listing recipient names.
    Default format: JSON ``{to, body, kind, tier}``.

    Textbelt env: BLACKBOX_NOTIFY_TEXTBELT_KEY (default ``textbelt`` = one free SMS/day on hosted API),
    BLACKBOX_NOTIFY_TEXTBELT_URL (default https://textbelt.com/text). US 10-digit from E.164 +1… only.
    """
    to_e164 = (to_e164 or "").strip()
    body = (body or "").strip()
    if not to_e164 or not body:
        return False, "missing_to_or_body"

    mode = delivery_mode()
    if mode in ("0", "off", "false", "no"):
        return False, "notify_mode_off"

    if mode == "twilio":
        return _send_twilio(to_e164, body)

    if mode == "webhook":
        return _send_webhook_single(to_e164, body, tier=tier)

    if mode == "textbelt":
        return _send_textbelt(to_e164, body)

    return False, f"unknown_notify_mode:{mode}"


def send_sms_to_targets(
    targets: list[tuple[str, str]],
    body: str,
    *,
    tier: int | None = None,
) -> list[tuple[bool, str, str]]:
    """Send the same body to each (name, e164). Returns list of (ok, reason, name)."""
    if (
        delivery_mode() == "webhook"
        and _env("BLACKBOX_NOTIFY_WEBHOOK_FORMAT").lower() == "slack"
        and targets
    ):
        ok, reason = _send_webhook_slack_multicast(body, tier=tier, targets=targets)
        label = ",".join(n for n, _ in targets)
        return [(ok, reason, label)]

    out: list[tuple[bool, str, str]] = []
    for name, e164 in targets:
        ok, reason = send_sms(e164, body, tier=tier)
        out.append((ok, reason, name))
    return out


def _send_twilio(to_e164: str, body: str) -> tuple[bool, str]:
    sid = _env("TWILIO_ACCOUNT_SID")
    token = _env("TWILIO_AUTH_TOKEN")
    from_num = _env("TWILIO_FROM_NUMBER")
    if not sid or not token or not from_num:
        return False, "twilio_env_incomplete"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to_e164, "From": from_num, "Body": body}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {auth}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = getattr(resp, "status", 200)
            return (200 <= code < 300), f"twilio_http_{code}"
    except urllib.error.HTTPError as e:
        return False, f"twilio_http_{e.code}"
    except Exception as e:
        return False, f"twilio_err:{e!s}"


def _post_webhook_payload(payload_obj: dict[str, Any]) -> tuple[bool, str]:
    wh = _env("BLACKBOX_NOTIFY_WEBHOOK_URL")
    if not wh:
        return False, "webhook_url_missing"
    secret = _env("BLACKBOX_NOTIFY_WEBHOOK_SECRET")
    payload = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(wh, data=payload, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if secret:
        req.add_header("X-Notify-Secret", secret)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = getattr(resp, "status", 200)
            return (200 <= code < 300), f"webhook_http_{code}"
    except urllib.error.HTTPError as e:
        return False, f"webhook_http_{e.code}"
    except Exception as e:
        return False, f"webhook_err:{e!s}"


def _send_webhook_single(to_e164: str, body: str, *, tier: int | None = None) -> tuple[bool, str]:
    if _env("BLACKBOX_NOTIFY_WEBHOOK_FORMAT").lower() == "slack":
        parts: list[str] = []
        if tier is not None:
            parts.append(f"*BLACKBOX · T{tier}*")
        parts.append(body)
        if to_e164:
            parts.append(f"_to {to_e164}_")
        return _post_webhook_payload({"text": "\n".join(parts)})

    payload_obj: dict[str, Any] = {"to": to_e164, "body": body, "kind": "notify"}
    if tier is not None:
        payload_obj["tier"] = int(tier)
    return _post_webhook_payload(payload_obj)


def _send_webhook_slack_multicast(
    body: str,
    *,
    tier: int | None,
    targets: list[tuple[str, str]],
) -> tuple[bool, str]:
    parts: list[str] = []
    if tier is not None:
        parts.append(f"*BLACKBOX · T{tier}*")
    parts.append(body)
    if targets:
        who = ", ".join(f"{n}" for n, _ in targets)
        parts.append(f"_Recipients: {who}_")
    return _post_webhook_payload({"text": "\n".join(parts)})


def _e164_to_textbelt_us_phone(e164: str) -> str | None:
    """Hosted Textbelt examples use 10-digit US numbers (no +1)."""
    d = re.sub(r"\D", "", e164 or "")
    if len(d) == 11 and d.startswith("1"):
        return d[1:]
    if len(d) == 10:
        return d
    return None


def _send_textbelt(to_e164: str, body: str) -> tuple[bool, str]:
    """
    POST application/x-www-form-urlencoded to Textbelt.

    Free tier: key ``textbelt`` — typically one outbound text per day (see textbelt.com).
    Paid: purchase key; same API.
    """
    phone = _e164_to_textbelt_us_phone(to_e164)
    if not phone:
        return False, "textbelt_phone_requires_us_10digit"

    key = _env("BLACKBOX_NOTIFY_TEXTBELT_KEY", "textbelt")
    url = _env("BLACKBOX_NOTIFY_TEXTBELT_URL", "https://textbelt.com/text")
    if not url:
        return False, "textbelt_url_missing"

    msg = (body or "")[:1600]
    data = urllib.parse.urlencode({"phone": phone, "message": msg, "key": key}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"textbelt_http_{e.code}"
    except Exception as e:
        return False, f"textbelt_err:{e!s}"

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return False, "textbelt_bad_json"

    if obj.get("success") is True:
        q = obj.get("quotaRemaining")
        return True, f"textbelt_ok:{q}" if q is not None else "textbelt_ok"

    err = obj.get("error") or obj.get("message") or "unknown"
    return False, f"textbelt_api:{err}"
