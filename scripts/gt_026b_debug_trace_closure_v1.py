#!/usr/bin/env python3
"""
GT_DIRECTIVE_026B — prove ``GET /api/debug/learning-loop/trace/<job_id>`` shows lifecycle overlay.

Runs the **operator seam** with ``exam_run_contract_request_v1`` carrying
``bars_trade_lifecycle_inclusive_v1``, appends a minimal scorecard line, then calls
``build_debug_learning_loop_trace_v1`` (same payload as the Flask route).

From repo root::

  python3 scripts/gt_026b_debug_trace_closure_v1.py

On clawbot, after this script prints ``job_id`` and ``ok: true``, curl::

  curl -sS "http://127.0.0.1:8765/api/debug/learning-loop/trace/<job_id>"

(Use the host/port your pattern-game Flask uses.)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("PATTERN_GAME_STUDENT_LOOP_SEAM", "1")

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.batch_scorecard import append_batch_scorecard_line
from renaissance_v4.game_theory.debug_learning_loop_trace_v1 import build_debug_learning_loop_trace_v1
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    parse_exam_run_contract_request_v1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
)


def _mono_bars(n: int) -> list[dict]:
    o: list[dict] = []
    for i in range(n):
        c = 100.0 + i * 0.35
        o.append(
            {
                "open": c - 0.02,
                "high": c + 0.12,
                "low": c - 0.1,
                "close": c,
                "volume": 100.0,
            }
        )
    return o


def _mk_uptrend_sqlite(path: str, n: int = 14) -> str:
    sym = "TESTUSDT"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE market_bars_5m (
            open_time INTEGER,
            symbol TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
        """
    )
    for i in range(1, n + 1):
        ts = i * 1_000_000
        c = 100.0 + (i - 1) * 0.45
        conn.execute(
            """
            INSERT INTO market_bars_5m (open_time, symbol, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, sym, c - 0.1, c + 0.2, c - 0.2, c, 1000.0),
        )
    conn.commit()
    conn.close()
    return sym


def main() -> int:
    job_id = f"gt026b_trace_{uuid.uuid4().hex[:16]}"
    lifecycle = _mono_bars(26)
    body = {
        "exam_run_contract_v1": {
            "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
            "candle_timeframe_minutes": 5,
            "bars_trade_lifecycle_inclusive_v1": lifecycle,
        }
    }
    ex_req, ex_err = parse_exam_run_contract_request_v1(body)
    if ex_err or ex_req is None:
        print(json.dumps({"ok": False, "error": ex_err or "parse_exam_run_contract_request_v1 failed"}))
        return 1

    o = OutcomeRecord(
        trade_id="sto_trade",
        symbol="TESTUSDT",
        direction="long",
        entry_time=6_000_000,
        exit_time=6_100_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=3.0,
        mae=0.0,
        mfe=1.0,
        exit_reason="tp",
    )
    results = [
        {
            "ok": True,
            "scenario_id": "row_a",
            "replay_outcomes_json": [outcome_record_to_jsonable(o)],
        }
    ]

    with tempfile.TemporaryDirectory() as td:
        os.environ["PATTERN_GAME_MEMORY_ROOT"] = td
        db = os.path.join(td, "bars.sqlite3")
        sym = _mk_uptrend_sqlite(db)
        assert sym == "TESTUSDT"
        store = os.path.join(td, "learn.jsonl")

        append_batch_scorecard_line(
            {
                "schema": "pattern_game_batch_scorecard_v1",
                "job_id": job_id,
                "status": "done",
                "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": "a" * 40},
            }
        )

        audit = student_loop_seam_after_parallel_batch_v1(
            results=results,
            run_id=job_id,
            db_path=db,
            store_path=store,
            strategy_id="pattern_learning",
            exam_run_contract_request_v1=ex_req,
            operator_batch_audit={"candle_timeframe_minutes": 5},
        )

        dbg = build_debug_learning_loop_trace_v1(job_id)
        overlay = (dbg.get("lifecycle_trace_overlay_v1") or {}) if isinstance(dbg, dict) else {}
        stages = overlay.get("lifecycle_stages_v1")
        if not isinstance(stages, list):
            stages = []
        summary = overlay.get("lifecycle_tape_summary_v1")

        exit_code = None
        closed = None
        if isinstance(summary, dict):
            closed = summary.get("closed_v1")
            exit_code = summary.get("exit_reason_code_v1")

        out = {
            "ok": bool(dbg.get("ok")) and len(stages) >= 2 and bool(summary) and bool(closed),
            "job_id": job_id,
            "PATTERN_GAME_MEMORY_ROOT": td,
            "seam": {
                "student_learning_rows_appended": audit.get("student_learning_rows_appended"),
                "errors": audit.get("errors") or [],
            },
            "debug": {
                "schema": dbg.get("schema"),
                "ok": dbg.get("ok"),
                "error": dbg.get("error"),
            },
            "026b_checks": {
                "lifecycle_trace_overlay_v1": bool(overlay.get("schema")),
                "lifecycle_stage_events_count_v1": int(overlay.get("lifecycle_stage_events_count_v1") or 0),
                "has_lifecycle_tape_summary_v1": bool(summary),
                "closed_v1": closed,
                "exit_reason_code_v1": exit_code,
            },
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if not out["ok"]:
            return 1
        print(
            f"\n026B closure: built and observable; re-run the same job_id on the Flask host "
            f"or curl: /api/debug/learning-loop/trace/{job_id}\n",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
