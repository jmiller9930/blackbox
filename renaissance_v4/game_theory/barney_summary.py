"""
Barney summary — plain-English operator recap from **structured facts only**.

The local LLM (when enabled) is a **formatter**: it must not invent metrics or causes.
Facts are built server-side from a completed parallel job snapshot (no full scenario dumps).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _runtime_imports() -> Any:
    rt = str(_REPO_ROOT / "scripts" / "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    from llm.local_llm_client import ollama_generate

    return ollama_generate


def barney_use_llm() -> bool:
    v = os.environ.get("BARNEY_USE_LLM")
    if v is not None and str(v).strip() != "":
        return str(v).strip().lower() not in ("0", "false", "no", "off")
    return os.environ.get("ANNA_USE_LLM", "1").strip().lower() not in ("0", "false", "no")


def build_barney_facts_from_job_state(
    *,
    status: str,
    error_message: str | None,
    parallel_result: dict[str, Any] | None,
    batch_timing: dict[str, Any] | None,
    telemetry_echo: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build ``barney_facts_v1`` — only fields suitable for operator recap (no per-bar logs).
    """
    oba: dict[str, Any] = {}
    if isinstance(parallel_result, dict):
        oba = dict(parallel_result.get("operator_batch_audit") or {})
    elif isinstance(batch_timing, dict):
        oba = dict((batch_timing.get("operator_batch_audit") or {}) if isinstance(batch_timing.get("operator_batch_audit"), dict) else {})

    learn: dict[str, Any] = {}
    if isinstance(parallel_result, dict):
        learn = dict(parallel_result.get("learning_batch_audit_v1") or {})
    if not learn and isinstance(batch_timing, dict):
        learn = dict(batch_timing.get("learning_batch_audit_v1") or {})

    bt: dict[str, Any] = dict(batch_timing) if isinstance(batch_timing, dict) else {}
    pnl: dict[str, Any] = {}
    if isinstance(parallel_result, dict):
        pnl = dict(parallel_result.get("pnl_summary") or {})

    results = parallel_result.get("results") if isinstance(parallel_result, dict) else None
    if not isinstance(results, list):
        results = []

    strategy_id: str | None = None
    for r in results:
        if not r.get("ok"):
            continue
        pc = r.get("policy_contract")
        if isinstance(pc, dict) and pc.get("strategy_id"):
            strategy_id = str(pc.get("strategy_id"))
            break

    mem_mode = None
    if isinstance(telemetry_echo, dict):
        mem_mode = telemetry_echo.get("context_signature_memory_mode")
    if mem_mode is None:
        mem_mode = oba.get("context_signature_memory_mode")

    ctx_sum: dict[str, Any] | None = None
    for r in results:
        if not r.get("ok"):
            continue
        ctx_panel = r.get("context_memory_operator_panel_v1")
        if isinstance(ctx_panel, dict) and ctx_panel.get("schema") == "context_memory_operator_panel_v1":
            ctx_sum = {
                "memory_saved_this_run": bool(ctx_panel.get("memory_saved_this_run")),
                "memory_loaded_any": bool(ctx_panel.get("memory_loaded")),
                "recall_matches_panel_sum": ctx_panel.get("recall_matches"),
                "bias_applied_panel_sum": ctx_panel.get("bias_applied"),
            }
            break

    mem_saved = mem_loaded = None
    recall_matches = bias_applied = None
    if isinstance(ctx_sum, dict):
        if "memory_saved_this_run" in ctx_sum:
            mem_saved = bool(ctx_sum.get("memory_saved_this_run"))
        else:
            mss = ctx_sum.get("memory_saved_scenarios")
            mem_saved = bool(int(mss) > 0) if isinstance(mss, (int, float)) else bool(mss) if mss is not None else None
        mem_loaded = ctx_sum.get("memory_loaded_any")
        recall_matches = ctx_sum.get("recall_matches_panel_sum")
        bias_applied = ctx_sum.get("bias_applied_panel_sum")
    if mem_saved is None and bt.get("memory_used") is not None:
        mem_saved = bool(bt.get("memory_used"))
    if recall_matches is None and bt.get("recall_matches") is not None:
        try:
            recall_matches = int(bt.get("recall_matches"))
        except (TypeError, ValueError):
            recall_matches = None
    if bias_applied is None and bt.get("recall_bias_applied") is not None:
        try:
            bias_applied = int(bt.get("recall_bias_applied"))
        except (TypeError, ValueError):
            bias_applied = None

    cand_count = int(bt.get("candidate_count") or 0)
    sel_winner = bt.get("selected_candidate_id")
    if sel_winner is None:
        sel_winner = learn.get("selected_candidate_id")
    sel_s = str(sel_winner).strip() if sel_winner not in (None, "") else None

    no_winner = bool(cand_count > 0 and not sel_s)
    w_delta = bt.get("winner_vs_control_delta") or learn.get("winner_vs_control_delta")
    wvc = learn.get("winner_vs_control") if isinstance(learn.get("winner_vs_control"), dict) else None
    pnl_delta = None
    if isinstance(wvc, dict) and wvc.get("pnl_delta") is not None:
        try:
            pnl_delta = float(wvc["pnl_delta"])
        except (TypeError, ValueError):
            pnl_delta = None

    run_class = bt.get("batch_run_classification_v1")
    if run_class is None and isinstance(parallel_result, dict):
        run_class = parallel_result.get("batch_run_classification_v1")

    ev_m = oba.get("evaluation_window_effective_calendar_months")

    mca: dict[str, Any] = {}
    if isinstance(bt.get("memory_context_impact_audit_v1"), dict):
        mca = dict(bt["memory_context_impact_audit_v1"])
    if not mca and isinstance(parallel_result, dict):
        prm = parallel_result.get("memory_context_impact_audit_v1")
        if isinstance(prm, dict):
            mca = dict(prm)

    facts: dict[str, Any] = {
        "schema": "barney_facts_v1",
        "run_status": status,
        "error_message": error_message,
        "pattern_used": oba.get("operator_recipe_id"),
        "pattern_label": oba.get("operator_recipe_label"),
        "strategy_id": strategy_id,
        "manifest_path_primary": oba.get("manifest_path_primary"),
        "operator_upload_manifest_repo_relative": oba.get("operator_upload_manifest_repo_relative"),
        "evaluation_window_months": ev_m,
        "run_type": run_class,
        "learning_lane": bt.get("learning_status"),
        "scenarios_submitted": parallel_result.get("ran") if isinstance(parallel_result, dict) else bt.get("total_scenarios"),
        "scenarios_ok": parallel_result.get("ok_count") if isinstance(parallel_result, dict) else None,
        "scenarios_failed": parallel_result.get("failed_count") if isinstance(parallel_result, dict) else None,
        "baseline_starting_equity_usd": pnl.get("starting_equity_usd"),
        "batch_combined_pnl_usd": pnl.get("batch_total_pnl_usd"),
        "ending_equity_usd": pnl.get("ending_equity_usd"),
        "winner_id": sel_s,
        "no_winner": no_winner,
        "candidate_count": cand_count,
        "winner_vs_control_delta": w_delta,
        "pnl_delta_vs_control": pnl_delta,
        "memory_mode": mem_mode,
        "memory_saved": mem_saved,
        "memory_loaded": mem_loaded,
        "recall_matches": recall_matches,
        "bias_applied": bias_applied,
        "groundhog_status": bt.get("groundhog_status"),
        "policy_framework_id": bt.get("policy_framework_id") or learn.get("policy_framework_id"),
        "memory_impact_yes_no": mca.get("memory_impact_yes_no"),
        "memory_operator_truth_line_v1": mca.get("barney_operator_truth_line_v1"),
        "memory_context_impact_audit_v1": mca if mca else None,
    }
    return facts


