"""
Operator A/B report — Baseline (A) vs Student (B) — single Markdown artifact (GT product surface).

Sources (server-side, same host as Pattern Game):
  * :func:`debug_learning_loop_trace_v1.build_debug_learning_loop_trace_v1` for B (with ``control_job_id=A``)
  * Scorecard lines for A and B
  * :func:`reasoning_model_operator_surface_v1.get_reasoning_model_operator_snapshot_v1` for current stack health (note: point-in-time, not historical)
  * ``learning_effect_closure_026c_v1`` embedded in the debug trace for B
"""

from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from typing import Any

SCHEMA = "operator_baseline_vs_student_report_v1"
CONTRACT_VERSION = 1


def _s(x: Any, default: str = "—") -> str:
    if x is None:
        return default
    t = str(x).strip()
    return t if t else default


def _md_kv(k: str, v: Any) -> str:
    return f"- **{k}:** {_s(v)}"


def _last_event_payload(
    events: list[dict[str, Any]], stage: str, key: str
) -> dict[str, Any] | None:
    for ev in reversed(events or []):
        if str(ev.get("stage") or "").strip() != stage:
            continue
        ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
        inner = ep.get(key)
        if isinstance(inner, dict):
            return inner
    return None


def _router_lines_from_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    d = _last_event_payload(events, "reasoning_router_decision_v1", "reasoning_router_decision_v1")
    if not isinstance(d, dict):
        return {}
    esc = str(d.get("escalation_decision_v1") or "")
    blockers = d.get("escalation_blockers_v1") if isinstance(d.get("escalation_blockers_v1"), list) else []
    final = str(d.get("final_route_v1") or "")
    ext_ok = d.get("api_call_succeeded_v1")
    return {
        "escalation_decision_v1": esc or "—",
        "final_route_v1": final or "—",
        "escalation_blockers_v1": ", ".join(str(x) for x in blockers[:8]) or "—",
        "api_call_succeeded_v1": ext_ok,
        "raw": d,
    }


