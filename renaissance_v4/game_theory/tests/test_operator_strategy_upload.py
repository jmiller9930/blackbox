"""Tests for operator strategy idea upload (parse → manifest → validate → persist)."""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.game_theory.operator_strategy_upload import (
    STRATEGY_IDEA_MAGIC,
    build_manifest_v1_from_idea,
    clear_active_operator_strategy,
    parse_strategy_idea_v1,
    process_strategy_idea_upload,
    public_state,
    recommend_pattern_template,
)


def _minimal_good_text(sid: str = "op_upload_test_v1") -> str:
    return f"""{STRATEGY_IDEA_MAGIC}

strategy_id: {sid}
strategy_name: Operator upload test
symbol: SOLUSDT
timeframe: 5m
factor_pipeline: feature_set_v1
signal_modules: trend_continuation, mean_reversion_fade
regime_module: regime_v1_default
risk_model: risk_governor_v1_default
fusion_module: fusion_geometric_v1
execution_template: execution_manager_v1_default
stop_target_template: none
experiment_type: replay_full_history
"""


def test_parse_strategy_idea_v1_ok() -> None:
    fields, errs = parse_strategy_idea_v1(_minimal_good_text())
    assert not errs
    assert fields["strategy_id"] == "op_upload_test_v1"
    assert fields["signal_modules"] == ["trend_continuation", "mean_reversion_fade"]


def test_parse_rejects_bad_header() -> None:
    _, errs = parse_strategy_idea_v1("wrong_header\nstrategy_id: x\n")
    assert errs


def test_parse_rejects_unknown_key() -> None:
    t = _minimal_good_text() + "\nfoo_bar_unknown: x\n"
    _, errs = parse_strategy_idea_v1(t)
    assert any("unsupported key" in e for e in errs)


def test_catalog_validation_unknown_signal() -> None:
    bad = _minimal_good_text().replace(
        "signal_modules: trend_continuation, mean_reversion_fade",
        "signal_modules: trend_continuation, not_a_real_signal",
    )
    fields, perrs = parse_strategy_idea_v1(bad)
    assert not perrs
    m = build_manifest_v1_from_idea(fields)
    from renaissance_v4.manifest.validate import validate_manifest_against_catalog

    verrs = validate_manifest_against_catalog(m)
    assert verrs and any("unknown signal" in e for e in verrs)


def test_process_upload_end_to_end(tmp_path: Path) -> None:
    clear_active_operator_strategy(tmp_path)
    raw = _minimal_good_text("e2e_upload_v1").encode("utf-8")
    res = process_strategy_idea_upload(raw, "idea.txt", repo_root=tmp_path)
    assert res.ok
    assert res.manifest_repo_relative
    man_abs = tmp_path / res.manifest_repo_relative
    assert man_abs.is_file()
    doc = json.loads(man_abs.read_text(encoding="utf-8"))
    assert doc["schema"] == "strategy_manifest_v1"
    assert doc["signal_modules"] == ["trend_continuation", "mean_reversion_fade"]
    st = public_state(tmp_path)
    assert st["has_active_upload"] is True
    assert st["strategy_loaded"] is True


def test_recommend_pattern_default() -> None:
    rec = recommend_pattern_template({"strategy_id": "x", "strategy_name": "baseline tweak", "experiment_type": "replay_full_history"})
    assert rec["primary_recipe_id"] == "pattern_learning"


def test_recommend_pattern_comparison_hint() -> None:
    rec = recommend_pattern_template(
        {"strategy_id": "x", "strategy_name": "tight vs wide comparison", "experiment_type": "replay_full_history"}
    )
    assert rec["primary_recipe_id"] == "reference_comparison"
