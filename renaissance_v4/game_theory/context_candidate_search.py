"""
Context-Conditioned Candidate Search v1 — deterministic, bounded bundle-parameter search.

Generates a small set of memory-bundle ``apply`` candidates from a context signature,
replays each against a control apply block, ranks outcomes, and emits a machine-readable
proof package. No LLM, no randomness, no keys outside :data:`memory_bundle.BUNDLE_APPLY_WHITELIST`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from renaissance_v4.core.fusion_engine import (
    MAX_CONFLICT_SCORE,
    MIN_FUSION_SCORE,
    OVERLAP_PENALTY_PER_EXTRA_SIGNAL,
)
from renaissance_v4.game_theory.context_signature_memory import (
    canonical_signature_key,
    derive_context_signature_v1,
)
from renaissance_v4.game_theory.memory_bundle import (
    MEMORY_BUNDLE_SCHEMA,
    BUNDLE_APPLY_WHITELIST,
    apply_memory_bundle_to_manifest,
)
from renaissance_v4.game_theory.pattern_outcome_quality_v1 import (
    compute_pattern_outcome_quality_v1,
    diff_outcome_quality_v1,
)
from renaissance_v4.manifest.validate import load_manifest_file, validate_manifest_against_catalog

CONTEXT_CANDIDATE_SEARCH_PROOF_SCHEMA = "context_candidate_search_proof_v1"
CONTEXT_CCS_V1_MAX_CANDIDATES = 8
CONTEXT_CCS_V1_MIN_CANDIDATES = 3

# Defaults when key absent from control (align with signal / fusion modules).
_DEFAULT_NUMERIC_BASELINE: dict[str, float] = {
    "fusion_min_score": float(MIN_FUSION_SCORE),
    "fusion_max_conflict_score": float(MAX_CONFLICT_SCORE),
    "fusion_overlap_penalty_per_extra_signal": float(OVERLAP_PENALTY_PER_EXTRA_SIGNAL),
    "mean_reversion_fade_min_confidence": 0.53,
    "mean_reversion_fade_stretch_threshold": 0.003,
    "trend_continuation_min_confidence": 0.55,
    "trend_continuation_min_regime_fit": 0.5,
    "pullback_continuation_min_confidence": 0.52,
    "pullback_continuation_volatility_threshold": 0.02,
    "breakout_expansion_min_confidence": 0.56,
}


def classify_context_family_v1(context_signature_v1: dict[str, Any] | None) -> str:
    """Deterministic coarse label from ``context_signature_v1`` (same spirit as DCR v2)."""
    if not isinstance(context_signature_v1, dict):
        return "unknown"
    if context_signature_v1.get("schema") != "context_signature_v1":
        return "unknown"
    vc = float(context_signature_v1.get("vol_compressed_share") or 0.0)
    rl = float(context_signature_v1.get("range_like_share") or 0.0)
    tl = float(context_signature_v1.get("trend_like_share") or 0.0)
    ve = float(context_signature_v1.get("vol_expanding_share") or 0.0)
    hc = float(context_signature_v1.get("high_conflict_share") or 0.0)
    if hc >= 0.20:
        return "high_conflict"
    if vc >= 0.28 or rl >= 0.35:
        return "compressed_range"
    if tl >= 0.22 and ve >= 0.12:
        return "trend_expansion"
    return "neutral"


def _eff_base(key: str, control: dict[str, Any]) -> float:
    if key in control and control[key] is not None:
        return float(control[key])
    return float(_DEFAULT_NUMERIC_BASELINE[key])


def _round6(x: float) -> float:
    return round(float(x), 6)


def _clamp_key(key: str, val: float) -> float:
    """Clamp to same bounds as memory_bundle validation."""
    f = float(val)
    if key == "mean_reversion_fade_stretch_threshold":
        return max(0.000001, min(0.2, f))
    if key in ("atr_stop_mult", "atr_target_mult"):
        return max(0.5, min(6.0, f))
    if key in (
        "fusion_min_score",
        "fusion_max_conflict_score",
        "fusion_overlap_penalty_per_extra_signal",
        "mean_reversion_fade_min_confidence",
        "trend_continuation_min_confidence",
        "trend_continuation_min_regime_fit",
        "pullback_continuation_min_confidence",
        "pullback_continuation_volatility_threshold",
        "breakout_expansion_min_confidence",
    ):
        return max(0.0, min(1.0, f))
    return max(0.0, min(1.0, f))


def _effective_apply(control_apply: dict[str, Any], patches: dict[str, Any]) -> dict[str, Any]:
    """Merge patches onto control; only whitelisted keys; ``disabled_signal_modules`` replaces if set in patches."""
    out = {k: v for k, v in control_apply.items() if k in BUNDLE_APPLY_WHITELIST}
    for k, v in patches.items():
        if k not in BUNDLE_APPLY_WHITELIST:
            continue
        if k == "disabled_signal_modules" and isinstance(v, list):
            out[k] = sorted({str(x) for x in v})
        else:
            out[k] = v
    return out


def _canonical_apply_key(apply: dict[str, Any]) -> str:
    """JSON for deduplication (sorted keys)."""
    filtered = {k: apply[k] for k in sorted(apply.keys()) if k in BUNDLE_APPLY_WHITELIST}
    return json.dumps(filtered, sort_keys=True, separators=(",", ":"))


def apply_diff_audit(control: dict[str, Any], effective: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-key old/new for proof (control baseline vs effective candidate)."""
    rows: list[dict[str, Any]] = []
    keys = sorted(set(control.keys()) | set(effective.keys()))
    for k in keys:
        if k not in BUNDLE_APPLY_WHITELIST:
            continue
        old = control.get(k)
        new = effective.get(k)
        if old != new:
            rows.append({"key": k, "old": old, "new": new})
    return rows