def _lifecycle_brief(overlay: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(overlay, dict):
        return {}
    ts = overlay.get("lifecycle_tape_summary_v1")
    if not isinstance(ts, dict):
        return {}
    return {
        "exit_reason_code_v1": ts.get("exit_reason_code_v1"),
        "closed_v1": ts.get("closed_v1"),
        "hold_bars_inferred_v1": ts.get("hold_bars_inferred_v1"),
        "pnl_net_v1": ts.get("pnl_net_v1") or ts.get("realized_pnl_v1"),
    }


def _entry_from_oba(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    oba = entry.get("operator_batch_audit")
    if not isinstance(oba, dict):
        return {}
    return {
        "pattern": oba.get("operator_recipe_id") or entry.get("operator_recipe_id") or entry.get("pattern"),
        "evaluation_window_mode": oba.get("evaluation_window_mode") or oba.get("evaluation_window"),
        "trade_window_mode": oba.get("trade_window_mode"),
        "candle_timeframe_minutes": oba.get("candle_timeframe_minutes"),
    }


def _plain_outcome(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    act_a = _s(a.get("student_action_v1") or a.get("student_output_direction"))
    act_b = _s(b.get("student_action_v1") or b.get("student_output_direction"))
    if act_a != act_b:
        lines.append(f"Entry-style action differed: Baseline **{act_a}** vs Student **{act_b}**.")
    else:
        lines.append(f"Entry-style action matched surface field: **{act_b}** (compare L3 for per-trade truth).")
    tw_a = a.get("avg_trade_win_pct")
    tw_b = b.get("avg_trade_win_pct")
    if tw_a is not None or tw_b is not None:
        lines.append(f"Referee batch trade-win proxy: Baseline **{_s(tw_a)}** · Student **{_s(tw_b)}**.")
    ex_a = a.get("expectancy_per_trade")
    ex_b = b.get("expectancy_per_trade")
    if ex_a is not None or ex_b is not None:
        lines.append(f"Expectancy / trade (scorecard): Baseline **{_s(ex_a)}** · Student **{_s(ex_b)}**.")
    if not lines:
        lines.append("Insufficient scorecard fields for automatic outcome comparison — inspect Referee outcomes in UI.")
    return lines


def build_operator_baseline_vs_student_report_markdown_v1(
    *,
    job_id_baseline: str,
    job_id_student: str,
    run_a_job_id: str | None = None,
    environment: str | None = None,
    ui_version: str | None = None,
) -> str:
    """
    Build the full Markdown report. Requires Pattern Game data on this host (scorecard + trace files).
    """
    from renaissance_v4.game_theory.debug_learning_loop_trace_v1 import build_debug_learning_loop_trace_v1
    from renaissance_v4.game_theory.reasoning_model_operator_surface_v1 import (
        get_reasoning_model_operator_snapshot_v1,
    )
    from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id

    ja = str(job_id_baseline or "").strip()
    jb = str(job_id_student or "").strip()
    env = environment or os.environ.get("PATTERN_GAME_AB_REPORT_ENV") or socket.gethostname()
    ui = ui_version or os.environ.get("PATTERN_GAME_WEB_UI_VERSION") or "unknown"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    entry_a = find_scorecard_entry_by_job_id(ja) if ja else None
    entry_b = find_scorecard_entry_by_job_id(jb) if jb else None
    meta_a = _entry_from_oba(entry_a)
    meta_b = _entry_from_oba(entry_b)

    trace_b: dict[str, Any] = {}
    err_b: str | None = None
    if jb:
        try:
            trace_b = build_debug_learning_loop_trace_v1(
                jb, run_a_job_id=(str(run_a_job_id).strip() or None), control_job_id=(ja or None)
            )
        except Exception as e:
            err_b = f"{type(e).__name__}: {e}"[:500]
            trace_b = {"ok": False, "error": err_b}

    events_b: list[dict[str, Any]] = list(trace_b.get("learning_trace_events_v1") or [])
    router = _router_lines_from_events(events_b)
    closure = trace_b.get("learning_effect_closure_026c_v1")
    if not isinstance(closure, dict):
        closure = {}
    overlay_b = trace_b.get("lifecycle_trace_overlay_v1") if isinstance(trace_b, dict) else {}
    life_b = _lifecycle_brief(overlay_b if isinstance(overlay_b, dict) else {})

    trace_a: dict[str, Any] = {}
    if ja:
        try:
            trace_a = build_debug_learning_loop_trace_v1(ja)
        except Exception:
            trace_a = {"ok": False}
    events_a: list[dict[str, Any]] = list(trace_a.get("learning_trace_events_v1") or [])
    overlay_a = trace_a.get("lifecycle_trace_overlay_v1") if isinstance(trace_a, dict) else {}
    life_a = _lifecycle_brief(overlay_a if isinstance(overlay_a, dict) else {})

    snap = get_reasoning_model_operator_snapshot_v1(jb or None)
    if not isinstance(snap, dict):
        snap = {}
    fields = snap.get("fields_v1")
    if not isinstance(fields, dict):
        fields = {}
    primary = str(snap.get("primary_escalation_code_v1") or fields.get("operator_block_code_v1") or "—")
    esc_sum = str(snap.get("escalation_summary_v1") or "—")
    rm_head = str(fields.get("headline_badge_v1") or snap.get("headline_badge_v1") or "—")

    inj = closure.get("run_b_026c_injection_and_apply_v1")
    if not isinstance(inj, dict):
        inj = {}
    det_apply = bool(inj.get("deterministic_learning_context_026c_v1") or inj.get("deterministic_apply_markers_v1"))

    lines: list[str] = []
    lines.append("# Baseline vs Student — operator A/B report")
    lines.append("")
    lines.append(f"*Generated: `{now}` · schema `{SCHEMA}` v{CONTRACT_VERSION}*")
    lines.append("")
    lines.append("## 1. Run identification")
    lines.append("")
    lines.append(_md_kv("Run A (Baseline) `job_id`", ja))
    lines.append(_md_kv("Run B (Student) `job_id`", jb))
    lines.append(_md_kv("Pattern / recipe", meta_b.get("pattern") or meta_a.get("pattern")))
    lines.append(_md_kv("Evaluation window", meta_b.get("evaluation_window_mode") or meta_a.get("evaluation_window_mode")))
    lines.append(_md_kv("Trade window", meta_b.get("trade_window_mode") or meta_a.get("trade_window_mode")))
    lines.append(_md_kv("Environment", env))
    lines.append(_md_kv("Pattern Game UI version", ui))
    lines.append("")

    lines.append("## 2. High-level outcome")
    lines.append("")
    if entry_a and entry_b:
        for p in _plain_outcome(entry_a, entry_b):
            lines.append(f"- {p}")
    else:
        lines.append("- One or both scorecard lines were not found — cannot compare outcomes from scorecard alone.")
    lines.append("")

    lines.append("## 3. Decision comparison (scorecard surface)")
    lines.append("")
    lines.append(_md_kv("Baseline — `student_action_v1` / direction", entry_a.get("student_action_v1") if entry_a else None))
    lines.append(_md_kv("Student — `student_action_v1` / direction", entry_b.get("student_action_v1") if entry_b else None))
    lines.append(_md_kv("Baseline — confidence (0–1)", entry_a.get("student_confidence_01") if entry_a else None))
    lines.append(_md_kv("Student — confidence (0–1)", entry_b.get("student_confidence_01") if entry_b else None))
    lines.append(_md_kv("Baseline — supporting indicators", entry_a.get("student_supporting_indicators") if entry_a else None))
    lines.append(_md_kv("Student — supporting indicators", entry_b.get("student_supporting_indicators") if entry_b else None))
    lines.append("- **Divergence:** see L3 decision records for per-trade `decision_changed_flag` and thesis deltas.")
    lines.append("")

    lines.append("## 4. Reasoning summary (Student only)")
    lines.append("")
    fm = trace_b.get("student_reasoning_fault_map_v1") if isinstance(trace_b, dict) else None
    if isinstance(fm, dict) and fm.get("nodes_v1"):
        lines.append("- Fault map nodes present in trace — open `/debug/learning-loop?job_id=" + _s(jb) + "` for full map.")
    else:
        lines.append("- No `student_reasoning_fault_map_v1` snapshot on this debug payload (or run predates capture).")
    lines.append(
        f"- **Trace events (Student):** {len(events_b)} `learning_trace_event_v1` lines ingested for Run B."
    )
    lines.append("")

    lines.append("## 5. Router behavior (026AI)")
    lines.append("")
    if router:
        r = router.get("raw") if isinstance(router.get("raw"), dict) else {}
        lines.append(_md_kv("Router decision — escalation", router.get("escalation_decision_v1")))
        lines.append(_md_kv("Final route", router.get("final_route_v1")))
        lines.append(_md_kv("Escalation blockers", router.get("escalation_blockers_v1")))
        lines.append(_md_kv("External API call succeeded (if escalated)", router.get("api_call_succeeded_v1")))
        if not r:
            lines.append(_md_kv("reasoning_router_decision_v1 (summary)", "(see learning trace)"))
    else:
        lines.append("- **No** `reasoning_router_decision_v1` event located in Run B trace (router not proven in this file).")
    lines.append(_md_kv("Status API — `primary_escalation_code_v1` (job-scoped slice)", primary))
    lines.append(_md_kv("Status API — `escalation_summary_v1`", esc_sum))
    if primary in ("ok",) or "no_escalation" in esc_sum.lower():
        lines.append("- *Interpretation:* escalation may be absent because no router escalation was requested, gateway/budget, or local path sufficed — see blockers above.")
    lines.append("")

    lines.append("## 6. Lifecycle outcome (026B)")
    lines.append("")
    lines.append("**Baseline (A)**")
    for k, v in life_a.items():
        lines.append(_md_kv(str(k), v))
    lines.append("**Student (B)**")
    for k, v in life_b.items():
        lines.append(_md_kv(str(k), v))
    lines.append("")

    lines.append("## 7. Learning (026C)")
    lines.append("")
    lines.append(_md_kv("Closure result", closure.get("closure_result_v1")))
    lines.append(_md_kv("Closure detail", closure.get("closure_detail_v1")))
    lines.append(_md_kv("026C packet injection evidenced", inj.get("packet_injection_evidence_in_trace_v1")))
    lines.append(_md_kv("Retrieved `record_id_026c` (from trace)", inj.get("retrieved_record_ids_026c_v1")))
    lines.append(_md_kv("Deterministic apply marker present", det_apply))
    if entry_b:
        lines.append(
            _md_kv("Learning rows appended (scorecard)", entry_b.get("student_learning_rows_appended"))
        )
        lines.append(_md_kv("Retrieval matches (scorecard)", entry_b.get("student_retrieval_matches")))
    lines.append("")

    lines.append("## 8. System health (current service snapshot)")
    lines.append("")
    lines.append(
        f"- **Reasoning Model tile:** {rm_head} (point-in-time; use trace for in-run router evidence)."
    )
    lines.append(
        f"- **External API health (effective):** {_s(fields.get('external_api_health') if fields else None)}"
    )
    bps = trace_b.get("breakpoints_v1") if isinstance(trace_b, dict) else None
    if isinstance(bps, (list, tuple)) and bps:
        lines.append(f"- **Debug breakpoints (Run B):** {', '.join(str(x) for x in bps[:6])}{'…' if len(bps) > 6 else ''}")
    if err_b:
        lines.append(f"- **Debug trace build:** `{err_b}`")
    lines.append("")

    lines.append("## 9. Operator conclusion")
    lines.append("")
    cr = str(closure.get("closure_result_v1") or "")
    if "LEARNING_CHANGED_BEHAVIOR" in cr:
        lines.append(
            "- **Learning / behavior change:** 026C closure reported **LEARNING_CHANGED_BEHAVIOR** (treatment vs control differed on a compared field). Validate in scorecard and L3."
        )
    elif "LEARNING_RETRIEVED_BUT_NO" in cr or "NO_BEHAVIOR" in cr:
        lines.append(
            "- **No material difference** on compared scorecard / lifecycle fields — **LEARNING_RETRIEVED_BUT_NO_BEHAVIOR_CHANGE**; router + 026C may still be evidenced."
        )
    elif "INSUFFICIENT_COMPARISON" in cr or "ROUTER_NOT_TRIGGERED" in cr or "LEARNING_BLOCKED" in cr:
        lines.append(
            f"- **Closure did not complete a full A/B proof:** {closure.get('closure_detail_v1') or 'see closure_detail_v1'}"
        )
    else:
        lines.append("- **Review** `learning_effect_closure_026c_v1` and Referee columns for a plain-language story.")
    lines.append("")
    lines.append("---")
    lines.append("*End of report — no raw JSON attached; pull `/api/debug/learning-loop/trace/{job_b}` for machine payload.*")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA",
    "build_operator_baseline_vs_student_report_markdown_v1",
]
