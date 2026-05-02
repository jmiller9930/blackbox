"""Tests for run_progressive_cycle() in training_cycle.py"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from training_cycle import run_progressive_cycle


def _write_json(path: str, obj: dict) -> None:
    with open(path, "w") as f:
        json.dump(obj, f)


CONFIG = {
    "schema": "finquant_agent_lab_config_v1",
    "agent_id": "finquant",
    "mode": "deterministic_stub_v1",
    "use_llm_v1": False,
    "memory_store_path": "",
    "retrieval_enabled_default_v1": False,
    "write_outputs_v1": True,
    "auto_promote_learning_v1": True,
    "retrieval_min_obs_v1": 1,
    "retrieval_min_win_rate_v1": 0.0,
    "retrieval_allow_candidate_v1": True,
}

SEED_CASE = {
    "schema": "finquant_lifecycle_case_v1",
    "case_id": "prog_seed",
    "symbol": "SOL-PERP",
    "timeframe_minutes": 60,
    "decision_start_index": 1,
    "decision_end_index": 2,
    "hidden_future_start_index": 3,
    "expected_learning_focus_v1": ["entry_quality"],
    "candles": [
        {"timestamp": "T0", "open": 99.0, "high": 100.0, "low": 98.8, "close": 99.8, "volume": 1000, "rsi_14": 51.0, "ema_20": 99.4, "atr_14": 1.6},
        {"timestamp": "T1", "open": 99.8, "high": 101.5, "low": 99.7, "close": 101.0, "volume": 1400, "rsi_14": 56.0, "ema_20": 100.0, "atr_14": 1.9},
        {"timestamp": "T2", "open": 101.0, "high": 103.0, "low": 100.9, "close": 102.7, "volume": 1800, "rsi_14": 61.0, "ema_20": 100.8, "atr_14": 2.0},
        {"timestamp": "T3", "open": 102.7, "high": 104.0, "low": 102.5, "close": 103.8, "volume": 1700, "rsi_14": 63.0, "ema_20": 101.6, "atr_14": 2.1},
    ],
}

CANDIDATE_CASE = {
    "schema": "finquant_lifecycle_case_v1",
    "case_id": "prog_candidate",
    "symbol": "SOL-PERP",
    "timeframe_minutes": 60,
    "decision_start_index": 1,
    "decision_end_index": 1,
    "hidden_future_start_index": 2,
    "expected_learning_focus_v1": ["entry_quality"],
    "candles": [
        {"timestamp": "C0", "open": 100.0, "high": 100.8, "low": 99.8, "close": 100.3, "volume": 1000, "rsi_14": 50.5, "ema_20": 100.0, "atr_14": 1.2},
        {"timestamp": "C1", "open": 100.3, "high": 101.4, "low": 100.2, "close": 101.0, "volume": 1080, "rsi_14": 53.2, "ema_20": 100.4, "atr_14": 1.3},
        {"timestamp": "C2", "open": 101.0, "high": 103.0, "low": 100.9, "close": 102.8, "volume": 1500, "rsi_14": 59.0, "ema_20": 101.0, "atr_14": 1.7},
    ],
}


def test_progressive_cycle_produces_n_reports():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        seed_path = os.path.join(tmpdir, "seed.json")
        candidate_path = os.path.join(tmpdir, "candidate.json")
        _write_json(config_path, CONFIG)
        _write_json(seed_path, SEED_CASE)
        _write_json(candidate_path, CANDIDATE_CASE)

        result = run_progressive_cycle(
            seed_case_path=seed_path,
            candidate_case_paths=[candidate_path],
            config_path=config_path,
            output_dir=tmpdir,
            n_passes=3,
        )

        assert len(result["reports"]) == 3
        assert len(result["report_paths"]) == 3
        for path in result["report_paths"]:
            assert os.path.exists(path)


def test_progressive_cycle_manifest_written():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        seed_path = os.path.join(tmpdir, "seed.json")
        candidate_path = os.path.join(tmpdir, "candidate.json")
        _write_json(config_path, CONFIG)
        _write_json(seed_path, SEED_CASE)
        _write_json(candidate_path, CANDIDATE_CASE)

        result = run_progressive_cycle(
            seed_case_path=seed_path,
            candidate_case_paths=[candidate_path],
            config_path=config_path,
            output_dir=tmpdir,
            n_passes=2,
        )

        assert os.path.exists(result["manifest_path"])
        manifest = json.load(open(result["manifest_path"]))
        assert manifest["schema"] == "finquant_progressive_cycle_manifest_v1"
        assert manifest["n_passes"] == 2
        assert len(manifest["pass_run_ids"]) == 2


def test_progressive_cycle_comparison_table():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        seed_path = os.path.join(tmpdir, "seed.json")
        candidate_path = os.path.join(tmpdir, "candidate.json")
        _write_json(config_path, CONFIG)
        _write_json(seed_path, SEED_CASE)
        _write_json(candidate_path, CANDIDATE_CASE)

        result = run_progressive_cycle(
            seed_case_path=seed_path,
            candidate_case_paths=[candidate_path],
            config_path=config_path,
            output_dir=tmpdir,
            n_passes=3,
        )

        table = result["comparison"]
        assert len(table) == 4  # control + 3 passes
        assert table[0]["run"] == "control"
        assert table[0]["memory_enabled"] is False
        for i in range(1, 4):
            assert table[i]["memory_enabled"] is True
            assert table[i]["run"] == f"pass_{i}"


def test_progressive_passes_accumulate_retrieval():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        seed_path = os.path.join(tmpdir, "seed.json")
        candidate_path = os.path.join(tmpdir, "candidate.json")
        _write_json(config_path, CONFIG)
        _write_json(seed_path, SEED_CASE)
        _write_json(candidate_path, CANDIDATE_CASE)

        result = run_progressive_cycle(
            seed_case_path=seed_path,
            candidate_case_paths=[candidate_path],
            config_path=config_path,
            output_dir=tmpdir,
            n_passes=3,
        )

        # Pass 1 should have retrieval from seed
        # Later passes have retrieval from seed + prior passes
        matches = [r["retrieval_match_count_v1"] for r in result["reports"]]
        # At minimum, pass 1 should find the seed record
        assert matches[0] >= 1
