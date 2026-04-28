"""
student_test_mode_v1 — human-readable decision fingerprint report (Markdown).

Writes ``runtime/student_test/<job_id>/decision_fingerprint_report.md`` from
``learning_trace_events_v1.jsonl`` (isolated memory root) plus optional seam audit.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.learning_trace_events_v1 import (
    count_learning_trace_terminal_integrity_v1,
    read_learning_trace_events_for_job_v1,
)
from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.student_test_mode_v1 import (
    STUDENT_TEST_ISOLATION_ENV_V1,
    student_test_job_runtime_root_v1,
    student_test_mode_isolation_active_v1,
)

REPORT_FILENAME_V1 = "decision_fingerprint_report.md"
STUDENT_TEST_LLM_TURN_V1 = "student_test_llm_turn_v1"
STUDENT_TEST_SEALED_SNAPSHOT_V1 = "student_test_sealed_output_snapshot_v1"
STUDENT_TEST_PRE_REVEAL_STRUCTURED_V1 = "student_test_pre_reveal_structured_context_v1"
PATTERN_MEMORY_EVALUATED_V1 = "pattern_memory_evaluated_v1"
EXPECTED_VALUE_RISK_COST_EVALUATED_V1 = "expected_value_risk_cost_evaluated_v1"


def _fence_md(label: str, body: str, *, lang: str = "") -> str:
    b = body if body else "(empty)"
    return f"```{lang}\n{b.rstrip()}\n```\n"


def _trade_ids_chronological_v1(events: list[dict[str, Any]]) -> list[str]:
    """Prefer sealed-output snapshot order; fallback to student_output_sealed.

    When LLM output is rejected for every trade, sealed snapshots may be absent while RM still
    emits Directive 4 EV rows — fall back to ``expected_value_risk_cost_evaluated_v1`` order so the
    fingerprint (including Expected Value / Risk Cost) remains closure-visible.
    """
    out: list[str] = []
    for ev in events:
        if str(ev.get("stage") or "") != STUDENT_TEST_SEALED_SNAPSHOT_V1:
            continue
        tid = str(ev.get("trade_id") or "").strip()
        if tid and tid not in out:
            out.append(tid)
    if out:
        return out
    for ev in events:
        if str(ev.get("stage") or "") == "student_output_sealed":
            tid = str(ev.get("trade_id") or "").strip()
            if tid and tid not in out:
                out.append(tid)
    if out:
        return out
    for ev in events:
        if str(ev.get("stage") or "") != EXPECTED_VALUE_RISK_COST_EVALUATED_V1:
            continue
        tid = str(ev.get("trade_id") or "").strip()
        if tid and tid not in out:
            out.append(tid)
    return out


def _events_for_trade(events: list[dict[str, Any]], trade_id: str) -> dict[str, list[dict[str, Any]]]:
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        if str(ev.get("trade_id") or "").strip() != trade_id:
            continue
        st = str(ev.get("stage") or "")
        by_stage[st].append(ev)
    return dict(by_stage)


def _seam_errors_for_trade(seam_audit: dict[str, Any] | None, trade_id: str) -> list[str]:
    if not isinstance(seam_audit, dict):
        return []
    errs = seam_audit.get("errors")
    if not isinstance(errs, list):
        return []
    needle = f"trade={trade_id}"
    return [str(e) for e in errs if needle in str(e)]


def write_student_test_decision_fingerprint_report_md_v1(
    job_id: str,
    *,
    seam_audit: dict[str, Any] | None = None,
    trace_path: Path | str | None = None,
) -> Path:
    """
    Build ``decision_fingerprint_report.md`` under ``runtime/student_test/<job_id>/``.

    Requires trace events produced during the seam (including ``student_test_llm_turn_v1`` and
    ``student_test_sealed_output_snapshot_v1`` when isolation is active).
    """
    jid = str(job_id or "").strip()
    root = student_test_job_runtime_root_v1(jid)
    root.mkdir(parents=True, exist_ok=True)
    tp = Path(trace_path).expanduser().resolve() if trace_path else default_learning_trace_events_jsonl().resolve()

    events = read_learning_trace_events_for_job_v1(jid, path=tp)
    integrity = count_learning_trace_terminal_integrity_v1(jid, path=tp)
    trade_ids = _trade_ids_chronological_v1(events)

    lines: list[str] = []
    lines.append("# Student Test Mode — Decision Fingerprint Report\n")
    lines.append("## Global summary\n")
    lines.append(f"- **job_id:** `{jid}`")
    lines.append(
        f"- **total trades (trace snapshots):** {len(trade_ids)} "
        "(student_test_mode_v1 target: **10** closed trades / snapshots)"
    )
    lines.append(
        f"- **sealed_count (trace):** {integrity.get('student_output_sealed_count')!s}"
    )
    lines.append(
        f"- **authority_count (trace):** {integrity.get('student_decision_authority_v1_count')!s}"
    )
    lines.append(f"- **integrity status (authority == sealed):** {'YES' if integrity.get('integrity_ok') else 'NO'}")
    fatal = bool((seam_audit or {}).get("fatal_authority_seal_mismatch_v1")) if seam_audit else False
    lines.append(f"- **fatal_authority_seal_mismatch_v1 present:** {'YES' if fatal else 'NO'}")
    sr = str((seam_audit or {}).get("student_seam_stop_reason_v1") or "") if seam_audit else ""
    lines.append(f"- **seam stop reason:** `{sr or '(unknown)'}`")
    lines.append(
        f"- **test mode isolation ({STUDENT_TEST_ISOLATION_ENV_V1}):** "
        f"{'YES' if student_test_mode_isolation_active_v1() else 'NO'}"
    )
    lines.append(f"- **trace file:** `{tp}`")
    lines.append("")

    if not trade_ids:
        lines.append("_No per-trade snapshot rows found in trace — report sections below are empty._\n")

    for idx, tid in enumerate(trade_ids, start=1):
        by_st = _events_for_trade(events, tid)
        snap_ev = (by_st.get(STUDENT_TEST_SEALED_SNAPSHOT_V1) or [{}])[-1]
        ep_snap = snap_ev.get("evidence_payload") if isinstance(snap_ev.get("evidence_payload"), dict) else {}
        so = ep_snap.get("student_output_v1") if isinstance(ep_snap.get("student_output_v1"), dict) else {}

        llm_ev = (by_st.get(STUDENT_TEST_LLM_TURN_V1) or [{}])[-1]
        ep_llm = llm_ev.get("evidence_payload") if isinstance(llm_ev.get("evidence_payload"), dict) else {}

        scen = str(snap_ev.get("scenario_id") or llm_ev.get("scenario_id") or "").strip() or "(unknown)"

        sa = str(so.get("student_action_v1") or "").strip().lower()
        if sa == "enter_long":
            final_dec = "enter_long"
        elif sa == "enter_short":
            final_dec = "enter_short"
        else:
            final_dec = "no_trade"

        decision_ms = so.get("decision_at_ms")
        lines.append(f"## Trade {idx}: `{tid}`\n")
        lines.append("### Trade header\n")
        lines.append(f"- **trade_id:** `{tid}`")
        lines.append(f"- **scenario_id:** `{scen}`")
        lines.append(f"- **timestamp / bar reference:** `decision_at_ms={decision_ms!s}`")
        lines.append(f"- **final decision:** `{final_dec}`")
        lines.append("")

        lines.append("### 1. What the Student Saw\n")
        pre_ev = (by_st.get(STUDENT_TEST_PRE_REVEAL_STRUCTURED_V1) or [{}])[-1]
        ep_pre = pre_ev.get("evidence_payload") if isinstance(pre_ev.get("evidence_payload"), dict) else {}
        annex_snap = ep_pre.get("student_context_annex_v1")
        if isinstance(annex_snap, dict) and annex_snap:
            lines.append(
                "- **Structured pre-reveal context (`student_context_annex_v1`, injected before LLM):** "
                "deterministic entry-reasoning slices (indicator / risk / synthesis / memory / prior)."
            )
            try:
                annex_blob = json.dumps(annex_snap, indent=2, ensure_ascii=False, default=str)
            except TypeError:
                annex_blob = str(annex_snap)
            lines.append(_fence_md("student_context_annex_v1", annex_blob[:48000], lang="json"))
            lines.append(
                f"- **bars_in_packet (with annex on same packet):** `{ep_pre.get('bars_in_packet')!s}`"
            )
            ind_annex = annex_snap.get("indicator_context") if isinstance(annex_snap.get("indicator_context"), dict) else {}
            ps_rm = ind_annex.get("perps_state_model_v1") if isinstance(ind_annex.get("perps_state_model_v1"), dict) else {}
            if ps_rm:
                lines.append("- **RM — `perps_state_model_v1` (deterministic, Directive 2):**")
                try:
                    ps_blob = json.dumps(ps_rm, indent=2, ensure_ascii=False, default=str)
                except TypeError:
                    ps_blob = str(ps_rm)
                lines.append(_fence_md("perps_state_model_v1", ps_blob[:16000], lang="json"))
            else:
                lines.append(
                    "- **RM — `perps_state_model_v1`:** _(absent from annex — expected after Directive 2 wiring)._"
                )
        else:
            lines.append(
                "- **Structured pre-reveal annex:** _(no `student_test_pre_reveal_structured_context_v1` row — "
                "non-isolated run or annex attach skipped)._"
            )

        pm_rows = [x for x in by_st.get(PATTERN_MEMORY_EVALUATED_V1) or []]
        pm_ev = pm_rows[-1] if pm_rows else {}
        ep_pm = pm_ev.get("evidence_payload") if isinstance(pm_ev.get("evidence_payload"), dict) else {}
        pm_blob = ep_pm.get("pattern_memory_eval_v1")
        sig_direct = ep_pm.get("perps_pattern_signature_v1")
        if isinstance(pm_blob, dict) and pm_blob:
            lines.append("#### Pattern memory (RM — Directive 3)\n")
            lines.append(
                "- **`pattern_memory_evaluated_v1` trace:** present for this trade "
                f"(producer `{pm_ev.get('producer')!s}`)."
            )
            try:
                pm_json = json.dumps(pm_blob, indent=2, ensure_ascii=False, default=str)
            except TypeError:
                pm_json = str(pm_blob)
            lines.append(_fence_md("pattern_memory_eval_v1", pm_json[:32000], lang="json"))
            sig = pm_blob.get("perps_pattern_signature_v1")
            if isinstance(sig_direct, dict) and sig_direct:
                sig = sig_direct
            lines.append("##### Pattern Signature\n")
            if isinstance(sig, dict):
                lines.append(
                    f"- **signature_hash_v1:** `{sig.get('signature_hash_v1')!s}` "
                    f"(symbol `{sig.get('symbol')!s}`, timeframe `{sig.get('timeframe_minutes')!s}m`)"
                )
            else:
                lines.append("- _(signature object missing — FAIL closure criteria)._")
            lines.append("##### Matches Found\n")
            mc = pm_blob.get("matched_count_v1")
            tf = ep_pm.get("top_matches_v1")
            tn = pm_blob.get("top_matches_v1")
            tops = tf if isinstance(tf, list) else (tn if isinstance(tn, list) else [])
            lines.append(
                f"- **matched_count_v1:** `{mc!s}` · **top_matches_v1 length:** `{len(tops) if isinstance(tops, list) else 0}`"
            )
            if isinstance(tops, list) and tops:
                lines.append("- **Top rows (record_id / similarity / historical pnl):**")
                for row in tops[:8]:
                    if not isinstance(row, dict):
                        continue
                    lines.append(
                        f"  - `{row.get('record_id')!s}` sim={row.get('similarity_v1')!s} "
                        f"pnl={row.get('historical_pnl')!s}"
                    )
            lines.append("##### Pattern Effect\n")
            eff = pm_blob.get("pattern_effect_to_score_v1")
            if ep_pm.get("pattern_effect_to_score_v1") is not None:
                eff = ep_pm.get("pattern_effect_to_score_v1")
            lines.append(
                f"- **pattern_effect_to_score_v1** (additive to RM `final_score`): **`{eff!s}`**"
            )
            stats = pm_blob.get("pattern_outcome_stats_v1")
            if isinstance(stats, dict):
                lines.append(
                    f"- **Outcome stats (eligible rows):** count={stats.get('count')!s}, "
                    f"win_fraction={stats.get('wins_total_fraction_v1')!s}, avg_pnl={stats.get('avg_pnl')!s}"
                )
        else:
            lines.append(
                "- **RM — Pattern memory:** _(no `pattern_memory_evaluated_v1` trace row for this trade — "
                "disabled env, missing trace, or path did not emit)._"
            )

        ev_rows = [x for x in by_st.get(EXPECTED_VALUE_RISK_COST_EVALUATED_V1) or []]
        ev_ev = ev_rows[-1] if ev_rows else {}
        ep_ev = ev_ev.get("evidence_payload") if isinstance(ev_ev.get("evidence_payload"), dict) else {}
        ev_doc = ep_ev.get("expected_value_risk_cost_v1")
        lines.append("#### Expected Value / Risk Cost (RM — Directive 4)\n")
        if isinstance(ev_doc, dict) and ev_doc:
            lines.append(
                f"- **`expected_value_risk_cost_evaluated_v1` trace:** present "
                f"(available_v1=`{ev_doc.get('available_v1')!s}`)."
            )
            lines.append(
                f"- **EV long / short / no-trade:** `{ev_doc.get('ev_long_v1')!s}` / "
                f"`{ev_doc.get('ev_short_v1')!s}` / `{ev_doc.get('ev_no_trade_v1')!s}`"
            )
            lines.append(f"- **preferred_action_v1:** `{ev_doc.get('preferred_action_v1')!s}`")
            lines.append(f"- **sample_count_v1:** `{ev_doc.get('sample_count_v1')!s}`")
            rc = ev_doc.get("risk_costs_v1")
            if isinstance(rc, dict):
                lines.append(
                    f"- **risk penalties:** vol=`{rc.get('volatility_penalty_v1')!s}`; "
                    f"funding=`{rc.get('funding_cost_v1')!s}`; liq=`{rc.get('liquidation_risk_penalty_v1')!s}`"
                )
            evsa = ep_ev.get("ev_score_adjustment_v1")
            lines.append(f"- **EV score adjustment (bounded, synthesis):** `{evsa!s}`")
            rsn = ev_doc.get("reason_codes_v1")
            if isinstance(rsn, list) and rsn:
                lines.append(f"- **reason_codes_v1:** `{json.dumps(rsn, ensure_ascii=False)}`")
            try:
                ev_blob = json.dumps(ev_doc, indent=2, ensure_ascii=False, default=str)
            except TypeError:
                ev_blob = str(ev_doc)
            lines.append(_fence_md("expected_value_risk_cost_v1", ev_blob[:24000], lang="json"))
        else:
            lines.append(
                "- _(No `expected_value_risk_cost_evaluated_v1` trace row for this trade.)_"
            )

        mem_ev = (by_st.get("memory_retrieval_completed") or [{}])[-1]
        ep_mem = mem_ev.get("evidence_payload") if isinstance(mem_ev.get("evidence_payload"), dict) else {}
        rm = ep_mem.get("student_retrieval_matches")
        n026 = ep_mem.get("retrieved_lifecycle_learning_026c_slice_count_v1")
        lines.append(
            f"- **context retrieval (store slices for packet):** matches={rm!s}; "
            f"026c lifecycle slices={n026!s}. "
            "In isolated student test mode, promoted lifecycle retrieval from production stores is disabled "
            f"(`{STUDENT_TEST_ISOLATION_ENV_V1}=1`); expect zero retrieved promoted rows."
        )
        mdl = [x for x in by_st.get("market_data_loaded") or []]
        ind_ev = [x for x in by_st.get("indicator_context_eval_v1") or []]
        if mdl:
            ep0 = mdl[-1].get("evidence_payload") if isinstance(mdl[-1].get("evidence_payload"), dict) else {}
            outs = ep0.get("outputs")
            lines.append("- **Bars / market snapshot (entry reasoning stage `market_data_loaded` outputs):**")
            try:
                blob = json.dumps(outs, indent=2, ensure_ascii=False, default=str)
            except TypeError:
                blob = str(outs)
            lines.append(_fence_md("outputs", blob[:24000], lang="json"))
        else:
            lines.append("- **Bars / market snapshot:** _(no `market_data_loaded` trace row for this trade — see packet build path)._")
        if ind_ev:
            ep_i = ind_ev[-1].get("evidence_payload") if isinstance(ind_ev[-1].get("evidence_payload"), dict) else {}
            outs_i = ep_i.get("outputs")
            lines.append("- **Indicators / signals (entry reasoning `indicator_context_eval_v1` outputs):**")
            try:
                blob_i = json.dumps(outs_i, indent=2, ensure_ascii=False, default=str)
            except TypeError:
                blob_i = str(outs_i)
            lines.append(_fence_md("outputs", blob_i[:24000], lang="json"))
        lines.append("")

        lines.append("### 2. What the Student Was Asked\n")
        lines.append(
            "- **Prompt includes full `student_decision_packet_v1` JSON** (OHLCV + `student_context_annex_v1` "
            "when present) and **PRE_REVEAL_CAUSAL_CONTEXT_ONLY** notice."
        )
        up = str(ep_llm.get("user_prompt_v1") or "")
        if up.strip():
            lines.append(_fence_md("prompt", up, lang="text"))
        else:
            lines.append(
                "_No `student_test_llm_turn_v1` prompt captured (shadow stub path, LLM cap, or trace not written)._"
            )
        lines.append("")

        lines.append("### 3. What the Student Said (Raw)\n")
        raw = str(ep_llm.get("raw_assistant_text_v1") or "")
        if raw.strip():
            lines.append(_fence_md("raw_llm", raw, lang="text"))
        else:
            lines.append("_No raw assistant text in trace (non-LLM path or failure before response)._")
        lines.append("")

        lines.append("### 4. Parsed Decision\n")
        lines.append(f"- **student_action_v1:** `{so.get('student_action_v1')!s}`")
        lines.append(f"- **act:** `{so.get('act')!s}` / **direction:** `{so.get('direction')!s}`")
        lines.append(f"- **confidence (confidence_01):** `{so.get('confidence_01')!s}`")
        lines.append(f"- **hypothesis:** `{so.get('hypothesis_text_v1')!s}`")
        lines.append(f"- **invalidation:** `{so.get('invalidation_text')!s}`")
        sup = so.get("supporting_indicators")
        con = so.get("conflicting_indicators")
        lines.append(f"- **supporting_indicators:** `{json.dumps(sup, ensure_ascii=False) if sup is not None else 'null'}`")
        lines.append(f"- **conflicting_indicators:** `{json.dumps(con, ensure_ascii=False) if con is not None else 'null'}`")
        lines.append("")

        lines.append("### 5. Validation Results\n")
        rej = [x for x in by_st.get("llm_output_rejected") or []]
        schema_pass = "FAIL" if rej else "PASS"
        lines.append(f"- **schema validation:** {schema_pass}")
        sealed_rows = by_st.get("student_output_sealed") or []
        ep_sealed = {}
        if sealed_rows:
            ep_sealed = (
                sealed_rows[-1].get("evidence_payload")
                if isinstance(sealed_rows[-1].get("evidence_payload"), dict)
                else {}
            )
        proto_ok = ep_sealed.get("student_decision_protocol_ok_v1")
        if proto_ok is None:
            proto_line = "N/A (not LLM profile or protocol extras absent)"
        else:
            proto_line = "PASS" if proto_ok else "FAIL"
        lines.append(f"- **protocol validation:** {proto_line}")
        auth_rows = by_st.get("student_decision_authority_v1") or []
        lines.append(f"- **authority emitted:** {'YES' if auth_rows else 'NO'}")
        lines.append(f"- **sealed:** {'YES' if sealed_rows else 'NO'}")
        lines.append("")

        lines.append("### 6. Final Outcome\n")
        lines.append(f"- **final sealed action:** `{so.get('student_action_v1')!s}`")
        terr = _seam_errors_for_trade(seam_audit, tid)
        contracts_ok = not terr and bool(sealed_rows) and schema_pass == "PASS"
        lines.append(f"- **passed all contracts (best-effort from trace + seam errors):** {'YES' if contracts_ok else 'NO'}")
        if terr:
            lines.append("- **errors during processing (from seam audit):**")
            for t in terr[:48]:
                lines.append(f"  - `{t}`")
        lines.append("")

    out_path = root / REPORT_FILENAME_V1
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


__all__ = [
    "REPORT_FILENAME_V1",
    "write_student_test_decision_fingerprint_report_md_v1",
]
