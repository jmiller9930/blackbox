"""
Compose `anna_analysis_v1` from modular layers (input context supplied by caller).

Pipeline (Directive 4.6.3.X): intent → context check → memory → rules (playbook) → local LLM → validate → respond → store (candidate).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from anna_modules.concept_retrieval import retrieve_concept_support
from anna_modules.context_ledger_consumer import resolve_context_bundle_attachment
from anna_modules.context_requirements import assess_context_completeness
from anna_modules.human_intent import build_factual_reply, classify_human_intent
from anna_modules.input_adapter import normalize_trader_text
from anna_modules.interpretation import build_interpretation, build_strategy_awareness
from anna_modules.pipeline import maybe_store_interaction, resolve_answer_layers
from anna_modules.policy import (
    apply_lesson_memory_to_suggested_action,
    build_policy_alignment_dict,
    build_suggested_action,
)
from anna_modules.education_definitions import build_registry_definition_summary
from anna_modules.analysis_math import (
    compute_math_engine_facts,
    merge_authoritative_fact_layers,
)
from anna_modules.rule_facts import compute_rule_facts
from anna_modules.lesson_memory import max_inject, min_score_threshold
from anna_modules.memory_control_plane import (
    MODE_BASELINE,
    MODE_OFF,
    build_memory_control_plane_payload,
    control_plane_enabled,
    detect_problem_signals,
    effective_retrieval_params,
    select_engagement_mode,
)
from anna_modules.strategy_playbook import apply_strategy_playbook
from modules.anna_training.catalog import CURRICULA
from modules.anna_training.cumulative import carryforward_fact_lines
from modules.anna_training.store import load_state
from anna_modules.risk import (
    build_market_context,
    build_risk_factors,
    determine_risk_level,
    resolve_context_for_risk,
)
from anna_modules.util import SCHEMA_VERSION, utc_now


def _use_llm_default() -> bool:
    return os.environ.get("ANNA_USE_LLM", "1").strip().lower() not in ("0", "false", "no")


def _lesson_memory_enabled() -> bool:
    return (os.environ.get("ANNA_LESSON_MEMORY_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _attach_context_ledger(
    out: dict[str, Any],
    ledger_attachment: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach Phase 5.9 context-ledger consumption summary; keep legacy output when not engaged."""
    if ledger_attachment is None:
        return out
    merged = dict(out)
    merged["context_ledger"] = ledger_attachment
    if ledger_attachment.get("consumption") == "rejected":
        reason = ledger_attachment.get("reason") or "unknown"
        notes = list(merged.get("notes") or [])
        notes.append(f"Context ledger bundle not usable: {reason}")
        merged["notes"] = notes
    return merged


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
    market_data_tick: dict[str, Any] | None = None,
    market_data_err: str | None = None,
    context_bundle_json: str | None = None,
    context_bundle_path: Path | None = None,
    context_profile_agent_id: str = "anna",
    context_profile_registry_path: Path | None = None,
) -> dict[str, Any]:
    ledger_attachment = resolve_context_bundle_attachment(
        bundle_json=context_bundle_json,
        bundle_path=context_bundle_path,
        agent_id=context_profile_agent_id,
        registry_path=context_profile_registry_path,
    )

    input_text = normalize_trader_text(input_text)
    human_intent = classify_human_intent(input_text)
    if human_intent.get("bypass") == "datetime":
        reply = build_factual_reply(input_text)
        if reply:
            return _attach_context_ledger(
                _build_factual_datetime_analysis(input_text, human_intent, reply),
                ledger_attachment,
            )

    if use_llm is None:
        use_llm = _use_llm_default()

    ctx_assess = assess_context_completeness(input_text)
    if not ctx_assess.get("is_complete"):
        return _attach_context_ledger(
            _build_clarification_analysis(input_text, human_intent, ctx_assess),
            ledger_attachment,
        )

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
    math_facts = compute_math_engine_facts(
        input_text,
        human_intent,
        market=market,
        market_data_tick=market_data_tick,
    )
    merged_rule_facts = merge_authoritative_fact_layers(rule_facts, math_facts)
    training_state_snapshot: dict[str, Any] | None = None
    try:
        training_state_snapshot = load_state()
        cf_layer = {
            "facts_for_prompt": carryforward_fact_lines(training_state_snapshot),
            "structured": {"cumulative_carryforward": True},
        }
        merged_rule_facts = merge_authoritative_fact_layers(merged_rule_facts, cf_layer)
    except Exception:
        training_state_snapshot = None

    phase5_market: dict[str, Any] | None = None
    if market_data_tick is not None:
        phase5_market = {
            "source": "phase5_market_data_db",
            "tick": market_data_tick,
            "gate_state": market_data_tick.get("gate_state"),
        }
    try:
        from modules.anna_training.regime_signal import (
            infer_regime_from_phase5_market,
            load_trading_core_signal,
            signal_fact_lines,
        )
        from modules.anna_training.strategy_catalog import strategy_catalog_fact_lines
        from modules.anna_training.strategy_stats import strategy_stats_fact_lines

        _regime = infer_regime_from_phase5_market(phase5_market)
        _tc = load_trading_core_signal()
        sr_layer = {
            "facts_for_prompt": signal_fact_lines(_tc, _regime)
            + strategy_catalog_fact_lines()
            + strategy_stats_fact_lines(),
            "structured": {"strategy_regime_catalog_facts": True},
        }
        merged_rule_facts = merge_authoritative_fact_layers(merged_rule_facts, sr_layer)
    except Exception:
        pass

    lesson_memory_payload: dict[str, Any] = {
        "enabled": False,
        "injected": [],
        "facts": [],
        "situation": None,
    }
    _regime_for_lesson: str | None = None
    try:
        from modules.anna_training.regime_signal import infer_regime_from_phase5_market

        _regime_for_lesson = infer_regime_from_phase5_market(phase5_market)
    except Exception:
        _regime_for_lesson = None

    pb_probe = apply_strategy_playbook(input_text, human_intent)
    playbook_hit = pb_probe is not None
    problem_signals = detect_problem_signals(
        input_text=input_text,
        guardrail_mode=gm,
        risk_level=risk_level,
        readiness=readiness,
        playbook_hit=playbook_hit,
        merged_rule_facts=merged_rule_facts,
    )
    lesson_memory_env_on = _lesson_memory_enabled()
    cp_active = control_plane_enabled()
    base_k = max_inject()
    base_ms = min_score_threshold()

    if not lesson_memory_env_on:
        engagement_mode = MODE_OFF
        retrieval = effective_retrieval_params(MODE_OFF, base_top_k=base_k, base_min_score=base_ms)
    elif not cp_active:
        engagement_mode = MODE_BASELINE
        retrieval = effective_retrieval_params(MODE_BASELINE, base_top_k=base_k, base_min_score=base_ms)
    else:
        engagement_mode = select_engagement_mode(
            problem_signals,
            guardrail_mode=gm,
            risk_level=risk_level,
        )
        retrieval = effective_retrieval_params(
            engagement_mode,
            base_top_k=base_k,
            base_min_score=base_ms,
        )

    memory_control_plane_payload = build_memory_control_plane_payload(
        lesson_memory_env_on=lesson_memory_env_on,
        signals=problem_signals,
        engagement_mode=engagement_mode,
        retrieval=retrieval,
        control_plane_active=cp_active,
    )

    if conn is not None and lesson_memory_env_on and not retrieval["bypass"]:
        try:
            from anna_modules.lesson_memory import build_lesson_memory_fact_lines, build_situation

            situation = build_situation(
                input_text=input_text,
                regime_tag=_regime_for_lesson,
            )
            lesson_lines, lesson_injected = build_lesson_memory_fact_lines(
                conn,
                situation,
                top_k=retrieval["top_k"],
                min_score=retrieval["min_score"],
            )
            lesson_memory_payload = {
                "enabled": True,
                "injected": lesson_injected,
                "facts": lesson_lines,
                "situation": situation,
                "bypass_reason": None,
            }
            if lesson_lines:
                lm_layer = {
                    "facts_for_prompt": lesson_lines,
                    "structured": {"lesson_memory": True, "injected": lesson_injected},
                }
                merged_rule_facts = merge_authoritative_fact_layers(merged_rule_facts, lm_layer)
        except Exception as exc:
            notes.append(f"lesson_memory: skipped ({exc})")
    elif lesson_memory_env_on and retrieval["bypass"]:
        lesson_memory_payload = {
            "enabled": False,
            "injected": [],
            "facts": [],
            "situation": None,
            "bypass_reason": engagement_mode,
        }
    if (os.environ.get("ANNA_LESSON_MEMORY_DEBUG") or "").strip().lower() in ("1", "true", "yes", "on"):
        lesson_memory_payload["authoritative_facts_all"] = list(
            merged_rule_facts.get("facts_for_prompt") or []
        )

    if (
        lesson_memory_env_on
        and lesson_memory_payload.get("enabled")
        and not retrieval["bypass"]
    ):
        suggested, behavior_applied = apply_lesson_memory_to_suggested_action(
            suggested,
            lesson_memory_payload.get("injected"),
            allow_behavior_effect=bool(retrieval.get("apply_behavior_effect")),
        )
        if behavior_applied:
            lesson_memory_payload["behavior_applied"] = behavior_applied

    resolved_summary, resolved_headline, extra_sig, answer_source, layer_meta = resolve_answer_layers(
        conn,
        input_text,
        human_intent,
        use_llm=use_llm,
        rule_facts=merged_rule_facts,
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
        if merged_rule_facts.get("structured", {}).get("math_engine"):
            sig.append("math_engine:v1")
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
        "rule_facts": merged_rule_facts.get("structured") or {},
        "lesson_memory": lesson_memory_payload,
        "memory_control_plane": memory_control_plane_payload,
    }

    if market_data_tick is not None:
        gate_st = market_data_tick.get("gate_state", "unknown")
        if gate_st == "blocked":
            notes.append(
                "Phase 5.1 market data tick is present but gate_state=blocked; "
                "treat price as unverified."
            )
        elif gate_st == "degraded":
            notes.append(
                "Phase 5.1 market data tick gate_state=degraded; use with caution."
            )
    elif market_data_err and market_data_err != "feature_disabled":
        notes.append(f"Phase 5.1 market data unavailable: {market_data_err}")

    _regime_out = "unknown"
    _tc_out: dict[str, Any] | None = None
    try:
        from modules.anna_training.regime_signal import infer_regime_from_phase5_market, load_trading_core_signal

        _regime_out = infer_regime_from_phase5_market(phase5_market)
        _tc_out = load_trading_core_signal()
    except Exception:
        pass

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
        "phase5_market_data": phase5_market,
        "regime": _regime_out,
        "signal_snapshot": _tc_out,
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
        "memory_control_plane": memory_control_plane_payload,
        "lesson_memory": lesson_memory_payload,
        "math_engine": merged_rule_facts.get("structured", {}).get("math_engine"),
        "cumulative_learning": (
            {
                "curriculum_id": training_state_snapshot.get("curriculum_id"),
                "stage": (CURRICULA.get(training_state_snapshot.get("curriculum_id") or "") or {}).get(
                    "stage"
                ),
                "carryforward_bullet_count": len(
                    (training_state_snapshot or {}).get("carryforward_bullets") or []
                ),
                "cumulative_log_entries": len(
                    (training_state_snapshot or {}).get("cumulative_learning_log") or []
                ),
            }
            if training_state_snapshot
            else {
                "curriculum_id": None,
                "stage": None,
                "carryforward_bullet_count": 0,
                "cumulative_log_entries": 0,
            }
        ),
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

    return _attach_context_ledger(out, ledger_attachment)


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
