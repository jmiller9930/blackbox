"""Short SMS-sized templates: trade vs system — who/what/when/where without noise."""

from __future__ import annotations

import re
from datetime import datetime, timezone


def _clip(s: str, max_len: int = 320) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _e164_hint(phone: str) -> str:
    """Last 4 digits only for logs (never log full number in shared code paths)."""
    d = re.sub(r"\D", "", phone or "")
    return f"…{d[-4:]}" if len(d) >= 4 else "(no-digits)"


def format_trade_notification(
    *,
    lane: str,
    action: str,
    symbol: str,
    qty: str | None = None,
    price: str | None = None,
    venue: str | None = None,
    ref: str | None = None,
    status: str,
    ts_utc: str | None = None,
    account: str | None = None,
    tier: int = 1,
) -> str:
    """
    Trade placement / outcome — one screen, facts only.

    * **Who** — optional account hint (masked)
    * **What** — action + symbol + qty/price
    * **When** — UTC ISO (caller supplies or now)
    * **Where** — venue if set
    """
    when = ts_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lane_u = (lane or "unknown").strip().lower()[:12]
    act = (action or "?").strip().upper()[:12]
    sym = (symbol or "?").strip().upper()[:16]
    q = (qty or "—").strip()[:24]
    px = (price or "—").strip()[:24]
    vn = (venue or "").strip()[:24]
    rf = (ref or "").strip()[:32]
    st = (status or "?").strip()[:24]
    acct = (account or "").strip()
    who = ""
    if acct:
        who = f"Acct: …{acct[-4:]}\n" if len(acct) >= 4 else ""

    line2 = f"{act} {sym}  qty {q}  @ {px}"
    if vn:
        line2 += f"\nVenue: {vn}"
    line3 = f"When: {when}\n"
    if rf:
        line3 += f"Ref: {rf}\n"
    line3 += f"Status: {st}"

    tier_label = f"T{int(tier)}"
    body = f"BLACKBOX · {tier_label} · TRADE · {lane_u}\n{who}{line2}\n{line3}"
    return _clip(body, 480)


def format_system_notification(
    *,
    severity: str,
    component: str,
    summary: str,
    host: str | None = None,
    check: str | None = None,
    ts_utc: str | None = None,
    trace_id: str | None = None,
    source_agent: str | None = None,
    tier: int = 2,
) -> str:
    """
    Error / degraded condition — what broke, where, when.

    * **What** — component + one-line summary
    * **Where** — host / target
    * **When** — UTC
    """
    when = ts_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    sev = (severity or "INFO").strip().upper()[:10]
    comp = (component or "system").strip()[:40]
    sm = (summary or "").strip().replace("\n", " ")[:200]
    ho = (host or "").strip()[:48]
    ck = (check or "").strip()[:40]
    tr = (trace_id or "").strip()[:32]

    tier_label = f"T{int(tier)}"
    lines = [
        f"BLACKBOX · {tier_label} · ALERT · {sev}",
        f"What: {comp}",
    ]
    if source_agent:
        lines.append(f"Who: {source_agent.strip()[:24]}")
    if ck:
        lines.append(f"Check: {ck}")
    lines.append(f"Detail: {sm}")
    if ho:
        lines.append(f"Where: {ho}")
    lines.append(f"When: {when}")
    if tr:
        lines.append(f"Trace: {tr}")

    return _clip("\n".join(lines), 480)


def format_training_notification(
    *,
    event_kind: str,
    summary: str,
    detail: str | None = None,
    metric: str | None = None,
    ts_utc: str | None = None,
    tier: int = 3,
) -> str:
    """
    Anna / university training milestones — graduation, improvement, completion.

    event_kind: graduation | improvement | completion | (other short label)
    """
    when = ts_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    kind = (event_kind or "event").strip().upper()[:24]
    sm = (summary or "").strip().replace("\n", " ")[:200]
    dt = (detail or "").strip().replace("\n", " ")[:160]
    mt = (metric or "").strip()[:80]

    tier_label = f"T{int(tier)}"
    lines = [
        f"BLACKBOX · {tier_label} · ANNA · TRAINING",
        f"Event: {kind}",
        f"What: {sm}",
    ]
    if mt:
        lines.append(f"Metric: {mt}")
    if dt:
        lines.append(f"Detail: {dt}")
    lines.append(f"When: {when}")
    return _clip("\n".join(lines), 480)


__all__ = [
    "format_trade_notification",
    "format_system_notification",
    "format_training_notification",
    "_e164_hint",
]
