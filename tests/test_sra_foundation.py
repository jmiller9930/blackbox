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


def test_generate_variants_from_hypothesis_appends_and_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from renaissance_v4.research import sra_foundation as sf

    monkeypatch.setattr(sf, "hypotheses_jsonl_path", lambda: tmp_path / "hypotheses.jsonl")
    base = {
        "hypothesis_id": "base_var_test",
        "description": "base",
        "parameters": {
            "signal_modules": [
                "trend_continuation",
                "mean_reversion_fade",
                "breakout_expansion",
            ],
            "strategy_id": "sra_base_var_test",
        },
        "created_at": "2026-04-14T00:00:00+00:00",
        "created_by": "test",
    }
    sf.append_hypothesis(base)

    ids = sf.generate_variants_from_hypothesis("base_var_test", 3)
    assert len(ids) == 3
    assert all("base_var_test_var_" in x for x in ids)

    for vid in ids:
        h = sf.get_hypothesis_by_id(vid)
        assert h is not None
        assert h.get("parent_hypothesis_id") == "base_var_test"
        assert h.get("variant_type") in ("signal_toggle", "mc_config_offset")
        sf.generate_manifest_from_hypothesis(h)


def test_rank_hypothesis_variants_ordering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.research import sra_foundation as sf

    results = tmp_path / "hypothesis_results.jsonl"
    lines = [
        {
            "hypothesis_id": "v_degrade",
            "parent_hypothesis_id": "parent_x",
            "classification": "degrade",
            "key_metrics": {"deterministic": {"expectancy": 0.5, "max_drawdown": -0.1, "total_trades": 10}},
        },
        {
            "hypothesis_id": "v_improve_low",
            "parent_hypothesis_id": "parent_x",
            "classification": "improve",
            "key_metrics": {"deterministic": {"expectancy": 0.1, "max_drawdown": -0.2, "total_trades": 5}},
        },
        {
            "hypothesis_id": "v_improve_high",
            "parent_hypothesis_id": "parent_x",
            "classification": "improve",
            "key_metrics": {"deterministic": {"expectancy": 0.3, "max_drawdown": -0.15, "total_trades": 8}},
        },
        {
            "hypothesis_id": "v_inconclusive",
            "parent_hypothesis_id": "parent_x",
            "classification": "inconclusive",
            "key_metrics": {"deterministic": {"expectancy": 0.9, "max_drawdown": -0.01, "total_trades": 99}},
        },
    ]
    results.write_text(
        "\n".join(json.dumps(x, sort_keys=True) for x in lines) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sf, "hypothesis_results_jsonl_path", lambda: results)

    r = sf.rank_hypothesis_variants("parent_x")
    assert r["best_variant"] == "v_improve_high"
    assert r["ordered_variants"][0] == "v_improve_high"
    assert r["ordered_variants"][1] == "v_improve_low"
    assert "v_inconclusive" in r["ordered_variants"]
    assert r["ordered_variants"][-1] == "v_degrade"


