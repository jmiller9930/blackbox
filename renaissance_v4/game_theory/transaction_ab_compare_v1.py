"""
Transaction-level Baseline (A) vs Student (B) comparison for one scenario.

**Source of truth:** ``batch_parallel_results_v1.json`` → ``replay_outcomes_json`` (``OutcomeRecord`` JSON),
same loader as D13/D14. No L1 aggregates, no ``data_gap`` string in operator export (missing → ``null``).

Router / 026C overlays: job-level router from ``learning_trace_events_v1``; per-trade Student fields from
``student_decision_record_v1`` when available (values ``data_gap`` are stripped to ``null`` for this API).
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.scorecard_drill import (
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    load_batch_parallel_results_v1,
)
from renaissance_v4.game_theory.student_panel_d13 import _ordered_parallel_rows
from renaissance_v4.game_theory.student_panel_d14 import build_student_decision_record_v1

SCHEMA = "operator_transaction_ab_compare_v1"
CONTRACT_VERSION = 1


def _strip_gap(v: Any) -> Any:
    if v == "data_gap" or (isinstance(v, str) and v.strip() == "data_gap"):
        return None
    return v


def _decision_from_outcome(oj: dict[str, Any]) -> str:
    d = str(oj.get("direction") or "").strip().lower()
    if d in ("long", "l"):
        return "ENTER_LONG"
    if d in ("short", "s"):
        return "ENTER_SHORT"
    if d in ("flat", "none", ""):
        return "NO_TRADE"
    return f"OTHER:{d or 'unknown'}"


def _bar_duration_ms_from_scorecard(entry: dict[str, Any] | None) -> int:
    if not isinstance(entry, dict):
        return 300_000
    oba = entry.get("operator_batch_audit")
    if not isinstance(oba, dict):
        return 300_000
    raw = oba.get("candle_timeframe_minutes")
    try:
        m = int(raw)
    except (TypeError, ValueError):
        m = 5
    return max(60_000, m * 60_000)


def _bars_held(oj: dict[str, Any], bar_ms: int) -> int | None:
    meta = oj.get("metadata") if isinstance(oj.get("metadata"), dict) else {}
    for k in ("bars_held_v1", "bars_in_trade", "bars_held"):
        v = meta.get(k)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    et = int(oj.get("entry_time") or 0)
    xt = int(oj.get("exit_time") or 0)
    if et > 0 and xt > et and bar_ms > 0:
        return max(1, int(round((xt - et) / float(bar_ms))))
    return None


def _replay_row_for_scenario(payload: dict[str, Any], scenario_id: str) -> dict[str, Any] | None:
    sid = str(scenario_id or "").strip()
    for row in _ordered_parallel_rows(payload):
        if not row.get("ok"):
            continue
        if str(row.get("scenario_id") or "").strip() == sid:
            return row
    return None


def _trades_from_job_scenario(job_id: str, scenario_id: str) -> tuple[list[dict[str, Any]], str | None]:
    jid = str(job_id or "").strip()
    sid = str(scenario_id or "").strip()
    if not jid or not sid:
        return [], "missing job_id or scenario_id"
    entry = find_scorecard_entry_by_job_id(jid)
    if not isinstance(entry, dict):
        return [], "scorecard_line_not_found"
    bd_s = entry.get("session_log_batch_dir")
    batch_dir, _sc, err = build_scenario_list_for_batch(jid, bd_s if isinstance(bd_s, str) else None)
    if err or not batch_dir or not batch_dir.is_dir():
        return [], err or "batch_dir_invalid"
    payload = load_batch_parallel_results_v1(batch_dir)
    if not isinstance(payload, dict):
        return [], "batch_parallel_results_v1_missing"
    row = _replay_row_for_scenario(payload, sid)
    if not isinstance(row, dict):
        return [], f"scenario_not_in_batch:{sid}"
    out: list[dict[str, Any]] = []
    for oj in row.get("replay_outcomes_json") or []:
        if isinstance(oj, dict):
            out.append(oj)
    return out, None


def _route_bucket_v1(final_route: str | None) -> str | None:
    fr = str(final_route or "").strip()
    if not fr:
        return None
    if fr in ("local_only", "external_blocked_budget", "external_blocked_config", "external_blocked_missing_key"):
        return "local"
    if fr in ("external_review", "external_failed_fallback_local"):
        return "external"
    return "other"


def _router_job_level_from_trace(job_id: str) -> dict[str, Any]:
    evs = read_learning_trace_events_for_job_v1(str(job_id).strip()) or []
    for ev in reversed(evs):
        if str(ev.get("stage") or "").strip() != "reasoning_router_decision_v1":
            continue
        ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
        d = ep.get("reasoning_router_decision_v1")
        if isinstance(d, dict):
            reasons = d.get("escalation_reason_codes_v1") or []
            rcodes = [str(x) for x in reasons if str(x).strip()][:8]
            esc_code = rcodes[0] if len(rcodes) == 1 else (";".join(rcodes) if rcodes else None)
            ext_called = bool(d.get("external_api_attempted_v1"))
            return {
                "router_invoked": True,
                "route_v1": _route_bucket_v1(d.get("final_route_v1")),  # local | external | other
                "final_route_v1": d.get("final_route_v1"),
                "escalation_decision_v1": d.get("escalation_decision_v1"),
                "escalation_code_v1": esc_code,
                "escalation_reason_codes_v1": rcodes,
                "escalation_blockers_v1": d.get("escalation_blockers_v1"),
                "api_call_succeeded_v1": d.get("api_call_succeeded_v1"),
                "external_called_v1": ext_called,
            }
    return {
        "router_invoked": False,
        "route_v1": None,
        "final_route_v1": None,
        "escalation_code_v1": None,
        "external_called_v1": None,
    }


def _learning_overlay_from_decision_rec(
    rec: dict[str, Any] | None,
    entry_b: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(rec, dict) or rec.get("schema") != "student_decision_record_v1":
        return {
            "learning_retrieved": None,
            "learning_record_id": None,
            "learning_applied": None,
            "student_confidence_01": None,
            "confidence_or_decision_influence_note_v1": None,
        }
    infl = _strip_gap(rec.get("influence_summary"))
    rec_id = None
    if isinstance(infl, str) and "student_learning_record_v1:" in infl:
        rec_id = infl.split(":", 1)[-1].strip() or None
    rc = _strip_gap(rec.get("retrieval_count"))
    retrieved = bool(isinstance(rc, (int, float)) and rc > 0)
    if not retrieved and isinstance(entry_b, dict):
        try:
            retrieved = int(entry_b.get("student_retrieval_matches") or 0) > 0
        except (TypeError, ValueError):
            pass
    s_act = _strip_gap(rec.get("student_action_v1")) or _strip_gap(rec.get("student_action"))
    applied = bool(s_act) and str(s_act).lower() not in ("", "none")
    conf = _strip_gap(rec.get("student_confidence_01"))
    note = None
    if isinstance(conf, (int, float)):
        note = "student_confidence_01 from store / decision record (advisory; engine authority unchanged)."
    return {
        "learning_retrieved": bool(retrieved or rec_id or _strip_gap(rec.get("retrieval_signature_key"))),
        "learning_record_id": rec_id,
        "learning_applied": applied,
        "student_confidence_01": conf,
        "confidence_or_decision_influence_note_v1": note,
    }


def _flatten_trade_row(
    *,
    role: str,
    job_id: str,
    scenario_id: str,
    oj: dict[str, Any],
    entry: dict[str, Any] | None,
    bar_ms: int,
    decision_rec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tid = str(oj.get("trade_id") or "").strip()
    rec = decision_rec
    if rec is None and tid and role == "B":
        rec = build_student_decision_record_v1(job_id, tid)
    conf = None
    s_act = None
    if isinstance(rec, dict) and rec.get("schema") == "student_decision_record_v1":
        conf = _strip_gap(rec.get("student_confidence_01"))
        s_act = _strip_gap(rec.get("student_action_v1")) or _strip_gap(rec.get("student_action"))
    meta = oj.get("metadata") if isinstance(oj.get("metadata"), dict) else {}
    return {
        "role": role,
        "job_id": job_id,
        "scenario_id": scenario_id,
        "trade_id": tid or None,
        "bar_index_or_entry_ms": int(oj.get("entry_time") or 0),
        "timestamp_entry_ms": int(oj.get("entry_time") or 0),
        "timestamp_exit_ms": int(oj.get("exit_time") or 0),
        "decision": _decision_from_outcome(oj),
        "confidence_01": conf,
        "student_action_v1": s_act,
        "entry_price": float(oj["entry_price"]) if oj.get("entry_price") is not None else None,
        "exit_price": float(oj["exit_price"]) if oj.get("exit_price") is not None else None,
        "exit_reason": str(oj.get("exit_reason") or "") or None,
        "bars_held": _bars_held(oj, bar_ms),
        "realized_pnl": float(oj["pnl"]) if oj.get("pnl") is not None else None,
        "contributing_signals": oj.get("contributing_signals") if isinstance(oj.get("contributing_signals"), list) else None,
        "outcome_metadata_keys_v1": sorted(meta.keys())[:24] if meta else None,
        "_decision_rec_b_v1": rec if role == "B" else None,
    }


def build_transaction_ab_compare_v1(
    *,
    job_id_baseline: str,
    job_id_student: str,
    scenario_id: str,
) -> dict[str, Any]:
    """
    Side-by-side rows: same ``scenario_id``, trades aligned by **order** in ``replay_outcomes_json``
    (deterministic replay for the same tape should preserve trade ordering).
    """
    ja, jb, sid = (
        str(job_id_baseline or "").strip(),
        str(job_id_student or "").strip(),
        str(scenario_id or "").strip(),
    )
    out: dict[str, Any] = {
        "ok": False,
        "schema": SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "job_id_baseline": ja,
        "job_id_student": jb,
        "scenario_id": sid,
        "error": None,
        "rows": [],
        "router_overlay_job_b_v1": {},
        "notes_v1": [
            "Trades are paired by ordinal index within scenario replay_outcomes_json (full set, not sampled).",
            "If Baseline and Student trade counts differ, unmatched rows appear with null on one side.",
        ],
    }
    if not ja or not jb or not sid:
        out["error"] = "job_id_baseline, job_id_student, and scenario_id are required"
        return out

    a_list, err_a = _trades_from_job_scenario(ja, sid)
    b_list, err_b = _trades_from_job_scenario(jb, sid)
    if err_a:
        out["error"] = f"baseline: {err_a}"
        return out
    if err_b:
        out["error"] = f"student: {err_b}"
        return out

    entry_a = find_scorecard_entry_by_job_id(ja)
    entry_b = find_scorecard_entry_by_job_id(jb)
    bar_ms_a = _bar_duration_ms_from_scorecard(entry_a if isinstance(entry_a, dict) else None)
    bar_ms_b = _bar_duration_ms_from_scorecard(entry_b if isinstance(entry_b, dict) else None)

    flat_a = [
        _flatten_trade_row(role="A", job_id=ja, scenario_id=sid, oj=x, entry=entry_a, bar_ms=bar_ms_a)
        for x in a_list
    ]
    flat_b_raw: list[dict[str, Any]] = []
    for x in b_list:
        tid_b = str(x.get("trade_id") or "").strip()
        drec = build_student_decision_record_v1(jb, tid_b) if tid_b else None
        flat_b_raw.append(
            _flatten_trade_row(
                role="B",
                job_id=jb,
                scenario_id=sid,
                oj=x,
                entry=entry_b,
                bar_ms=bar_ms_b,
                decision_rec=drec,
            )
        )

    def _strip_internal_keys(d: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(d, dict):
            return None
        return {k: v for k, v in d.items() if not str(k).startswith("_")}

    flat_b = [_strip_internal_keys(x) for x in flat_b_raw]

    router_b = _router_job_level_from_trace(jb)

    def _decision_changed_v1(ra: dict[str, Any] | None, rb: dict[str, Any] | None) -> bool | None:
        if not ra and not rb:
            return None
        if bool(ra) != bool(rb):
            return True
        return (ra or {}).get("decision") != (rb or {}).get("decision")

    def _exit_reason_changed_v1(ra: dict[str, Any] | None, rb: dict[str, Any] | None) -> bool | None:
        if not ra and not rb:
            return None
        if not ra or not rb:
            return True
        return (ra.get("exit_reason") != rb.get("exit_reason"))

    n = max(len(flat_a), len(flat_b))
    rows: list[dict[str, Any]] = []
    for i in range(n):
        ra = flat_a[i] if i < len(flat_a) else None
        rb = flat_b[i] if i < len(flat_b) else None
        ca = (ra or {}).get("confidence_01")
        cb = (rb or {}).get("confidence_01")
        pa = (ra or {}).get("realized_pnl")
        pb = (rb or {}).get("realized_pnl")
        drec_b = flat_b_raw[i].get("_decision_rec_b_v1") if i < len(flat_b_raw) else None
        row: dict[str, Any] = {
            "pair_index_v1": i,
            "baseline": ra,
            "student": rb,
            "delta": {
                "decision_changed": _decision_changed_v1(ra, rb),
                "confidence_delta": (
                    float(cb) - float(ca)
                    if isinstance(ca, (int, float)) and isinstance(cb, (int, float))
                    else None
                ),
                "exit_reason_changed": _exit_reason_changed_v1(ra, rb),
                "pnl_delta": (
                    float(pb) - float(pa) if isinstance(pa, (int, float)) and isinstance(pb, (int, float)) else None
                ),
            },
            "learning_overlay_b_v1": _learning_overlay_from_decision_rec(
                drec_b if isinstance(drec_b, dict) else None,
                entry_b if isinstance(entry_b, dict) else None,
            ),
            "router_overlay_b_v1": dict(router_b),
        }
        rows.append(row)

    out["rows"] = rows
    out["router_overlay_job_b_v1"] = router_b
    excerpt_n = min(20, len(rows))
    out["excerpt_rows_v1"] = rows[:excerpt_n] if excerpt_n else []
    out["excerpt_row_count_v1"] = excerpt_n
    out["ok"] = True
    return out


def transaction_ab_compare_to_csv_v1(payload: dict[str, Any]) -> str:
    """Flatten ``rows`` to CSV (no ``data_gap`` cell values — None → empty)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "pair_index",
            "a_trade_id",
            "a_entry_ms",
            "a_decision",
            "a_confidence",
            "a_entry_px",
            "a_exit_reason",
            "a_bars_held",
            "a_pnl",
            "b_trade_id",
            "b_entry_ms",
            "b_decision",
            "b_confidence",
            "b_entry_px",
            "b_exit_reason",
            "b_bars_held",
            "b_pnl",
            "delta_decision_changed",
            "delta_confidence",
            "delta_exit_reason_changed",
            "delta_pnl",
            "b_learning_retrieved",
            "b_learning_record_id",
            "b_router_invoked",
            "b_route_local_or_external",
            "b_final_route",
            "b_escalation_code",
            "b_external_called",
        ]
    )
    router_fallback = payload.get("router_overlay_job_b_v1") if isinstance(payload, dict) else {}
    for r in payload.get("rows") or []:
        if not isinstance(r, dict):
            continue
        a = r.get("baseline") if isinstance(r.get("baseline"), dict) else {}
        b = r.get("student") if isinstance(r.get("student"), dict) else {}
        d = r.get("delta") if isinstance(r.get("delta"), dict) else {}
        lo = r.get("learning_overlay_b_v1") if isinstance(r.get("learning_overlay_b_v1"), dict) else {}
        rtr = r.get("router_overlay_b_v1") if isinstance(r.get("router_overlay_b_v1"), dict) else router_fallback
        r_inv = rtr.get("router_invoked") if isinstance(rtr, dict) else None
        r_route = rtr.get("final_route_v1") if isinstance(rtr, dict) else None
        r_bucket = rtr.get("route_v1") if isinstance(rtr, dict) else None
        r_esc = rtr.get("escalation_code_v1") if isinstance(rtr, dict) else None
        r_ext = rtr.get("external_called_v1") if isinstance(rtr, dict) else None
        w.writerow(
            [
                r.get("pair_index_v1"),
                a.get("trade_id"),
                a.get("timestamp_entry_ms"),
                a.get("decision"),
                a.get("confidence_01"),
                a.get("entry_price"),
                a.get("exit_reason"),
                a.get("bars_held"),
                a.get("realized_pnl"),
                b.get("trade_id"),
                b.get("timestamp_entry_ms"),
                b.get("decision"),
                b.get("confidence_01"),
                b.get("entry_price"),
                b.get("exit_reason"),
                b.get("bars_held"),
                b.get("realized_pnl"),
                d.get("decision_changed"),
                d.get("confidence_delta"),
                d.get("exit_reason_changed"),
                d.get("pnl_delta"),
                lo.get("learning_retrieved"),
                lo.get("learning_record_id"),
                r_inv,
                r_bucket,
                r_route,
                r_esc,
                r_ext,
            ]
        )
    return buf.getvalue()


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA",
    "build_transaction_ab_compare_v1",
    "transaction_ab_compare_to_csv_v1",
]

