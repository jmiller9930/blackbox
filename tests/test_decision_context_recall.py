"""Decision Context Recall v1 — signatures, causal partial context, bounded bias, no future leakage."""

from __future__ import annotations

from collections import Counter

import pytest

from renaissance_v4.game_theory.context_signature_memory import (
    SignatureMatchParamsV1,
    derive_context_signature_v1,
    find_matching_records_v1,
)
from renaissance_v4.core.fusion_engine import fuse_signal_results
from renaissance_v4.game_theory.decision_context_recall import (
    DECISION_CONTEXT_RECALL_SCHEMA_V2,
    build_causal_partial_pattern_context_v1,
    build_decision_recall_trace_v1,
    compute_decision_fusion_bias,
    compute_decision_signal_module_bias_v2,
    derive_decision_context_signature_for_matching,
    fusion_engine_supports_decision_recall,
    volatility_bucket_for_vol20,
)
from renaissance_v4.signals.signal_result import SignalResult
from renaissance_v4.registry import default_catalog_path
from renaissance_v4.registry.load import load_catalog


def test_volatility_bucket_deterministic() -> None:
    assert volatility_bucket_for_vol20(0.0001) == "compressed"
    assert volatility_bucket_for_vol20(0.02) == "expanding"
    assert volatility_bucket_for_vol20(0.005) == "neutral"


def test_causal_partial_excludes_future_fusion_counts() -> None:
    """Counters 'before' must not include the current bar's fusion outcome."""
    pc = build_causal_partial_pattern_context_v1(
        regime_bar_counts_before=Counter({"range": 5}),
        volatility_bucket_counts_before=Counter({"neutral": 5}),
        fusion_direction_counts_before=Counter({"no_trade": 4, "long": 1}),
        high_conflict_bars_before=1,
        aligned_directional_bars_before=1,
        countertrend_directional_bars_before=0,
        current_regime="range",
        vol20=0.005,
    )
    assert pc["high_conflict_bars"] == 1
    assert pc["bars_processed"] == 6
    sig = derive_decision_context_signature_for_matching(pc)
    assert sig["schema"] == "context_signature_v1"


def test_fusion_engine_supports_recall_baseline_manifest() -> None:
    from renaissance_v4.manifest.validate import load_manifest_file

    m = load_manifest_file(
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "renaissance_v4"
        / "configs"
        / "manifests"
        / "baseline_v1_recipe.json"
    )
    cat = load_catalog(default_catalog_path())
    assert fusion_engine_supports_decision_recall(m, cat) is True


def test_compute_decision_fusion_bias_bounded() -> None:
    matches = [
        {
            "record_id": "m1",
            "effective_apply": {"fusion_min_score": 0.2},
            "outcome_summary": {
                "expectancy": 1.0,
                "max_drawdown": 1.0,
                "win_rate": 0.5,
                "total_trades": 5,
                "cumulative_pnl": 0.0,
            },
        }
    ]
    mn, mc, diff, codes, bid = compute_decision_fusion_bias(
        matches,
        base_fusion_min=0.35,
        base_fusion_max_conflict=0.45,
        apply_bias=True,
    )
    assert bid == "m1"
    assert mn < 0.35
    assert abs(mn - 0.35) <= 0.011
    assert "DCR_V1_BIAS_FUSION_MIN" in codes


def test_memory_match_roundtrip() -> None:
    pc = build_causal_partial_pattern_context_v1(
        regime_bar_counts_before=Counter({"range": 10}),
        volatility_bucket_counts_before=Counter({"neutral": 10}),
        fusion_direction_counts_before=Counter(),
        high_conflict_bars_before=0,
        aligned_directional_bars_before=0,
        countertrend_directional_bars_before=0,
        current_regime="range",
        vol20=0.005,
    )
    sig = derive_context_signature_v1(pc)
    rec = {
        "context_signature": sig,
        "record_id": "x",
        "outcome_summary": {
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "cumulative_pnl": 0.0,
        },
        "effective_apply": {},
    }
    m2 = find_matching_records_v1(sig, [rec], params=SignatureMatchParamsV1(structure_share_abs_tol=0.5))
    assert len(m2) == 1


def test_bias_skipped_when_apply_false() -> None:
    matches = [
        {
            "record_id": "m1",
            "effective_apply": {"fusion_min_score": 0.2},
            "outcome_summary": {
                "expectancy": 1.0,
                "max_drawdown": 1.0,
                "win_rate": 0.5,
                "total_trades": 5,
                "cumulative_pnl": 0.0,
            },
        }
    ]
    mn, _mc, diff, _c, _bid = compute_decision_fusion_bias(
        matches,
        base_fusion_min=0.35,
        base_fusion_max_conflict=0.45,
        apply_bias=False,
    )
    assert mn == 0.35
    assert diff == []


