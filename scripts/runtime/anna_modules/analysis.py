"""
Compose `anna_analysis_v1` from modular layers (input context supplied by caller).

Pipeline (Directive 4.6.3.X): intent → context check → memory → rules (playbook) → local LLM → validate → respond → store (candidate).
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from anna_modules.concept_retrieval import retrieve_concept_support
from anna_modules.context_requirements import assess_context_completeness
from anna_modules.human_intent import build_factual_reply, classify_human_intent
from anna_modules.input_adapter import normalize_trader_text
from anna_modules.interpretation import build_interpretation, build_strategy_awareness
from anna_modules.pipeline import maybe_store_interaction, resolve_answer_layers
from anna_modules.policy import build_policy_alignment_dict, build_suggested_action
from anna_modules.education_definitions import build_registry_definition_summary
from anna_modules.rule_facts import compute_rule_facts
from anna_modules.risk import (
    build_market_context,
    build_risk_factors,
    determine_risk_level,
    resolve_context_for_risk,
)
from anna_modules.util import SCHEMA_VERSION, utc_now


def _use_llm_default() -> bool:
    return os.environ.get("ANNA_USE_LLM", "1").strip().lower() not in ("0", "false", "no")


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
    conn: sqlite3.Connection | None = None,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    input_text = normalize_trader_text(input_text)
    human_intent = classify_human_intent(input_text)
    if human_intent.get("bypass") == "datetime":
        reply = build_factual_reply(input_text)
        if reply:
            return _build_factual_datetime_analysis(input_text, human_intent, reply)

    if use_llm is None:
        use_llm = _use_llm_default()

    ctx_assess = assess_context_completeness(input_text)
    if not ctx_assess.get("is_complete"):
        return _build_clarification_analysis(input_text, human_intent, ctx_assess)

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
    concepts, concept_support, concept_notes, registry_loaded = retrieve_concept_support(input_text)
    notes.extend(concept_notes)
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
        trend=trend,
        input_text=input_text,
    )
    suggested = build_suggested_action(
        guardrail_mode=gm,
        risk_level=risk_level,
        input_text=input_text,
    )

    rule_facts = compute_rule_facts(input_text, human_intent, concepts)

    resolved_summary, resolved_headline, extra_sig, answer_source, layer_meta = resolve_answer_layers(
        conn,
        input_text,
        human_intent,
        use_llm=use_llm,
        rule_facts=rule_facts,
    )

    # "What is X?" — canonical definitions from the concept registry when no LLM/playbook layer produced text.
    if registry_loaded and concepts and not resolved_summary:
        rsum, rhead = build_registry_definition_summary(input_text, concepts)
        if rsum:
            resolved_summary = rsum
            resolved_headline = rhead or resolved_headline
            answer_source = "registry_definition"
            extra_sig = list(extra_sig or []) + ["registry:definition"]

    interpretation = build_interpretation(
        input_text,
        concepts,
        gm,
        readiness,
        registry_loaded=registry_loaded,
        human_intent=human_intent,
    )

    playbook_applied = bool(layer_meta.get("playbook_hit"))
    if resolved_summary is not None:
        interpretation["summary"] = resolved_summary
        if resolved_headline:
            interpretation["headline"] = resolved_headline
        sig = list(interpretation.get("signals") or [])
        sig.extend(extra_sig or [])
        interpretation["signals"] = sig
    else:
        answer_source = "template_fallback"
        # Directive 4.6.3.1 — no generic interpretation template as the Telegram "answer"
        interpretation["headline"] = "Need more to go on"
        interpretation["summary"] = (
            "I can’t ground a reliable answer from rules or model output for that yet — I’m not going to "
            "fill in with generic trading filler. What symbol, timeframe, and setup are we discussing? "
            "Or narrow the question (e.g. concept vs a specific live trade)."
        )
        interpretation["signals"] = list(interpretation.get("signals") or []) + [
            "pipeline:explicit_limitation",
        ]

    pol_align = build_policy_alignment_dict(policy, suggested["intent"], input_text)
    strategy_awareness = build_strategy_awareness(
        input_text, price=price, spread=spread, market_notes=m_notes
    )

    pipeline_trace = {
        "answer_source": answer_source,
        "steps": _build_steps(
            answer_source=answer_source or "template_fallback",
            layer_meta=layer_meta,
        ),
        "layer_meta": layer_meta,
        "rule_facts": rule_facts.get("structured") or {},
    }

    out: dict[str, Any] = {
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
        "concept_support": concept_support,
        "strategy_awareness": strategy_awareness,
        "caution_flags": [
            "anna_analysis_v1 is advisory only; no execution.",
            (
                "Registry-backed concept IDs are informational; status does not authorize execution."
                if registry_loaded and concepts
                else "Do not infer execution permission from analysis output alone."
            ),
        ],
        "notes": notes,
        "human_intent": human_intent,
        "strategy_playbook_applied": playbook_applied,
        "pipeline": pipeline_trace,
        "context_assessment": {"is_complete": True, "missing_fields": []},
    }

    memory_id = maybe_store_interaction(
        conn,
        input_text=input_text,
        human_intent=human_intent,
        final_summary=str(interpretation.get("summary") or ""),
        answer_source=answer_source,
        pipeline_meta=pipeline_trace,
    )
    if memory_id:
        out["pipeline"]["stored_memory_id"] = memory_id

    return out


def _build_steps(
    *,
    answer_source: str,
    layer_meta: dict[str, Any],
) -> list[str]:
    s = ["receive", "classify_intent", "context_ok"]
    if answer_source == "memory_only":
        s.append("contextual_memory")
        return s
    if answer_source == "registry_definition":
        s.extend(["concept_registry", "registry_definition"])
        return s
    if answer_source == "rules_only":
        s.append("deterministic_rules")
        return s
    if answer_source in ("rules_plus_qwen", "playbook_plus_qwen", "memory_plus_qwen"):
        if answer_source == "memory_plus_qwen":
            s.extend(
                ["contextual_memory", "ground_deterministic", "llm_qwen", "validate_llm_output"]
            )
        elif answer_source == "playbook_plus_qwen":
            s.extend(
                [
                    "contextual_memory_miss",
                    "deterministic_rules",
                    "ground_llm_prompt",
                    "llm_qwen",
                    "validate_llm_output",
                ]
            )
        else:
            s.extend(
                [
                    "contextual_memory_miss",
                    "deterministic_rules_miss",
                    "llm_qwen",
                    "validate_llm_output",
                ]
            )
        return s
    if answer_source == "template_fallback":
        if layer_meta.get("llm_called"):
            s.append("llm_qwen_failed")
            if layer_meta.get("llm_error"):
                s.append(f"llm_error:{layer_meta['llm_error']}")
        s.append("template_fallback")
        return s
    s.append("respond")
    return s


def _build_clarification_analysis(
    input_text: str,
    human_intent: dict[str, Any],
    ctx_assess: dict[str, Any],
) -> dict[str, Any]:
    cq = ctx_assess.get("clarifying_question") or "What symbol, timeframe, and setup are we discussing?"
    return {
        "kind": "anna_analysis_v1",
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "input_text": input_text,
        "interpretation": {
            "headline": "Need a bit more context",
            "summary": cq,
            "signals": ["pipeline:clarification_required"],
            "assumptions": [],
        },
        "market_context": {"price": None, "spread": None, "notes": []},
        "risk_assessment": {"level": "low", "factors": []},
        "policy_alignment": {},
        "suggested_action": {"intent": "", "rationale": ""},
        "concepts_used": [],
        "concept_support": {},
        "strategy_awareness": None,
        "caution_flags": [],
        "notes": [],
        "human_intent": human_intent,
        "strategy_playbook_applied": False,
        "pipeline": {
            "answer_source": "clarification_requested",
            "steps": ["receive", "classify_intent", "context_incomplete_stop"],
            "layer_meta": {"missing_fields": ctx_assess.get("missing_fields") or []},
        },
        "context_assessment": ctx_assess,
    }


def _build_factual_datetime_analysis(
    input_text: str,
    human_intent: dict[str, Any],
    reply: str,
) -> dict[str, Any]:
    """Calendar/time questions — no fake 'market commentary' template."""
    return {
        "kind": "anna_analysis_v1",
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "input_text": input_text,
        "interpretation": {
            "headline": "Quick answer",
            "summary": reply,
            "signals": ["intent:factual_datetime"],
            "assumptions": [],
        },
        "market_context": {"price": None, "spread": None, "notes": []},
        "risk_assessment": {"level": "low", "factors": []},
        "policy_alignment": {},
        "suggested_action": {"intent": "", "rationale": ""},
        "concepts_used": [],
        "concept_support": {},
        "strategy_awareness": None,
        "caution_flags": [],
        "notes": [],
        "human_intent": human_intent,
        "pipeline": {
            "answer_source": "rules_only",
            "steps": ["receive", "factual_datetime"],
        },
        "context_assessment": {"is_complete": True, "missing_fields": []},
    }


assemble_anna_analysis_v1 = build_analysis
