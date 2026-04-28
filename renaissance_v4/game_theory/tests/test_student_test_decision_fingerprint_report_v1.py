"""Tests for student_test decision fingerprint Markdown report."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.student_test_decision_fingerprint_report_v1 import (
    REPORT_FILENAME_V1,
    write_student_test_decision_fingerprint_report_md_v1,
)


def test_report_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    jid = "report-job-test-1"
    root = tmp_path / "runtime" / "student_test" / jid
    root.mkdir(parents=True)
    trace = root / "learning_trace_events_v1.jsonl"
    trace.write_text(
        json.dumps(
            {
                "schema": "learning_trace_event_v1",
                "job_id": jid,
                "trade_id": "t1",
                "scenario_id": "scen_a",
                "stage": "student_test_sealed_output_snapshot_v1",
                "status": "pass",
                "summary": "snap",
                "evidence_payload": {
                    "student_output_v1": {
                        "student_action_v1": "no_trade",
                        "act": False,
                        "direction": "flat",
                        "confidence_01": 0.5,
                        "hypothesis_text_v1": "h",
                        "invalidation_text": "inv",
                        "supporting_indicators": ["a"],
                        "conflicting_indicators": ["b"],
                        "decision_at_ms": 123,
                    }
                },
                "producer": "student_test_mode_v1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", "1")

    with patch(
        "renaissance_v4.game_theory.student_test_decision_fingerprint_report_v1.student_test_job_runtime_root_v1",
        lambda j: root,
    ):
        p = write_student_test_decision_fingerprint_report_md_v1(
            jid, seam_audit={"student_seam_stop_reason_v1": "x"}, trace_path=trace
        )
    assert p.name == REPORT_FILENAME_V1
    assert "Trade 1: `t1`" in p.read_text(encoding="utf-8")
    assert "Global summary" in p.read_text(encoding="utf-8")


def test_report_trade_ids_fallback_from_ev_when_no_sealed_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GT_DIRECTIVE_033: sealed snapshots may be absent when Student LLM rejects all outputs."""
    jid = "report-job-ev-fallback-1"
    root = tmp_path / "runtime" / "student_test" / jid
    root.mkdir(parents=True)
    trace = root / "learning_trace_events_v1.jsonl"
    ev_payload = {
        "entry_reasoning_stage": "expected_value_risk_cost_evaluated_v1",
        "expected_value_risk_cost_v1": {
            "schema": "expected_value_risk_cost_v1",
            "available_v1": False,
            "ev_long_v1": 0.0,
            "ev_short_v1": 0.0,
            "ev_no_trade_v1": 0.0,
            "sample_count_v1": 0,
            "reason_codes_v1": ["insufficient_sample_v1"],
        },
        "ev_score_adjustment_v1": 0.0,
    }
    lines = [
        json.dumps(
            {
                "schema": "learning_trace_event_v1",
                "job_id": jid,
                "trade_id": "trade_a",
                "scenario_id": "scen_a",
                "stage": "expected_value_risk_cost_evaluated_v1",
                "status": "pass",
                "summary": "ev",
                "evidence_payload": ev_payload,
                "producer": "entry_reasoning_engine_v1",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "schema": "learning_trace_event_v1",
                "job_id": jid,
                "trade_id": "trade_b",
                "scenario_id": "scen_a",
                "stage": "expected_value_risk_cost_evaluated_v1",
                "status": "pass",
                "summary": "ev",
                "evidence_payload": ev_payload,
                "producer": "entry_reasoning_engine_v1",
            },
            ensure_ascii=False,
        ),
    ]
    trace.write_text("\n".join(lines) + "\n", encoding="utf-8")

    monkeypatch.setenv("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", "1")

    with patch(
        "renaissance_v4.game_theory.student_test_decision_fingerprint_report_v1.student_test_job_runtime_root_v1",
        lambda j: root,
    ):
        p = write_student_test_decision_fingerprint_report_md_v1(jid, seam_audit=None, trace_path=trace)
    text = p.read_text(encoding="utf-8")
    assert "total trades (trace snapshots):** 2" in text
    assert "Trade 1: `trade_a`" in text
    assert "Trade 2: `trade_b`" in text
    assert "#### Expected Value / Risk Cost (RM — Directive 4)" in text
