"""
Tests for retrieval.py

Critical governance rule: records with retrieval_enabled_v1=false must NEVER be returned.
"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from retrieval import retrieve_eligible

CONFIG_RETRIEVAL_ON = {
    "retrieval_enabled_default_v1": True,
    "memory_store_path": "",  # will be overridden in tests
}

CONFIG_RETRIEVAL_OFF = {
    "retrieval_enabled_default_v1": False,
    "memory_store_path": "",
}

CASE = {"case_id": "test_ret_001", "symbol": "SOL-PERP"}


def _write_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_retrieval_disabled_config_returns_empty():
    eligible, trace = retrieve_eligible(
        shared_store_path=None,
        case=CASE,
        config=CONFIG_RETRIEVAL_OFF,
    )
    assert eligible == []
    assert any(e["reason"] == "no_memory_store_path" for e in trace)


def test_blocked_records_never_returned():
    """Records with retrieval_enabled_v1=false must not come back."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "records.jsonl")
        blocked = [
            {
                "record_id": "lr_blocked_001",
                "symbol": "SOL-PERP",
                "retrieval_enabled_v1": False,
                "schema": "finquant_learning_record_v1",
            }
        ]
        _write_jsonl(store_path, blocked)

        cfg = dict(CONFIG_RETRIEVAL_ON, memory_store_path=store_path)
        eligible, trace = retrieve_eligible(
            shared_store_path=store_path,
            case=CASE,
            config=cfg,
        )
        assert eligible == [], "blocked records must not be returned"
        blocked_reasons = [e["reason"] for e in trace]
        assert "retrieval_disabled" in blocked_reasons


def test_enabled_records_returned():
    """Records with retrieval_enabled_v1=true, matching symbol, and passing quality gate are returned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "records.jsonl")
        records = [
            {
                "record_id": "lr_good_001",
                "symbol": "SOL-PERP",
                "retrieval_enabled_v1": True,
                "schema": "finquant_learning_record_v1",
                # RMv2 quality gate fields
                "pattern_total_obs_v1": 10,
                "pattern_win_rate_v1": 0.70,
                "pattern_status_v1": "provisional",
            }
        ]
        _write_jsonl(store_path, records)

        cfg = dict(CONFIG_RETRIEVAL_ON, memory_store_path=store_path)
        eligible, trace = retrieve_eligible(
            shared_store_path=store_path,
            case=CASE,
            config=cfg,
        )
        assert len(eligible) == 1
        assert eligible[0]["record_id"] == "lr_good_001"
        assert any(e["reason"] == "retrieved" for e in trace)


def test_symbol_mismatch_not_returned():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "records.jsonl")
        records = [
            {
                "record_id": "lr_wrong_sym",
                "symbol": "BTC-PERP",
                "retrieval_enabled_v1": True,
                "schema": "finquant_learning_record_v1",
            }
        ]
        _write_jsonl(store_path, records)

        cfg = dict(CONFIG_RETRIEVAL_ON, memory_store_path=store_path)
        eligible, trace = retrieve_eligible(
            shared_store_path=store_path,
            case=CASE,
            config=cfg,
        )
        assert eligible == []
        assert any(e["reason"] == "symbol_mismatch" for e in trace)


def test_prefers_enter_long_over_recent_no_trade():
    """Later NO_TRADE rows must not crowd out an older ENTER_LONG lesson (same symbol)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "records.jsonl")
        _quality = {"pattern_total_obs_v1": 10, "pattern_win_rate_v1": 0.70, "pattern_status_v1": "provisional"}
        records = [
            {
                "record_id": "lr_long_old",
                "symbol": "SOL-PERP",
                "entry_action_v1": "ENTER_LONG",
                "retrieval_enabled_v1": True,
                "schema": "finquant_learning_record_v1",
                **_quality,
            },
            {
                "record_id": "lr_nt_recent",
                "symbol": "SOL-PERP",
                "entry_action_v1": "NO_TRADE",
                "retrieval_enabled_v1": True,
                "schema": "finquant_learning_record_v1",
                **_quality,
            },
        ]
        _write_jsonl(store_path, records)

        cfg = dict(CONFIG_RETRIEVAL_ON, memory_store_path=store_path, retrieval_max_records_v1=1)
        eligible, trace = retrieve_eligible(
            shared_store_path=store_path,
            case=CASE,
            config=cfg,
        )
        assert len(eligible) == 1
        assert eligible[0]["record_id"] == "lr_long_old"
        assert any(e["reason"] == "retrieved" for e in trace)


def test_mixed_records_only_eligible_returned():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "records.jsonl")
        records = [
            {"record_id": "lr_blocked", "symbol": "SOL-PERP",
             "retrieval_enabled_v1": False, "schema": "finquant_learning_record_v1",
             "pattern_total_obs_v1": 10, "pattern_win_rate_v1": 0.70, "pattern_status_v1": "provisional"},
            {"record_id": "lr_eligible", "symbol": "SOL-PERP",
             "retrieval_enabled_v1": True, "schema": "finquant_learning_record_v1",
             "pattern_total_obs_v1": 10, "pattern_win_rate_v1": 0.70, "pattern_status_v1": "provisional"},
            {"record_id": "lr_wrong", "symbol": "ETH-PERP",
             "retrieval_enabled_v1": True, "schema": "finquant_learning_record_v1",
             "pattern_total_obs_v1": 10, "pattern_win_rate_v1": 0.70, "pattern_status_v1": "provisional"},
        ]
        _write_jsonl(store_path, records)

        cfg = dict(CONFIG_RETRIEVAL_ON, memory_store_path=store_path)
        eligible, trace = retrieve_eligible(
            shared_store_path=store_path,
            case=CASE,
            config=cfg,
        )
        assert len(eligible) == 1
        assert eligible[0]["record_id"] == "lr_eligible"
