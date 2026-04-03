#!/usr/bin/env python3
"""Karpathy learning loop supervisor — runs until SIGTERM/INT (repeat continuously).

Assigns Grade 12 + Karpathy if missing; each tick advances ``karpathy_loop_iteration`` in
``state.json``, appends ``karpathy_loop_heartbeat.jsonl``, snapshots grade-12 gates, and
optionally records ``market_data``. Does not place live trades — harness / paper logging
remain operator-driven.

Env:
  ANNA_LOOP_INTERVAL_SEC — seconds between ticks (default 10; supervisor cadence, not exchange tick rate)
  RECORD_MARKET_SNAPSHOT_EACH_TICK — 1 to record one market row per successful tick
  MARKET_DATA_SKIP_JUPITER — 1 to skip Jupiter quote when snapshotting
  ANNA_SKIP_PREFLIGHT — 1 bypasses data preflight (tests/dev only)

Repo root:
  PYTHONPATH=scripts/runtime:. python3 scripts/runtime/anna_karpathy_loop_daemon.py
  PYTHONPATH=scripts/runtime:. python3 scripts/runtime/anna_karpathy_loop_daemon.py --once
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_RT = ROOT / "scripts" / "runtime"
if str(_RT) not in sys.path:
    sys.path.insert(0, str(_RT))

from modules.anna_training.catalog import CURRICULA, TRAINING_METHODS  # noqa: E402
from modules.anna_training.gates import evaluate_grade12_gates  # noqa: E402
from modules.anna_training.readiness import ensure_anna_data_preflight, preflight_skipped  # noqa: E402
from modules.anna_training.store import anna_training_dir, load_state, save_state, utc_now_iso  # noqa: E402

_DEFAULT_CURRICULUM = "grade_12_paper_only"
_DEFAULT_METHOD = "karpathy_loop_v1"
_HEARTBEAT_REL = "karpathy_loop_heartbeat.jsonl"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_enrolled(state: dict) -> dict:
    changed = False
    if not state.get("curriculum_id") or state.get("curriculum_id") not in CURRICULA:
        state["curriculum_id"] = _DEFAULT_CURRICULUM
        state["curriculum_assigned_at_utc"] = utc_now_iso()
        changed = True
    if not state.get("training_method_id") or state.get("training_method_id") not in TRAINING_METHODS:
        state["training_method_id"] = _DEFAULT_METHOD
        state["method_invoked_at_utc"] = utc_now_iso()
        changed = True
    if changed:
        save_state(state)
    return state


def _interval_sec(cli: float | None) -> float:
    if cli is not None:
        return max(5.0, float(cli))
    raw = (os.environ.get("ANNA_LOOP_INTERVAL_SEC") or "").strip()
    if not raw:
        return 10.0
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 10.0


def _snapshot_market_if_requested() -> dict | None:
    if (os.environ.get("RECORD_MARKET_SNAPSHOT_EACH_TICK") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return None
    from market_data.recorder import record_market_snapshot

    if (os.environ.get("MARKET_DATA_SKIP_JUPITER") or "").strip().lower() in ("1", "true", "yes"):
        return record_market_snapshot(include_jupiter=False)
    return record_market_snapshot(include_jupiter=None)


def _append_heartbeat(obj: dict) -> None:
    hb = anna_training_dir() / _HEARTBEAT_REL
    hb.parent.mkdir(parents=True, exist_ok=True)
    with hb.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run_one_tick(*, tick_index: int) -> tuple[dict, bool]:
    """Returns (heartbeat_row, success). Success = preflight ok or skipped."""
    pf = ensure_anna_data_preflight()
    ok_pf = bool(pf.get("ok")) or bool(pf.get("skipped"))

    if not ok_pf:
        row = {
            "kind": "karpathy_loop_heartbeat_v1",
            "tick_index": tick_index,
            "at_utc": _utc_iso(),
            "preflight_ok": False,
            "blockers": pf.get("blockers") or [],
            "readiness": {
                "pyth_stream": (pf.get("readiness") or {}).get("pyth_stream"),
                "market_data_db": (pf.get("readiness") or {}).get("market_data_db"),
            },
        }
        _append_heartbeat(row)
        return row, False

    st = _ensure_enrolled(load_state())
    n = int(st.get("karpathy_loop_iteration") or 0) + 1
    st["karpathy_loop_iteration"] = n
    st["karpathy_loop_last_tick_utc"] = utc_now_iso()
    save_state(st)

    g12 = evaluate_grade12_gates()
    snap = _snapshot_market_if_requested()

    row = {
        "kind": "karpathy_loop_heartbeat_v1",
        "tick_index": tick_index,
        "at_utc": _utc_iso(),
        "preflight_ok": True,
        "karpathy_loop_iteration": n,
        "curriculum_id": st.get("curriculum_id"),
        "training_method_id": st.get("training_method_id"),
        "grade12_gate": {
            "pass": g12.get("pass"),
            "decisive_trades": g12.get("decisive_trades"),
            "wins": g12.get("wins"),
            "losses": g12.get("losses"),
            "win_rate": g12.get("win_rate"),
        },
        "market_snapshot_row_id": (snap or {}).get("row_id") if isinstance(snap, dict) else None,
    }
    _append_heartbeat(row)
    return row, True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Karpathy learning loop daemon — runs until SIGTERM")
    ap.add_argument(
        "--interval-sec",
        type=float,
        default=None,
        help="Seconds between ticks (default ANNA_LOOP_INTERVAL_SEC or 10)",
    )
    ap.add_argument(
        "--once",
        action="store_true",
        help="Run one tick and exit (exit 1 if preflight failed and not skipped)",
    )
    args = ap.parse_args(argv)

    interval = _interval_sec(args.interval_sec)
    stop = {"flag": False}

    def _handle(_signum, _frame):  # noqa: ANN001
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    print(
        json.dumps(
            {
                "kind": "karpathy_loop_daemon_start_v1",
                "interval_sec": interval,
                "once": args.once,
                "heartbeat_path": str(anna_training_dir() / _HEARTBEAT_REL),
                "state_path": str(anna_training_dir() / "state.json"),
            },
            indent=2,
        ),
        flush=True,
    )

    tick_idx = 0
    while not stop["flag"]:
        tick_idx += 1
        try:
            row, ok = run_one_tick(tick_index=tick_idx)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        except Exception as e:  # noqa: BLE001
            err = {"kind": "karpathy_loop_tick_error", "error": str(e), "at_utc": _utc_iso(), "tick_index": tick_idx}
            _append_heartbeat(err)
            print(json.dumps(err), file=sys.stderr, flush=True)
            if args.once:
                return 1

        if args.once:
            if not ok and not preflight_skipped():
                return 1
            return 0

        if not ok and not preflight_skipped():
            # Back off when data path is broken; still responsive to SIGTERM
            target = min(60.0, interval)
        else:
            target = interval

        print(
            f"[karpathy_loop] Sleeping {target:.0f}s until next tick (not hung — interval). "
            "Ctrl+C or SIGTERM to stop.",
            file=sys.stderr,
            flush=True,
        )

        slept = 0.0
        while slept < target and not stop["flag"]:
            step = min(1.0, target - slept)
            time.sleep(step)
            slept += step

    print(json.dumps({"kind": "karpathy_loop_daemon_stop", "at_utc": _utc_iso()}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
