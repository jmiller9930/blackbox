"""Tests for run_ab_comparison.py — uses synthetic dataset."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

from synthetic_dataset import generate_dataset
from run_ab_comparison import _ab_verdict, run_ab


def _metrics(**kwargs):
    base = {
        "cases_v1": 1,
        "decisions_v1": 1,
        "learning_observations_v1": 1,
        "wins_v1": 0,
        "losses_v1": 0,
        "no_trade_correct_v1": 0,
        "no_trade_missed_v1": 0,
        "total_pnl_v1": 0.0,
        "win_rate_v1": 0.0,
        "expectancy_v1": 0.0,
        "evaluation_pass_v1": 0,
        "evaluation_fail_v1": 0,
        "evaluation_info_v1": 1,
        "decision_quality_pass_rate_v1": 0.0,
    }
    base.update(kwargs)
    return base


def test_verdict_fails_when_replay_has_overlap_but_no_behavior_change():
    """Same-case replay without any decision diff is a hard FAIL (not an INFO footnote)."""
    snap = {"total_units_v1": 2, "by_status_v1": {"candidate": 2}}
    proto = {"run_b_mode_v1": "replay_run_a"}
    diff = {
        "overlap_cases_v1": 2,
        "decisions_same_v1": 2,
        "decisions_changed_v1": 0,
        "decision_change_rate_v1": 0.0,
        "first_10_diffs_v1": [],
    }
    a = _metrics(cases_v1=2, learning_observations_v1=2)
    b = _metrics(learning_observations_v1=2)
    verdict = _ab_verdict(a, b, snap, snap, diff, proto)
    assert verdict["overall_v1"] == "FAIL"
    assert any(x.startswith("FAIL:") and "matched Run A" in x for x in verdict["issues_v1"])


def _write_config(tmpdir: str) -> str:
    config = {
        "schema": "finquant_agent_lab_config_v1",
        "agent_id": "finquant",
        "mode": "deterministic_stub_v1",
        "use_llm_v1": False,
        "memory_store_path": "",
        "retrieval_enabled_default_v1": False,
        "write_outputs_v1": True,
        "auto_promote_learning_v1": True,
        # Stub quality gate: permissive so tests work without accumulation cycles
        "retrieval_min_obs_v1": 1,
        "retrieval_min_win_rate_v1": 0.0,
        "retrieval_allow_candidate_v1": True,
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


def test_memory_replay_pack_flips_marginal_case():
    """Golden-path proof: shared governed JSONL + retrieval ranking yields decision diff."""
    lab_root = Path(__file__).resolve().parents[1]
    pack = lab_root / "cases" / "ab_memory_replay_pack"
    assert pack.is_dir()
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _write_config(tmpdir)
        manifest = run_ab(
            cases_dir=str(pack),
            config_path=config_path,
            output_dir=str(Path(tmpdir) / "outputs"),
            run_a_fraction=1.0,
            run_b_mode="replay_run_a",
        )
        comp = json.load(open(manifest["comparison_path_v1"]))
        dd = comp["decision_diff_v1"]
        assert dd["overlap_cases_v1"] == 2
        assert dd["decisions_changed_v1"] >= 1
        flip = next(
            d for d in dd["first_10_diffs_v1"]
            if d["case_id"] == "ab_marginal_memory_flip_v1"
        )
        assert flip["run_a_actions"] == ["NO_TRADE"]
        assert flip["run_b_actions"] == ["ENTER_LONG"]
        assert comp["verdict_v1"]["overall_v1"] == "PASS"


def test_replay_run_a_full_overlap():
    """Run B replays Run A: every Run A case_id must appear in decision diff overlap."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cases_dir = Path(tmpdir) / "cases"
        generate_dataset(out_dir=cases_dir, case_count=12, seed=99)
        config_path = _write_config(tmpdir)
        manifest = run_ab(
            cases_dir=str(cases_dir),
            config_path=config_path,
            output_dir=str(Path(tmpdir) / "outputs"),
            run_a_fraction=0.7,
            run_b_mode="replay_run_a",
        )
        comparison = json.load(open(manifest["comparison_path_v1"]))
        run_a_n = manifest["run_a_case_count_v1"]
        assert comparison["decision_diff_v1"]["overlap_cases_v1"] == run_a_n
        assert manifest["run_b_mode_v1"] == "replay_run_a"


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
