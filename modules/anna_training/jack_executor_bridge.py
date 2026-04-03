"""Optional handoff: after an approved execution request completes, invoke Jack (executor).

**Paper vs live (intent):** same **execution_request** shape and handoff; **settlement** differs —
paper/sim mapping or no real capital vs live venue submit. Anna and the control plane stay on the
same path until the adapter.

**Separation of roles:** Anna analyzes and emits strategy (``anna_proposal_v1`` / go–no-go posture).
She does **not** implement venue submit mechanics. **Jack** is the Jupiter executor: how the trade is
placed, filled, or paper-mapped is **Jack’s** concern; this bridge only passes the approved
``execution_request_v1`` snapshot on stdin and may append a **paper** row from Jack’s stdout.

Contract (operator-supplied executable via ``BLACKBOX_JACK_EXECUTOR_CMD``):
  - **stdin:** one JSON object:
    ``{"kind":"blackbox_jack_handoff_v1","execution_request":{...},"mock_execution_result":{...}}``
  - **stdout:** one JSON object, either:
    - ``{"ok": true, "paper_trade": {"symbol", "side", "result", "pnl_usd", "timeframe", optional "notes", "venue", optional "bid", "ask", "spread", optional "regime", "signal_snapshot", "strategy_label"}}``
      → appended to ``paper_trades.jsonl`` via :func:`append_paper_trade` (placement-time quote, venue-specific units)
    - ``{"ok": false, "error": "..."}`` → no append

Default: no command set → no-op (bridge not active). Does not place orders from Slack chat; use
execution plane (create → approve → run_execution) or your own caller.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any

from modules.anna_training.paper_trades import (
    append_paper_trade,
    placement_quote_kwargs_from_mapping,
    regime_signal_kwargs_from_mapping,
)
from modules.anna_training.trade_attempts import append_trade_attempt


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def maybe_delegate_to_jack(
    *,
    execution_request: dict[str, Any],
    mock_execution_result: dict[str, Any],
) -> dict[str, Any]:
    """
    If ``BLACKBOX_JACK_EXECUTOR_CMD`` points to an executable and
    ``BLACKBOX_JACK_DELEGATE_ENABLED`` is truthy (default **on** when cmd set), run it.

    Returns a JSON-serializable status dict.
    """
    cmd = (os.environ.get("BLACKBOX_JACK_EXECUTOR_CMD") or "").strip()
    rid = str((execution_request or {}).get("request_id") or "")

    def _jack_fail(err: str, **extra: Any) -> dict[str, Any]:
        try:
            append_trade_attempt(
                phase="jack_handoff",
                status="fail",
                request_id=rid or None,
                detail={"error": err, **extra},
            )
        except Exception:
            pass
        return {"delegated": True, "ok": False, "error": err, **{k: v for k, v in extra.items() if k in ("returncode", "stderr", "stdout", "stdout_preview")}}

    if not cmd:
        return {"delegated": False, "reason": "BLACKBOX_JACK_EXECUTOR_CMD unset"}

    if not _env_bool("BLACKBOX_JACK_DELEGATE_ENABLED", True):
        return {"delegated": False, "reason": "BLACKBOX_JACK_DELEGATE_ENABLED off"}

    argv = shlex.split(cmd)
    if not argv:
        return {"delegated": False, "reason": "BLACKBOX_JACK_EXECUTOR_CMD empty after parse"}

    try:
        timeout_sec = int((os.environ.get("BLACKBOX_JACK_EXECUTOR_TIMEOUT_SEC") or "120").strip() or "120")
    except ValueError:
        timeout_sec = 120

    payload = {
        "kind": "blackbox_jack_handoff_v1",
        "execution_request": execution_request,
        "mock_execution_result": mock_execution_result,
    }
    try:
        append_trade_attempt(phase="jack_handoff", status="started", request_id=rid or None, detail={})
        proc = subprocess.run(
            argv,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=max(1, timeout_sec),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _jack_fail("jack_executor_timeout")
    except OSError as e:
        return _jack_fail(f"jack_spawn_failed:{e!s}")

    raw_out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return _jack_fail(
            "jack_nonzero_exit",
            returncode=proc.returncode,
            stderr=(proc.stderr or "")[-2000:],
            stdout=raw_out[-2000:],
        )
    if not raw_out:
        return _jack_fail("jack_empty_stdout")

    try:
        out = json.loads(raw_out)
    except json.JSONDecodeError:
        return _jack_fail("jack_stdout_not_json", stdout_preview=raw_out[:500])

    if not out.get("ok"):
        return _jack_fail(str(out.get("error") or "jack_rejected"))

    pt = out.get("paper_trade")
    if not isinstance(pt, dict):
        try:
            append_trade_attempt(
                phase="jack_handoff",
                status="ok",
                request_id=rid or None,
                detail={"paper_logged": False, "note": "no paper_trade in response"},
            )
        except Exception:
            pass
        return {"delegated": True, "ok": True, "paper_logged": False, "note": "no paper_trade in response"}

    try:
        qk = placement_quote_kwargs_from_mapping(pt)
        rk = regime_signal_kwargs_from_mapping(pt)
        row = append_paper_trade(
            symbol=str(pt.get("symbol") or ""),
            side=str(pt.get("side") or ""),
            result=str(pt.get("result") or ""),
            pnl_usd=float(pt.get("pnl_usd") or 0.0),
            timeframe=str(pt.get("timeframe") or ""),
            venue=str(pt.get("venue") or "jupiter_perp"),
            notes=str(pt.get("notes") or ""),
            log_manual_activity=False,
            source="jack_bridge",
            proposal_ref=rid or None,
            strategy_label=(
                xs if (xs := str(pt.get("strategy_label") or "").strip()) else None
            ),
            **qk,
            **rk,
        )
    except (TypeError, ValueError) as e:
        return _jack_fail(f"paper_trade_invalid:{e!s}")

    try:
        append_trade_attempt(
            phase="jack_handoff",
            status="ok",
            request_id=rid or None,
            trade_id=str(row.get("trade_id")),
            detail={"paper_logged": True},
        )
    except Exception:
        pass
    return {"delegated": True, "ok": True, "paper_logged": True, "trade": row}
