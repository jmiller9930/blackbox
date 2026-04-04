"""
Control-plane memory engagement: problem-state signals → engagement mode → lesson retrieval parameters.

This layer does NOT relax validated/promoted-only injection or global hard caps.
"""

from __future__ import annotations

import os
import re
from typing import Any

# Engagement modes (Training Architect directive)
MODE_BASELINE = "baseline"
MODE_INTENSIFIED = "intensified"
MODE_CONSTRAINED = "constrained"
MODE_BYPASS = "bypass"
MODE_OFF = "off"  # ANNA_LESSON_MEMORY_ENABLED=0

ABS_MAX_LESSONS = 4
ABS_MIN_SCORE_FLOOR = 1
ABS_MIN_SCORE_CEIL = 10


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def control_plane_enabled() -> bool:
    """When False, retrieval uses baseline env defaults (W9-compatible); signals still computed.

    Default **on** when env unset (Training Architect: runtime control plane required).
    Set ``ANNA_LESSON_MEMORY_CONTROL_PLANE=0`` to disable dynamic retrieval modes.
    """
    raw = os.environ.get("ANNA_LESSON_MEMORY_CONTROL_PLANE")
    if raw is None or str(raw).strip() == "":
        return True
    return _env_truthy("ANNA_LESSON_MEMORY_CONTROL_PLANE")


def high_risk_engagement_policy() -> str:
    """constrained | intensified — applies when elevated risk triggers high-risk branch."""
    raw = (os.environ.get("ANNA_LESSON_MEMORY_HIGH_RISK_MODE") or "constrained").strip().lower()
    return raw if raw in ("constrained", "intensified") else "constrained"


def _semantic_ambiguity(input_text: str) -> bool:
    low = (input_text or "").lower()
    if re.search(
        r"\b(maybe|perhaps|unclear|could go either|not sure|ambiguous|either way|"
        r"conflicted|mixed|both sides|nuance|unsure|hedge)\b",
        low,
    ):
        return True
    tfs = re.findall(r"\b(5m|15m|1h|4h|daily|5min|15min)\b", low, re.I)
    if len({t.lower() for t in tfs}) >= 2:
        return True
    return False


def _conflicting_signals_heuristic(
    input_text: str,
    risk_level: str,
    merged_structured: dict[str, Any],
) -> bool:
    """Derived: adversative language + medium risk, or math+strategy layers both present with medium+ risk."""
    low = (input_text or "").lower()
    if risk_level == "medium" and re.search(r"\b(but|however|though|yet|conflict)\b", low):
        return True
    st = merged_structured or {}
    has_math = bool(st.get("math_engine"))
    has_sr = bool(st.get("strategy_regime_catalog_facts"))
    if has_math and has_sr and risk_level in ("medium", "high"):
        return True
    return False


def detect_problem_signals(
    *,
    input_text: str,
    guardrail_mode: str,
    risk_level: str,
    readiness: str | None,
    playbook_hit: bool,
    merged_rule_facts: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Runtime problem-state signals — all booleans inspectable on anna_analysis_v1.
    """
    merged_structured = (merged_rule_facts or {}).get("structured") or {}
    sem = _semantic_ambiguity(input_text)
    conf = _conflicting_signals_heuristic(input_text, risk_level, merged_structured)

    low_confidence = False
    if readiness in ("degraded", "unstable"):
        low_confidence = True
    elif risk_level == "medium":
        low_confidence = True
    elif sem:
        low_confidence = True

    elevated_risk = risk_level in ("medium", "high") or guardrail_mode in ("CAUTION", "FROZEN")

    bypass_lesson_memory = guardrail_mode == "FROZEN" and risk_level == "high"

    clear_routine = (
        risk_level == "low"
        and guardrail_mode == "NORMAL"
        and not sem
        and not conf
        and readiness not in ("degraded", "unstable")
    )

    return {
        "semantic_ambiguity": sem,
        "low_confidence_derived": low_confidence,
        "conflicting_signals": conf,
        "elevated_risk": elevated_risk,
        "bypass_lesson_memory": bypass_lesson_memory,
        "clear_routine": clear_routine,
        "playbook_hit": bool(playbook_hit),
    }


def select_engagement_mode(
    signals: dict[str, Any],
    *,
    guardrail_mode: str,
    risk_level: str,
) -> str:
    if signals.get("bypass_lesson_memory"):
        return MODE_BYPASS

    hrp = high_risk_engagement_policy()
    if risk_level == "high" or guardrail_mode == "FROZEN":
        return MODE_CONSTRAINED if hrp == "constrained" else MODE_INTENSIFIED

    if signals.get("low_confidence_derived") or signals.get("conflicting_signals"):
        return MODE_INTENSIFIED

    if signals.get("clear_routine"):
        return MODE_BASELINE

    return MODE_BASELINE


def effective_retrieval_params(
    mode: str,
    *,
    base_top_k: int,
    base_min_score: int,
) -> dict[str, Any]:
    """
    Maps mode → actual top_k / min_score (bounded). Also whether behavior_effect may apply.
    """
    bk = max(1, min(ABS_MAX_LESSONS, base_top_k))
    bm = max(ABS_MIN_SCORE_FLOOR, min(ABS_MIN_SCORE_CEIL, base_min_score))

    if mode == MODE_OFF:
        return {
            "top_k": bk,
            "min_score": bm,
            "bypass": True,
            "apply_behavior_effect": False,
        }
    if mode == MODE_BYPASS:
        return {
            "top_k": bk,
            "min_score": bm,
            "bypass": True,
            "apply_behavior_effect": False,
        }
    if mode == MODE_BASELINE:
        return {
            "top_k": bk,
            "min_score": bm,
            "bypass": False,
            "apply_behavior_effect": True,
        }
    if mode == MODE_INTENSIFIED:
        return {
            "top_k": max(1, min(ABS_MAX_LESSONS, bk + 2)),
            "min_score": max(ABS_MIN_SCORE_FLOOR, bm - 1),
            "bypass": False,
            "apply_behavior_effect": True,
        }
    if mode == MODE_CONSTRAINED:
        return {
            "top_k": max(1, bk - 1),
            "min_score": min(ABS_MIN_SCORE_CEIL, bm + 1),
            "bypass": False,
            "apply_behavior_effect": False,
        }
    return {
        "top_k": bk,
        "min_score": bm,
        "bypass": False,
        "apply_behavior_effect": True,
    }


def build_memory_control_plane_payload(
    *,
    lesson_memory_env_on: bool,
    signals: dict[str, Any],
    engagement_mode: str,
    retrieval: dict[str, Any],
    control_plane_active: bool,
) -> dict[str, Any]:
    return {
        "signals": dict(signals),
        "engagement_mode": engagement_mode,
        "retrieval": {
            "top_k": retrieval["top_k"],
            "min_score": retrieval["min_score"],
            "bypass": retrieval["bypass"],
            "apply_behavior_effect": retrieval["apply_behavior_effect"],
            "scope": "validated_promoted_similarity",
        },
        "lesson_memory_env_on": lesson_memory_env_on,
        "control_plane_enabled": control_plane_active,
    }
