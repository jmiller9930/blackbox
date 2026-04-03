"""Internalize Grade-12 learning into durable FACT context for Anna's analyst path.

Two layers (both merge via ``carryforward_fact_lines`` → ``facts_for_prompt`` in ``analysis.py``;
Anna does not need to "ask" for these — they are always merged as authoritative cumulative FACT):

1. **Skills** — all four ``grade_12_tool_mastery`` true → ``grade_12_knowledge_internalized``.
2. **Trading gate** — overall Grade-12 gate PASS (tools + paper cohort) → ``grade_12_trading_knowledge_internalized``.
"""

from __future__ import annotations

from typing import Any

from modules.anna_training.curriculum_tools import (
    GRADE_12_TOOLS,
    curriculum_tools_complete,
    normalize_tool_mastery,
)
from modules.anna_training.cumulative import append_cumulative_log
from modules.anna_training.store import utc_now_iso


def maybe_grade12_internalize(state: dict[str, Any]) -> bool:
    """
    If all four tools are passed and we have not yet stamped internalization, set
    ``grade_12_knowledge_internalized``, append carryforward bullets, and log once.

    Idempotent: does nothing if ``grade_12_knowledge_internalized`` is already set.
    Returns True if this call performed the snapshot.
    """
    m = normalize_tool_mastery(state.get("grade_12_tool_mastery"))
    if not curriculum_tools_complete(m):
        return False
    if state.get("grade_12_knowledge_internalized"):
        return False

    now = utc_now_iso()
    state["grade_12_knowledge_internalized"] = {
        "version": 1,
        "at_utc": now,
        "skills": [
            {"id": t["id"], "title": t["title"], "summary": t["summary"]} for t in GRADE_12_TOOLS
        ],
    }

    bullets = list(state.get("carryforward_bullets") or [])
    summary_line = (
        "Grade 12 curriculum internalized (durable operating knowledge): "
        + "; ".join(t["title"] for t in GRADE_12_TOOLS)
        + ". These habits are cumulative FACT for analysis and the paper harness."
    )
    if summary_line not in bullets:
        bullets.append(summary_line)
    for t in GRADE_12_TOOLS:
        line = f"[INTERNALIZED G12] {t['id']}: {t['summary']}"
        if line not in bullets:
            bullets.append(line)
    state["carryforward_bullets"] = bullets

    append_cumulative_log(
        state,
        kind="grade_12_knowledge_internalized_v1",
        summary="All four Grade-12 skills recorded as internalized knowledge (carryforward + state snapshot).",
        curriculum_id=state.get("curriculum_id"),
        meta={"version": 1, "at_utc": now},
    )
    return True


def maybe_grade12_trading_gate_internalize(state: dict[str, Any]) -> bool:
    """
    When overall Grade-12 gate PASS (sequential skills + paper numeric cohort), stamp trading
    competence as internalized knowledge once — same carryforward / FACT path as skills.

    Uses ``evaluate_grade12_gates(state)`` so mastery matches the state about to be saved.
    """
    from modules.anna_training.gates import evaluate_grade12_gates

    if state.get("grade_12_trading_knowledge_internalized"):
        return False

    g12 = evaluate_grade12_gates(state)
    if not g12.get("pass"):
        return False

    now = utc_now_iso()
    wr = g12.get("win_rate")
    wr_s = f"{wr:.0%}" if wr is not None else "n/a"
    state["grade_12_trading_knowledge_internalized"] = {
        "version": 1,
        "at_utc": now,
        "decisive_trades": g12.get("decisive_trades"),
        "min_decisive_trades": g12.get("min_decisive_trades"),
        "win_rate": wr,
        "min_win_rate": g12.get("min_win_rate"),
    }

    bullets = list(state.get("carryforward_bullets") or [])
    line = (
        f"[INTERNALIZED G12 TRADING] Grade-12 paper cohort gate satisfied "
        f"(decisive {g12.get('decisive_trades')}/{g12.get('min_decisive_trades')} @ win rate {wr_s} "
        f"vs floor {g12.get('min_win_rate')}). "
        "Trading competence is cumulative FACT in analysis context — available without re-asking."
    )
    if line not in bullets:
        bullets.append(line)
    state["carryforward_bullets"] = bullets

    append_cumulative_log(
        state,
        kind="grade_12_trading_knowledge_internalized_v1",
        summary="Grade-12 overall gate PASS: paper trading competence recorded as internalized knowledge.",
        curriculum_id=state.get("curriculum_id"),
        meta={"version": 1, "at_utc": now, "gate_id": g12.get("gate_id")},
    )
    return True


def internalized_grade12_snapshot(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the skills internalization record if present (for status JSON / tooling)."""
    if not state:
        return None
    raw = state.get("grade_12_knowledge_internalized")
    return raw if isinstance(raw, dict) else None


def internalized_trading_snapshot(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the trading-gate internalization record if present."""
    if not state:
        return None
    raw = state.get("grade_12_trading_knowledge_internalized")
    return raw if isinstance(raw, dict) else None


def apply_internalization_hooks(state: dict[str, Any]) -> None:
    """Run all one-time internalization snapshots (called from ``save_state``)."""
    maybe_grade12_internalize(state)
    maybe_grade12_trading_gate_internalize(state)