def render_barney_fallback_text(facts: dict[str, Any]) -> str:
    """Deterministic plain text when LLM is off or fails."""
    lines: list[str] = []
    st = str(facts.get("run_status") or "unknown")
    if st == "error":
        err = facts.get("error_message")
        lines.append("This run failed before or during the batch.")
        if err:
            lines.append(f"Reason from the system (verbatim): {err}")
        else:
            lines.append("No error message was present in run data (Unknown).")
        lines.append("No valid comparison totals are available for this batch.")
        return "\n".join(lines)

    pat = facts.get("pattern_label") or facts.get("pattern_used") or "Unknown (not in run data)"
    sid = facts.get("strategy_id") or "Unknown (not in run data)"
    mp = facts.get("manifest_path_primary") or "Unknown (not in run data)"
    if facts.get("operator_upload_manifest_repo_relative"):
        mp = str(facts["operator_upload_manifest_repo_relative"])
    ev = facts.get("evaluation_window_months")
    ev_s = f"{ev} months" if ev is not None else "Unknown (not in run data)"
    lines.append(f"What ran: Pattern «{pat}» on strategy id «{sid}» using manifest «{mp}».")
    lines.append(f"Evaluation window setting: {ev_s}.")
    rt = facts.get("run_type") or "Unknown (not in run data)"
    lines.append(f"Run classification: {rt}.")

    truth = facts.get("memory_operator_truth_line_v1")
    if truth:
        lines.append("Memory / context impact (from learning_run_audit_v1 counters): " + str(truth))

    ok = facts.get("scenarios_ok")
    fail = facts.get("scenarios_failed")
    tot = facts.get("scenarios_submitted")
    if ok is not None and fail is not None and tot is not None:
        lines.append(f"Scenarios finished: {ok} ok, {fail} failed, out of {tot} submitted.")
    else:
        lines.append("Per-scenario ok/fail counts: Unknown (not in run data).")

    pnl = facts.get("batch_combined_pnl_usd")
    start = facts.get("baseline_starting_equity_usd")
    if isinstance(pnl, (int, float)) and isinstance(start, (int, float)):
        lines.append(
            f"Paper PnL (sum of each scenario’s cumulative PnL vs ${start:g} starting equity): {float(pnl):.4f} USD combined."
        )
    else:
        lines.append("Paper PnL summary: Unknown (not in run data).")

    if facts.get("no_winner"):
        lines.append("No candidate beat the baseline in this run (no selected winner id). No improvement was found.")
    elif facts.get("winner_id"):
        wd = facts.get("winner_vs_control_delta") or "Unknown (not in run data)"
        lines.append(f"Selected winner id: {facts['winner_id']}. Delta vs control summary: {wd}.")
    elif int(facts.get("candidate_count") or 0) <= 0:
        lines.append("No candidate search was recorded for this batch (candidates tested = 0).")
    else:
        lines.append("Winner status: Unknown (not in run data).")

    mm = facts.get("memory_mode") or "Unknown (not in run data)"
    ms = facts.get("memory_saved")
    ml = facts.get("memory_loaded")
    rm = facts.get("recall_matches")
    ba = facts.get("bias_applied")
    lines.append(
        f"Memory mode: {mm}. Memory saved this run: {ms if ms is not None else 'Unknown'}. "
        f"Memory loaded: {ml if ml is not None else 'Unknown'}."
    )
    lines.append(
        f"Recall matches (panel sum): {rm if rm is not None else 'Unknown'}. "
        f"Bias applied (panel sum): {ba if ba is not None else 'Unknown'}."
    )

    lane = facts.get("learning_lane")
    if lane == "learning_active":
        lines.append("This batch was learning-active (harness/memory/recall signals engaged per audit rules).")
    elif lane == "execution_only":
        lines.append("This batch was execution-only (no learning-active counters in the audit rollup).")
    else:
        lines.append(f"Learning lane: {lane or 'Unknown (not in run data)'}.")
    lines.append(
        "Suggested next step: review the scorecard row and session logs; if something failed, fix inputs "
        "and rerun; if results are flat, adjust hypothesis or evaluation window only after you agree "
        "what to change."
    )
    return "\n".join(lines)


