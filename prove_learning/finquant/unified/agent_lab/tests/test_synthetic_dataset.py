"""Tests for synthetic_dataset.py"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from synthetic_dataset import generate_dataset, REGIMES
from pathlib import Path


def test_generates_requested_count():
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest = generate_dataset(out_dir=Path(tmpdir), case_count=20, seed=42)
        assert manifest["case_count"] == 20
        assert sum(manifest["regime_counts_v1"].values()) == 20


def test_all_regimes_represented_when_count_large():
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest = generate_dataset(out_dir=Path(tmpdir), case_count=25, seed=42)
        for regime in REGIMES:
            assert manifest["regime_counts_v1"].get(regime, 0) > 0


def test_cases_have_valid_schema():
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest = generate_dataset(out_dir=Path(tmpdir), case_count=10, seed=42)
        for path in manifest["case_paths_v1"]:
            case = json.load(open(path))
            assert case["schema"] == "finquant_lifecycle_case_v1"
            assert case["timeframe_minutes"] == 15
            assert case["decision_start_index"] < case["hidden_future_start_index"]
            assert len(case["candles"]) > case["hidden_future_start_index"]


def test_deterministic_with_same_seed():
    with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
        m1 = generate_dataset(out_dir=Path(tmpdir1), case_count=5, seed=42)
        m2 = generate_dataset(out_dir=Path(tmpdir2), case_count=5, seed=42)
        c1 = json.load(open(m1["case_paths_v1"][0]))
        c2 = json.load(open(m2["case_paths_v1"][0]))
        assert c1["candles"] == c2["candles"]