def generate_candidates_v1(
    *,
    control_apply: dict[str, Any] | None,
    context_signature_v1: dict[str, Any] | None,
    memory_prior_apply: dict[str, Any] | None,
    manifest_signal_modules: list[str],
) -> list[dict[str, Any]]:
    """
    Build 3–8 deterministic candidate specs. Each item:

    * ``candidate_id`` — stable id
    * ``parent_reference_id`` — parent label (caller fills)
    * ``context_family`` — classification used
    * ``generation_reason_codes`` — explicit codes
    * ``apply_effective`` — full whitelisted apply dict to merge via memory bundle path
    * ``apply_patches`` — raw patches before merge (for audit)
    """
    control = {k: v for k, v in (control_apply or {}).items() if k in BUNDLE_APPLY_WHITELIST}
    if isinstance(control.get("disabled_signal_modules"), list):
        control["disabled_signal_modules"] = sorted({str(x) for x in control["disabled_signal_modules"]})

    family = classify_context_family_v1(context_signature_v1)
    if family == "unknown":
        family = "neutral"
    raw_specs: list[tuple[str, dict[str, Any], list[str]]] = []

    def push(suffix: str, patches: dict[str, Any], codes: list[str]) -> None:
        eff = _effective_apply(control, patches)
        # Enforce at least one signal module remains if disabling
        if "disabled_signal_modules" in eff:
            dis = set(eff["disabled_signal_modules"])
            active = [m for m in manifest_signal_modules if m not in dis]
            if len(active) < 1:
                return
        raw_specs.append((suffix, patches, codes))

    fm = _eff_base("fusion_min_score", control)
    fmc = _eff_base("fusion_max_conflict_score", control)
    fop = _eff_base("fusion_overlap_penalty_per_extra_signal", control)

    if family == "compressed_range":
        push(
            "relax_fusion_min",
            {"fusion_min_score": _clamp_key("fusion_min_score", fm - 0.01)},
            ["CCS_V1_FAMILY_COMPRESSED_RANGE", "CCS_V1_RELAX_FUSION_MIN"],
        )
        mrm = _eff_base("mean_reversion_fade_min_confidence", control)
        push(
            "favor_mr_conf",
            {"mean_reversion_fade_min_confidence": _clamp_key("mean_reversion_fade_min_confidence", mrm - 0.03)},
            ["CCS_V1_FAMILY_COMPRESSED_RANGE", "CCS_V1_FAVOR_MR_LOWER_CONF_FLOOR"],
        )
        bcm = _eff_base("breakout_expansion_min_confidence", control)
        push(
            "tighten_breakout_conf",
            {"breakout_expansion_min_confidence": _clamp_key("breakout_expansion_min_confidence", bcm + 0.05)},
            ["CCS_V1_FAMILY_COMPRESSED_RANGE", "CCS_V1_TIGHTEN_BREAKOUT_CONF"],
        )
        push(
            "raise_overlap_penalty",
            {"fusion_overlap_penalty_per_extra_signal": _clamp_key("fusion_overlap_penalty_per_extra_signal", fop + 0.02)},
            ["CCS_V1_FAMILY_COMPRESSED_RANGE", "CCS_V1_RAISE_OVERLAP_PENALTY"],
        )
    elif family == "trend_expansion":
        mrm = _eff_base("mean_reversion_fade_min_confidence", control)
        push(
            "disfavor_mr_conf",
            {"mean_reversion_fade_min_confidence": _clamp_key("mean_reversion_fade_min_confidence", mrm + 0.05)},
            ["CCS_V1_FAMILY_TREND_EXPANSION", "CCS_V1_DISFAVOR_MR_HIGHER_CONF_FLOOR"],
        )
        tcm = _eff_base("trend_continuation_min_confidence", control)
        push(
            "favor_trend_conf",
            {"trend_continuation_min_confidence": _clamp_key("trend_continuation_min_confidence", tcm - 0.02)},
            ["CCS_V1_FAMILY_TREND_EXPANSION", "CCS_V1_FAVOR_TREND_LOWER_CONF_FLOOR"],
        )
        push(
            "tighten_conflict_gate",
            {"fusion_max_conflict_score": _clamp_key("fusion_max_conflict_score", fmc - 0.01)},
            ["CCS_V1_FAMILY_TREND_EXPANSION", "CCS_V1_TIGHTEN_FUSION_MAX_CONFLICT"],
        )
        pcm = _eff_base("pullback_continuation_min_confidence", control)
        push(
            "favor_pullback_conf",
            {"pullback_continuation_min_confidence": _clamp_key("pullback_continuation_min_confidence", pcm - 0.02)},
            ["CCS_V1_FAMILY_TREND_EXPANSION", "CCS_V1_FAVOR_PULLBACK_LOWER_CONF_FLOOR"],
        )
    elif family == "high_conflict":
        push(
            "tighten_conflict_gate_hc",
            {"fusion_max_conflict_score": _clamp_key("fusion_max_conflict_score", fmc - 0.02)},
            ["CCS_V1_FAMILY_HIGH_CONFLICT", "CCS_V1_TIGHTEN_FUSION_MAX_CONFLICT"],
        )
        push(
            "raise_overlap_penalty_hc",
            {"fusion_overlap_penalty_per_extra_signal": _clamp_key("fusion_overlap_penalty_per_extra_signal", fop + 0.03)},
            ["CCS_V1_FAMILY_HIGH_CONFLICT", "CCS_V1_RAISE_OVERLAP_PENALTY"],
        )
        push(
            "tighten_fusion_min_hc",
            {"fusion_min_score": _clamp_key("fusion_min_score", fm + 0.01)},
            ["CCS_V1_FAMILY_HIGH_CONFLICT", "CCS_V1_TIGHTEN_FUSION_MIN"],
        )
    else:
        push(
            "neutral_relax_fusion",
            {"fusion_min_score": _clamp_key("fusion_min_score", fm - 0.01)},
            ["CCS_V1_FAMILY_NEUTRAL", "CCS_V1_RELAX_FUSION_MIN"],
        )
        push(
            "neutral_tighten_fusion",
            {"fusion_min_score": _clamp_key("fusion_min_score", fm + 0.01)},
            ["CCS_V1_FAMILY_NEUTRAL", "CCS_V1_TIGHTEN_FUSION_MIN"],
        )
        push(
            "neutral_conflict_mid",
            {"fusion_max_conflict_score": _clamp_key("fusion_max_conflict_score", fmc - 0.01)},
            ["CCS_V1_FAMILY_NEUTRAL", "CCS_V1_TIGHTEN_FUSION_MAX_CONFLICT"],
        )

    # Memory prior: bounded nudges toward stored fusion keys (deterministic).
    prior = {k: v for k, v in (memory_prior_apply or {}).items() if k in BUNDLE_APPLY_WHITELIST}
    if prior:
        if prior.get("fusion_min_score") is not None:
            pv = float(prior["fusion_min_score"])
            push(
                "mem_prior_fusion_min_blend",
                {"fusion_min_score": _clamp_key("fusion_min_score", (fm + pv) * 0.5)},
                ["CCS_V1_MEMORY_PRIOR_BLEND", "CCS_V1_MEM_BLEND_FUSION_MIN"],
            )
            push(
                "mem_prior_fusion_min_step_toward",
                {"fusion_min_score": _clamp_key("fusion_min_score", fm + min(0.01, abs(pv - fm) * 0.5))},
                ["CCS_V1_MEMORY_PRIOR_STEP", "CCS_V1_MEM_STEP_TOWARD_PRIOR_FUSION_MIN"],
            )
        if prior.get("fusion_max_conflict_score") is not None:
            pv = float(prior["fusion_max_conflict_score"])
            push(
                "mem_prior_fusion_mc_blend",
                {"fusion_max_conflict_score": _clamp_key("fusion_max_conflict_score", (fmc + pv) * 0.5)},
                ["CCS_V1_MEMORY_PRIOR_BLEND", "CCS_V1_MEM_BLEND_FUSION_MAX_CONFLICT"],
            )

    # Deduplicate by effective apply snapshot
    seen: set[str] = set()
    deduped: list[tuple[str, dict[str, Any], list[str]]] = []
    for suffix, patches, codes in raw_specs:
        eff = _effective_apply(control, patches)
        key = _canonical_apply_key(eff)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((suffix, patches, codes))

    # Pad to minimum count with neutral fusion steps (if needed)
    pad_i = 0
    while len(deduped) < CONTEXT_CCS_V1_MIN_CANDIDATES:
        delta = 0.01 * (pad_i + 1)
        fm0 = _eff_base("fusion_min_score", control)
        patches = {"fusion_min_score": _clamp_key("fusion_min_score", fm0 + ((-1) ** pad_i) * delta)}
        eff = _effective_apply(control, patches)
        key = _canonical_apply_key(eff)
        if key not in seen:
            seen.add(key)
            deduped.append((f"pad_{pad_i}", patches, ["CCS_V1_PAD_MIN_COUNT", "CCS_V1_FUSION_MIN_SWEEP"]))
        pad_i += 1
        if pad_i > 20:
            break

    out: list[dict[str, Any]] = []
    for i, (suffix, patches, codes) in enumerate(deduped[:CONTEXT_CCS_V1_MAX_CANDIDATES]):
        eff = _effective_apply(control, patches)
        cid = f"ccs_v1_{i + 1:03d}_{suffix}"
        out.append(
            {
                "candidate_id": cid,
                "parent_reference_id": "control_apply",
                "context_family": family,
                "generation_reason_codes": codes + [f"CCS_V1_CONTEXT_FAMILY_{family.upper()}"],
                "apply_patches": patches,
                "apply_effective": eff,
            }
        )
    return out