def test_compute_decision_signal_module_bias_v2_bounded_and_clamped() -> None:
    """Rule multipliers stay within soft clamp; fusion layer clamps again to [0, 1.12]."""
    pc = build_causal_partial_pattern_context_v1(
        regime_bar_counts_before=Counter({"range": 60}),
        volatility_bucket_counts_before=Counter({"compressed": 55, "neutral": 5}),
        fusion_direction_counts_before=Counter(),
        high_conflict_bars_before=0,
        aligned_directional_bars_before=0,
        countertrend_directional_bars_before=0,
        current_regime="range",
        vol20=0.0001,
    )
    sig = derive_decision_context_signature_for_matching(pc)
    mods = ["breakout_expansion", "trend_continuation", "mean_reversion_fade", "pullback_continuation"]
    mult, applied, diff, _sup, _fav, codes, _mj = compute_decision_signal_module_bias_v2(
        signature=sig,
        matches=[],
        manifest_signal_modules=mods,
        apply_signal_bias=True,
    )
    assert applied is True
    assert "DCR_V2_RULE_VOL_COMPRESS_DEEMPH_BREAKOUT" in codes
    assert 0.75 <= mult["breakout_expansion"] <= 1.08


def test_compute_decision_signal_module_bias_v2_fail_closed_all_paths() -> None:
    """Do not zero the only enabled module when memory asks to disable it."""
    pc = build_causal_partial_pattern_context_v1(
        regime_bar_counts_before=Counter({"range": 10}),
        volatility_bucket_counts_before=Counter({"neutral": 10}),
        fusion_direction_counts_before=Counter(),
        high_conflict_bars_before=0,
        aligned_directional_bars_before=0,
        countertrend_directional_bars_before=0,
        current_regime="range",
        vol20=0.005,
    )
    sig = derive_decision_context_signature_for_matching(pc)
    matches = [
        {
            "record_id": "mem_only_one",
            "effective_apply": {"disabled_signal_modules": ["trend_continuation"]},
        }
    ]
    mult, applied, _diff, sup, _fav, codes, _mj = compute_decision_signal_module_bias_v2(
        signature=sig,
        matches=matches,
        manifest_signal_modules=["trend_continuation"],
        apply_signal_bias=True,
    )
    assert "DCR_V2_SKIP_SUPPRESS_ALL_PATHS" in codes
    assert mult["trend_continuation"] == 1.0
    assert sup == []
    assert applied is False


def test_compute_decision_signal_module_bias_v2_memory_intersection_suppresses() -> None:
    """Intersection disable applies when at least one other module remains."""
    pc = build_causal_partial_pattern_context_v1(
        regime_bar_counts_before=Counter({"range": 10}),
        volatility_bucket_counts_before=Counter({"neutral": 10}),
        fusion_direction_counts_before=Counter(),
        high_conflict_bars_before=0,
        aligned_directional_bars_before=0,
        countertrend_directional_bars_before=0,
        current_regime="range",
        vol20=0.005,
    )
    sig = derive_decision_context_signature_for_matching(pc)
    matches = [
        {"record_id": "a", "effective_apply": {"disabled_signal_modules": ["mean_reversion_fade"]}},
        {"record_id": "b", "effective_apply": {"disabled_signal_modules": ["mean_reversion_fade"]}},
    ]
    mult, applied, _diff, sup, _fav, codes, mem = compute_decision_signal_module_bias_v2(
        signature=sig,
        matches=matches,
        manifest_signal_modules=["trend_continuation", "mean_reversion_fade"],
        apply_signal_bias=True,
    )
    assert applied is True
    assert mult["mean_reversion_fade"] == 0.0
    assert "mean_reversion_fade" in sup
    assert "DCR_V2_MEMORY_INTERSECTION_DISABLE" in codes
    assert mem and mem[0].get("from_record_ids")


def test_build_decision_recall_trace_emits_signal_bias_v2_proof_keys() -> None:
    blk = build_decision_recall_trace_v1(
        enabled=True,
        attempted=True,
        partial_pc=None,
        signature={"schema": "context_signature_v1"},
        signature_key="k",
        matches=[],
        match_summaries=[],
        best_id=None,
        best_summary=None,
        bias_applied=False,
        bias_diff=[],
        reason_codes=[],
        signal_bias_v2_enabled=True,
        decision_context_signal_bias_applied=True,
        decision_context_signal_bias_diff=[{"signal_module": "breakout_expansion", "new_multiplier": 0.88}],
        decision_context_signal_reason_codes=["DCR_V2_RULE_VOL_COMPRESS_DEEMPH_BREAKOUT"],
        decision_context_suppressed_modules=[],
        decision_context_favored_signal_families=[],
        memory_justification_signal_bias=[],
    )
    assert blk["schema"] == DECISION_CONTEXT_RECALL_SCHEMA_V2
    assert blk["version"] == 2
    assert blk["decision_context_signal_bias_applied"] is True
    assert blk["decision_context_signal_bias_diff"]
    assert "decision_context_signal_reason_codes" in blk
    assert "decision_context_suppressed_modules" in blk
    assert "decision_context_favored_signal_families" in blk


def test_fuse_signal_results_per_signal_multiplier_changes_scores() -> None:
    base = {
        "confidence": 0.85,
        "expected_edge": 0.85,
        "regime_fit": 0.85,
        "stability_score": 0.85,
        "active": True,
        "suppression_reason": "",
        "evidence_trace": {},
    }
    a = SignalResult(signal_name="breakout_expansion", direction="long", **base)
    b = SignalResult(signal_name="trend_continuation", direction="long", **base)
    r0 = fuse_signal_results([a, b])
    r1 = fuse_signal_results(
        [a, b],
        per_signal_contribution_multiplier={"breakout_expansion": 0.0},
    )
    assert r1.long_score < r0.long_score
    assert r1.long_score >= 0.0
