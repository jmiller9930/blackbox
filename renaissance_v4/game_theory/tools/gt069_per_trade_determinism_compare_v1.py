#!/usr/bin/env python3
"""
GT069 — Per-trade determinism compare (Run A vs Run B on the same slice).

Uses ``learning_trace_events_v1`` as primary evidence. Optionally enriches with
``student_learning_records_v1`` for ``student_output`` fingerprint and ``student_decision_ref``.

Classification (shortest path triage)::

    digest differs (or missing on either side) → RM / retrieval / store drift
    digest matches but sealed action or SO fingerprint or LLM repair tuple differs → LLM seam drift

Usage::

    python3 -m renaissance_v4.game_theory.tools.gt069_per_trade_determinism_compare_v1 \\
        <job_id_a> <job_id_b> [--trace PATH] [--student-learning-store PATH]

Outputs JSON on stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    default_student_learning_store_path_v1,
    list_student_learning_records_by_run_id,
)


def _trade_key(scenario_id: str | None, trade_id: str | None) -> str | None:
    s = str(scenario_id or "").strip()
    t = str(trade_id or "").strip()
    if not s or not t:
        return None
    return f"{s}\t{t}"


def _student_output_content_sha256_v1(so: dict[str, Any]) -> str:
    canonical = json.dumps(so, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _latest_by_trade_v1(
    evs: list[dict[str, Any]],
    stage: str,
    pick: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    """Last event wins (append order within job trace)."""
    best: dict[str, tuple[float, Any]] = {}
    for i, ev in enumerate(evs):
        if str(ev.get("stage") or "") != stage:
            continue
        k = _trade_key(ev.get("scenario_id"), ev.get("trade_id"))
        if k is None:
            continue
        best[k] = (float(i), pick(ev))
    return {k: v[1] for k, v in best.items()}


def _pick_digest_v1(ev: dict[str, Any]) -> str | None:
    ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
    out = ep.get("outputs")
    if isinstance(out, dict):
        d = str(out.get("entry_reasoning_eval_digest_v1") or "").strip()
        return d or None
    return None


def _pick_retrieval_matches_v1(ev: dict[str, Any]) -> int | None:
    ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
    try:
        return int(ep.get("student_retrieval_matches"))
    except (TypeError, ValueError):
        return None


def _pick_llm_resolution_slim_v1(ev: dict[str, Any]) -> dict[str, Any]:
    ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
    return {
        "json_repair_attempted_v1": bool(ep.get("json_repair_attempted_v1")),
        "validation_repair_attempted_v1": bool(ep.get("validation_repair_attempted_v1")),
        "json_contract_retry_used_v1": bool(ep.get("json_contract_retry_used_v1")),
        "ollama_chat_rounds_v1": int(ep.get("ollama_chat_rounds_v1") or 0),
        "student_llm_contract_repair_path_v1": bool(ep.get("student_llm_contract_repair_path_v1")),
        "final_validation_accepted_v1": bool(ep.get("final_validation_accepted_v1")),
    }


def _pick_sealed_action_v1(ev: dict[str, Any]) -> str | None:
    ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
    a = str(ep.get("student_action_v1_echo") or ep.get("student_action_v1") or "").strip().lower()
    return a or None


def _pick_router_route_v1(ev: dict[str, Any]) -> str | None:
    ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
    d = ep.get("reasoning_router_decision_v1")
    if isinstance(d, dict):
        r = str(d.get("final_route_v1") or "").strip()
        return r or None
    return None


def _learning_rows_by_graded_unit_v1(
    store_path: Path,
    job_id: str,
) -> dict[str, list[dict[str, Any]]]:
    if not store_path.is_file():
        return {}
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in list_student_learning_records_by_run_id(store_path, job_id):
        if not isinstance(rec, dict):
            continue
        so = rec.get("student_output")
        tid = ""
        if isinstance(so, dict):
            tid = str(so.get("graded_unit_id") or "").strip()
        if not tid:
            tid = str(rec.get("graded_unit_id") or "").strip()
        if tid:
            out[tid].append(rec)
    return dict(out)


def _learning_extras_for_trade_v1(
    rows_by_tid: dict[str, list[dict[str, Any]]],
    trade_id: str,
) -> tuple[str | None, str | None, bool]:
    """
    Returns (student_output_sha256, student_decision_ref, ambiguous_multi_row).
    """
    rows = rows_by_tid.get(str(trade_id).strip(), [])
    if not rows:
        return None, None, False
    if len(rows) > 1:
        # Same graded_unit_id twice in one run — rare; still hash first row but flag.
        r0 = rows[0]
        so = r0.get("student_output") if isinstance(r0.get("student_output"), dict) else {}
        fp = _student_output_content_sha256_v1(so) if so else None
        ref = str(so.get("student_decision_ref") or "").strip() if so else None
        return fp, ref or None, True
    r0 = rows[0]
    so = r0.get("student_output") if isinstance(r0.get("student_output"), dict) else {}
    if not so:
        return None, None, False
    return (
        _student_output_content_sha256_v1(so),
        str(so.get("student_decision_ref") or "").strip() or None,
        False,
    )


def build_gt069_compare_report_v1(
    job_id_a: str,
    job_id_b: str,
    *,
    trace_path: Path,
    store_path: Path | None,
) -> dict[str, Any]:
    ja = str(job_id_a or "").strip()
    jb = str(job_id_b or "").strip()
    ev_a = read_learning_trace_events_for_job_v1(ja, path=trace_path)
    ev_b = read_learning_trace_events_for_job_v1(jb, path=trace_path)

    dig_a = _latest_by_trade_v1(ev_a, "entry_reasoning_sealed_v1", _pick_digest_v1)
    dig_b = _latest_by_trade_v1(ev_b, "entry_reasoning_sealed_v1", _pick_digest_v1)
    ret_a = _latest_by_trade_v1(ev_a, "memory_retrieval_completed", _pick_retrieval_matches_v1)
    ret_b = _latest_by_trade_v1(ev_b, "memory_retrieval_completed", _pick_retrieval_matches_v1)
    llm_a = _latest_by_trade_v1(ev_a, "student_llm_contract_resolution_v1", _pick_llm_resolution_slim_v1)
    llm_b = _latest_by_trade_v1(ev_b, "student_llm_contract_resolution_v1", _pick_llm_resolution_slim_v1)
    act_a = _latest_by_trade_v1(ev_a, "student_output_sealed", _pick_sealed_action_v1)
    act_b = _latest_by_trade_v1(ev_b, "student_output_sealed", _pick_sealed_action_v1)
    rt_a = _latest_by_trade_v1(ev_a, "reasoning_router_decision_v1", _pick_router_route_v1)
    rt_b = _latest_by_trade_v1(ev_b, "reasoning_router_decision_v1", _pick_router_route_v1)

    sealed_keys_a = set(act_a.keys())
    sealed_keys_b = set(act_b.keys())
    intersection = sorted(sealed_keys_a & sealed_keys_b)

    rows_by_tid_a: dict[str, list[dict[str, Any]]] = {}
    rows_by_tid_b: dict[str, list[dict[str, Any]]] = {}
    if store_path is not None:
        rows_by_tid_a = _learning_rows_by_graded_unit_v1(store_path, ja)
        rows_by_tid_b = _learning_rows_by_graded_unit_v1(store_path, jb)

    per_rows: list[dict[str, Any]] = []
    n_rm = n_llm = n_none = n_ins = 0

    for tk in intersection:
        _scen, _sep, tid = tk.partition("\t")
        da, db = dig_a.get(tk), dig_b.get(tk)
        ra, rb = ret_a.get(tk), ret_b.get(tk)
        la, lb = llm_a.get(tk), llm_b.get(tk)
        aa, ab = act_a.get(tk), act_b.get(tk)
        fa, fambig_a = (None, False)
        fb, fambig_b = (None, False)
        refa, refb = None, None
        if store_path is not None:
            fa, refa, fambig_a = _learning_extras_for_trade_v1(rows_by_tid_a, tid)
            fb, refb, fambig_b = _learning_extras_for_trade_v1(rows_by_tid_b, tid)

        digest_match = bool(da and db and da == db)
        retrieval_match = ra == rb
        llm_match = la == lb
        action_match = aa == ab
        fp_match = None
        if fa is not None and fb is not None:
            fp_match = fa == fb
        ref_match = None
        if refa is not None and refb is not None:
            ref_match = refa == refb

        router_a, router_b = rt_a.get(tk), rt_b.get(tk)
        router_match = router_a == router_b if (router_a or router_b) else True

        if not da or not db:
            drift = "insufficient_trace"
            n_ins += 1
        elif da != db:
            drift = "rm_or_retrieval"
            n_rm += 1
        elif (not action_match) or (fp_match is False) or (not llm_match) or (not router_match):
            drift = "llm_seam"
            n_llm += 1
        else:
            drift = "none"
            n_none += 1

        per_rows.append(
            {
                "trade_key_v1": tk,
                "entry_reasoning_eval_digest_v1": {"run_a": da, "run_b": db, "match_v1": digest_match},
                "student_retrieval_matches_v1": {"run_a": ra, "run_b": rb, "match_v1": retrieval_match},
                "student_llm_contract_resolution_v1": {"run_a": la, "run_b": lb, "match_v1": llm_match},
                "reasoning_router_final_route_v1": {"run_a": router_a, "run_b": router_b, "match_v1": router_match},
                "student_output_content_sha256_v1": {"run_a": fa, "run_b": fb, "match_v1": fp_match},
                "student_decision_ref_v1": {"run_a": refa, "run_b": refb, "match_v1": ref_match},
                "sealed_student_action_v1": {"run_a": aa, "run_b": ab, "match_v1": action_match},
                "learning_store_ambiguous_multi_row_v1": {"run_a": fambig_a, "run_b": fambig_b},
                "drift_classification_v1": drift,
            }
        )

    return {
        "schema": "gt069_per_trade_determinism_compare_v1",
        "job_id_run_a_v1": ja,
        "job_id_run_b_v1": jb,
        "trace_path_v1": str(trace_path),
        "student_learning_store_path_v1": str(store_path) if store_path else None,
        "trade_keys_sealed_run_a_v1": len(sealed_keys_a),
        "trade_keys_sealed_run_b_v1": len(sealed_keys_b),
        "intersection_trade_keys_v1": len(intersection),
        "summary_v1": {
            "drift_rm_or_retrieval_count_v1": n_rm,
            "drift_llm_seam_count_v1": n_llm,
            "drift_none_count_v1": n_none,
            "drift_insufficient_trace_count_v1": n_ins,
        },
        "interpretation_note_v1": (
            "digest mismatch → RM inputs/path differ (often retrieval store or bar packet). "
            "digest match + downstream mismatch → Student LLM / repair / authority merge / router call path."
        ),
        "per_trade_v1": per_rows,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="GT069 per-trade determinism compare (two job_ids).")
    ap.add_argument("job_id_a", help="First parallel batch job_id (= run_id on learning rows).")
    ap.add_argument("job_id_b", help="Second job_id.")
    ap.add_argument("--trace", type=Path, default=None, help="learning_trace_events_v1.jsonl path.")
    ap.add_argument(
        "--student-learning-store",
        type=Path,
        default=None,
        help="student_learning_store JSONL (optional fingerprint + decision_ref).",
    )
    args = ap.parse_args(argv)
    trace_path = (args.trace or default_learning_trace_events_jsonl()).expanduser().resolve()
    store_path: Path | None = None
    if args.student_learning_store is not None:
        store_path = args.student_learning_store.expanduser().resolve()
    else:
        try:
            store_path = default_student_learning_store_path_v1().expanduser().resolve()
        except Exception:
            store_path = None

    rep = build_gt069_compare_report_v1(
        args.job_id_a,
        args.job_id_b,
        trace_path=trace_path,
        store_path=store_path if store_path and store_path.is_file() else None,
    )
    if store_path and not store_path.is_file():
        rep["student_learning_store_note_v1"] = "path_missing_or_not_file_v1_store_skipped_v1"
    print(json.dumps(rep, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