def extract_comparison_metrics(replay_result: dict[str, Any]) -> dict[str, Any]:
    """Normalize replay output for ranking / proof (includes pattern outcome quality from outcomes)."""
    sm = replay_result.get("summary") if isinstance(replay_result.get("summary"), dict) else {}
    sanity = replay_result.get("sanity") if isinstance(replay_result.get("sanity"), dict) else {}
    sc = replay_result.get("scorecards") if isinstance(replay_result.get("scorecards"), dict) else {}
    neg_exp_signals = 0
    for _sid, row in sc.items():
        if not isinstance(row, dict):
            continue
        try:
            ex = float(row.get("expectancy") or 0.0)
        except (TypeError, ValueError):
            continue
        if ex < 0.0:
            neg_exp_signals += 1
    outcomes = list(replay_result.get("outcomes") or [])
    outcome_quality_v1 = compute_pattern_outcome_quality_v1(outcomes)
    return {
        "pnl": float(replay_result.get("cumulative_pnl") or 0.0),
        "trade_count": int(sm.get("total_trades") or 0),
        "max_drawdown": float(sm.get("max_drawdown") or 0.0),
        "expectancy": float(sm.get("expectancy") or 0.0),
        "win_rate": float(sm.get("win_rate") or 0.0),
        "closes_recorded": int(sanity.get("closes_recorded") or 0),
        "entries_attempted": int(sanity.get("entries_attempted") or 0),
        "signal_scorecards_negative_expectancy_count": neg_exp_signals,
        "outcome_quality_v1": outcome_quality_v1,
    }


