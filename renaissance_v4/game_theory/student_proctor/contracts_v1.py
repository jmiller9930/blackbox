"""
Student–Proctor contract freeze (Directive 01).

Versioned JSON-serializable artifacts:

* ``student_output_v1`` — shadow Student decision (no execution authority).
* ``reveal_v1`` — sanctioned join of Student output + Referee truth post-decision.
* ``student_learning_record_v1`` — persistent learning row for cross-run retrieval.

Graded unit v1: **closed trade** (see ``GRADED_UNIT_TYPE_V1``).

**§1.0 thesis + decision protocol:** shape-validated when present on ``student_output_v1``. For
``memory_context_llm_student`` (Ollama), **all** keys in ``THESIS_REQUIRED_FOR_LLM_PROFILE_V1`` are **mandatory**
(see ``validate_student_output_directional_thesis_required_for_llm_profile_v1``): context interpretation,
hypothesis (kind + text), evidence lists, resolution (confidence_band + context_fit), decision
(``student_action_v1``), and invalidation. Other profiles: same keys are optional; core required keys
unchanged for backward compatibility.
"""

from __future__ import annotations

import re
from typing import Any

CONTRACT_VERSION_STUDENT_PROCTOR_V1 = 1

# v1: one Student episode == one closed trade (OutcomeRecord / trade_id) unless architect changes.
GRADED_UNIT_TYPE_V1 = "closed_trade"

SCHEMA_STUDENT_OUTPUT_V1 = "student_output_v1"
SCHEMA_REVEAL_V1 = "reveal_v1"
SCHEMA_STUDENT_LEARNING_RECORD_V1 = "student_learning_record_v1"
# Pre-reveal-safe slice embedded in ``student_decision_packet_v1`` (Directive 06).
SCHEMA_STUDENT_RETRIEVAL_SLICE_V1 = "student_retrieval_slice_v1"
FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1 = "retrieved_student_experience_v1"

# Directive 03 — optional structured trading-context buckets (target shape from
# ``TRADING_CONTEXT_REFERENCE_V1``). Emitted only as a **versioned annex** checked here + pre-reveal.
TRADING_CONTEXT_BUCKET_KEYS_V1: frozenset[str] = frozenset(
    {"price_context", "structure_context", "indicator_context", "time_context"}
)
SCHEMA_STUDENT_CONTEXT_ANNEX_V1 = "student_context_annex_v1"
FIELD_STUDENT_CONTEXT_ANNEX_V1 = "student_context_annex_v1"
_STUDENT_CONTEXT_ANNEX_TOP_LEVEL_KEYS_V1: frozenset[str] = frozenset(
    {"schema", "contract_version", *TRADING_CONTEXT_BUCKET_KEYS_V1}
)

_DIRECTIONS = frozenset({"long", "short", "flat"})
# Optional §1.0 “directional thesis” extension on ``student_output_v1`` (parallel seam + learning store).
# When absent, validators do not require them; when present, types/shape are enforced (additive v1).
_THESIS_CONFIDENCE_BANDS_V1 = frozenset({"low", "medium", "high"})
_STUDENT_ACTION_A_V1 = frozenset({"enter_long", "enter_short", "no_trade"})
_THESIS_MAX_INDICATORS = 32
_THESIS_MAX_INDICATOR_LEN = 128
_THESIS_MAX_CONTEXT_FIT_LEN = 128
_THESIS_MAX_INVALIDATION_LEN = 4000
_THESIS_MAX_CONTEXT_INTERPRETATION_LEN = 2000
_THESIS_MIN_CONTEXT_INTERPRETATION_LEN = 16
_THESIS_MAX_HYPOTHESIS_TEXT_LEN = 512
_HYPOTHESIS_KINDS_V1 = frozenset({"trend_continuation", "mean_reversion", "no_clear_edge"})

# Precondition for **GT_DIRECTIVE_017** + Student decision protocol: LLM profile must seal a full
# structured reasoning chain or reject before persist (see ``emit_student_output_via_ollama_v1``).
# Explicit packet-grounded label when the Student sees no contrary evidence (LLM profile — not optional).
CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1 = "none_observed_from_packet_v1"

THESIS_REQUIRED_FOR_LLM_PROFILE_V1: tuple[str, ...] = (
    "context_interpretation_v1",
    "hypothesis_kind_v1",
    "hypothesis_text_v1",
    "supporting_indicators",
    "conflicting_indicators",
    "confidence_band",
    "context_fit",
    "invalidation_text",
    "student_action_v1",
)


