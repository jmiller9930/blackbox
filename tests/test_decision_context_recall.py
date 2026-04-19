"""Decision Context Recall v1 — signatures, causal partial context, bounded bias, no future leakage."""

from __future__ import annotations

from collections import Counter

import pytest

from renaissance_v4.game_theory.context_signature_memory import (
    SignatureMatchParamsV1,
    derive_context_signature_v1,
    find_matching_records_v1,
)
from renaissance_v4.game_theory.decision_context_recall import (
    build_causal_partial_pattern_context_v1,
    compute_decision_fusion_bias,
    derive_decision_context_signature_for_matching,
    fusion_engine_supports_decision_recall,
    volatility_bucket_for_vol20,
)
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
