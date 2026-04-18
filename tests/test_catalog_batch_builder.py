"""Tests for Chef path: :mod:`renaissance_v4.game_theory.catalog_batch_builder`."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory.catalog_batch_builder import (
    build_atr_sweep_scenarios,
    catalog_batch_builder_meta,
)
from renaissance_v4.game_theory.scenario_contract import validate_scenarios

_REPO = Path(__file__).resolve().parent.parent
_BASELINE = _REPO / "renaissance_v4/configs/manifests/baseline_v1_recipe.json"


def test_catalog_batch_builder_meta() -> None:
    m = catalog_batch_builder_meta()
    assert m.get("modes") == ["atr_sweep"]
    assert "default_max_scenarios" in m


def test_build_atr_sweep_truncates_and_hypothesis() -> None:
    scenarios = build_atr_sweep_scenarios(
        _BASELINE,
        max_scenarios=5,
        scenario_id_prefix="tchef",
    )
    assert len(scenarios) == 5
    for i, s in enumerate(scenarios):
        assert s["scenario_id"].startswith("tchef_")
        assert "manifest_path" in s
        assert s["manifest_path"].replace("\\", "/").startswith("renaissance_v4/")
        assert "agent_explanation" in s
        assert "hypothesis" in s["agent_explanation"]
        assert "Chef ATR sweep" in s["agent_explanation"]["hypothesis"]
    ok, msgs = validate_scenarios(scenarios, require_hypothesis=True)
    assert ok, msgs


def test_build_atr_sweep_explicit_pairs() -> None:
    scenarios = build_atr_sweep_scenarios(
        _BASELINE,
        pairs=[(1.5, 3.0), (2.0, 4.0)],
        scenario_id_prefix="pair",
    )
    assert len(scenarios) == 2
    assert scenarios[0]["atr_stop_mult"] == pytest.approx(1.5)
    assert scenarios[0]["atr_target_mult"] == pytest.approx(3.0)


def test_manifest_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        build_atr_sweep_scenarios(_REPO / "renaissance_v4/configs/manifests/nope_nope.json")


def test_api_catalog_batch_meta_and_generate() -> None:
    from renaissance_v4.game_theory.web_app import create_app

    app = create_app()
    cli = app.test_client()
    mr = cli.get("/api/catalog-batch-meta")
    assert mr.status_code == 200
    mj = mr.get_json()
    assert mj.get("ok") is True
    assert "default_stop_values" in mj

    gr = cli.post(
        "/api/catalog-batch-generate",
        json={
            "mode": "atr_sweep",
            "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
            "max_scenarios": 3,
        },
    )
    assert gr.status_code == 200
    gj = gr.get_json()
    assert gj.get("ok") is True
    assert gj.get("count") == 3
    assert len(gj["scenarios"]) == 3


def test_api_catalog_batch_generate_missing_manifest_404() -> None:
    from renaissance_v4.game_theory.web_app import create_app

    app = create_app()
    cli = app.test_client()
    gr = cli.post(
        "/api/catalog-batch-generate",
        json={"mode": "atr_sweep", "manifest_path": "renaissance_v4/configs/manifests/does_not_exist_x.json"},
    )
    assert gr.status_code == 404