def barney_format_with_llm(facts: dict[str, Any], *, timeout: float = 120.0) -> tuple[str, str | None]:
    """
    Returns (text, error). Formatter-only prompt — facts JSON is the only numeric source.
    """
    from renaissance_v4.game_theory.ollama_role_routing_v1 import (
        pml_lightweight_ollama_base_url,
        pml_lightweight_ollama_model,
    )

    ollama_generate = _runtime_imports()
    base = pml_lightweight_ollama_base_url()
    model = pml_lightweight_ollama_model()
    payload = json.dumps(facts, indent=2, ensure_ascii=False)
    prompt = (
        "You are Barney — an operator-facing formatter.\n\n"
        "RULES (hard):\n"
        "- You will receive JSON facts labeled barney_facts_v1. Use ONLY those fields. "
        "If a field is null or missing, write exactly: Unknown (not in run data) for that item — "
        "do not invent numbers, causes, or exchange behavior.\n"
        "- Do NOT infer that the strategy is good or bad for live trading.\n"
        "- If run_status is error, say clearly the run failed; quote error_message if non-null; "
        "if error_message is null, say no error text was recorded.\n"
        "- If no_winner is true, say clearly that no candidate beat the baseline and no improvement was found.\n"
        "- Explain memory_mode, memory_saved, memory_loaded, recall_matches, bias_applied only as stated.\n"
        "- If memory_operator_truth_line_v1 is non-null, quote it verbatim as the authoritative memory/context impact line; "
        "do not contradict memory_impact_yes_no.\n"
        "- If learning_lane is learning_active vs execution_only, say which in plain English.\n"
        "- End with a short 'Suggested next step:' line using only conservative, non-guaranteed advice.\n\n"
        "--- FACTS JSON ---\n"
        + payload
    )
    res = ollama_generate(prompt, base_url=base, model=model, timeout=timeout)
    if res.error:
        return "", res.error
    return (res.text or "").strip(), None


def barney_summarize_job_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Return {ok, text, source, error} where source is llm|fallback."""
    if not barney_use_llm():
        return {
            "ok": True,
            "text": render_barney_fallback_text(facts),
            "source": "fallback",
            "error": None,
        }
    txt, err = barney_format_with_llm(facts)
    if err or not txt:
        return {
            "ok": True,
            "text": render_barney_fallback_text(facts),
            "source": "fallback",
            "error": err,
        }
    return {"ok": True, "text": txt, "source": "llm", "error": None}
