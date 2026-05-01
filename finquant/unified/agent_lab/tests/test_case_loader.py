"""Tests for case_loader.py"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from case_loader import load_case, load_cases

VALID_CASE = {
    "schema": "finquant_lifecycle_case_v1",
    "case_id": "test_case_001",
    "symbol": "SOL-PERP",
    "timeframe_minutes": 5,
    "decision_start_index": 0,
    "decision_end_index": 0,
    "hidden_future_start_index": 1,
    "expected_learning_focus_v1": [],
    "candles": [
        {"timestamp": "2024-01-01T00:00:00Z", "open": 100.0, "high": 101.0,
         "low": 99.0, "close": 100.5, "volume": 1000},
    ],
}


def _write_tmp(obj) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(obj, f)
    f.close()
    return f.name


def test_load_case_valid():
    path = _write_tmp(VALID_CASE)
    try:
        case = load_case(path)
        assert case["case_id"] == "test_case_001"
        assert case["symbol"] == "SOL-PERP"
        assert len(case["candles"]) == 1
    finally:
        os.unlink(path)


def test_load_case_wrong_schema():
    bad = dict(VALID_CASE, schema="wrong_schema_v1")
    path = _write_tmp(bad)
    try:
        with pytest.raises(ValueError, match="schema must be"):
            load_case(path)
    finally:
        os.unlink(path)


def test_load_case_missing_field():
    bad = {k: v for k, v in VALID_CASE.items() if k != "symbol"}
    path = _write_tmp(bad)
    try:
        with pytest.raises(ValueError, match="missing fields"):
            load_case(path)
    finally:
        os.unlink(path)


def test_load_cases_list():
    path = _write_tmp([VALID_CASE, dict(VALID_CASE, case_id="test_case_002")])
    try:
        cases = load_cases(path)
        assert len(cases) == 2
        assert cases[1]["case_id"] == "test_case_002"
    finally:
        os.unlink(path)


def test_load_cases_wrapper():
    path = _write_tmp({"cases": [VALID_CASE]})
    try:
        cases = load_cases(path)
        assert len(cases) == 1
    finally:
        os.unlink(path)


def test_load_cases_single_object():
    path = _write_tmp(VALID_CASE)
    try:
        cases = load_cases(path)
        assert len(cases) == 1
        assert cases[0]["case_id"] == "test_case_001"
    finally:
        os.unlink(path)
