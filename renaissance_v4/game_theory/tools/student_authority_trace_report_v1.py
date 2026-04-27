#!/usr/bin/env python3
"""CLI: summarize persisted ``student_decision_authority_v1`` lines for one or two job_ids (A/B).

Usage::

    python3 -m renaissance_v4.game_theory.tools.student_authority_trace_report_v1 <job_id_student> [<job_id_baseline>]

Exit 0. Prints JSON to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
    count_student_decision_authority_trace_lines_v1,
)


def _summarize_job(job_id: str, *, path: Path | None = None) -> dict[str, Any]:
    jid = str(job_id or "").strip()
    evs = read_learning_trace_events_for_job_v1(jid, path=path)
    auth = [e for e in evs if str(e.get("stage") or "") == "student_decision_authority_v1"]
    rows: list[dict[str, Any]] = []
    for e in auth:
        pl = (e.get("evidence_payload") or {}).get("student_decision_authority_v1") or {}
        if not isinstance(pl, dict):
            continue
        rows.append(
            {
                "trade_id": e.get("trade_id"),
                "scenario_id": e.get("scenario_id"),
                "authority_mode_v1": pl.get("authority_mode_v1"),
                "authority_applied_v1": pl.get("authority_applied_v1"),
                "authority_would_apply_v1": pl.get("authority_would_apply_v1"),
                "before_action": (pl.get("before_decision_snapshot_v1") or {}).get("decision_action_v1"),
                "after_action": (pl.get("after_decision_snapshot_v1") or {}).get("decision_action_v1"),
                "authority_reason_codes_v1": pl.get("authority_reason_codes_v1"),
                "referee_passed_v1": (pl.get("referee_safety_check_v1") or {}).get("passed_v1"),
            }
        )
    return {
        "job_id": jid,
        "student_decision_authority_event_count_v1": len(auth),
        "count_student_decision_authority_trace_lines_v1": count_student_decision_authority_trace_lines_v1(
            jid, path=path
        ),
        "per_trade_summary_v1": rows,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: student_authority_trace_report_v1.py <job_id_student> [<job_id_baseline>]", file=sys.stderr)
        return 2
    student_j = argv[1]
    baseline_j = argv[2] if len(argv) > 2 else None
    out: dict[str, Any] = {"student_job": _summarize_job(student_j)}
    if baseline_j:
        out["baseline_job"] = _summarize_job(baseline_j)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
