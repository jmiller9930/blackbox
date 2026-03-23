"""
Risk reasoning: level, factors, market_context notes (spread / snapshot context).
"""
from __future__ import annotations

import re
from typing import Any

from anna_modules.input_adapter import guardrail_mode_from_policy, readiness_from_context
from anna_modules.util import read_float


def build_market_context(
    market: dict[str, Any] | None,
    *,
    use_snapshot: bool,
    market_err: str | None,
) -> tuple[float | None, float | None, list[str]]:
    price = read_float(market, "price") if market else None
    spread = read_float(market, "spread") if market else None
    m_notes: list[str] = []
    if market and market.get("source") == "unavailable":
        m_notes.append("Market snapshot source was unavailable when recorded; no fabricated prices.")
    if not use_snapshot:
        m_notes.append("Market snapshot not requested; price/spread may be null.")
    elif market_err or not market:
        m_notes.append("No market snapshot data applied.")
    if price is not None and spread is not None and price > 0:
        bps = (spread / price) * 10000.0
        m_notes.append(f"Snapshot mid context: spread ≈ {bps:.2f} bps of price (informational).")
    return price, spread, m_notes


def build_risk_factors(
    input_text: str,
    *,
    guardrail_mode: str,
    readiness: str | None,
    trend: dict[str, Any] | None,
    price: float | None,
    spread: float | None,
) -> list[str]:
    factors: list[str] = []
    neg = re.search(r"\b(thin|crash|panic|liquidat|unsafe|avoid|stop\s*hunt)\b", input_text, re.I)
    if neg:
        factors.append("Language suggests stress or adverse conditions.")
    if guardrail_mode == "FROZEN":
        factors.append("Guardrail policy mode is FROZEN.")
    elif guardrail_mode == "CAUTION":
        factors.append("Guardrail policy mode is CAUTION.")
    if readiness == "unstable":
        factors.append("Decision context reports unstable system readiness.")
    elif readiness == "degraded":
        factors.append("Decision context reports degraded readiness.")
    if trend and isinstance(trend.get("flags"), list) and trend["flags"]:
        factors.append(f"System trend flags present: {len(trend['flags'])} flag(s).")
    if price is not None and spread is not None and price > 0 and (spread / price) > 0.005:
        factors.append("Observed spread is large relative to price (rough check).")

    if not factors:
        factors.append("No strong risk amplifiers detected from text and available context.")
    return factors


def determine_risk_level(
    *,
    guardrail_mode: str,
    readiness: str | None,
    trend: dict[str, Any] | None,
    input_text: str,
) -> str:
    neg = re.search(r"\b(thin|crash|panic|liquidat|unsafe|avoid|stop\s*hunt)\b", input_text, re.I)
    risk_level = "low"
    if guardrail_mode == "FROZEN" or readiness == "unstable":
        risk_level = "high"
    elif guardrail_mode == "CAUTION" or readiness == "degraded" or neg or (
        trend and trend.get("flags")
    ):
        risk_level = "medium"
    if risk_level != "high" and re.search(r"\b(risk|risky)\b", input_text, re.I):
        risk_level = "medium"
    return risk_level


def resolve_context_for_risk(
    policy: dict[str, Any] | None,
    ctx: dict[str, Any] | None,
) -> tuple[str, str | None]:
    return guardrail_mode_from_policy(policy), readiness_from_context(ctx)
