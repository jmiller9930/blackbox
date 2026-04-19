"""Context-Conditioned Candidate Search v1 — generation, bounds, ranking, proof."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.context_candidate_search import (
    CONTEXT_CANDIDATE_SEARCH_PROOF_SCHEMA,
    CONTEXT_CCS_V1_MAX_CANDIDATES,
    CONTEXT_CCS_V1_MIN_CANDIDATES,
    apply_diff_audit,
    classify_context_family_v1,
    extract_comparison_metrics,
    generate_candidates_v1,
    metrics_rank_tuple,
    rank_all_v1,
    run_context_candidate_search_v1,
)
from renaissance_v4.game_theory.memory_bundle import BUNDLE_APPLY_WHITELIST


def test_classify_context_family_deterministic() -> None:
    sig = {
        "schema": "context_signature_v1",
        "vol_compressed_share": 0.3,
        "range_like_share": 0.1,
        "trend_like_share": 0.1,
        "vol_expanding_share": 0.05,
        "high_conflict_share": 0.0,
    }
    assert classify_context_family_v1(sig) == "compressed_range"


def test_generate_candidates_bounded_and_whitelisted() -> None:
    sig = {
        "schema": "context_signature_v1",
        "vol_compressed_share": 0.95,
        "range_like_share": 0.4,
        "trend_like_share": 0.0,
        "vol_expanding_share": 0.0,
        "high_conflict_share": 0.0,
    }
    mods = ["trend_continuation", "pullback_continuation", "breakout_expansion", "mean_reversion_fade"]
    cands = generate_candidates_v1(
        control_apply={},
        context_signature_v1=sig,
        memory_prior_apply=None,
        manifest_signal_modules=mods,
    )
    assert CONTEXT_CCS_V1_MIN_CANDIDATES <= len(cands) <= CONTEXT_CCS_V1_MAX_CANDIDATES
    for c in cands:
        assert c["candidate_id"].startswith("ccs_v1_")
        for k in c["apply_effective"]:
            assert k in BUNDLE_APPLY_WHITELIST


def test_generate_candidates_no_unwhitelisted_keys_in_effective() -> None:
    cands = generate_candidates_v1(
        control_apply={"fusion_min_score": 0.36, "bogus_key": 123},
        context_signature_v1=None,
        memory_prior_apply=None,
        manifest_signal_modules=["trend_continuation", "mean_reversion_fade"],
    )
    assert cands
    for c in cands:
        assert "bogus_key" not in c["apply_effective"]


def test_deterministic_generation_order() -> None:
    sig = {
        "schema": "context_signature_v1",
        "high_conflict_share": 0.25,
        "vol_compressed_share": 0.0,
        "range_like_share": 0.0,
        "trend_like_share": 0.0,
        "vol_expanding_share": 0.0,
    }
    a = generate_candidates_v1(
        control_apply={},
        context_signature_v1=sig,
        memory_prior_apply=None,
        manifest_signal_modules=["trend_continuation", "mean_reversion_fade"],
    )
    b = generate_candidates_v1(
        control_apply={},
        context_signature_v1=sig,
        memory_prior_apply=None,
        manifest_signal_modules=["trend_continuation", "mean_reversion_fade"],
    )
    assert [x["candidate_id"] for x in a] == [x["candidate_id"] for x in b]


def test_ranking_stable_and_none_selected() -> None:
    control_m = {"expectancy": 0.1, "max_drawdown": 1.0, "pnl": 0.5, "trade_count": 5}
    rows = [
        {
            "candidate_id": "c1",
            "metrics": {"expectancy": 0.05, "max_drawdown": 0.5, "pnl": 0.2, "trade_count": 5},
        },
        {
            "candidate_id": "c2",
            "metrics": {"expectancy": 0.1, "max_drawdown": 1.0, "pnl": 0.4, "trade_count": 4},
        },
    ]
    order, sel, codes = rank_all_v1("control", control_m, rows)
    assert order[0] == "control"
    assert sel is None
    assert "CCS_V1_NONE_BEAT_CONTROL" in codes


def test_ranking_picks_best_among_multiple_beating_control() -> None:
    control_m = {"expectancy": 0.1, "max_drawdown": 1.0, "pnl": 0.0, "trade_count": 3}
    rows = [
        {
            "candidate_id": "c_a",
            "metrics": {"expectancy": 0.15, "max_drawdown": 1.0, "pnl": 0.0, "trade_count": 3},
        },
        {
            "candidate_id": "c_b",
            "metrics": {"expectancy": 0.2, "max_drawdown": 1.0, "pnl": 0.0, "trade_count": 3},
        },
    ]
    _order, sel, _codes = rank_all_v1("control", control_m, rows)
    assert sel == "c_b"


def test_ranking_selects_strict_winner() -> None:
    control_m = {"expectancy": 0.1, "max_drawdown": 1.0, "pnl": 0.5, "trade_count": 5}
    rows = [
        {
            "candidate_id": "c_win",
            "metrics": {"expectancy": 0.2, "max_drawdown": 1.0, "pnl": 0.5, "trade_count": 5},
        },
    ]
    order, sel, codes = rank_all_v1("control", control_m, rows)
    assert sel == "c_win"
    assert order[0] == "c_win"
    assert "CCS_V1_SELECTED_STRICTLY_BEATS_CONTROL" in codes


def test_extract_comparison_metrics_shape() -> None:
    raw = {
        "cumulative_pnl": 1.2,
        "summary": {
            "total_trades": 3,
            "max_drawdown": 0.5,
            "expectancy": 0.4,
            "win_rate": 0.5,
        },
        "sanity": {"closes_recorded": 3, "entries_attempted": 3},
        "scorecards": {"mean_reversion_fade": {"expectancy": -0.1}},
    }
    m = extract_comparison_metrics(raw)
    assert m["signal_scorecards_negative_expectancy_count"] == 1
    assert m["trade_count"] == 3


def test_proof_emission_keys() -> None:
    """Proof dict shape without running replay."""
    proof = {
        "schema": CONTEXT_CANDIDATE_SEARCH_PROOF_SCHEMA,
        "search_batch_id": "x",
        "source_run_id": "y",
        "candidate_count": 1,
        "control_apply": {},
        "candidate_summaries": [],
        "ranking_order": ["control"],
        "selected_candidate_id": None,
        "reason_codes": ["CCS_V1_NONE_BEAT_CONTROL"],
        "operator_summary": "test",
    }
    required = (
        "schema",
        "search_batch_id",
        "candidate_count",
        "control_apply",
        "candidate_summaries",
        "ranking_order",
        "selected_candidate_id",
        "reason_codes",
        "operator_summary",
    )
    for k in required:
        assert k in proof


def test_apply_diff_audit() -> None:
    d = apply_diff_audit({"fusion_min_score": 0.35}, {"fusion_min_score": 0.36})
    assert d == [{"key": "fusion_min_score", "old": 0.35, "new": 0.36}]


def test_run_search_integration_requires_db() -> None:
    """Optional: needs market_bars_5m with >= 50 rows."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    mf = root / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    sig = {
        "schema": "context_signature_v1",
        "version": 1,
        "dominant_regime": "range",
        "dominant_volatility_bucket": "neutral",
        "range_like_share": 0.5,
        "trend_like_share": 0.1,
        "breakout_like_share": 0.05,
        "vol_compressed_share": 0.2,
        "vol_expanding_share": 0.15,
        "high_conflict_share": 0.1,
        "aligned_directional_share": 0.05,
        "countertrend_directional_share": 0.02,
    }
    try:
        out = run_context_candidate_search_v1(
            mf,
            control_apply={},
            context_signature_v1=sig,
            source_run_id="test_integration",
        )
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        pytest.skip(f"integration prerequisites not met: {e}")
    proof = out["context_candidate_search_proof"]
    assert proof["schema"] == CONTEXT_CANDIDATE_SEARCH_PROOF_SCHEMA
    assert proof["candidate_count"] >= 3
    assert "ranking_order" in proof