def metrics_rank_tuple(m: dict[str, Any]) -> tuple[float, float, float, int]:
    """Higher tuple = better (lexicographic)."""
    return (
        float(m.get("expectancy") or 0.0),
        -float(m.get("max_drawdown") or 0.0),
        float(m.get("pnl") or 0.0),
        int(m.get("trade_count") or 0),
    )


def rank_all_v1(
    control_id: str,
    control_metrics: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
) -> tuple[list[str], str | None, list[str]]:
    """
    Return ``(ranking_order_ids_best_first, selected_candidate_id_or_none, reason_codes)``.

    Selection requires a candidate to **strictly** beat control on ``metrics_rank_tuple``.
    """
    reason_codes: list[str] = []
    rows = [{"id": control_id, "metrics": control_metrics}] + [
        {"id": r["candidate_id"], "metrics": r["metrics"]} for r in candidate_rows
    ]
    order = sorted(
        rows,
        key=lambda r: (metrics_rank_tuple(r["metrics"]), r["id"]),
        reverse=True,
    )
    ranking_order = [r["id"] for r in order]

    beating = [
        r
        for r in candidate_rows
        if metrics_rank_tuple(r["metrics"]) > metrics_rank_tuple(control_metrics)
    ]
    if not beating:
        reason_codes.append("CCS_V1_NONE_BEAT_CONTROL")
        return ranking_order, None, reason_codes

    best = max(beating, key=lambda r: (metrics_rank_tuple(r["metrics"]), r["candidate_id"]))
    reason_codes.append("CCS_V1_SELECTED_STRICTLY_BEATS_CONTROL")
    return ranking_order, str(best["candidate_id"]), reason_codes


