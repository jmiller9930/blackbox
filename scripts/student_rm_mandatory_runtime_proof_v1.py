#!/usr/bin/env python3
"""
Mandatory Student RM runtime proof bundle (engineering artifact).

Reads ``learning_trace_events_v1.jsonl`` for a ``job_id`` and optionally a saved parallel
``batch_result`` JSON (API payload or a dict with ``results`` + ``student_loop_seam_audit``).

Prints one JSON object suitable for architect acceptance:

* Coverage: replay closed trade count (from batch if provided) vs trace authority vs ``trades_considered`` from seam audit
* Sealing: ``student_output_sealed`` vs ``llm_output_rejected``; flags ``conflicting_indicators`` rejections
* Integrity: ``count_learning_trace_terminal_integrity_v1`` + ``count_learning_trace_rm_breadcrumbs_for_job_v1``
* Completion: ``student_seam_stop_reason_v1`` from seam audit when batch path given
* Sample: first / last three trades (by first sealed event order) with key lifecycle stages present in trace

Usage::

    python3 scripts/student_rm_mandatory_runtime_proof_v1.py <job_id> \\
        [--trace PATH] [--batch-json PATH]

Exit **0** when ``acceptance_ok_v1`` is true (strict bar: full coverage alignment, authority==sealed,
no conflicting-indicator structural rejects, integrity, ``completed_all_trades_v1``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from renaissance_v4.game_theory.learning_trace_events_v1 import (
    SCHEMA_EVENT,
    count_learning_trace_rm_breadcrumbs_for_job_v1,
    count_learning_trace_terminal_integrity_v1,
    read_learning_trace_events_for_job_v1,
)
from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    _replay_closed_trades_total_v1,
)


def _replay_total_from_batch_obj(obj: Any) -> int | None:
    if not isinstance(obj, dict):
        return None
    results = obj.get("results")
    if not isinstance(results, list):
        inner = obj.get("result")
        if isinstance(inner, dict):
            results = inner.get("results")
    if not isinstance(results, list):
        return None
    return _replay_closed_trades_total_v1(results)


def _seam_audit_from_batch_obj(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    for k in ("student_loop_seam_audit", "student_loop_seam_audit_v1"):
        v = obj.get(k)
        if isinstance(v, dict):
            return v
    inner = obj.get("result")
    if isinstance(inner, dict):
        for k in ("student_loop_seam_audit", "student_loop_seam_audit_v1"):
            v = inner.get(k)
            if isinstance(v, dict):
                return v
    return None


def _snip(ev: dict[str, Any], max_chars: int = 1200) -> dict[str, Any]:
    raw = json.dumps(ev, default=str)
    if len(raw) <= max_chars:
        return dict(ev)
    return {"_truncated_json_v1": raw[:max_chars] + "…", "stage": ev.get("stage")}


def _lifecycle_samples_v1(
    events: list[dict[str, Any]],
    *,
    first_n: int = 3,
    last_n: int = 3,
) -> dict[str, Any]:
    order: list[str] = []
    seen: set[str] = set()
    by_key: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        if str(ev.get("schema") or "") != SCHEMA_EVENT:
            continue
        sid = str(ev.get("scenario_id") or "").strip()
        tid = str(ev.get("trade_id") or "").strip()
        if not sid or not tid:
            continue
        k = f"{sid}\t{tid}"
        by_key.setdefault(k, []).append(ev)
        if k not in seen and str(ev.get("stage") or "") == "student_output_sealed":
            seen.add(k)
            order.append(k)
    want = order[:first_n] + (order[-last_n:] if len(order) > first_n + last_n else [])
    # Dedupe preserving order when overlap
    out_keys: list[str] = []
    for k in want:
        if k not in out_keys:
            out_keys.append(k)
    stages_pick = (
        "entry_reasoning_sealed_v1",
        "student_decision_authority_v1",
        "llm_called",
        "llm_output_received",
        "llm_output_rejected",
        "student_output_sealed",
    )
    samples: dict[str, Any] = {}
    for k in out_keys:
        rows = by_key.get(k) or []
        by_stage: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            st = str(r.get("stage") or "")
            by_stage.setdefault(st, []).append(r)
        samples[k] = {
            "merge_note_v1": (
                "Engine merge is apply_engine_authority_to_student_output_v1 — no separate trace row; "
                "sealed row follows merge in the runtime pipeline."
            ),
            "stages_v1": {s: _snip(by_stage[s][-1]) for s in stages_pick if by_stage.get(s)},
        }
    return {"sealed_trade_key_order_v1": order, "sample_keys_v1": out_keys, "by_trade_v1": samples}


def build_mandatory_proof_v1(
    job_id: str,
    *,
    trace_path: Path | None = None,
    batch_json_path: Path | None = None,
) -> dict[str, Any]:
    jid = str(job_id or "").strip()
    tp = (trace_path or default_learning_trace_events_jsonl()).expanduser().resolve()
    events = read_learning_trace_events_for_job_v1(
        jid, path=tp, max_lines=2_000_000
    )
    integrity_term = count_learning_trace_terminal_integrity_v1(jid, path=tp)
    integrity_rm = count_learning_trace_rm_breadcrumbs_for_job_v1(jid, path=tp)

    auth_n = int(integrity_term.get("student_decision_authority_v1_count") or 0)
    sealed_n = int(integrity_term.get("student_output_sealed_count") or 0)
    mismatch_n = int(integrity_rm.get("authority_sealed_mismatch_v1") or 0)

    rej_conflicting = 0
    rej_total = 0
    for ev in events:
        if str(ev.get("stage") or "") != "llm_output_rejected":
            continue
        rej_total += 1
        ep = ev.get("evidence_payload")
        errs: list[str] = []
        if isinstance(ep, dict):
            raw = ep.get("errors")
            if isinstance(raw, list):
                errs = [str(x) for x in raw]
        joined = " ".join(errs).lower()
        if "conflicting_indicators" in joined:
            rej_conflicting += 1

    batch_obj: Any = None
    replay_from_batch: int | None = None
    seam_audit: dict[str, Any] | None = None
    trades_considered: int | None = None
    stop_reason: str | None = None
    replay_audit_field: int | None = None
    if batch_json_path is not None:
        p = batch_json_path.expanduser().resolve()
        batch_obj = json.loads(p.read_text(encoding="utf-8"))
        replay_from_batch = _replay_total_from_batch_obj(batch_obj)
        seam_audit = _seam_audit_from_batch_obj(batch_obj)
        if seam_audit:
            trades_considered = int(seam_audit.get("trades_considered") or 0)
            stop_reason = str(seam_audit.get("student_seam_stop_reason_v1") or "") or None
            replay_audit_field = int(seam_audit.get("replay_closed_trades_total_v1") or 0)

    coverage_aligned = (
        replay_from_batch is not None
        and trades_considered is not None
        and replay_from_batch == trades_considered
        and replay_from_batch == auth_n
        and replay_from_batch == sealed_n
        and replay_from_batch > 0
    )
    sealing_ok = sealed_n > 0 and auth_n == sealed_n and rej_conflicting == 0
    integrity_ok = bool(integrity_term.get("integrity_ok")) and mismatch_n == 0
    completion_ok = stop_reason == "completed_all_trades_v1"
    if batch_json_path is None:
        completion_ok = False
        coverage_aligned = False

    acceptance_ok_v1 = bool(
        coverage_aligned and sealing_ok and integrity_ok and completion_ok and rej_total >= 0
    )

    return {
        "schema": "student_rm_mandatory_runtime_proof_v1",
        "job_id": jid,
        "trace_path_resolved_v1": str(tp),
        "batch_json_path_v1": str(batch_json_path) if batch_json_path else None,
        "coverage_v1": {
            "replay_closed_trades_from_batch_json_v1": replay_from_batch,
            "replay_closed_trades_from_seam_audit_v1": replay_audit_field,
            "trades_considered_seam_audit_v1": trades_considered,
            "student_decision_authority_v1_count_trace_v1": auth_n,
            "student_output_sealed_count_trace_v1": sealed_n,
            "coverage_aligned_v1": coverage_aligned,
        },
        "sealing_v1": {
            "llm_output_rejected_count_trace_v1": rej_total,
            "llm_output_rejected_conflicting_indicators_rows_v1": rej_conflicting,
            "sealing_ok_v1": sealing_ok,
        },
        "integrity_v1": {
            "learning_trace_terminal_integrity_v1": integrity_term,
            "learning_trace_rm_breadcrumbs_v1": integrity_rm,
            "integrity_ok_v1": integrity_ok,
        },
        "completion_v1": {
            "student_seam_stop_reason_v1": stop_reason,
            "completion_ok_v1": completion_ok,
        },
        "lifecycle_samples_v1": _lifecycle_samples_v1(events),
        "acceptance_ok_v1": acceptance_ok_v1,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("job_id", help="Parallel job_id (UUID string)")
    ap.add_argument(
        "--trace",
        type=Path,
        default=None,
        help="learning_trace_events_v1.jsonl path (default: memory_paths default)",
    )
    ap.add_argument(
        "--batch-json",
        type=Path,
        default=None,
        help="Saved API/batch JSON with results + student_loop_seam_audit",
    )
    ns = ap.parse_args()
    rep = build_mandatory_proof_v1(
        ns.job_id,
        trace_path=ns.trace,
        batch_json_path=ns.batch_json,
    )
    print(json.dumps(rep, indent=2, default=str))
    return 0 if rep.get("acceptance_ok_v1") else 1


if __name__ == "__main__":
    raise SystemExit(main())
