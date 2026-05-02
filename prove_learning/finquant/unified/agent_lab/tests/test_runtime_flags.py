"""Tests for runtime_flags.py"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from runtime_flags import (
    apply_runtime_overrides_v1,
    interval_minutes_v1,
    normalize_interval_v1,
    validate_data_window_months_v1,
)


def test_normalize_interval_aliases():
    assert normalize_interval_v1("5") == "5m"
    assert normalize_interval_v1("15m") == "15m"
    assert normalize_interval_v1("45") == "45m"
    assert normalize_interval_v1("1hour") == "1h"


def test_interval_minutes():
    assert interval_minutes_v1("5m") == 5
    assert interval_minutes_v1("15") == 15
    assert interval_minutes_v1("45m") == 45
    assert interval_minutes_v1("1h") == 60


def test_invalid_interval_raises():
    with pytest.raises(ValueError, match="interval must be one of"):
        normalize_interval_v1("30m")


def test_validate_data_window_months():
    assert validate_data_window_months_v1(12) == 12
    assert validate_data_window_months_v1("18") == 18


def test_invalid_data_window_months_raises():
    with pytest.raises(ValueError, match="must be > 0"):
        validate_data_window_months_v1(0)


def test_apply_runtime_overrides():
    cfg = {
        "schema": "finquant_agent_lab_config_v1",
        "agent_id": "finquant",
        "mode": "deterministic_stub_v1",
        "use_llm_v1": False,
        "memory_store_path": "x.jsonl",
        "retrieval_enabled_default_v1": False,
        "write_outputs_v1": True,
    }
    out = apply_runtime_overrides_v1(
        cfg,
        data_window_months=25,
        interval="1hour",
    )
    assert out["runtime_data_window_months_v1"] == 25
    assert out["runtime_interval_v1"] == "1h"
    assert out["runtime_interval_minutes_v1"] == 60
    assert out["runtime_request_v1"]["data_window_months_v1"] == 25