def _replay_with_apply_dict(
    manifest_path: Path,
    apply_block: dict[str, Any],
    *,
    bar_window_calendar_months: int | None = None,
    decision_context_recall_enabled: bool = False,
    decision_context_recall_apply_bias: bool = False,
    decision_context_recall_apply_signal_bias_v2: bool = False,
    decision_context_recall_memory_path: Path | str | None = None,
    decision_context_recall_max_samples: int = 24,
    decision_context_recall_drill_matched_max: int = 0,
    decision_context_recall_drill_bias_max: int = 0,
    decision_context_recall_drill_trade_entry_max: int = 0,
) -> dict[str, Any]:
    from renaissance_v4.research.replay_runner import run_manifest_replay

    m = copy.deepcopy(load_manifest_file(manifest_path))
    if apply_block:
        apply_memory_bundle_to_manifest(
            m,
            bundle_dict={"schema": MEMORY_BUNDLE_SCHEMA, "apply": dict(apply_block)},
        )
    errs = validate_manifest_against_catalog(m)
    if errs:
        raise ValueError("[context_candidate_search] manifest validation failed: " + "; ".join(errs))

    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="ccs_v1_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(m, fh, indent=2)
        return run_manifest_replay(
            Path(tmp),
            emit_baseline_artifacts=False,
            verbose=False,
            bar_window_calendar_months=bar_window_calendar_months,
            decision_context_recall_enabled=decision_context_recall_enabled,
            decision_context_recall_apply_bias=decision_context_recall_apply_bias,
            decision_context_recall_apply_signal_bias_v2=decision_context_recall_apply_signal_bias_v2,
            decision_context_recall_memory_path=decision_context_recall_memory_path,
            decision_context_recall_max_samples=decision_context_recall_max_samples,
            decision_context_recall_drill_matched_max=decision_context_recall_drill_matched_max,
            decision_context_recall_drill_bias_max=decision_context_recall_drill_bias_max,
            decision_context_recall_drill_trade_entry_max=decision_context_recall_drill_trade_entry_max,
        )
    finally:
        if os.path.isfile(tmp):
            os.unlink(tmp)


