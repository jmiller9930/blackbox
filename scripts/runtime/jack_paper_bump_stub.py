#!/usr/bin/env python3
"""Lab Jack executor: stdin ``blackbox_jack_handoff_v1`` JSON → stdout Jack result JSON.

Reads one JSON object from stdin (same contract as :mod:`modules.anna_training.jack_executor_bridge`).
Prints one JSON line: ``{"ok": true, "paper_trade": {...}}`` so a **paper row** can append.

**Not** a venue — no bank settlement. Anna still follows **live market context**; rows this script writes go to the
same **paper ledger** gates and scorecards use. **Monopoly money** means no transfer — **not** that the row is
ignored: when this is the configured executor, these outcomes are **judgment-grade** for training.

When no explicit result is set, outcomes are **deterministic from** a mix key
(``request_id`` + ``created_at`` + ``proposal_id`` from the handoff JSON) so each **new** execution request gets
its own bucket — cohorts are not 100% ``won``, and runs are reproducible for the same handoff payload.

Override fields via env (all optional):

- ``JACK_STUB_SYMBOL`` (default ``SOL-PERP``)
- ``JACK_STUB_SIDE`` (default ``long``)
- ``JACK_STUB_RESULT`` — if set: ``won`` | ``lost`` | ``breakeven`` | ``abstain`` (skips automatic cohort mix)
- ``JACK_STUB_PNL_USD`` — if set: fixed P&L (otherwise derived from the deterministic mix above)
- ``JACK_STUB_TIMEFRAME`` (default ``5m``)
- ``JACK_STUB_ALWAYS_WIN`` — ``1``/true: always ``won`` + 0 P&amp;L when result not set (smoke tests only)
- ``JACK_STUB_SIMULATE`` — **deprecated**; ``0``/false is treated like ``JACK_STUB_ALWAYS_WIN=1``
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _legacy_always_won_mode() -> bool:
    """Always ``won`` + 0 P&L when no explicit result (smoke test). ``JACK_STUB_SIMULATE=0`` kept as alias."""
    if _env_bool("JACK_STUB_ALWAYS_WIN", False):
        return True
    raw = (os.environ.get("JACK_STUB_SIMULATE") or "").strip()
    if raw:
        return not _env_bool("JACK_STUB_SIMULATE", True)
    return False


def _handoff_mix_key(payload: dict[str, Any]) -> str:
    """Stable string per unique execution request (avoids hashing request_id alone if ever reused)."""
    er = payload.get("execution_request")
    if not isinstance(er, dict):
        er = {}
    parts = [
        str(er.get("request_id") or "").strip(),
        str(er.get("created_at") or "").strip(),
        str(er.get("proposal_id") or "").strip(),
    ]
    key = "|".join(parts) if any(parts) else "empty"
    return key


def _notional_paper_outcome(mix_key: str) -> tuple[str, float]:
    """Deterministic won/lost/breakeven + P&L for the paper ledger (judgment track; stub is not a venue feed)."""
    rid = (mix_key or "").strip() or "empty"
    h = int.from_bytes(hashlib.sha256(rid.encode("utf-8")).digest()[:8], "big")
    bucket = h % 100
    # ~38% loss, ~22% breakeven, ~40% win — cohort variance for gates, not a claim about alpha
    if bucket < 38:
        r = "lost"
        pnl = -round((h % 5000) / 1000.0 + 0.01, 2)  # about -0.01 .. -5.0
    elif bucket < 60:
        r = "breakeven"
        pnl = round(((h % 21) - 10) / 100.0, 2)  # about -0.10 .. +0.10
    else:
        r = "won"
        pnl = round((h % 5000) / 1000.0 + 0.01, 2)  # about +0.01 .. +5.0
    return r, pnl


def main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    er = payload.get("execution_request")
    if not isinstance(er, dict):
        er = {}
    rid = str(er.get("request_id") or "")
    mix_key = _handoff_mix_key(payload if isinstance(payload, dict) else {})
    sym = (os.environ.get("JACK_STUB_SYMBOL") or "SOL-PERP").strip() or "SOL-PERP"
    side = (os.environ.get("JACK_STUB_SIDE") or "long").strip() or "long"
    tf = (os.environ.get("JACK_STUB_TIMEFRAME") or "5m").strip() or "5m"

    explicit_result = (os.environ.get("JACK_STUB_RESULT") or "").strip()
    explicit_pnl = (os.environ.get("JACK_STUB_PNL_USD") or "").strip()

    if explicit_result:
        result = explicit_result.lower()
        if result not in ("won", "lost", "breakeven", "abstain"):
            result = "won"
        try:
            pnl = float(explicit_pnl) if explicit_pnl else 0.0
        except ValueError:
            pnl = 0.0
    elif explicit_pnl:
        try:
            pnl = float(explicit_pnl)
        except ValueError:
            pnl = 0.0
        result = "won" if pnl > 0 else ("lost" if pnl < 0 else "breakeven")
    elif _legacy_always_won_mode():
        print(
            "jack_paper_bump_stub: WARNING — JACK_STUB_ALWAYS_WIN or JACK_STUB_SIMULATE=0: "
            "every row is won + $0 (smoke mode); unset for cohort mix.",
            file=sys.stderr,
        )
        result = "won"
        pnl = 0.0
    else:
        result, pnl = _notional_paper_outcome(mix_key)

    notes = f"jack_paper_bump_stub judgment_ledger rid={rid[:12] if rid else '—'}"
    out = {
        "ok": True,
        "paper_trade": {
            "symbol": sym,
            "side": side,
            "result": result,
            "pnl_usd": pnl,
            "timeframe": tf,
            "notes": notes,
            "venue": "jupiter_perp",
        },
    }
    print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
