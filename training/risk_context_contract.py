"""
Shared risk_context_v1 + recommended_risk_pct for finquant_agentic_qa_v1 gold rows.

Normative shape from training/CURRENT_TRAINING_STATUS.md (learning engineer 2026-05-03).
"""
from __future__ import annotations

from typing import Any


def build_risk_context_for_gold(
    final_status: str,
    *,
    conf_gap: float,
    regime: str,
    atr_pct: float | None,
    i_dont_know: bool,
    baseline_risk_pct: float | None = None,
) -> tuple[dict[str, Any], float]:
    """
    Returns (risk_context_v1 dict, recommended_risk_pct).
    ENTER_*: positive bounded risk %; NO_TRADE / INSUFFICIENT_DATA: 0.0.
    """
    base = float(baseline_risk_pct) if baseline_risk_pct is not None else 1.0
    atr_pf = float(atr_pct) if atr_pct is not None else 3.0

    # volatility_factor: high ATR% → lower deploy (0.5–1.2)
    if atr_pf > 5.0:
        vol_f, vol_note = 0.65, "ATR% elevated — elevated chop risk — reduce deploy"
    elif atr_pf > 3.0:
        vol_f, vol_note = 0.85, "ATR% above quiet baseline — slight caution"
    elif atr_pf > 1.5:
        vol_f, vol_note = 1.0, "ATR% normal range — no adjustment"
    else:
        vol_f, vol_note = 1.1, "ATR% compressed — quiet trending bias — slight increase allowed"

    rl = (regime or "").lower()
    if "range" in rl or "chop" in rl:
        struct_f, struct_note = 0.75, "Ranging/chop — reduce deploy vs clean trend"
    elif "volatile" in rl:
        struct_f, struct_note = 0.85, "Volatile regime — structure not clean HH/HL — caution"
    elif "trend" in rl:
        struct_f, struct_note = 1.1, "Trending structure — modest increase vs chop"
    else:
        struct_f, struct_note = 1.0, "Structure neutral — no adjustment"

    if conf_gap >= 0.55:
        sig_f, sig_note = 1.45, f"conviction spread {conf_gap:.2f} — strong signal — increase"
    elif conf_gap >= 0.35:
        sig_f, sig_note = 1.1, f"spread {conf_gap:.2f} — solid separation"
    elif conf_gap >= 0.25:
        sig_f, sig_note = 1.05, f"spread {conf_gap:.2f} — meets gate"
    else:
        sig_f, sig_note = 0.65, f"spread {conf_gap:.2f} — weak separation"

    session_f, session_note = 1.0, "Session not supplied in DATA — assume neutral liquidity"
    health_f, health_note = 1.0, "Health not supplied in DATA — neutral"

    if final_status in ("NO_TRADE", "INSUFFICIENT_DATA"):
        primary = "confidence" if i_dont_know else "gates"
        if final_status == "INSUFFICIENT_DATA":
            primary = "confidence" if i_dont_know else "data_gaps"
        notes = {
            "volatility": vol_note,
            "structure": struct_note,
            "signal": sig_note,
            "session": session_note,
            "health": health_note,
            "no_deploy": f"final_risk_pct=0 — {primary} drove NO_DEPLOY",
        }
        rc: dict[str, Any] = {
            "baseline_risk_pct": round(base, 4),
            "volatility_factor": vol_f,
            "structure_factor": struct_f,
            "signal_factor": sig_f,
            "session_factor": session_f,
            "health_factor": health_f,
            "final_risk_pct": 0.0,
            "risk_bounds": {"min": 0.5, "max": 2.0},
            "factor_notes": notes,
        }
        return rc, 0.0

    raw = base * vol_f * struct_f * sig_f * session_f * health_f
    final_pct = max(0.5, min(2.0, round(raw, 2)))
    notes = {
        "volatility": vol_note,
        "structure": struct_note,
        "signal": sig_note,
        "session": session_note,
        "health": health_note,
    }
    rc = {
        "baseline_risk_pct": round(base, 4),
        "volatility_factor": vol_f,
        "structure_factor": struct_f,
        "signal_factor": sig_f,
        "session_factor": session_f,
        "health_factor": health_f,
        "final_risk_pct": final_pct,
        "risk_bounds": {"min": 0.5, "max": 2.0},
        "factor_notes": notes,
    }
    return rc, final_pct