def test_run_rank_cli_persists_rankings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.research import sra_foundation as sf

    res = tmp_path / "hypothesis_results.jsonl"
    res.write_text(
        json.dumps(
            {
                "hypothesis_id": "v1",
                "parent_hypothesis_id": "par",
                "classification": "improve",
                "key_metrics": {"deterministic": {"expectancy": 0.2}},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rank_path = tmp_path / "hypothesis_rankings.json"
    monkeypatch.setattr(sf, "hypothesis_results_jsonl_path", lambda: res)
    monkeypatch.setattr(sf, "hypothesis_rankings_json_path", lambda: rank_path)

    out = sf.run_rank_cli("par")
    assert out["best_variant"] == "v1"
    data = json.loads(rank_path.read_text(encoding="utf-8"))
    assert data["schema"] == "renaissance_v4_hypothesis_rankings_v1"
    assert len(data["rankings"]) == 1
    assert data["rankings"][0]["parent_hypothesis_id"] == "par"


def test_rank_deterministic_tiebreak_hypothesis_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.research import sra_foundation as sf

    results = tmp_path / "hypothesis_results.jsonl"
    lines = [
        {
            "hypothesis_id": "b",
            "parent_hypothesis_id": "p",
            "classification": "improve",
            "key_metrics": {"deterministic": {"expectancy": 1.0, "max_drawdown": -0.1, "total_trades": 1}},
        },
        {
            "hypothesis_id": "a",
            "parent_hypothesis_id": "p",
            "classification": "improve",
            "key_metrics": {"deterministic": {"expectancy": 1.0, "max_drawdown": -0.1, "total_trades": 1}},
        },
    ]
    results.write_text(
        "\n".join(json.dumps(x, sort_keys=True) for x in lines) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sf, "hypothesis_results_jsonl_path", lambda: results)
    r = sf.rank_hypothesis_variants("p")
    assert r["ordered_variants"] == ["a", "b"]


def test_lineage_fields_on_results_shape() -> None:
    from renaissance_v4.research.sra_foundation import _lineage_fields_from_hypothesis

    assert _lineage_fields_from_hypothesis({}) == {}
    out = _lineage_fields_from_hypothesis(
        {"parent_hypothesis_id": "p1", "variant_type": "signal_toggle", "variant_index": 0}
    )
    assert out["parent_hypothesis_id"] == "p1"
    assert out["variant_type"] == "signal_toggle"
    assert out["variant_index"] == 0


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


def test_evaluate_promotion_candidate_eligible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.research import sra_foundation as sf

    res = tmp_path / "hypothesis_results.jsonl"
    res.write_text(
        json.dumps(
            {
                "hypothesis_id": "best1",
                "parent_hypothesis_id": "par_elig",
                "experiment_id": "exp_1",
                "classification": "improve",
                "key_metrics": {
                    "pipeline_ok": True,
                    "deterministic": {
                        "expectancy": 0.1,
                        "total_trades": 10,
                        "max_drawdown": -0.05,
                    },
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rank_path = tmp_path / "hypothesis_rankings.json"
    rank_path.write_text(
        json.dumps(
            {
                "rankings": [
                    {
                        "parent_hypothesis_id": "par_elig",
                        "best_variant": "best1",
                        "ordered_variants": ["best1"],
                    }
                ],
                "schema": "renaissance_v4_hypothesis_rankings_v1",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sf, "hypothesis_results_jsonl_path", lambda: res)
    monkeypatch.setattr(sf, "hypothesis_rankings_json_path", lambda: rank_path)
    monkeypatch.setenv("SRA_PROMOTION_MIN_TRADES", "5")
    monkeypatch.setenv("SRA_PROMOTION_MAX_DRAWDOWN_FLOOR", "-1.0")

    out = sf.evaluate_promotion_candidate("par_elig")
    assert out["eligible"] is True
    assert out["reason"] is None
    assert out["selected_hypothesis_id"] == "best1"
    assert out["experiment_id"] == "exp_1"


def test_evaluate_promotion_candidate_not_improve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.research import sra_foundation as sf

    res = tmp_path / "hypothesis_results.jsonl"
    res.write_text(
        json.dumps(
            {
                "hypothesis_id": "v1",
                "parent_hypothesis_id": "par_x",
                "classification": "inconclusive",
                "key_metrics": {
                    "pipeline_ok": True,
                    "deterministic": {"expectancy": 0.0, "total_trades": 99, "max_drawdown": -0.01},
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rank_path = tmp_path / "hypothesis_rankings.json"
    rank_path.write_text(
        json.dumps(
            {
                "rankings": [
                    {
                        "parent_hypothesis_id": "par_x",
                        "best_variant": "v1",
                        "ordered_variants": ["v1"],
                    }
                ],
                "schema": "renaissance_v4_hypothesis_rankings_v1",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sf, "hypothesis_results_jsonl_path", lambda: res)
    monkeypatch.setattr(sf, "hypothesis_rankings_json_path", lambda: rank_path)

    out = sf.evaluate_promotion_candidate("par_x")
    assert out["eligible"] is False
    assert out["reason"] == "classification_not_improve"


def test_run_promote_cli_writes_promotion_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.research import sra_foundation as sf

    res = tmp_path / "hypothesis_results.jsonl"
    res.write_text(
        json.dumps(
            {
                "hypothesis_id": "b",
                "parent_hypothesis_id": "p_prom",
                "experiment_id": "e",
                "classification": "improve",
                "key_metrics": {
                    "pipeline_ok": True,
                    "deterministic": {"expectancy": 1.0, "total_trades": 8, "max_drawdown": -0.1},
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rank_path = tmp_path / "hypothesis_rankings.json"
    rank_path.write_text(
        json.dumps(
            {
                "rankings": [
                    {
                        "parent_hypothesis_id": "p_prom",
                        "best_variant": "b",
                        "ordered_variants": ["b"],
                    }
                ],
                "schema": "renaissance_v4_hypothesis_rankings_v1",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    prom_path = tmp_path / "promotion_candidates.json"
    monkeypatch.setattr(sf, "hypothesis_results_jsonl_path", lambda: res)
    monkeypatch.setattr(sf, "hypothesis_rankings_json_path", lambda: rank_path)
    monkeypatch.setattr(sf, "promotion_candidates_json_path", lambda: prom_path)
    monkeypatch.setenv("SRA_PROMOTION_MIN_TRADES", "5")

    sf.run_promote_cli("p_prom")
    data = json.loads(prom_path.read_text(encoding="utf-8"))
    assert data["schema"] == "renaissance_v4_promotion_candidates_v1"
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["parent_hypothesis_id"] == "p_prom"
    assert data["candidates"][0]["eligible"] is True
