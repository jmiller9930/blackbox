"""GT_DIRECTIVE_038 — deterministic grading rubric (evaluation-only)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1,
)


_FORBIDDEN_HALLUCINATION_MARKERS_V1 = (
    "guaranteed",
    "cannot lose",
    "100% win",
    "tomorrow's",
    "next week",
    "inside information",
    "secret alpha",
)


def _final_action_v1(so: dict[str, Any] | None) -> str:
    if not isinstance(so, dict):
        return "no_trade"
    a = str(so.get("student_action_v1") or "").strip().lower()
    if a in ("enter_long", "enter_short", "no_trade"):
        return a
    return "no_trade"


def _ds_action_v1(ere: dict[str, Any] | None) -> str:
    if not isinstance(ere, dict):
        return "no_trade"
    ds = ere.get("decision_synthesis_v1")
    if not isinstance(ds, dict):
        return "no_trade"
    return str(ds.get("action") or "no_trade").strip().lower()


def _aggregate_memory_class_v1(ere: dict[str, Any] | None) -> str:
    m = ere.get("memory_context_eval_v1") if isinstance(ere, dict) else None
    if not isinstance(m, dict):
        return ""
    return str(m.get("aggregate_memory_effect_v1") or "").strip()


def _ev_doc_v1(ere: dict[str, Any] | None) -> dict[str, Any]:
    ev = ere.get("expected_value_risk_cost_v1") if isinstance(ere, dict) else None
    return ev if isinstance(ev, dict) else {}


def _ic_vol_v1(ere: dict[str, Any] | None) -> str:
    ic = ere.get("indicator_context_eval_v1") if isinstance(ere, dict) else None
    if not isinstance(ic, dict):
        return ""
    return str(ic.get("atr_volume_state") or "").strip()


def _hypothesis_text_v1(so: dict[str, Any] | None) -> str:
    if not isinstance(so, dict):
        return ""
    return str(so.get("hypothesis_text_v1") or so.get("reasoning_text") or "").lower()


def _risk_text_bundle_v1(so: dict[str, Any] | None) -> str:
    if not isinstance(so, dict):
        return ""
    parts = [
        str(so.get("invalidation_text") or ""),
        str(so.get("context_interpretation_v1") or ""),
        str(so.get("reasoning_text") or ""),
    ]
    return " ".join(parts).lower()


def detect_hallucination_v1(*, raw_llm_text: str, merge_errors: list[str]) -> bool:
    """YES means hallucination detected (directive: any hallucination → FAIL)."""
    blob = (raw_llm_text or "").lower()
    for m in _FORBIDDEN_HALLUCINATION_MARKERS_V1:
        if m in blob:
            return True
    for e in merge_errors or []:
        es = str(e).lower()
        if "hallucinated_memory_id" in es:
            return True
    # Invented OHLCV levels often appear as bare repeated digits — keep conservative.
    if re.search(r"\b(?:btc|eth|sol)\s+at\s+\d{2,}\.\d{4,}\b", blob):
        return True
    return False


def build_stub_student_json_aligned_to_engine_v1(
    ere: dict[str, Any],
    *,
    scenario_id: str,
) -> dict[str, Any]:
    """Deterministic JSON object acceptable to ``emit_student_output_via_ollama_v1`` repair path."""
    act_s = _ds_action_v1(ere)
    if act_s == "enter_long":
        act, direction, sa = True, "long", "enter_long"
    elif act_s == "enter_short":
        act, direction, sa = True, "short", "enter_short"
    else:
        act, direction, sa = False, "flat", "no_trade"
    rid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"gt038_stub:{scenario_id}"))
    return {
        "act": act,
        "direction": direction,
        "confidence_01": float(ere.get("confidence_01") or 0.55),
        "pattern_recipe_ids": ["student_reasoning_exam_stub_v1"],
        "reasoning_text": "Exam stub: thesis aligned to engine decision_synthesis_v1 (deterministic).",
        "student_decision_ref": rid,
        "context_interpretation_v1": (
            "Structured annex and OHLCV describe the causal window; no future bars claimed."
        ),
        "hypothesis_kind_v1": "trend_continuation"
        if sa != "no_trade"
        else "no_clear_edge",
        "hypothesis_text_v1": (
            "Follow engine synthesis for this exam slice."
            if sa != "no_trade"
            else "No edge — prefer standing aside unless EV/memory justify risk."
        ),
        "supporting_indicators": ["engine_decision_synthesis_v1"],
        "conflicting_indicators": [CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1],
        "confidence_band": "medium",
        "context_fit": "exam",
        "invalidation_text": "Invalid if thesis contradicts cited annex signals.",
        "student_action_v1": sa,
        "cited_memory_record_ids": [],
    }


def grade_scenario_v1(
    *,
    scenario: dict[str, Any],
    ere: dict[str, Any] | None,
    final_so: dict[str, Any] | None,
    raw_llm_text: str,
    merge_errors: list[str],
) -> dict[str, Any]:
    """Populate directive grading fields for one scenario row."""
    primary = str(scenario.get("grade_primary_action_v1") or "").strip()
    fin = _final_action_v1(final_so)
    ds_act = _ds_action_v1(ere)
    ev = _ev_doc_v1(ere)
    ev_avail = bool(ev.get("available_v1"))
    pref = str(ev.get("preferred_action_v1") or "").strip().lower()
    mclass = _aggregate_memory_class_v1(ere)
    ic_vol = _ic_vol_v1(ere)

    hallu = detect_hallucination_v1(raw_llm_text=raw_llm_text, merge_errors=list(merge_errors or []))

    # --- state_alignment ---
    state_alignment = "PASS"
    if ere is None:
        state_alignment = "FAIL"
    elif primary in ("long", "short"):
        if primary == "long" and ds_act == "enter_short":
            state_alignment = "FAIL"
        if primary == "short" and ds_act == "enter_long":
            state_alignment = "FAIL"

    # --- memory_alignment ---
    memory_alignment = "PASS"
    inj = scenario.get("memory_injection_v1")
    if inj == "negative":
        if mclass == "conflict" and fin in ("enter_long", "enter_short"):
            memory_alignment = "FAIL"
    if inj == "positive":
        if mclass in ("aligned", "partial") and fin in ("enter_long", "enter_short"):
            memory_alignment = "PASS"
        elif mclass == "conflict" and fin in ("enter_long", "enter_short"):
            memory_alignment = "FAIL"

    # --- ev_alignment ---
    ev_alignment = "PASS"
    if ev_avail and pref in ("enter_long", "enter_short", "no_trade"):
        # Strong-ignore rule: if EV strongly prefers no_trade but student traded
        if pref == "no_trade" and fin in ("enter_long", "enter_short"):
            ev_alignment = "FAIL"
        # If EV prefers a direction and merge disagrees on directional trade — FAIL
        if pref in ("enter_long", "enter_short") and fin in ("enter_long", "enter_short") and pref != fin:
            ev_alignment = "FAIL"

    # --- risk_awareness ---
    risk_text = _risk_text_bundle_v1(final_so)
    hypo = _hypothesis_text_v1(final_so)
    risk_awareness = "PASS"
    if primary == "risk_ack" or scenario.get("scenario_id") == "d6_s08_high_volatility_danger":
        rk_ok = ("vol" in risk_text or "risk" in risk_text or "atr" in risk_text or "stop" in risk_text)
        rk_ok = rk_ok or ic_vol == "high_volatility"
        rk_ok = rk_ok or fin == "no_trade"
        if not rk_ok:
            risk_awareness = "FAIL"
    if scenario.get("scenario_id") == "d6_s06_overextended_long":
        ex_ok = "exhaust" in hypo or "mean" in hypo or "fade" in hypo or fin in ("no_trade", "enter_short")
        if not ex_ok:
            risk_awareness = "FAIL"
    if scenario.get("scenario_id") == "d6_s07_overextended_short":
        sh_ok = "reversal" in hypo or "squeeze" in hypo or "cover" in hypo or fin in ("no_trade", "enter_long")
        if not sh_ok:
            risk_awareness = "FAIL"

    # --- action_correct / no_trade_correct ---
    action_correct = "NO"
    no_trade_correct = "YES"
    if primary == "long":
        action_correct = "YES" if fin == "enter_long" else "NO"
    elif primary == "short":
        action_correct = "YES" if fin == "enter_short" else "NO"
    elif primary == "no_trade":
        action_correct = "YES" if fin == "no_trade" else "NO"
    elif primary == "contextual":
        action_correct = "YES" if state_alignment == "PASS" else "NO"
    elif primary == "risk_ack":
        action_correct = "YES" if risk_awareness == "PASS" else "NO"
    elif primary == "memory_obey":
        action_correct = "YES" if memory_alignment == "PASS" and ev_alignment == "PASS" else "NO"
    elif primary == "memory_conflict":
        action_correct = "YES" if fin == "no_trade" else "NO"

    sid = str(scenario.get("scenario_id") or "")
    strict_no_trade_ids = (
        "d6_s03_sideways_chop",
        "d6_s04_fake_breakout_trap",
        "d6_s10_memory_warning_trade",
    )
    if sid in strict_no_trade_ids:
        no_trade_correct = "YES" if fin == "no_trade" else "NO"
    else:
        no_trade_correct = "YES"

    reasoning_quality = "PASS"
    if hallu:
        reasoning_quality = "FAIL"
    elif memory_alignment == "FAIL" or ev_alignment == "FAIL":
        reasoning_quality = "FAIL"
    elif risk_awareness == "FAIL":
        reasoning_quality = "FAIL"

    return {
        "action_correct": action_correct,
        "no_trade_correct": no_trade_correct,
        "state_alignment": state_alignment,
        "memory_alignment": memory_alignment,
        "ev_alignment": ev_alignment,
        "risk_awareness": risk_awareness,
        "reasoning_quality": reasoning_quality,
        "hallucination": "YES" if hallu else "NO",
    }


__all__ = [
    "build_stub_student_json_aligned_to_engine_v1",
    "detect_hallucination_v1",
    "grade_scenario_v1",
]