def resolve_context_signature(
    *,
    context_signature_v1: dict[str, Any] | None,
    pattern_context_v1: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if context_signature_v1 is not None and isinstance(context_signature_v1, dict):
        return context_signature_v1
    if pattern_context_v1 is not None and isinstance(pattern_context_v1, dict):
        if pattern_context_v1.get("schema") == "pattern_context_v1":
            return derive_context_signature_v1(pattern_context_v1)
    return None


def run_context_candidate_search_v1(
    manifest_path: Path | str,
    *,
    control_apply: dict[str, Any] | None = None,
    context_signature_v1: dict[str, Any] | None = None,
    pattern_context_v1: dict[str, Any] | None = None,
    memory_prior_apply: dict[str, Any] | None = None,
    source_run_id: str = "unspecified",
    parent_reference_id: str = "manifest_baseline",
    manifest_signal_modules: list[str] | None = None,
    bar_window_calendar_months: int | None = None,
    decision_context_recall_enabled: bool = False,
    decision_context_recall_apply_bias: bool = False,
    decision_context_recall_apply_signal_bias_v2: bool = False,
    decision_context_recall_memory_path: Path | str | None = None,
    decision_context_recall_max_samples: int = 24,
    decision_context_recall_drill_matched_max: int = 0,
    decision_context_recall_drill_bias_max: int = 0,
    decision_context_recall_drill_trade_entry_max: int = 0,
    goal_v2: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Replay control + each candidate under identical replay settings; return proof package + raw replays.

    Requires the same SQLite ``market_bars_5m`` dataset as :func:`run_manifest_replay`.
    Optional ``goal_v2`` is echoed in the proof for operator alignment (does not change ranking).
    """
    mp = Path(manifest_path)
    resolved_path = mp.resolve()
    manifest0 = load_manifest_file(resolved_path)
    if manifest_signal_modules is None:
        disabled = set(manifest0.get("disabled_signal_modules") or [])
        manifest_signal_modules = [s for s in (manifest0.get("signal_modules") or []) if s not in disabled]

    sig = resolve_context_signature(
        context_signature_v1=context_signature_v1,
        pattern_context_v1=pattern_context_v1,
    )
    sk = ""
    if isinstance(sig, dict) and sig.get("schema") == "context_signature_v1":
        try:
            sk = canonical_signature_key(sig)
        except Exception:
            sk = ""

    control = {k: v for k, v in (control_apply or {}).items() if k in BUNDLE_APPLY_WHITELIST}
    candidates = generate_candidates_v1(
        control_apply=control,
        context_signature_v1=sig,
        memory_prior_apply=memory_prior_apply,
        manifest_signal_modules=list(manifest_signal_modules),
    )

    batch_inputs = json.dumps(
        {
            "control": control,
            "sig_key": sk,
            "candidates": [c["candidate_id"] for c in candidates],
            "source_run_id": source_run_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    search_batch_id = hashlib.sha256(batch_inputs.encode("utf-8")).hexdigest()[:24]

    control_replay = _replay_with_apply_dict(
        resolved_path,
        control,
        bar_window_calendar_months=bar_window_calendar_months,
        decision_context_recall_enabled=decision_context_recall_enabled,
        decision_context_recall_apply_bias=decision_context_recall_apply_bias,
        decision_context_recall_apply_signal_bias_v2=decision_context_recall_apply_signal_bias_v2,
        decision_context_recall_memory_path=decision_context_recall_memory_path,
        decision_context_recall_max_samples=decision_context_recall_max_samples,
        decision_context_recall_drill_matched_max=decision_context_recall_drill_matched_max,
        decision_context_recall_drill_bias_max=decision_context_recall_drill_bias_max,
        decision_context_recall_drill_trade_entry_max=decision_context_recall_drill_trade_entry_max,
    )
    control_metrics = extract_comparison_metrics(control_replay)
    coq = control_metrics.get("outcome_quality_v1") or {}

    summaries: list[dict[str, Any]] = []
    for c in candidates:
        rid = str(c["candidate_id"])
        raw = _replay_with_apply_dict(
            resolved_path,
            c["apply_effective"],
            bar_window_calendar_months=bar_window_calendar_months,
            decision_context_recall_enabled=decision_context_recall_enabled,
            decision_context_recall_apply_bias=decision_context_recall_apply_bias,
            decision_context_recall_apply_signal_bias_v2=decision_context_recall_apply_signal_bias_v2,
            decision_context_recall_memory_path=decision_context_recall_memory_path,
            decision_context_recall_max_samples=decision_context_recall_max_samples,
            decision_context_recall_drill_matched_max=decision_context_recall_drill_matched_max,
            decision_context_recall_drill_bias_max=decision_context_recall_drill_bias_max,
            decision_context_recall_drill_trade_entry_max=decision_context_recall_drill_trade_entry_max,
        )
        m = extract_comparison_metrics(raw)
        moq = m.get("outcome_quality_v1") or {}
        diff = apply_diff_audit(control, c["apply_effective"])
        oq_diff = diff_outcome_quality_v1(coq, moq) if coq and moq else {}
        summaries.append(
            {
                "candidate_id": rid,
                "parent_reference_id": parent_reference_id,
                "context_family": c["context_family"],
                "generation_reason_codes": c["generation_reason_codes"],
                "apply_diff_from_control": diff,
                "apply_effective_snapshot": c["apply_effective"],
                "metrics": m,
                "vs_control": {
                    "expectancy_delta": _round6(m["expectancy"] - control_metrics["expectancy"]),
                    "max_drawdown_delta": _round6(m["max_drawdown"] - control_metrics["max_drawdown"]),
                    "pnl_delta": _round6(m["pnl"] - control_metrics["pnl"]),
                    "trade_count_delta": int(m["trade_count"] - control_metrics["trade_count"]),
                },
                "vs_control_outcome_quality_v1": oq_diff,
                "replay_validation_checksum": raw.get("validation_checksum"),
                "decision_context_recall_stats": raw.get("decision_context_recall_stats"),
            }
        )

    ranking_order, selected_id, reason_codes = rank_all_v1("control", control_metrics, summaries)

    winner_metrics: dict[str, Any] | None = None
    winner_vs_control: dict[str, Any] | None = None
    if selected_id:
        for s in summaries:
            if s["candidate_id"] == selected_id:
                winner_metrics = dict(s["metrics"])
                winner_vs_control = {
                    **dict(s["vs_control"]),
                    "outcome_quality_v1": dict(s.get("vs_control_outcome_quality_v1") or {}),
                }
                break

    op_parts = [
        f"batch={search_batch_id}",
        f"candidates={len(candidates)}",
        f"ranking_first={ranking_order[0] if ranking_order else ''}",
    ]
    if selected_id:
        op_parts.append(f"selected={selected_id}")
    else:
        op_parts.append("selected=none_no_candidate_beat_control")

    proof: dict[str, Any] = {
        "schema": CONTEXT_CANDIDATE_SEARCH_PROOF_SCHEMA,
        "version": 1,
        "search_batch_id": search_batch_id,
        "source_run_id": source_run_id,
        "source_context_signature_key": sk or None,
        "source_context_signature_v1": sig if isinstance(sig, dict) else None,
        "source_context_family": classify_context_family_v1(sig),
        "manifest_path": str(resolved_path),
        "candidate_count": len(candidates),
        "control_apply": control,
        "control_metrics": control_metrics,
        "control_replay_validation_checksum": control_replay.get("validation_checksum"),
        "candidate_summaries": summaries,
        "ranking_order": ranking_order,
        "selected_candidate_id": selected_id,
        "winner_metrics": winner_metrics,
        "winner_vs_control": winner_vs_control,
        "reason_codes": reason_codes,
        "operator_summary": " ".join(op_parts),
        "goal_v2": goal_v2,
    }
    return {
        "context_candidate_search_proof": proof,
        "control_replay": control_replay,
        "candidate_ids": [c["candidate_id"] for c in candidates],
    }


__all__ = [
    "CONTEXT_CANDIDATE_SEARCH_PROOF_SCHEMA",
    "CONTEXT_CCS_V1_MAX_CANDIDATES",
    "CONTEXT_CCS_V1_MIN_CANDIDATES",
    "apply_diff_audit",
    "classify_context_family_v1",
    "extract_comparison_metrics",
    "generate_candidates_v1",
    "metrics_rank_tuple",
    "rank_all_v1",
    "resolve_context_signature",
    "run_context_candidate_search_v1",
]
