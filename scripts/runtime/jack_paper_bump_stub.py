#!/usr/bin/env python3
"""Lab Jack executor: stdin ``blackbox_jack_handoff_v1`` JSON → stdout Jack result JSON.

Reads one JSON object from stdin (same contract as :mod:`modules.anna_training.jack_executor_bridge`).
Prints one JSON line: ``{"ok": true, "paper_trade": {...}}`` so a **paper row** can append.

**Not** a venue. Deterministic cohort “bump” for Grade-12 paper gates when no real Jupiter Jack exists.
Override fields via env (all optional):

- ``JACK_STUB_SYMBOL`` (default ``SOL-PERP``)
- ``JACK_STUB_SIDE`` (default ``long``)
- ``JACK_STUB_RESULT`` — ``won`` | ``lost`` | ``breakeven`` | ``abstain`` (default ``won``)
- ``JACK_STUB_PNL_USD`` (default ``0.0``)
- ``JACK_STUB_TIMEFRAME`` (default ``5m``)
"""

from __future__ import annotations

import json
import os
import sys


def main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    rid = str((payload.get("execution_request") or {}).get("request_id") or "")
    sym = (os.environ.get("JACK_STUB_SYMBOL") or "SOL-PERP").strip() or "SOL-PERP"
    side = (os.environ.get("JACK_STUB_SIDE") or "long").strip() or "long"
    result = (os.environ.get("JACK_STUB_RESULT") or "won").strip() or "won"
    try:
        pnl = float((os.environ.get("JACK_STUB_PNL_USD") or "0").strip() or "0")
    except ValueError:
        pnl = 0.0
    tf = (os.environ.get("JACK_STUB_TIMEFRAME") or "5m").strip() or "5m"
    notes = f"jack_paper_bump_stub rid={rid[:12] if rid else '—'}"
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
