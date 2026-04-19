"""learning_run_audit_v1 — classification, batch aggregate, scorecard record."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from renaissance_v4.game_theory.batch_scorecard import record_parallel_batch_finished
from renaissance_v4.game_theory.learning_run_audit import (
    aggregate_batch_learning_run_audit_v1,
    build_per_scenario_learning_run_audit_v1,
)


def _minimal_ra(**kwargs: int) -> dict[str, int]:
    base = {
        "bars_processed": 100,
        "decision_windows_total": 100,
        "trade_entries_total": 0,
        "trade_exits_total": 0,
        "recall_attempts_total": 0,
        "recall_match_windows_total": 0,
        "recall_match_records_total": 0,
        "recall_bias_applied_total": 0,
        "recall_signal_bias_applied_total": 0,
    }
    base.update(kwargs)
    return base


def test_execution_only_when_no_mechanism_despite_windows() -> None:
    out = {
        "replay_attempt_aggregates_v1": _minimal_ra(),
        "outcomes": [],
        "summary": {},
        "memory_bundle_proof": {
            "memory_bundle_loaded": False,
            "memory_bundle_applied": False,
            "memory_bundle_path": None,
            "memory_keys_applied": [],
        },
    }
    a = build_per_scenario_learning_run_audit_v1(out, scenario={})
    assert a["run_classification_v1"] == "execution_only"
    assert a["learning_engaged_v1"] is False
    assert "execution_only" in a["operator_learning_status_line_v1"]


def test_learning_engaged_when_memory_applied() -> None:
    out = {
        "replay_attempt_aggregates_v1": _minimal_ra(trade_entries_total=2, trade_exits_total=2),
        "outcomes": [],
        "summary": {"win_rate": 0.5, "expectancy": 0.01},
        "memory_bundle_proof": {
            "memory_bundle_loaded": True,
            "memory_bundle_applied": True,
            "memory_bundle_path": "/tmp/bundle.json",
            "memory_keys_applied": ["fusion_min_score"],
        },
    }
    a = build_per_scenario_learning_run_audit_v1(out, scenario={})
    assert a["learning_engaged_v1"] is True
    assert "memory_bundle_apply" in a["learning_mechanisms_observed_v1"]


def test_aggregate_batch_marks_execution_only_all_baseline() -> None:
    row = {
        "ok": True,
        "learning_run_audit_v1": build_per_scenario_learning_run_audit_v1(
            {
                "replay_attempt_aggregates_v1": _minimal_ra(),
                "outcomes": [],
                "summary": {},
                "memory_bundle_proof": {
                    "memory_bundle_loaded": False,
                    "memory_bundle_applied": False,
                    "memory_keys_applied": [],
                },
            },
            {},
        ),
    }
    agg = aggregate_batch_learning_run_audit_v1([row])
    assert agg["batch_run_classification_v1"] == "execution_only"
    assert agg["any_learning_engaged"] is False
    assert agg["replay_decision_windows_sum"] == 100


def test_record_parallel_batch_finished_includes_learning_block() -> None:
    la = build_per_scenario_learning_run_audit_v1(
        {
            "replay_attempt_aggregates_v1": _minimal_ra(),
            "outcomes": [],
            "summary": {},
            "memory_bundle_proof": {
                "memory_bundle_loaded": False,
                "memory_bundle_applied": False,
                "memory_keys_applied": [],
            },
        },
        {},
    )
    fd, tmp = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    tpath = Path(tmp)
    try:
        timing = record_parallel_batch_finished(
            job_id="testjob_learning_audit",
            started_at_utc="2020-01-01T00:00:00Z",
            start_unix=0.0,
            total_scenarios=1,
            workers_used=1,
            results=[{"ok": True, "learning_run_audit_v1": la}],
            session_log_batch_dir=None,
            error=None,
            path=tpath,
        )
    finally:
        tpath.unlink(missing_ok=True)
    assert timing.get("batch_run_classification_v1") == "execution_only"
    assert timing.get("learning_batch_audit_v1", {}).get("schema") == "learning_batch_audit_v1"
    assert timing.get("batch_depth_v1", {}).get("replay_decision_windows_sum") == 100
