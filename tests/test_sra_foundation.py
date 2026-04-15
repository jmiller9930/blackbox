"""DV-ARCH-SRA-FOUNDATION-030 — SRA hypothesis → manifest + storage helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_generate_manifest_from_hypothesis_deterministic() -> None:
    from renaissance_v4.research.sra_foundation import generate_manifest_from_hypothesis

    h = {
        "hypothesis_id": "h_test_det_001",
        "description": "Two-signal slice",
        "parameters": {
            "signal_modules": ["trend_continuation", "mean_reversion_fade"],
            "strategy_id": "sra_h_test_det_001",
        },
        "created_at": "2026-04-14T12:00:00+00:00",
        "created_by": "test",
    }
    a = generate_manifest_from_hypothesis(h)
    b = generate_manifest_from_hypothesis(h)
    assert a == b
    assert a["schema"] == "strategy_manifest_v1"
    assert a["signal_modules"] == ["trend_continuation", "mean_reversion_fade"]
    assert a["strategy_id"] == "sra_h_test_det_001"


def test_generate_manifest_rejects_unknown_signal() -> None:
    from renaissance_v4.research.sra_foundation import generate_manifest_from_hypothesis

    h = {
        "hypothesis_id": "h_bad_sig",
        "description": "bad",
        "parameters": {"signal_modules": ["not_a_real_signal_module_id"]},
        "created_at": "2026-04-14T12:00:00+00:00",
        "created_by": "test",
    }
    with pytest.raises(ValueError, match="manifest validation failed"):
        generate_manifest_from_hypothesis(h)


def test_append_and_get_hypothesis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.research import sra_foundation as sf

    monkeypatch.setattr(sf, "hypotheses_jsonl_path", lambda: tmp_path / "hypotheses.jsonl")
    rec = {
        "hypothesis_id": "h_line_1",
        "description": "d",
        "parameters": {},
        "created_at": "2026-04-14T00:00:00+00:00",
        "created_by": "human",
    }
    sf.append_hypothesis(rec)
    got = sf.get_hypothesis_by_id("h_line_1")
    assert got == rec


def test_write_manifest_for_run_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.research import sra_foundation as sf

    monkeypatch.setattr(sf, "_rv4_root", lambda: tmp_path / "renaissance_v4")
    man = {
        "schema": "strategy_manifest_v1",
        "manifest_version": "1.0",
        "strategy_id": "x",
        "strategy_name": "n",
        "baseline_tag": "RenaissanceV4_baseline_v1",
        "symbol": "SOLUSDT",
        "timeframe": "5m",
        "factor_pipeline": "feature_set_v1",
        "signal_modules": ["trend_continuation"],
        "regime_module": "regime_v1_default",
        "risk_model": "risk_governor_v1_default",
        "fusion_module": "fusion_geometric_v1",
        "execution_template": "execution_manager_v1_default",
        "stop_target_template": "none",
        "experiment_type": "replay_full_history",
    }
    p = sf.write_manifest_for_run(man, "hid", "exp_20260414_abc12345")
    assert p.name.startswith("sra_")
    assert p.suffix == ".json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["strategy_id"] == "x"