def validate_student_output_directional_thesis_required_for_llm_profile_v1(doc: dict[str, Any]) -> list[str]:
    """
    ``memory_context_llm_student`` profile: all thesis fields must be present and shape-valid.

    Call **after** ``validate_student_output_v1`` succeeds on the same document.
    """
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("student_output_v1 must be a dict for thesis requirement check")
    for k in THESIS_REQUIRED_FOR_LLM_PROFILE_V1:
        if k not in doc or doc.get(k) is None:
            errs.append(f"directional_thesis_required_for_llm_profile: missing {k}")
            continue
        if k in ("supporting_indicators", "conflicting_indicators") and not isinstance(doc.get(k), list):
            errs.append(f"directional_thesis_required_for_llm_profile: {k} must be a list")
    if errs:
        return errs
    for k in ("supporting_indicators", "conflicting_indicators"):
        v = doc.get(k)
        if isinstance(v, list) and len(v) == 0:
            if k == "conflicting_indicators":
                errs.append(
                    "directional_thesis_required_for_llm_profile: conflicting_indicators must be non-empty "
                    f"(use {CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1!r} when no contrary evidence "
                    "is visible in the packet)"
                )
            else:
                errs.append(
                    f"directional_thesis_required_for_llm_profile: {k} must be non-empty "
                    "(name at least one concrete packet-derived label per side)"
                )
    if errs:
        return errs
    return _validate_student_output_optional_thesis_v1(doc)


# Keys that must **not** appear anywhere in a **pre-reveal** decision packet (leakage prevention v1).
# Conservative list — refine per architect if false positives appear in real packets.
# Exposed as PRE_REVEAL_FORBIDDEN_KEYS_V1 for operators / tests.
_FORBIDDEN_KEYS_PRE_REVEAL_V1: frozenset[str] = frozenset(
    {
        "pnl",
        "mfe",
        "mae",
        "exit_time",
        "exit_price",
        "exit_reason",
        "wins",
        "losses",
        "win_rate",
        "cumulative_pnl",
        "expectancy",
        "binary_scorecard",
        "validation_checksum",
        "referee_truth",
        "referee_flashcard",
        "reveal_v1",
        "outcome_record",
        "graded_reveal_payload",
    }
)

PRE_REVEAL_FORBIDDEN_KEYS_V1: frozenset[str] = _FORBIDDEN_KEYS_PRE_REVEAL_V1

_UUID_LOOSE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _err(msg: str) -> list[str]:
    return [msg]


def _is_uuid(s: str) -> bool:
    return bool(_UUID_LOOSE.match(s.strip()))


