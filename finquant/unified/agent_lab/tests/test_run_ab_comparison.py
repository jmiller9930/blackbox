"""Tests for run_ab_comparison.py — uses synthetic dataset."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

from synthetic_dataset import generate_dataset
from run_ab_comparison import run_ab


def _write_config(tmpdir: str) -> str:
    config = {
        "schema": "finquant_agent_lab_config_v1",
        "agent_id": "finquant",
        "mode": "deterministic_stub_v1",
        "use_llm_v1": False,
        "memory_store_path": "",
        "retrieval_enabled_default_v1": False,
        "write_outputs_v1": True,
    }
    config_path = os.path.join(tmpdir, "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f)
    return config_path


def test_run_ab_produces_comparison_artifact():
    with tempfile.TemporaryDirectory() as tmpdir:
        cases_dir = Path(tmpdir) / "cases"
        generate_dataset(out_dir=cases_dir, case_count=15, seed=99)

        config_path = _write_config(tmpdir)
        manifest = run_ab(
            cases_dir=str(cases_dir),
            config_path=config_path,
            output_dir=str(Path(tmpdir) / "outputs"),
            run_a_fraction=0.6,
            interval="15m",
            data_window_months=18,
        )
        assert os.path.exists(manifest["comparison_path_v1"])
        comparison = json.load(open(manifest["comparison_path_v1"]))
        assert comparison["schema"] == "finquant_run_ab_comparison_v1"
        assert "run_a_metrics_v1" in comparison
        assert "run_b_metrics_v1" in comparison


def test_run_a_produces_learning_units():
    with tempfile.TemporaryDirectory() as tmpdir:
        cases_dir = Path(tmpdir) / "cases"
        generate_dataset(out_dir=cases_dir, case_count=10, seed=99)

        config_path = _write_config(tmpdir)
        manifest = run_ab(
            cases_dir=str(cases_dir),
            config_path=config_path,
            output_dir=str(Path(tmpdir) / "outputs"),
            run_a_fraction=0.7,
        )
        snap_a = manifest["snapshot_after_a_v1"]
        assert snap_a["total_units_v1"] > 0


def test_run_ab_writes_observations_jsonl():
    with tempfile.TemporaryDirectory() as tmpdir:
        cases_dir = Path(tmpdir) / "cases"
        generate_dataset(out_dir=cases_dir, case_count=10, seed=99)

        config_path = _write_config(tmpdir)
        manifest = run_ab(
            cases_dir=str(cases_dir),
            config_path=config_path,
            output_dir=str(Path(tmpdir) / "outputs"),
            run_a_fraction=0.7,
        )
        cycle_dir = Path(manifest["cycle_dir"])
        assert (cycle_dir / "run_a_learning_observations.jsonl").exists()
        assert (cycle_dir / "run_b_learning_observations.jsonl").exists()


def test_verdict_has_required_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        cases_dir = Path(tmpdir) / "cases"
        generate_dataset(out_dir=cases_dir, case_count=12, seed=99)
        config_path = _write_config(tmpdir)
        manifest = run_ab(
            cases_dir=str(cases_dir),
            config_path=config_path,
            output_dir=str(Path(tmpdir) / "outputs"),
            run_a_fraction=0.7,
        )
        comparison = json.load(open(manifest["comparison_path_v1"]))
        verdict = comparison["verdict_v1"]
        assert verdict["overall_v1"] in ("PASS", "FAIL")
        assert isinstance(verdict["successes_v1"], list)
        assert isinstance(verdict["issues_v1"], list)
