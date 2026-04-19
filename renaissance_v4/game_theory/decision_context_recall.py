"""
Decision Context Recall v1 — per five-minute window context signature, memory lookup,
and optional bounded fusion bias. Deterministic; no LLM; no future leakage.

Causal partial ``pattern_context_v1``-shaped aggregates use history **through the prior bar**
plus **current** regime and volatility bucket only; fusion-derived counters exclude the
current bar until after fusion runs.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from renaissance_v4.core.fusion_engine import (
    MAX_CONFLICT_SCORE,
    MIN_FUSION_SCORE,
    signal_family_bucket,
)
from renaissance_v4.core.regime_classifier import (
    VOLATILITY_COMPRESSION_THRESHOLD,
    VOLATILITY_EXPANSION_THRESHOLD,
)
from renaissance_v4.game_theory.context_signature_memory import (
    ContextSignatureMemoryError,
    SignatureMatchParamsV1,
    canonical_signature_key,
    derive_context_signature_v1,
    find_matching_records_v1,
    read_context_memory_records,
    select_best_outcome_record,
)

DECISION_CONTEXT_RECALL_SCHEMA = "decision_context_recall_v1"
DECISION_CONTEXT_RECALL_SCHEMA_V2 = "decision_context_recall_v2"
DECISION_FUSION_BIAS_MAX_STEP = 0.01

# Bounded contribution multipliers (applied in fusion after base directional contribution).
DCR_V2_MULT_SOFT_MIN = 0.75
DCR_V2_MULT_SOFT_MAX = 1.08
DCR_V2_RULE_VOL_COMPRESS_THRESHOLD = 0.28
DCR_V2_RULE_RANGE_LIKE_THRESHOLD = 0.35
DCR_V2_RULE_TREND_EXPANSION_MR = (0.22, 0.12)  # trend_like_share, vol_expanding_share
DCR_V2_RULE_HIGH_CONFLICT_THRESHOLD = 0.20
DCR_V2_RULE_ALIGNED_TREND = (0.06, 0.18)  # aligned_directional_share, trend_like_share


def _dominant_counter(c: Counter[str]) -> str | None:
    if not c:
        return None
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def volatility_bucket_for_vol20(vol20: float) -> str:
    if vol20 <= VOLATILITY_COMPRESSION_THRESHOLD:
        return "compressed"
    if vol20 >= VOLATILITY_EXPANSION_THRESHOLD:
        return "expanding"
    return "neutral"


def build_causal_partial_pattern_context_v1(
    *,
    regime_bar_counts_before: Counter[str],
    volatility_bucket_counts_before: Counter[str],
    fusion_direction_counts_before: Counter[str],
    high_conflict_bars_before: int,
    aligned_directional_bars_before: int,
    countertrend_directional_bars_before: int,
    current_regime: str,
    vol20: float,
) -> dict[str, Any]:
    """
    Build a ``pattern_context_v1``-compatible dict from **causal** state only (no current fusion).

    * Regime / vol histograms include the **current** bar's regime and vol bucket.
    * Conflict / alignment counts are from **completed** bars only (before this bar's fusion).
    """
    tc: Counter[str] = Counter(regime_bar_counts_before)
    tc[current_regime] += 1

    vbc: Counter[str] = Counter(volatility_bucket_counts_before)
    vb = volatility_bucket_for_vol20(float(vol20))
    vbc[vb] += 1

    n = int(sum(tc.values()))
    if n < 1:
        raise ContextSignatureMemoryError("causal partial bars_processed must be >= 1")

    bp = float(n)
    rc = dict(tc)
    range_like = int(rc.get("range", 0)) + int(rc.get("volatility_compression", 0))
    trend_like = int(rc.get("trend_up", 0)) + int(rc.get("trend_down", 0))
    breakout_like = int(rc.get("volatility_expansion", 0))

    tags = {
        "range_like": round(range_like / bp, 6),
        "trend_like": round(trend_like / bp, 6),
        "breakout_like": round(breakout_like / bp, 6),
        "vol_compressed": round(float(vbc.get("compressed", 0)) / bp, 6),
        "vol_expanding": round(float(vbc.get("expanding", 0)) / bp, 6),
    }

    dom_r = _dominant_counter(tc) or current_regime
    dom_v = _dominant_counter(vbc) or vb

    return {
        "schema": "pattern_context_v1",
        "bars_processed": n,
        "regime_bar_counts": {k: int(tc[k]) for k in sorted(tc)},
        "fusion_direction_counts": {
            k: int(fusion_direction_counts_before[k]) for k in sorted(fusion_direction_counts_before)
        },
        "volatility_bucket_counts": {k: int(vbc[k]) for k in sorted(vbc)},
        "structure_tag_shares": tags,
        "dominant_regime": dom_r,
        "dominant_volatility_bucket": dom_v,
        "high_conflict_bars": int(high_conflict_bars_before),
        "aligned_directional_bars": int(aligned_directional_bars_before),
        "countertrend_directional_bars": int(countertrend_directional_bars_before),
        "signal_family_active_bar_counts": {},
    }


def derive_decision_context_signature_for_matching(
    partial_pattern_context_v1: dict[str, Any],
) -> dict[str, Any]:
    """Same canonical signature as run-level context memory (``context_signature_v1``)."""
    return derive_context_signature_v1(partial_pattern_context_v1)


def compute_decision_fusion_bias(
    matches: list[dict[str, Any]],
    *,
    base_fusion_min: float,
    base_fusion_max_conflict: float,
    apply_bias: bool,
) -> tuple[float, float, list[dict[str, Any]], list[str], str | None]:
    """
    Nudge fusion thresholds toward the best matching record's ``effective_apply`` (by expectancy),
    capped per key by :data:`DECISION_FUSION_BIAS_MAX_STEP`.

    Returns ``(fusion_min, max_conflict, bias_diff, reason_codes, best_record_id)``.
    """
    diff: list[dict[str, Any]] = []
    codes: list[str] = []
    if not apply_bias or not matches:
        return base_fusion_min, base_fusion_max_conflict, diff, codes, None

    best = select_best_outcome_record(matches)
    if best is None:
        codes.append("DCR_V1_BIAS_SKIPPED_NO_MATCH")
        return base_fusion_min, base_fusion_max_conflict, diff, codes, None

    best_id = str(best.get("record_id", ""))
    eff = dict(best.get("effective_apply") or {})
    out_min = base_fusion_min
    out_mc = base_fusion_max_conflict

    pm = eff.get("fusion_min_score")
    if pm is not None:
        try:
            pf = float(pm)
            step = min(abs(pf - base_fusion_min), DECISION_FUSION_BIAS_MAX_STEP)
            if step > 1e-15:
                if pf > base_fusion_min:
                    out_min = round(base_fusion_min + step, 6)
                else:
                    out_min = round(base_fusion_min - step, 6)
                diff.append(
                    {
                        "key": "fusion_min_score",
                        "old": base_fusion_min,
                        "new": out_min,
                        "from_record_id": best_id,
                        "reason": "DCR_V1_BOUNDED_STEP_TOWARD_MEMORY",
                    }
                )
                codes.append("DCR_V1_BIAS_FUSION_MIN")
        except (TypeError, ValueError):
            codes.append("DCR_V1_BIAS_SKIP_BAD_PRIOR_FUSION_MIN")

    pmc = eff.get("fusion_max_conflict_score")
    if pmc is not None:
        try:
            pfc = float(pmc)
            stepc = min(abs(pfc - base_fusion_max_conflict), DECISION_FUSION_BIAS_MAX_STEP)
            if stepc > 1e-15:
                if pfc > base_fusion_max_conflict:
                    out_mc = round(base_fusion_max_conflict + stepc, 6)
                else:
                    out_mc = round(base_fusion_max_conflict - stepc, 6)
                diff.append(
                    {
                        "key": "fusion_max_conflict_score",
                        "old": base_fusion_max_conflict,
                        "new": out_mc,
                        "from_record_id": best_id,
                        "reason": "DCR_V1_BOUNDED_STEP_TOWARD_MEMORY",
                    }
                )
                codes.append("DCR_V1_BIAS_FUSION_MAX_CONFLICT")
        except (TypeError, ValueError):
            codes.append("DCR_V1_BIAS_SKIP_BAD_PRIOR_CONFLICT")

    if not diff:
        codes.append("DCR_V1_MATCH_BUT_NO_APPLICABLE_FUSION_KEYS")

    return out_min, out_mc, diff, codes, best_id


def _clamp_soft_multiplier(x: float) -> float:
    return max(DCR_V2_MULT_SOFT_MIN, min(DCR_V2_MULT_SOFT_MAX, float(x)))


def compute_decision_signal_module_bias_v2(
    *,
    signature: dict[str, Any] | None,
    matches: list[dict[str, Any]],
    manifest_signal_modules: list[str],
    apply_signal_bias: bool,
) -> tuple[
    dict[str, float],
    bool,
    list[dict[str, Any]],
    list[str],
    list[dict[str, Any]],
    list[str],
    list[dict[str, Any]],
]:
    """
    Deterministic, bounded per-signal contribution multipliers from (1) current context signature
    numeric fields and (2) intersection of ``disabled_signal_modules`` across matching memory records.

    Returns
    -------
    per_signal_mult
        Catalog signal id → multiplier (1.0 = no change).
    signal_bias_applied
        True if any multiplier differs from 1.0.
    signal_bias_diff
        Audit rows for each change.
    suppressed_modules
        Modules with multiplier 0.0.
    favored_signal_families
        Entries for modules that received a boost (factor > 1.0 before soft clamp).
    signal_reason_codes
        Machine reason codes for signal/module layer.
    memory_justification_rows
        Which record ids justified intersection-based suppressions.
    """
    diff: list[dict[str, Any]] = []
    signal_reason_codes: list[str] = []
    mem_just: list[dict[str, Any]] = []
    favored: list[dict[str, Any]] = []
    suppressed: list[str] = []

    mods = sorted(set(manifest_signal_modules))
    mult: dict[str, float] = {m: 1.0 for m in mods}
    if not apply_signal_bias:
        return mult, False, [], [], [], [], []

    if not isinstance(signature, dict) or signature.get("schema") != "context_signature_v1":
        signal_reason_codes.append("DCR_V2_SKIPPED_INVALID_SIGNATURE")
        return mult, False, [], [], [], signal_reason_codes, []

    vc = float(signature.get("vol_compressed_share") or 0.0)
    rl = float(signature.get("range_like_share") or 0.0)
    tl = float(signature.get("trend_like_share") or 0.0)
    ve = float(signature.get("vol_expanding_share") or 0.0)
    hc = float(signature.get("high_conflict_share") or 0.0)
    al = float(signature.get("aligned_directional_share") or 0.0)

    def _mul_signal(sid: str, factor: float, reason: str) -> None:
        if sid not in mult:
            return
        old = mult[sid]
        mult[sid] = old * factor
        diff.append(
            {
                "signal_module": sid,
                "family": signal_family_bucket(sid),
                "old_multiplier": old,
                "new_multiplier": mult[sid],
                "factor_applied": factor,
                "reason_code": reason,
                "from_record_ids": [],
            }
        )
        signal_reason_codes.append(reason)

    if vc >= DCR_V2_RULE_VOL_COMPRESS_THRESHOLD and "breakout_expansion" in mult:
        _mul_signal("breakout_expansion", 0.88, "DCR_V2_RULE_VOL_COMPRESS_DEEMPH_BREAKOUT")
    if rl >= DCR_V2_RULE_RANGE_LIKE_THRESHOLD and "breakout_expansion" in mult:
        _mul_signal("breakout_expansion", 0.90, "DCR_V2_RULE_RANGE_LIKE_DEEMPH_BREAKOUT")
    tl_th, ve_th = DCR_V2_RULE_TREND_EXPANSION_MR
    if tl >= tl_th and ve >= ve_th and "mean_reversion_fade" in mult:
        _mul_signal("mean_reversion_fade", 0.88, "DCR_V2_RULE_TREND_EXPANSION_DEEMPH_MR")
    if hc >= DCR_V2_RULE_HIGH_CONFLICT_THRESHOLD and "breakout_expansion" in mult:
        _mul_signal("breakout_expansion", 0.85, "DCR_V2_RULE_HIGH_CONFLICT_DEEMPH_BREAKOUT")
    al_th, ttr_th = DCR_V2_RULE_ALIGNED_TREND
    if al >= al_th and tl >= ttr_th:
        for sid in ("trend_continuation", "pullback_continuation"):
            if sid in mult:
                old = mult[sid]
                mult[sid] = old * 1.04
                diff.append(
                    {
                        "signal_module": sid,
                        "family": signal_family_bucket(sid),
                        "old_multiplier": old,
                        "new_multiplier": mult[sid],
                        "factor_applied": 1.04,
                        "reason_code": "DCR_V2_RULE_ALIGNED_TREND_FAVOR_CONTINUATION",
                        "from_record_ids": [],
                    }
                )
                signal_reason_codes.append("DCR_V2_RULE_ALIGNED_TREND_FAVOR_CONTINUATION")
                favored.append(
                    {
                        "signal_family": signal_family_bucket(sid),
                        "signal_module": sid,
                        "factor": 1.04,
                        "reason_code": "DCR_V2_RULE_ALIGNED_TREND_FAVOR_CONTINUATION",
                    }
                )

    for sid in mult:
        if mult[sid] > 0:
            mult[sid] = _clamp_soft_multiplier(mult[sid])

    # Memory: intersection of disabled modules across all matching records (deterministic).
    if matches:
        dis_sets: list[set[str]] = []
        for rec in matches:
            eff = rec.get("effective_apply") if isinstance(rec.get("effective_apply"), dict) else {}
            d = eff.get("disabled_signal_modules")
            if isinstance(d, list) and d:
                dis_sets.append(set(str(x) for x in d))
        if dis_sets:
            inter = set.intersection(*dis_sets)
            for mod in sorted(inter):
                if mod not in mult:
                    continue
                remaining = [m for m in mods if m != mod and mult.get(m, 1.0) > 1e-12]
                if not remaining:
                    signal_reason_codes.append("DCR_V2_SKIP_SUPPRESS_ALL_PATHS")
                    continue
                old = mult[mod]
                mult[mod] = 0.0
                rids = sorted(str(rec.get("record_id", "")) for rec in matches)
                diff.append(
                    {
                        "signal_module": mod,
                        "family": signal_family_bucket(mod),
                        "old_multiplier": old,
                        "new_multiplier": 0.0,
                        "factor_applied": 0.0,
                        "reason_code": "DCR_V2_MEMORY_INTERSECTION_DISABLE",
                        "from_record_ids": rids,
                    }
                )
                suppressed.append(mod)
                signal_reason_codes.append("DCR_V2_MEMORY_INTERSECTION_DISABLE")
                mem_just.append(
                    {"signal_module": mod, "from_record_ids": rids, "reason": "intersection_disabled_modules"}
                )

    applied = any(abs(mult.get(m, 1.0) - 1.0) > 1e-12 for m in mods)
    return mult, applied, diff, suppressed, favored, signal_reason_codes, mem_just


def fusion_engine_supports_decision_recall(manifest: dict[str, Any], catalog: dict[str, Any]) -> bool:
    """True when manifest fusion resolves to :func:`fuse_signal_results` (threshold overrides supported)."""
    fid = manifest.get("fusion_module")
    meta = next((f for f in catalog.get("fusion_engines") or [] if f.get("id") == fid), None)
    if not meta:
        return False
    return str(meta.get("import_path")) == "renaissance_v4.core.fusion_engine" and str(
        meta.get("callable")
    ) == "fuse_signal_results"


def build_decision_recall_trace_v1(
    *,
    enabled: bool,
    attempted: bool,
    partial_pc: dict[str, Any] | None,
    signature: dict[str, Any] | None,
    signature_key: str | None,
    matches: list[dict[str, Any]],
    match_summaries: list[dict[str, Any]],
    best_id: str | None,
    best_summary: dict[str, Any] | None,
    bias_applied: bool,
    bias_diff: list[dict[str, Any]],
    reason_codes: list[str],
    signal_bias_v2_enabled: bool = False,
    decision_context_signal_bias_applied: bool = False,
    decision_context_signal_bias_diff: list[dict[str, Any]] | None = None,
    decision_context_signal_reason_codes: list[str] | None = None,
    decision_context_suppressed_modules: list[str] | None = None,
    decision_context_favored_signal_families: list[dict[str, Any]] | None = None,
    memory_justification_signal_bias: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Structured recall block for ``DecisionContract.reason_trace`` (v1 fusion + optional v2 signal/module)."""
    nmatch = len(matches)
    schema_id = DECISION_CONTEXT_RECALL_SCHEMA_V2 if signal_bias_v2_enabled else DECISION_CONTEXT_RECALL_SCHEMA
    ver = 2 if signal_bias_v2_enabled else 1
    out: dict[str, Any] = {
        "schema": schema_id,
        "version": ver,
        "decision_context_recall_enabled": enabled,
        "decision_context_recall_attempted": attempted,
        "decision_context_recall_match_count": nmatch,
        "decision_context_signature_current": signature,
        "decision_context_signature_key_current": signature_key,
        "causal_partial_pattern_context_v1": partial_pc,
        "context_memory_matches_for_decision": match_summaries,
        "context_memory_match_count_for_decision": nmatch,
        "best_context_match_id": best_id,
        "best_context_match_summary": best_summary,
        "decision_context_recall_bias_applied": bias_applied,
        "decision_context_recall_bias_diff": bias_diff,
        "decision_context_recall_reason_codes": reason_codes,
    }
    if signal_bias_v2_enabled:
        out["decision_context_signal_bias_applied"] = decision_context_signal_bias_applied
        out["decision_context_signal_bias_diff"] = list(decision_context_signal_bias_diff or [])
        out["decision_context_signal_reason_codes"] = list(decision_context_signal_reason_codes or [])
        out["decision_context_suppressed_modules"] = list(decision_context_suppressed_modules or [])
        out["decision_context_favored_signal_families"] = list(decision_context_favored_signal_families or [])
        out["memory_justification_signal_bias"] = list(memory_justification_signal_bias or [])
    return out


__all__ = [
    "DECISION_CONTEXT_RECALL_SCHEMA",
    "DECISION_CONTEXT_RECALL_SCHEMA_V2",
    "DECISION_FUSION_BIAS_MAX_STEP",
    "build_causal_partial_pattern_context_v1",
    "build_decision_recall_trace_v1",
    "compute_decision_fusion_bias",
    "compute_decision_signal_module_bias_v2",
    "derive_decision_context_signature_for_matching",
    "fusion_engine_supports_decision_recall",
    "read_context_memory_records",
    "find_matching_records_v1",
    "SignatureMatchParamsV1",
    "volatility_bucket_for_vol20",
]
