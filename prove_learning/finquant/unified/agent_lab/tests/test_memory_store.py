"""Tests for memory_store.py"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory_store import MemoryStore

CONFIG = {
    "schema": "finquant_agent_lab_config_v1",
    "agent_id": "finquant",
    "mode": "deterministic_stub_v1",
    "use_llm_v1": False,
    "memory_store_path": "",
    "retrieval_enabled_default_v1": False,
    "write_outputs_v1": True,
}

CASE = {
    "case_id": "test_mem_001",
    "symbol": "SOL-PERP",
    "timeframe_minutes": 5,
    "hidden_future_start_index": 1,
    "candles": [],
    "expected_learning_focus_v1": [],
}

EVALUATION = {
    "schema": "finquant_lifecycle_evaluation_v1",
    "case_id": "test_mem_001",
    "final_status_v1": "INFO",
    "entry_quality_v1": "correctly_abstained",
    "exit_quality_v1": "no_exit_needed",
    "hold_quality_v1": "hold_steps=0",
    "no_trade_correctness_v1": "traded_as_expected",
    "actions_taken": ["NO_TRADE"],
    "final_action": "NO_TRADE",
    "step_decisions_emitted": 1,
    "learning_labels_v1": [],
    "notes": [],
}


def test_write_learning_record():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(config=CONFIG, base_output_dir=tmpdir)
        record = store.write_learning_record(case=CASE, evaluation=EVALUATION)
        assert record["schema"] == "finquant_learning_record_v1"
        assert record["case_id"] == "test_mem_001"
        assert record["stored_v1"] is True
        assert record["promotion_eligible_v1"] is False
        assert record["retrieval_enabled_v1"] is False


def test_finalize_writes_all_artifacts():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(config=CONFIG, base_output_dir=tmpdir)
        store.write_learning_record(case=CASE, evaluation=EVALUATION)
        run_id = store.finalize(case=CASE, evaluation=EVALUATION)
        run_dir = store.get_run_dir()

        for artifact in [
            "decision_trace.json",
            "learning_records.jsonl",
            "retrieval_trace.json",
            "evaluation.json",
            "run_summary.json",
        ]:
            assert (run_dir / artifact).exists(), f"missing artifact: {artifact}"


def test_run_summary_schema():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(config=CONFIG, base_output_dir=tmpdir)
        store.write_learning_record(case=CASE, evaluation=EVALUATION)
        store.finalize(case=CASE, evaluation=EVALUATION)
        run_dir = store.get_run_dir()
        with open(run_dir / "run_summary.json") as f:
            summary = json.load(f)
        assert summary["schema"] == "finquant_agent_lab_run_summary_v1"
        assert summary["case_id"] == "test_mem_001"
        assert summary["final_status_v1"] == "INFO"


def test_retrieval_disabled_by_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(config=CONFIG, base_output_dir=tmpdir)
        record = store.write_learning_record(case=CASE, evaluation=EVALUATION)
        assert record["retrieval_enabled_v1"] is False