def _collect_string_keys(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Return (dotted_path, key) for every string key in dicts (recursive)."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            path = f"{prefix}.{k}" if prefix else k
            out.append((path, k))
            out.extend(_collect_string_keys(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_collect_string_keys(v, f"{prefix}[{i}]"))
    return out


def validate_student_context_annex_v1(doc: Any) -> list[str]:
    """
    Validate optional **versioned** ``student_context_annex_v1`` — structured buckets only,
    no forbidden outcome keys (recursive pre-reveal scan).
    """
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("student_context_annex_v1 must be a dict")
    extra = set(doc.keys()) - _STUDENT_CONTEXT_ANNEX_TOP_LEVEL_KEYS_V1
    if extra:
        errs.append(f"student_context_annex_v1 unknown keys: {sorted(extra)!r}")
    if doc.get("schema") != SCHEMA_STUDENT_CONTEXT_ANNEX_V1:
        errs.append(f"schema must be {SCHEMA_STUDENT_CONTEXT_ANNEX_V1!r}")
    if doc.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append(f"contract_version must be {CONTRACT_VERSION_STUDENT_PROCTOR_V1}")
    for bk in TRADING_CONTEXT_BUCKET_KEYS_V1:
        v = doc.get(bk)
        if v is None:
            continue
        if not isinstance(v, dict):
            errs.append(f"{bk} must be a dict or null/absent")
    errs.extend(validate_pre_reveal_bundle_v1(doc))
    return errs


def validate_pre_reveal_bundle_v1(bundle: Any) -> list[str]:
    """
    Ensure **pre-reveal** payloads contain none of the forbidden keys (recursive key-name check).

    **Boundary:** A legal pre-reveal packet describes **causal market / context / memory hooks**
    only. It must not embed Referee outcome fields for the pending graded unit or session summaries
    that substitute for flashcards.

    Returns empty list if valid; otherwise human-readable violation messages.
    """
    if not isinstance(bundle, dict):
        return _err("pre_reveal bundle must be a dict")
    forbidden_lower = {x.lower() for x in _FORBIDDEN_KEYS_PRE_REVEAL_V1}
    msgs: list[str] = []
    for path, key in _collect_string_keys(bundle):
        if key.lower() in forbidden_lower:
            msgs.append(f"forbidden pre_reveal key {key!r} at {path}")
    return msgs


def _validate_student_output_optional_thesis_v1(doc: dict[str, Any]) -> list[str]:
    """Validate optional §1.0 thesis + decision-protocol fields when present on ``student_output_v1``."""
    errs: list[str] = []
    ci = doc.get("context_interpretation_v1")
    if ci is not None:
        if not isinstance(ci, str) or not ci.strip():
            errs.append("context_interpretation_v1 must be a non-empty string when present")
        elif len(ci.strip()) < _THESIS_MIN_CONTEXT_INTERPRETATION_LEN:
            errs.append(
                f"context_interpretation_v1 must be at least {_THESIS_MIN_CONTEXT_INTERPRETATION_LEN} "
                "characters (summarize OHLCV / regime / fusion from the packet only)"
            )
        elif len(ci) > _THESIS_MAX_CONTEXT_INTERPRETATION_LEN:
            errs.append(
                f"context_interpretation_v1 exceeds max length {_THESIS_MAX_CONTEXT_INTERPRETATION_LEN}"
            )

    hk = doc.get("hypothesis_kind_v1")
    if hk is not None:
        if not isinstance(hk, str) or not hk.strip():
            errs.append("hypothesis_kind_v1 must be a non-empty string when present")
        elif hk.strip().lower() not in _HYPOTHESIS_KINDS_V1:
            errs.append(
                "hypothesis_kind_v1 must be one of "
                + ", ".join(sorted(_HYPOTHESIS_KINDS_V1))
            )

    ht = doc.get("hypothesis_text_v1")
    if ht is not None:
        if not isinstance(ht, str) or not ht.strip():
            errs.append("hypothesis_text_v1 must be a non-empty string when present")
        elif len(ht) > _THESIS_MAX_HYPOTHESIS_TEXT_LEN:
            errs.append(f"hypothesis_text_v1 exceeds max length {_THESIS_MAX_HYPOTHESIS_TEXT_LEN}")

    cb = doc.get("confidence_band")
    if cb is not None:
        if not isinstance(cb, str) or not cb.strip():
            errs.append("confidence_band must be a non-empty string when present")
        elif cb.strip().lower() not in _THESIS_CONFIDENCE_BANDS_V1:
            errs.append("confidence_band must be low|medium|high when present")

    def _ind_list(name: str) -> None:
        v = doc.get(name)
        if v is None:
            return
        if not isinstance(v, list):
            errs.append(f"{name} must be a list[str] when present")
            return
        if len(v) > _THESIS_MAX_INDICATORS:
            errs.append(f"{name} must have at most {_THESIS_MAX_INDICATORS} entries")
            return
        for i, x in enumerate(v):
            if not isinstance(x, str):
                errs.append(f"{name}[{i}] must be string")
            elif len(x.strip()) > _THESIS_MAX_INDICATOR_LEN:
                errs.append(f"{name}[{i}] exceeds max length {_THESIS_MAX_INDICATOR_LEN}")

    _ind_list("supporting_indicators")
    _ind_list("conflicting_indicators")

    cf = doc.get("context_fit")
    if cf is not None:
        if not isinstance(cf, str) or not cf.strip() or len(cf) > _THESIS_MAX_CONTEXT_FIT_LEN:
            errs.append(
                f"context_fit must be a non-empty string of length <= {_THESIS_MAX_CONTEXT_FIT_LEN} when present"
            )

    inv = doc.get("invalidation_text")
    if inv is not None:
        if not isinstance(inv, str) or not inv.strip() or len(inv) > _THESIS_MAX_INVALIDATION_LEN:
            errs.append(
                "invalidation_text must be a non-empty string of length "
                f"<= {_THESIS_MAX_INVALIDATION_LEN} when present"
            )

    sa = doc.get("student_action_v1")
    if sa is not None:
        if not isinstance(sa, str) or not sa.strip():
            errs.append("student_action_v1 must be a non-empty string when present")
        else:
            sa_l = sa.strip().lower()
            if sa_l not in _STUDENT_ACTION_A_V1:
                errs.append("student_action_v1 must be enter_long|enter_short|no_trade when present")
            else:
                act = doc.get("act")
                d = doc.get("direction")
                d_l = d.lower().strip() if isinstance(d, str) and d.strip() else None
                if sa_l == "no_trade" and act is True:
                    errs.append("student_action_v1 no_trade requires act false")
                if sa_l == "enter_long" and (act is not True or d_l != "long"):
                    errs.append("student_action_v1 enter_long requires act true and direction long")
                if sa_l == "enter_short" and (act is not True or d_l != "short"):
                    errs.append("student_action_v1 enter_short requires act true and direction short")
    return errs


def validate_student_output_v1(doc: Any) -> list[str]:
    """Validate ``student_output_v1`` — shadow Student decision."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("student_output_v1 must be a dict")
    if doc.get("schema") != SCHEMA_STUDENT_OUTPUT_V1:
        errs.append(f"schema must be {SCHEMA_STUDENT_OUTPUT_V1!r}")
    if doc.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append(f"contract_version must be {CONTRACT_VERSION_STUDENT_PROCTOR_V1}")
    gut = doc.get("graded_unit_type")
    if gut != GRADED_UNIT_TYPE_V1:
        errs.append(f"graded_unit_type must be {GRADED_UNIT_TYPE_V1!r} for v1")
    guid = doc.get("graded_unit_id")
    if not isinstance(guid, str) or not guid.strip():
        errs.append("graded_unit_id must be a non-empty string (trade_id for closed_trade)")
    dam = doc.get("decision_at_ms")
    if not isinstance(dam, int):
        errs.append("decision_at_ms must be int (Unix ms)")
    if not isinstance(doc.get("act"), bool):
        errs.append("act must be bool")
    d = doc.get("direction")
    if d is not None and (not isinstance(d, str) or d.lower() not in _DIRECTIONS):
        errs.append("direction must be one of long|short|flat or null")
    pr = doc.get("pattern_recipe_ids")
    if not isinstance(pr, list) or not all(isinstance(x, str) for x in pr):
        errs.append("pattern_recipe_ids must be a list[str]")
    conf = doc.get("confidence_01")
    if not isinstance(conf, (int, float)) or not 0.0 <= float(conf) <= 1.0:
        errs.append("confidence_01 must be a number in [0, 1]")
    rt = doc.get("reasoning_text")
    if rt is not None and not isinstance(rt, str):
        errs.append("reasoning_text must be str or null")
    sdr = doc.get("student_decision_ref")
    if not isinstance(sdr, str) or not _is_uuid(sdr):
        errs.append("student_decision_ref must be a UUID string")

    # student_output_v1 must never smuggle flashcard fields (forbidden keys anywhere on doc)
    pre = validate_pre_reveal_bundle_v1(doc)
    errs.extend(pre)
    if errs:
        return errs
    # Optional thesis extension (§1.0) — only when core document is otherwise valid
    errs.extend(_validate_student_output_optional_thesis_v1(doc))
    return errs


def validate_reveal_v1(doc: Any) -> list[str]:
    """Validate ``reveal_v1`` — post-decision join (Student + Referee truth)."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("reveal_v1 must be a dict")
    if doc.get("schema") != SCHEMA_REVEAL_V1:
        errs.append(f"schema must be {SCHEMA_REVEAL_V1!r}")
    if doc.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append(f"contract_version must be {CONTRACT_VERSION_STUDENT_PROCTOR_V1}")
    if not isinstance(doc.get("graded_unit_id"), str) or not str(doc.get("graded_unit_id")).strip():
        errs.append("graded_unit_id required")
    so = doc.get("student_output")
    if not isinstance(so, dict):
        errs.append("student_output must be embedded dict")
    else:
        errs.extend(validate_student_output_v1(so))
    rt = doc.get("referee_truth_v1")
    if not isinstance(rt, dict):
        errs.append("referee_truth_v1 must be a dict")
    else:
        for k in ("trade_id", "symbol", "pnl"):
            if k not in rt:
                errs.append(f"referee_truth_v1 must contain {k!r}")
    comp = doc.get("comparison_v1")
    if not isinstance(comp, dict):
        errs.append("comparison_v1 must be a dict")
    if not isinstance(doc.get("revealed_at_utc"), str) or not doc.get("revealed_at_utc"):
        errs.append("revealed_at_utc must be non-empty ISO8601 string")
    # Reveal **may** contain pnl etc. — do not run pre_reveal on full reveal doc
    return errs


def validate_student_learning_record_v1(doc: Any) -> list[str]:
    """Validate ``student_learning_record_v1`` for append-only store."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("student_learning_record_v1 must be a dict")
    if doc.get("schema") != SCHEMA_STUDENT_LEARNING_RECORD_V1:
        errs.append(f"schema must be {SCHEMA_STUDENT_LEARNING_RECORD_V1!r}")
    if doc.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append(f"contract_version must be {CONTRACT_VERSION_STUDENT_PROCTOR_V1}")
    for k in ("record_id", "created_utc", "run_id", "graded_unit_id"):
        v = doc.get(k)
        if not isinstance(v, str) or not str(v).strip():
            errs.append(f"{k} must be non-empty string")
    if not isinstance(doc.get("context_signature_v1"), dict):
        errs.append("context_signature_v1 must be a dict")
    if not isinstance(doc.get("student_output"), dict):
        errs.append("student_output must be a dict")
    else:
        errs.extend(validate_student_output_v1(doc["student_output"]))
    if not isinstance(doc.get("referee_outcome_subset"), dict):
        errs.append("referee_outcome_subset must be a dict")
    if not isinstance(doc.get("alignment_flags_v1"), dict):
        errs.append("alignment_flags_v1 must be a dict")
    ctf = doc.get("candle_timeframe_minutes")
    if ctf is not None:
        try:
            ci = int(ctf)
        except (TypeError, ValueError):
            errs.append("candle_timeframe_minutes must be int when present")
        else:
            from renaissance_v4.game_theory.candle_timeframe_runtime import (
                is_allowed_candle_timeframe_minutes_v1,
            )

            if not is_allowed_candle_timeframe_minutes_v1(ci):
                errs.append("candle_timeframe_minutes must be one of 5, 15, 60, 240 when present")
    lg = doc.get("learning_governance_v1")
    if lg is not None:
        if not isinstance(lg, dict):
            errs.append("learning_governance_v1 must be a dict when present")
        else:
            if lg.get("schema") != "learning_governance_v1":
                errs.append("learning_governance_v1.schema must be 'learning_governance_v1'")
            if str(lg.get("decision") or "") not in ("promote", "hold", "reject"):
                errs.append("learning_governance_v1.decision must be promote|hold|reject")
            if not isinstance(lg.get("reason_codes"), list):
                errs.append("learning_governance_v1.reason_codes must be a list")
            if not isinstance(lg.get("source_job_id"), str) or not str(lg.get("source_job_id")).strip():
                errs.append("learning_governance_v1.source_job_id required")
            if lg.get("fingerprint") is not None and not isinstance(lg.get("fingerprint"), str):
                errs.append("learning_governance_v1.fingerprint must be a string or null")
            if not isinstance(lg.get("timestamp_utc"), str) or not str(lg.get("timestamp_utc")).strip():
                errs.append("learning_governance_v1.timestamp_utc required")
    return errs


def legal_example_student_output_v1() -> dict[str, Any]:
    """Minimal valid ``student_output_v1`` for tests and docs."""
    return {
        "schema": SCHEMA_STUDENT_OUTPUT_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_type": GRADED_UNIT_TYPE_V1,
        "graded_unit_id": "trade_example_001",
        "decision_at_ms": 1_700_000_000_000,
        "act": True,
        "direction": "long",
        "pattern_recipe_ids": ["trend_continuation"],
        "confidence_01": 0.65,
        "reasoning_text": "Hypothesis: continuation in line with cookbook.",
        "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
    }


def legal_example_student_output_with_thesis_v1() -> dict[str, Any]:
    """Valid ``student_output_v1`` including full §1.0 thesis + decision protocol (LONG)."""
    base = legal_example_student_output_v1()
    base["context_interpretation_v1"] = (
        "Price above rising EMA20 on 5m; fusion directional long; RSI not extreme; regime suggests "
        "trend continuation risk acceptable."
    )
    base["hypothesis_kind_v1"] = "trend_continuation"
    base["hypothesis_text_v1"] = "Trend continuation likely while structure holds above last swing low."
    base["confidence_band"] = "medium"
    base["supporting_indicators"] = ["rsi_14", "ema_20_slope"]
    base["conflicting_indicators"] = ["atr_elevated"]
    base["context_fit"] = "trend"
    base["invalidation_text"] = "Close back below prior swing low."
    base["student_action_v1"] = "enter_long"
    return base


def legal_example_student_output_protocol_short_v1() -> dict[str, Any]:
    """Example valid protocol output — SHORT (same schema as LONG with flipped action)."""
    base = legal_example_student_output_v1()
    base["act"] = True
    base["direction"] = "short"
    base["context_interpretation_v1"] = (
        "Price rolled below VWAP after failed reclaim; fusion skewed short; momentum fading on "
        "higher timeframe resistance test."
    )
    base["hypothesis_kind_v1"] = "mean_reversion"
    base["hypothesis_text_v1"] = "Mean reversion likely from overbought stretch into supply."
    base["confidence_band"] = "low"
    base["supporting_indicators"] = ["rsi_14_overbought", "vwap_reject"]
    base["conflicting_indicators"] = ["low_atr_chop"]
    base["context_fit"] = "reversal"
    base["invalidation_text"] = "Acceptance back above VWAP with expanding range invalidates short."
    base["student_action_v1"] = "enter_short"
    base["reasoning_text"] = "Protocol test SHORT — structured only."
    return base


def legal_example_student_output_protocol_no_trade_v1() -> dict[str, Any]:
    """Example valid protocol output — NO_TRADE with full reasoning (no guessing)."""
    base = legal_example_student_output_v1()
    base["act"] = False
    base["direction"] = "flat"
    base["context_interpretation_v1"] = (
        "Mixed signals: fusion flat, ADX low, price mid-range; no clear edge vs noise per packet."
    )
    base["hypothesis_kind_v1"] = "no_clear_edge"
    base["hypothesis_text_v1"] = "No clear edge — refuse to force a directional thesis."
    base["confidence_band"] = "low"
    base["supporting_indicators"] = ["range_mid"]
    base["conflicting_indicators"] = ["fusion_flat", "low_adx"]
    base["context_fit"] = "chop"
    base["invalidation_text"] = "N/A for no_trade: would trade only after fusion + structure align."
    base["student_action_v1"] = "no_trade"
    base["reasoning_text"] = "NO_TRADE per protocol — lists populated, not narrative-only."
    return base


def legal_example_student_context_annex_v1() -> dict[str, Any]:
    """Minimal valid ``student_context_annex_v1`` for tests (causal labels only)."""
    return {
        "schema": SCHEMA_STUDENT_CONTEXT_ANNEX_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "price_context": {"window_label": "inside_prior_range", "last_print_vs_mid": "near_mid"},
        "structure_context": {"market_state": "trend_up", "pullback_state": "none"},
        "indicator_context": {"vwap_relation": "above_vwap", "momentum_state": "neutral"},
        "time_context": {"session_segment": "regular", "minutes_to_session_end": 120},
    }


def illegal_pre_reveal_bundle_example_v1() -> dict[str, Any]:
    """Bundle that must fail ``validate_pre_reveal_bundle_v1`` (leaked outcome key)."""
    return {
        "schema": "pre_reveal_decision_packet_v1",
        "graded_unit_id": "trade_x",
        "bars_context": {"close": 101.2},
        "pnl": 12.34,
    }


def legal_example_reveal_v1() -> dict[str, Any]:
    """Minimal valid ``reveal_v1`` (Student snapshot + Referee truth)."""
    so = legal_example_student_output_v1()
    return {
        "schema": SCHEMA_REVEAL_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_id": so["graded_unit_id"],
        "student_output": so,
        "referee_truth_v1": {
            "trade_id": so["graded_unit_id"],
            "symbol": "SOLUSDT",
            "direction": "long",
            "pnl": 4.2,
            "mfe": 8.0,
            "mae": 2.1,
            "exit_reason": "take_profit",
        },
        "comparison_v1": {"direction_match": True, "quality_note": "stub"},
        "revealed_at_utc": "2026-04-20T16:00:00Z",
    }


def legal_example_student_learning_record_v1() -> dict[str, Any]:
    """Minimal valid ``student_learning_record_v1``."""
    so = legal_example_student_output_v1()
    return {
        "schema": SCHEMA_STUDENT_LEARNING_RECORD_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "record_id": "660e8400-e29b-41d4-a716-446655440001",
        "created_utc": "2026-04-20T16:00:00Z",
        "run_id": "run_example_abc",
        "graded_unit_id": so["graded_unit_id"],
        "candle_timeframe_minutes": 5,
        "manifest_sha256": None,
        "strategy_id": "renaissance_baseline_v1_stack",
        "context_signature_v1": {"schema": "context_signature_v1", "signature_key": "demo"},
        "student_output": so,
        "referee_outcome_subset": {"pnl": 4.2, "exit_reason": "take_profit"},
        "alignment_flags_v1": {"direction_aligned": True},
    }
