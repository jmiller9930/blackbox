"""ACL-lite: next focus from gates + curriculum stage; bachelor eligibility."""

from __future__ import annotations

import os
from typing import Any

from modules.anna_training.curriculum_tools import curriculum_tools_complete, missing_grade_12_tools
from modules.anna_training.gates import evaluate_grade12_gates
from modules.anna_training.paper_trades import load_paper_trades, summarize_trades
from modules.anna_training.store import load_state


def suggest_next_focus(
    *,
    curriculum_id: str | None,
    training_method_id: str | None,
) -> dict[str, Any]:
    """
    Operator-facing JSON: what to emphasize next (not an autonomous agent loop).
    Order: curriculum tools (cohesive) → numeric gate → advance / bachelor.
    """
    st = load_state()
    mastery = st.get("grade_12_tool_mastery")
    cid = (curriculum_id or "").strip() or (st.get("curriculum_id") or "").strip()

    g12 = evaluate_grade12_gates()
    trades = load_paper_trades()
    s = summarize_trades(trades)
    focus = "maintain_measurement"
    hints: list[str] = []

    if cid == "grade_12_paper_only" or cid == "":
        if not curriculum_tools_complete(mastery):
            missing = missing_grade_12_tools(mastery)
            focus = "curriculum_tools"
            hints.append(
                "Pass each Grade 12 tool (cohesive set) before 60% / revenue metrics are the headline bar."
            )
            hints.append(f"Missing tools: {', '.join(missing)}")
            hints.append("After evidence: `anna tool-pass <tool_id>` (see `anna tool-list`).")
            return {
                "focus": focus,
                "curriculum_id": cid or None,
                "training_method_id": training_method_id or st.get("training_method_id"),
                "grade12_gate": {k: g12.get(k) for k in ("pass", "blockers", "win_rate", "decisive_trades")},
                "curriculum_tools_pass": g12.get("curriculum_tools_pass"),
                "numeric_gate_pass": g12.get("numeric_gate_pass"),
                "missing_curriculum_tools": missing,
                "paper_trade_count": s.trade_count,
                "hints": hints,
            }

    if not g12.get("pass"):
        focus = "grade12_numeric_gate"
        hints.append("Numeric cohort: decisive trades + win rate vs gate (tools must already be PASS).")
        if g12.get("blockers"):
            hints.extend(str(b) for b in (g12.get("blockers") or [])[:6])

    if g12.get("pass") and cid == "grade_12_paper_only":
        focus = "eligible_to_advance_curriculum"
        hints.append(
            "Grade-12 gate PASS — you may advance to bachelor_paper_track_v1 when human policy allows "
            "(`advance-curriculum bachelor_paper_track_v1` or `assign-curriculum bachelor_paper_track_v1`)."
        )

    if cid == "bachelor_paper_track_v1":
        focus = "bachelor_track_active"
        hints.append("Cumulative learning from Grade 12 applies; continue Karpathy loop with deeper paper metrics.")

    return {
        "focus": focus,
        "curriculum_id": cid or None,
        "training_method_id": training_method_id or st.get("training_method_id"),
        "grade12_gate": {k: g12.get(k) for k in ("pass", "blockers", "win_rate", "decisive_trades")},
        "curriculum_tools_pass": g12.get("curriculum_tools_pass"),
        "numeric_gate_pass": g12.get("numeric_gate_pass"),
        "missing_curriculum_tools": g12.get("missing_curriculum_tools") or [],
        "paper_trade_count": s.trade_count,
        "hints": hints,
    }


def bachelor_eligibility_report(
    *,
    curriculum_id: str | None,
    completed_milestones: list[Any],
) -> dict[str, Any]:
    """Whether bachelor assignment is allowed (prereq + full grade12 gate including tools)."""
    g12 = evaluate_grade12_gates()
    bypass = (os.environ.get("ANNA_ALLOW_BACHELOR_WITHOUT_GATE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    gate_ok = bool(g12.get("pass")) or bypass
    prereq = "grade_12_paper_only" in {str(x) for x in (completed_milestones or [])} or (
        (curriculum_id or "") == "grade_12_paper_only"
    )
    eligible = gate_ok and prereq
    return {
        "eligible_for_bachelor_paper_track_v1": eligible,
        "grade12_gate_pass": g12.get("pass"),
        "curriculum_tools_pass": g12.get("curriculum_tools_pass"),
        "numeric_gate_pass": g12.get("numeric_gate_pass"),
        "prerequisite_grade12_engaged": prereq,
        "bypass_env_ANNA_ALLOW_BACHELOR_WITHOUT_GATE": bypass,
    }
