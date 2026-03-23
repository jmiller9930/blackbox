"""
Compose `anna_analysis_v1` from modular layers (input context supplied by caller).
"""
from __future__ import annotations

from typing import Any

from anna_modules.interpretation import build_interpretation, extract_concepts
from anna_modules.policy import build_policy_alignment_dict, build_suggested_action
from anna_modules.risk import (
    build_market_context,
    build_risk_factors,
    determine_risk_level,
    resolve_context_for_risk,
)
from anna_modules.util import SCHEMA_VERSION, utc_now


def build_analysis(
    input_text: str,
    *,
    market: dict[str, Any] | None,
    market_err: str | None,
    ctx: dict[str, Any] | None,
    ctx_err: str | None,
    trend: dict[str, Any] | None,
    trend_err: str | None,
    policy: dict[str, Any] | None,
    policy_err: str | None,
    use_snapshot: bool,
    use_ctx: bool,
    use_trend: bool,
    use_policy: bool,
) -> dict[str, Any]:
    notes: list[str] = []
    if use_snapshot and market_err:
        notes.append(market_err)
    if use_ctx and ctx_err:
        notes.append(ctx_err)
    if use_trend and trend_err:
        notes.append(trend_err)
    if use_policy and policy_err:
        notes.append(policy_err)

    gm, readiness = resolve_context_for_risk(policy, ctx)
    concepts = extract_concepts(input_text)
    price, spread, m_notes = build_market_context(
        market, use_snapshot=use_snapshot, market_err=market_err
    )
    factors = build_risk_factors(
        input_text,
        guardrail_mode=gm,
        readiness=readiness,
        trend=trend,
        price=price,
        spread=spread,
    )
    risk_level = determine_risk_level(
        guardrail_mode=gm,
        readiness=readiness,
        concepts=concepts,
        trend=trend,
        input_text=input_text,
    )
    suggested = build_suggested_action(
        guardrail_mode=gm,
        risk_level=risk_level,
        input_text=input_text,
    )
    interpretation = build_interpretation(input_text, concepts, gm, readiness)
    pol_align = build_policy_alignment_dict(policy, suggested["intent"], input_text)

    return {
        "kind": "anna_analysis_v1",
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "input_text": input_text,
        "interpretation": interpretation,
        "market_context": {
            "price": price,
            "spread": spread,
            "notes": m_notes,
        },
        "risk_assessment": {
            "level": risk_level,
            "factors": factors[:12],
        },
        "policy_alignment": pol_align,
        "suggested_action": suggested,
        "concepts_used": concepts,
        "caution_flags": [
            "anna_analysis_v1 is advisory only; no execution.",
            "Do not treat keyword concepts as validated registry entries.",
        ],
        "notes": notes,
    }
