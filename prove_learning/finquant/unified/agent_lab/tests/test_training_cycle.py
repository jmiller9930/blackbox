"""Tests for training_cycle.py"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from training_cycle import run_training_cycle


def _write_json(path: str, obj: dict) -> None:
    with open(path, "w") as f:
        json.dump(obj, f)


def test_training_cycle_produces_referee_report():
    config = {
        "schema": "finquant_agent_lab_config_v1",
        "agent_id": "finquant",
        "mode": "deterministic_stub_v1",
        "use_llm_v1": False,
        "memory_store_path": "",
        "retrieval_enabled_default_v1": False,
        "write_outputs_v1": True,
        "llm_model_v1": "qwen2.5:7b",
        "ollama_base_url_v1": "http://172.20.2.230:11434",
    }
    seed_case = {
        "schema": "finquant_lifecycle_case_v1",
        "case_id": "seed_trend_memory",
        "symbol": "SOL-PERP",
        "timeframe_minutes": 60,
        "decision_start_index": 1,
        "decision_end_index": 2,
        "hidden_future_start_index": 3,
        "expected_learning_focus_v1": ["entry_quality"],
        "candles": [
            {"timestamp": "2024-01-01T00:00:00Z", "open": 99.0, "high": 100.0, "low": 98.8, "close": 99.8, "volume": 1000, "rsi_14": 51.0, "ema_20": 99.4, "atr_14": 1.6},
            {"timestamp": "2024-01-01T01:00:00Z", "open": 99.8, "high": 101.5, "low": 99.7, "close": 101.0, "volume": 1400, "rsi_14": 56.0, "ema_20": 100.0, "atr_14": 1.9},
            {"timestamp": "2024-01-01T02:00:00Z", "open": 101.0, "high": 103.0, "low": 100.9, "close": 102.7, "volume": 1800, "rsi_14": 61.0, "ema_20": 100.8, "atr_14": 2.0},
            {"timestamp": "2024-01-01T03:00:00Z", "open": 102.7, "high": 104.0, "low": 102.5, "close": 103.8, "volume": 1700, "rsi_14": 63.0, "ema_20": 101.6, "atr_14": 2.1}
        ],
    }
    candidate_case = {
        "schema": "finquant_lifecycle_case_v1",
        "case_id": "candidate_threshold_memory",
        "symbol": "SOL-PERP",
        "timeframe_minutes": 60,
        "decision_start_index": 1,
        "decision_end_index": 1,
        "hidden_future_start_index": 2,
        "expected_learning_focus_v1": ["entry_quality"],
        "candles": [
            {"timestamp": "2024-01-02T00:00:00Z", "open": 100.0, "high": 100.3, "low": 99.95, "close": 100.3, "volume": 1000, "rsi_14": 50.5, "ema_20": 100.0, "atr_14": 0.44},
            {"timestamp": "2024-01-02T01:00:00Z", "open": 100.3, "high": 100.6, "low": 100.2, "close": 101.0, "volume": 1080, "rsi_14": 53.2, "ema_20": 100.4, "atr_14": 0.45},
            {"timestamp": "2024-01-02T02:00:00Z", "open": 101.0, "high": 101.3, "low": 100.9, "close": 101.5, "volume": 1500, "rsi_14": 55.0, "ema_20": 100.8, "atr_14": 0.45},
            {"timestamp": "2024-01-02T03:00:00Z", "open": 101.5, "high": 101.8, "low": 101.4, "close": 101.9, "volume": 1600, "rsi_14": 57.0, "ema_20": 101.1, "atr_14": 0.45}
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        seed_path = os.path.join(tmpdir, "seed.json")
        candidate_path = os.path.join(tmpdir, "candidate.json")
        _write_json(config_path, config)
        _write_json(seed_path, seed_case)
        _write_json(candidate_path, candidate_case)

        result = run_training_cycle(
            seed_case_path=seed_path,
            candidate_case_path=candidate_path,
            config_path=config_path,
            output_dir=tmpdir,
            data_window_months=12,
            interval="1hour",
        )

        report = result["report"]
        assert os.path.exists(result["report_path"])
        assert report["schema"] == "student_learning_referee_report_v1"
        assert report["retrieval_match_count_v1"] >= 1
        assert report["verdict_v1"] == "LEARNED_BEHAVIOR_PROVEN"
