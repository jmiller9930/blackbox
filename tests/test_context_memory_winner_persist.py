"""Harness winner → contextual JSONL persist (no Groundhog)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.operator_test_harness_v1 import run_operator_test_harness_v1


def _minimal_agg(n: int = 100) -> dict:
    return {
        "bars_processed": n,
        "decision_windows_total": n,
        "recall_attempts_total": n,
        "recall_match_windows_total": 0,
        "recall_match_records_total": 0,
        "recall_bias_applied_total": 0,
        "recall_signal_bias_applied_total": 0,
        "recall_no_effect_windows_total": n,
        "recall_skipped_unsupported_fusion_total": 0,
        "recall_utilization_rate": 0.0,
        "actionable_signal_windows_total": 0,
        "no_trade_windows_total": n,
        "trade_entries_total": 0,
        "trade_exits_total": 0,
        "risk_blocked_bars_total": 0,
        "memory_records_loaded_count": 0,
        "suppressed_module_slots_total": 0,
    }


def test_persist_appends_jsonl_when_winner_and_read_write(tmp_path: Path) -> None:
    mf = Path(__file__).resolve().parents[1] / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    try:
        from renaissance_v4.research.replay_runner import run_manifest_replay

        raw = run_manifest_replay(mf, emit_baseline_artifacts=False, verbose=False)
    except (RuntimeError, FileNotFoundError) as e:
        pytest.skip(str(e))
    pc = raw.get("pattern_context_v1")
    assert isinstance(pc, dict) and pc.get("schema") == "pattern_context_v1"
    sb = raw.get("signal_behavior_proof_v1")
    assert isinstance(sb, dict) and sb.get("schema") == "signal_behavior_proof_v1"

    mem = tmp_path / "ctx.jsonl"
    fake_proof = {
        "schema": "context_candidate_search_proof_v1",
        "search_batch_id": "batch1",
        "source_context_family": "neutral",
        "source_context_signature_v1": {"schema": "context_signature_v1"},
        "candidate_count": 1,
        "control_apply": {},
        "control_metrics": {
            "trade_count": 2,
            "expectancy": 0.01,
            "max_drawdown": 1.0,
            "pnl": 0.5,
            "win_rate": 0.5,
            "outcome_quality_v1": {
                "expectancy_per_trade": 0.01,
                "exit_efficiency": 0.5,
                "win_loss_size_ratio": 1.0,
            },
        },
        "candidate_summaries": [
            {
                "candidate_id": "ccs_v1_001_x",
                "apply_diff_from_control": [],
                "apply_effective_snapshot": {"fusion_min_score": 0.34},
                "metrics": {
                    "expectancy": 0.05,
                    "max_drawdown": 0.5,
                    "pnl": 1.0,
                    "trade_count": 3,
                    "win_rate": 0.55,
                },
            }
        ],
        "ranking_order": ["ccs_v1_001_x", "control"],
        "selected_candidate_id": "ccs_v1_001_x",
        "winner_metrics": {
            "expectancy": 0.05,
            "max_drawdown": 0.5,
            "pnl": 1.0,
            "trade_count": 3,
            "win_rate": 0.55,
        },
        "winner_vs_control": {"expectancy_delta": 0.04},
        "reason_codes": ["CCS_V1_SELECTED_STRICTLY_BEATS_CONTROL"],
        "operator_summary": "",
    }
    fake_control = {
        "validation_checksum": "chk",
        "pattern_context_v1": pc,
        "replay_attempt_aggregates_v1": _minimal_agg(int(pc.get("bars_processed") or 100)),
        "decision_context_recall_drill_down_v1": {
            "matched_samples": [],
            "bias_applied_samples": [],
            "trade_entry_samples": [],
        },
        "decision_context_recall_stats": {"memory_records_loaded_count": 0},
        "summary": {"expectancy": 0.01, "max_drawdown": 1.0, "win_rate": 0.5, "total_trades": 2},
        "outcomes": [],
    }
    fake_search = {"context_candidate_search_proof": fake_proof, "control_replay": fake_control, "candidate_ids": ["x"]}
    with patch(
        "renaissance_v4.game_theory.operator_test_harness_v1.run_context_candidate_search_v1",
        return_value=fake_search,
    ):
        out = run_operator_test_harness_v1(
            mf,
            test_run_id="persist_test",
            context_signature_memory_mode="read_write",
            context_signature_memory_path=mem,
            decision_context_recall_memory_path=mem,
        )
    h = out["operator_test_harness_v1"]
    panel = h.get("context_memory_operator_panel_v1") or {}
    assert panel.get("memory_saved_this_run") is True
    assert mem.is_file()
    lines = [ln for ln in mem.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec.get("schema") == "context_signature_memory_record_v1"
    assert rec.get("source_run_id") == "persist_test"
    assert "fusion_min_score" in (rec.get("effective_apply") or {})


def test_read_mode_skips_append(tmp_path: Path) -> None:
    mf = Path(__file__).resolve().parents[1] / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    mem = tmp_path / "empty.jsonl"
    mem.write_text("", encoding="utf-8")
    try:
        from renaissance_v4.research.replay_runner import run_manifest_replay

        raw = run_manifest_replay(mf, emit_baseline_artifacts=False, verbose=False)
    except (RuntimeError, FileNotFoundError) as e:
        pytest.skip(str(e))
    pc = raw["pattern_context_v1"]
    assert isinstance(raw.get("signal_behavior_proof_v1"), dict)
    fake_proof = {
        "schema": "context_candidate_search_proof_v1",
        "search_batch_id": "b2",
        "source_context_family": "neutral",
        "candidate_count": 1,
        "control_apply": {},
        "control_metrics": {
            "trade_count": 1,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "pnl": 0.0,
            "win_rate": 0.0,
            "outcome_quality_v1": {},
        },
        "candidate_summaries": [
            {
                "candidate_id": "cwin",
                "apply_diff_from_control": [],
                "apply_effective_snapshot": {"fusion_min_score": 0.4},
                "metrics": {
                    "expectancy": 0.1,
                    "max_drawdown": 0.1,
                    "pnl": 1.0,
                    "trade_count": 2,
                    "win_rate": 0.6,
                },
            }
        ],
        "ranking_order": ["cwin", "control"],
        "selected_candidate_id": "cwin",
        "winner_metrics": {
            "expectancy": 0.1,
            "max_drawdown": 0.1,
            "pnl": 1.0,
            "trade_count": 2,
            "win_rate": 0.6,
        },
        "winner_vs_control": {},
        "reason_codes": ["CCS_V1_SELECTED_STRICTLY_BEATS_CONTROL"],
        "operator_summary": "",
    }
    fake_control = {
        "validation_checksum": "c2",
        "pattern_context_v1": pc,
        "replay_attempt_aggregates_v1": _minimal_agg(int(pc.get("bars_processed") or 50)),
        "decision_context_recall_drill_down_v1": {
            "matched_samples": [],
            "bias_applied_samples": [],
            "trade_entry_samples": [],
        },
        "decision_context_recall_stats": {},
        "summary": {},
        "outcomes": [],
    }
    fake_search = {"context_candidate_search_proof": fake_proof, "control_replay": fake_control, "candidate_ids": ["cwin"]}
    with patch(
        "renaissance_v4.game_theory.operator_test_harness_v1.run_context_candidate_search_v1",
        return_value=fake_search,
    ):
        run_operator_test_harness_v1(
            mf,
            context_signature_memory_mode="read",
            context_signature_memory_path=mem,
            decision_context_recall_memory_path=mem,
        )
    assert mem.read_text(encoding="utf-8").strip() == ""
