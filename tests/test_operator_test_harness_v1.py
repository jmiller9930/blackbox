"""Operator Test Harness v1 — aggregates, recall counters, Groundhog recommendation, proof shape."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.operator_test_harness_v1 import (
    OPERATOR_TEST_HARNESS_SCHEMA,
    build_groundhog_commit_block_v1,
    build_operator_summary_block_v1,
    run_operator_test_harness_v1,
)

REQUIRED_AGG_KEYS = (
    "bars_processed",
    "decision_windows_total",
    "recall_attempts_total",
    "recall_match_windows_total",
    "recall_match_records_total",
    "recall_bias_applied_total",
    "recall_signal_bias_applied_total",
    "recall_no_effect_windows_total",
    "actionable_signal_windows_total",
    "no_trade_windows_total",
    "trade_entries_total",
    "trade_exits_total",
)


def test_groundhog_no_commit_when_no_winner() -> None:
    gh = build_groundhog_commit_block_v1(
        selected_candidate_id=None,
        winner_apply_effective=None,
        search_reason_codes=["CCS_V1_NONE_BEAT_CONTROL"],
    )
    assert gh["groundhog_commit_candidate"] is False
    assert gh["groundhog_commit_apply"] == {}
    assert gh["no_commit_reason"] == "CCS_V1_NONE_BEAT_CONTROL"
    assert "GTH_V1_NO_COMMIT" in gh["groundhog_commit_reason_codes"]


def test_groundhog_commit_when_winner() -> None:
    gh = build_groundhog_commit_block_v1(
        selected_candidate_id="ccs_v1_001_x",
        winner_apply_effective={"fusion_min_score": 0.34},
        search_reason_codes=["CCS_V1_SELECTED_STRICTLY_BEATS_CONTROL"],
    )
    assert gh["groundhog_commit_candidate"] is True
    assert gh["groundhog_commit_apply"] == {"fusion_min_score": 0.34}
    assert gh["no_commit_reason"] is None


def test_operator_summary_block_strings() -> None:
    blk = build_operator_summary_block_v1(
        context_family="compressed_range",
        decision_windows_total=1000,
        recall_utilization_rate=0.5,
        trade_count=12,
        selected_candidate_id=None,
        winner_vs_control=None,
        winner_apply_diff=None,
        groundhog_commit_candidate=False,
    )
    assert blk["groundhog_update_recommended"] == "no"
    assert blk["total_decision_attempts"] == "1000"
    assert blk["winner_or_none"] == "none"


def test_harness_completeness_mocked() -> None:
    fake_proof = {
        "schema": "context_candidate_search_proof_v1",
        "search_batch_id": "batch1",
        "source_context_family": "neutral",
        "source_context_signature_v1": {"schema": "context_signature_v1"},
        "candidate_count": 1,
        "control_apply": {},
        "control_metrics": {"trade_count": 0, "expectancy": 0.0, "max_drawdown": 0.0, "pnl": 0.0},
        "candidate_summaries": [],
        "ranking_order": ["control"],
        "selected_candidate_id": None,
        "winner_metrics": None,
        "winner_vs_control": None,
        "reason_codes": ["CCS_V1_NONE_BEAT_CONTROL"],
        "operator_summary": "",
    }
    fake_control = {
        "validation_checksum": "chk",
        "replay_attempt_aggregates_v1": {k: 0 for k in REQUIRED_AGG_KEYS}
        | {"recall_skipped_unsupported_fusion_total": 0, "recall_utilization_rate": 0.0, "risk_blocked_bars_total": 0},
        "decision_context_recall_drill_down_v1": {
            "matched_samples": [],
            "bias_applied_samples": [],
            "trade_entry_samples": [],
        },
        "decision_context_recall_stats": {},
    }
    fake_search = {"context_candidate_search_proof": fake_proof, "control_replay": fake_control, "candidate_ids": []}
    with patch(
        "renaissance_v4.game_theory.operator_test_harness_v1.run_context_candidate_search_v1",
        return_value=fake_search,
    ):
        out = run_operator_test_harness_v1(
            "dummy_manifest.json",
            test_run_id="t1",
            decision_context_recall_enabled=True,
        )
    h = out["operator_test_harness_v1"]
    assert h["schema"] == OPERATOR_TEST_HARNESS_SCHEMA
    assert "reproducibility_v1" in h
    assert "context_candidate_search_proof" in h
    assert "groundhog_commit_recommendation_v1" in h
    assert "operator_summary_block_v1" in h
    assert h["replay_attempt_aggregates_v1"]["decision_windows_total"] == 0
    dd = h["decision_context_recall_drill_down_v1"]
    assert "matched_samples" in dd and "trade_entry_samples" in dd


def test_replay_aggregates_from_runner_shape() -> None:
    """Replay output must expose aggregates (integration / smoke)."""
    from pathlib import Path

    from renaissance_v4.research.replay_runner import run_manifest_replay

    mf = Path(__file__).resolve().parents[1] / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    try:
        raw = run_manifest_replay(mf, emit_baseline_artifacts=False, verbose=False)
    except (RuntimeError, FileNotFoundError) as e:
        pytest.skip(str(e))
    agg = raw.get("replay_attempt_aggregates_v1") or {}
    for k in REQUIRED_AGG_KEYS:
        assert k in agg, f"missing {k}"
    assert int(agg["decision_windows_total"]) == int(agg["bars_processed"])
    dd = raw.get("decision_context_recall_drill_down_v1") or {}
    assert "matched_samples" in dd


def test_trade_vs_no_trade_accounting() -> None:
    from pathlib import Path

    from renaissance_v4.research.replay_runner import run_manifest_replay

    mf = Path(__file__).resolve().parents[1] / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    try:
        raw = run_manifest_replay(mf, emit_baseline_artifacts=False, verbose=False)
    except (RuntimeError, FileNotFoundError) as e:
        pytest.skip(str(e))
    agg = raw["replay_attempt_aggregates_v1"]
    s = raw["sanity"]
    assert int(agg["no_trade_windows_total"]) + int(agg["actionable_signal_windows_total"]) == int(
        agg["decision_windows_total"]
    )
    assert int(s["entries_attempted"]) == int(agg["trade_entries_total"])
