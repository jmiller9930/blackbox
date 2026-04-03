"""
Karpathy-aligned skill practice: each cycle can *attempt* the current curriculum skill.

Contract alignment: every objective here is a **boolean predicate** only. Each
``attempt_curriculum_skill`` / practice hook returns ``passed: True|False`` — no partial
credit. ``ANNA_KARPATHY_AUTO_ATTEST_TOOLS`` defaults **on** for Grade-12 education: checklist
mastery flips when the skill’s **automated benchmark** passes (see ``curriculum_tools``
``education_benchmark``). Set to ``0`` to require manual ``anna tool-pass`` only.
"""

from __future__ import annotations

import os
from typing import Any

from modules.anna_training.curriculum_tools import (
    TOOL_IDS,
    build_grade12_skills_deck,
    normalize_tool_mastery,
)
from modules.anna_training.paper_trades import load_paper_trades_for_gates
from modules.anna_training.quant_metrics import compute_paper_quant_metrics
from modules.anna_training.wilson_nist_reference import run_wilson_reference_check


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _harness_min_iterations() -> int:
    raw = (os.environ.get("ANNA_KARPATHY_HARNESS_MIN_ITERATIONS") or "").strip()
    if not raw:
        return 10
    try:
        return max(1, int(raw))
    except ValueError:
        return 10


def attempt_curriculum_skill(
    skill_id: str,
    *,
    state: dict[str, Any],
    g12: dict[str, Any],
) -> dict[str, Any]:
    """
    Run one measurable practice for `skill_id` in TOOL_IDS.

    Returns JSON-serializable dict: passed, skill_id, summary, detail (dict), practice_kind.
    """
    if skill_id not in TOOL_IDS:
        return {
            "passed": False,
            "skill_id": skill_id,
            "summary": "not_a_tool_skill",
            "detail": {},
            "practice_kind": "noop",
        }

    if skill_id == "math_engine_literacy":
        r = run_wilson_reference_check()
        ok = bool(r.get("ok"))
        return {
            "passed": ok,
            "skill_id": skill_id,
            "summary": "Wilson NIST reference: float vs Decimal oracle",
            "detail": {k: r.get(k) for k in ("ok", "cases_total", "cases_passed", "engine")},
            "practice_kind": "wilson_nist_reference",
        }

    if skill_id == "analysis_algorithms":
        trades = load_paper_trades_for_gates()
        if not trades:
            return {
                "passed": False,
                "skill_id": skill_id,
                "summary": "Need at least one paper trade to run quant metrics practice",
                "detail": {"trade_count": 0},
                "practice_kind": "paper_quant_metrics",
            }
        m = compute_paper_quant_metrics(trades)
        ntr = int(m.get("trade_count") or 0)
        passed = ntr >= 1
        return {
            "passed": passed,
            "skill_id": skill_id,
            "summary": "Paper cohort quant metrics computed",
            "detail": {"trade_count": m.get("trade_count")},
            "practice_kind": "paper_quant_metrics",
        }

    if skill_id == "rcs_rca_discipline":
        trades = load_paper_trades_for_gates()
        with_notes = sum(1 for t in trades if (str(t.get("notes") or "").strip()))
        # Minimal bar: at least one paper outcome includes a non-empty reflection note (RCS habit).
        ok = with_notes >= 1
        return {
            "passed": ok,
            "skill_id": skill_id,
            "summary": "RCS practice: paper trade notes present",
            "detail": {"trades_with_notes": with_notes, "trade_count": len(trades)},
            "practice_kind": "rcs_paper_notes",
        }

    if skill_id == "karpathy_harness_loop":
        it = int(state.get("karpathy_loop_iteration") or 0)
        need = _harness_min_iterations()
        ok = it >= need
        return {
            "passed": ok,
            "skill_id": skill_id,
            "summary": f"Sustained Karpathy supervisor iterations (need {need}, have {it})",
            "detail": {"karpathy_loop_iteration": it, "required": need},
            "practice_kind": "harness_iteration_threshold",
        }

    return {
        "passed": False,
        "skill_id": skill_id,
        "summary": "unhandled_skill",
        "detail": {},
        "practice_kind": "unknown",
    }


def run_skill_practice_cycle(
    state: dict[str, Any],
    g12: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Practice the current deck focus if it is one of the four tools; return attempt result or None.

    Side effect: may set ``grade_12_tool_mastery[skill_id]=True`` when
    ``ANNA_KARPATHY_AUTO_ATTEST_TOOLS=1`` and attempt passes.
    """
    deck = build_grade12_skills_deck(state, g12)
    focus = str(deck.get("current_focus_requirement") or "")
    if focus not in TOOL_IDS:
        return None

    attempt = attempt_curriculum_skill(focus, state=state, g12=g12)
    if _env_bool("ANNA_KARPATHY_AUTO_ATTEST_TOOLS", True) and attempt.get("passed"):
        mp = normalize_tool_mastery(state.get("grade_12_tool_mastery"))
        mp[focus] = True
        state["grade_12_tool_mastery"] = mp

    return attempt
