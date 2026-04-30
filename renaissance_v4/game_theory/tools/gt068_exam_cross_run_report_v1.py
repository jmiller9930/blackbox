#!/usr/bin/env python3
"""
GT068 — Cross-run exam report: trace-backed determinism hints, LLM repair/Ollama rounds,
optional GT056/GT055 from the student learning store (same ``run_id`` as parallel ``job_id``).

Does **not** prove Referee replay bitwise identity (workers + SQLite versioning); it answers the
Student-visible layers the directive named.

Usage::

    python3 -m renaissance_v4.game_theory.tools.gt068_exam_cross_run_report_v1 \\
        <job_id_run1> <job_id_run2> [<job_id_run3> ...] \\
        [--trace PATH] [--student-learning-store PATH]

Outputs JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.opportunity_selection_metrics_v1 import compute_opportunity_selection_metrics_v1
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    default_student_learning_store_path_v1,
    list_student_learning_records_by_run_id,
)


def _key(scenario_id: str | None, trade_id: str | None) -> str | None:
    s = str(scenario_id or "").strip()
    t = str(trade_id or "").strip()
    if not s or not t:
        return None
    return f"{s}\t{t}"


def _actions_from_sealed_v1(evs: list[dict[str, Any]]) -> dict[str, str]:
    """Latest ``student_action_v1`` echo per (scenario, trade) from ``student_output_sealed`` rows."""
    latest: dict[str, tuple[float, str]] = {}
    for i, ev in enumerate(evs):
        if str(ev.get("stage") or "") != "student_output_sealed":
            continue
        k = _key(ev.get("scenario_id"), ev.get("trade_id"))
        if k is None:
            continue
        ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
        act = str(ep.get("student_action_v1_echo") or ep.get("student_action_v1") or "").strip().lower()
        latest[k] = (float(i), act)
    return {k: v[1] for k, v in latest.items()}


def _trade_keys_from_stage_v1(evs: list[dict[str, Any]], stage: str) -> set[str]:
    out: set[str] = set()
    for ev in evs:
        if str(ev.get("stage") or "") != stage:
            continue
        k = _key(ev.get("scenario_id"), ev.get("trade_id"))
        if k:
            out.add(k)
    return out


def _llm_resolution_aggregate_v1(evs: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [e for e in evs if str(e.get("stage") or "") == "student_llm_contract_resolution_v1"]
    n = len(rows)
    json_rep = 0
    val_rep = 0
    retry_used = 0
    rounds_sum = 0
    rounds_max = 0
    accepted = 0
    for e in rows:
        ep = e.get("evidence_payload") if isinstance(e.get("evidence_payload"), dict) else {}
        if ep.get("json_repair_attempted_v1"):
            json_rep += 1
        if ep.get("validation_repair_attempted_v1"):
            val_rep += 1
        if ep.get("json_contract_retry_used_v1"):
            retry_used += 1
        r = int(ep.get("ollama_chat_rounds_v1") or 0)
        rounds_sum += r
        rounds_max = max(rounds_max, r)
        if ep.get("final_validation_accepted_v1"):
            accepted += 1
    return {
        "student_llm_contract_resolution_events_v1": int(n),
        "trades_json_repair_attempted_v1": int(json_rep),
        "trades_validation_repair_attempted_v1": int(val_rep),
        "trades_any_contract_retry_used_v1": int(retry_used),
        "pct_trades_json_repair_v1": round(100.0 * json_rep / n, 4) if n else None,
        "pct_trades_validation_repair_v1": round(100.0 * val_rep / n, 4) if n else None,
        "ollama_chat_rounds_sum_v1": int(rounds_sum),
        "ollama_chat_rounds_max_v1": int(rounds_max),
        "ollama_chat_rounds_mean_v1": round(rounds_sum / n, 6) if n else None,
        "final_validation_accepted_count_v1": int(accepted),
    }


def _gt055_label_counts_v1(records: list[dict[str, Any]]) -> dict[str, Any]:
    labels: dict[int, list[float]] = defaultdict(list)
    for rec in records:
        sub = rec.get("referee_outcome_subset") if isinstance(rec.get("referee_outcome_subset"), dict) else {}
        lab = sub.get("triple_barrier_label_v1")
        try:
            li = int(lab)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        try:
            pnl = float(sub.get("pnl"))
        except (TypeError, ValueError):
            continue
        labels[li].append(pnl)
    pos_n = neg_n = 0
    pos_sum = neg_sum = 0.0
    for li, pnls in labels.items():
        if li > 0:
            pos_n += len(pnls)
            pos_sum += sum(pnls)
        elif li < 0:
            neg_n += len(pnls)
            neg_sum += sum(pnls)
    return {
        "triple_barrier_label_histogram_v1": {str(k): len(v) for k, v in sorted(labels.items())},
        "positive_label_count_v1": int(pos_n),
        "negative_label_count_v1": int(neg_n),
        "avg_pnl_positive_labels_v1": round(pos_sum / pos_n, 10) if pos_n else None,
        "avg_pnl_negative_labels_v1": round(neg_sum / neg_n, 10) if neg_n else None,
    }


def _per_job_v1(
    job_id: str,
    *,
    trace_path: Path,
    store_path: Path | None,
) -> dict[str, Any]:
    jid = str(job_id or "").strip()
    evs = read_learning_trace_events_for_job_v1(jid, path=trace_path)
    sealed_keys = _trade_keys_from_stage_v1(evs, "student_output_sealed")
    ere_keys = _trade_keys_from_stage_v1(evs, "entry_reasoning_sealed_v1")
    actions = _actions_from_sealed_v1(evs)
    taken = sum(1 for a in actions.values() if a in ("enter_long", "enter_short"))
    skipped = sum(1 for a in actions.values() if a == "no_trade")
    out: dict[str, Any] = {
        "schema": "gt068_exam_job_slice_v1",
        "job_id": jid,
        "trace_line_count_v1": len(evs),
        "trade_keys_entry_reasoning_sealed_v1": len(ere_keys),
        "trade_keys_student_output_sealed_v1": len(sealed_keys),
        "student_actions_distinct_keys_v1": len(actions),
        "selection_student_trades_taken_proxy_v1": int(taken),
        "selection_student_trades_skipped_proxy_v1": int(skipped),
        "llm_resolution_aggregate_v1": _llm_resolution_aggregate_v1(evs),
    }
    if store_path is not None and store_path.is_file():
        recs = list_student_learning_records_by_run_id(store_path, jid)
        out["student_learning_rows_for_run_v1"] = len(recs)
        try:
            out["gt056_opportunity_selection_v1"] = compute_opportunity_selection_metrics_v1(recs)
        except Exception as e:
            out["gt056_opportunity_selection_v1"] = {"schema": "opportunity_selection_metrics_v1", "error": str(e)}
        out["gt055_label_distribution_v1"] = _gt055_label_counts_v1(recs)
    else:
        out["student_learning_store_note_v1"] = "no_store_path_or_missing_file_gt056_gt055_skipped_v1"
    out["student_action_by_trade_key_v1"] = dict(sorted(actions.items()))
    return out


def _pairwise_decision_diffs_v1(
    jobs: list[str],
    per: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare ``student_action_by_trade_key_v1`` on intersection of trade keys."""
    rows: list[dict[str, Any]] = []
    act_maps = {j: dict(per[j].get("student_action_by_trade_key_v1") or {}) for j in jobs}
    for i, a in enumerate(jobs):
        for b in jobs[i + 1 :]:
            ka = set(act_maps[a].keys())
            kb = set(act_maps[b].keys())
            inter = ka & kb
            diff = sum(1 for k in inter if act_maps[a].get(k) != act_maps[b].get(k))
            rows.append(
                {
                    "pair_v1": [a, b],
                    "intersection_trade_keys_v1": len(inter),
                    "decision_mismatch_count_v1": int(diff),
                    "only_in_first_v1": len(ka - kb),
                    "only_in_second_v1": len(kb - ka),
                }
            )
    return rows


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="GT068 cross-run trace + optional GT056/GT055 aggregates.")
    p.add_argument("job_ids", nargs="+", help="Parallel batch job_id values (= run_id on learning rows).")
    p.add_argument(
        "--trace",
        type=Path,
        default=None,
        help="learning_trace_events_v1.jsonl path (default: pattern-game memory path).",
    )
    p.add_argument(
        "--student-learning-store",
        type=Path,
        default=None,
        help="student_learning_store JSONL (default: default_student_learning_store_path_v1()).",
    )
    args = p.parse_args(argv)
    trace_path = (args.trace or default_learning_trace_events_jsonl()).expanduser().resolve()
    store_path: Path | None = None
    if args.student_learning_store is not None:
        store_path = args.student_learning_store.expanduser().resolve()
    else:
        try:
            store_path = default_student_learning_store_path_v1().expanduser().resolve()
        except Exception:
            store_path = None

    jobs = [str(x).strip() for x in args.job_ids if str(x).strip()]
    per = {j: _per_job_v1(j, trace_path=trace_path, store_path=store_path) for j in jobs}

    report: dict[str, Any] = {
        "schema": "gt068_exam_cross_run_report_v1",
        "trace_path_v1": str(trace_path),
        "student_learning_store_path_v1": str(store_path) if store_path else None,
        "dominant_non_determinism_hypothesis_note_v1": (
            "If Run1 vs Run2 differ on intersection trade keys with LLM profile: H1/H2 (Ollama + repair) "
            "before H3-H5. RM preflight uses stub seal, not live LLM (see rm_preflight skipped llm_inference_v1). "
            "Extended calendar (18m vs 12m) changes trade population - overlap metrics below do not assert same slice."
        ),
        "per_job_v1": per,
        "pairwise_student_action_diffs_v1": _pairwise_decision_diffs_v1(jobs, per),
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
