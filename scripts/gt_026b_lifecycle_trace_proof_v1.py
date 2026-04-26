#!/usr/bin/env python3
"""
GT_DIRECTIVE_026B closure assist — one job writes lifecycle events to a temp learning-trace JSONL
and prints event counts. Uses the same code path as ``run_lifecycle_tape_v1(emit_lifecycle_traces=True)``.

Run from repo root: ``python3 scripts/gt_026b_lifecycle_trace_proof_v1.py``
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid

# Repo root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("PATTERN_GAME_LEARNING_TRACE_EVENTS", "1")

from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import run_entry_reasoning_pipeline_v1
from renaissance_v4.game_theory.student_proctor.lifecycle_reasoning_engine_v1 import run_lifecycle_tape_v1


def _bars(n: int) -> list[dict]:
    o = []
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


def main() -> int:
    bars = _bars(22)
    ere, e2, _t, _fm = run_entry_reasoning_pipeline_v1(
        student_decision_packet={"symbol": "P26B", "bars_inclusive_up_to_t": bars[:5]},
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    if ere is None or e2:
        print("entry reasoning failed", e2, file=sys.stderr)
        return 1
    jid = f"gt026b_script_{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory() as td:
        os.environ["PATTERN_GAME_MEMORY_ROOT"] = td
        res = run_lifecycle_tape_v1(
            all_bars=bars,
            entry_bar_index=3,
            side="long",
            entry_reasoning_eval_v1=ere,
            run_candle_timeframe_minutes=5,
            symbol="P26B",
            max_hold_bars=50,
            job_id=jid,
            fingerprint="script_fp_026b",
            emit_lifecycle_traces=True,
            trade_id="script_trade",
            scenario_id="script_scn",
        )
        evs = read_learning_trace_events_for_job_v1(jid)
    n_s = sum(1 for e in evs if e.get("stage") == "lifecycle_reasoning_stage_v1")
    n_t = sum(1 for e in evs if e.get("stage") == "lifecycle_tape_summary_v1")
    out = {
        "job_id": jid,
        "lifecycle_tape": {
            "closed_v1": res.get("closed_v1"),
            "exit_reason_code_v1": res.get("exit_reason_code_v1"),
            "n_per_bar": len(res.get("per_bar_v1") or []),
        },
        "learning_trace_events": {
            "total_for_job": len(evs),
            "lifecycle_reasoning_stage_v1": n_s,
            "lifecycle_tape_summary_v1": n_t,
        },
    }
    print(json.dumps(out, indent=2))
    if n_s < 1 or n_t != 1:
        print("expected at least one stage event and one tape summary", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
