"""Policy framework v1 — schema, attach wiring, operator echo."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory.hunter_planner import resolve_repo_root
from renaissance_v4.game_theory.memory_bundle import BUNDLE_APPLY_WHITELIST
from renaissance_v4.game_theory.operator_recipes import build_scenarios_for_recipe, recipe_meta_by_id
from renaissance_v4.game_theory.policy_framework import (
    DEFAULT_BASELINE_POLICY_FRAMEWORK_REL,
    attach_policy_framework_audits,
    load_policy_framework,
    validate_policy_framework_v1,
)
from renaissance_v4.game_theory.run_memory import build_operator_run_audit
from renaissance_v4.game_theory.scenario_contract import extract_scenario_echo_fields, validate_scenarios
from renaissance_v4.game_theory.web_app import _prepare_parallel_payload


def _fw_path() -> Path:
    root = resolve_repo_root()
    return (root / DEFAULT_BASELINE_POLICY_FRAMEWORK_REL).resolve()


def test_baseline_policy_framework_schema_and_tunable_surface() -> None:
    doc = load_policy_framework(_fw_path())
    root = resolve_repo_root()
    ok, msgs = validate_policy_framework_v1(doc, repo_root=root)
    assert ok, msgs
    keys = (
        (doc.get("allowed_adaptations") or {})
        .get("tunable_surface", {})
        .get("memory_bundle_apply_keys")
    )
    assert isinstance(keys, list)
    assert set(keys) == set(BUNDLE_APPLY_WHITELIST)


def test_recipe_meta_includes_policy_framework_path() -> None:
    meta = recipe_meta_by_id("pattern_learning")
    assert meta is not None
    assert meta.get("policy_framework_path") == DEFAULT_BASELINE_POLICY_FRAMEWORK_REL


def test_operator_mode_cards_for_curated_patterns() -> None:
    for rid in ("pattern_learning", "reference_comparison"):
        meta = recipe_meta_by_id(rid)
        assert meta is not None
        card = meta.get("operator_mode_card_v1")
        assert isinstance(card, dict)
        sections = card.get("sections")
        assert isinstance(sections, list) and len(sections) >= 6
        for row in sections:
            assert isinstance(row.get("k"), str) and row["k"].strip()
            assert isinstance(row.get("v"), str) and row["v"].strip()


def test_build_scenarios_attaches_policy_framework_path() -> None:
    scenarios = build_scenarios_for_recipe("pattern_learning")
    assert len(scenarios) == 1
    assert scenarios[0].get("policy_framework_path") == DEFAULT_BASELINE_POLICY_FRAMEWORK_REL


def test_attach_policy_framework_audits_resolved_manifest() -> None:
    scenarios = build_scenarios_for_recipe("pattern_learning")
    for s in scenarios:
        s["manifest_path"] = str(Path(s["manifest_path"]).expanduser().resolve())
    ok, msgs = attach_policy_framework_audits(scenarios)
    assert ok, msgs
    assert scenarios[0].get("policy_framework_audit", {}).get("framework_id") == "baseline_v1_policy_framework"


def test_attach_rejects_manifest_mismatch() -> None:
    scenarios = build_scenarios_for_recipe("pattern_learning")
    scenarios[0]["manifest_path"] = str(Path(__file__).resolve())  # wrong file
    ok, _ = attach_policy_framework_audits(scenarios)
    assert ok is False


def test_validate_scenarios_accepts_framework_keys() -> None:
    scenarios = build_scenarios_for_recipe("pattern_learning")
    scenarios[0]["manifest_path"] = str(Path(scenarios[0]["manifest_path"]).expanduser().resolve())
    ok, _ = attach_policy_framework_audits(scenarios)
    assert ok
    v_ok, v_msgs = validate_scenarios(scenarios, require_hypothesis=False)
    assert v_ok, v_msgs
    extra = [m for m in v_msgs if "undocumented keys" in m]
    assert not extra


def test_prepare_parallel_payload_echoes_framework() -> None:
    prep = _prepare_parallel_payload(
        {
            "operator_recipe_id": "pattern_learning",
            "evaluation_window_mode": "12",
            "evaluation_window_custom_months": None,
            "scenarios_json": "[]",
        }
    )
    assert prep["ok"] is True
    audit = prep["operator_batch_audit"].get("policy_framework_audit")
    assert isinstance(audit, dict)
    assert audit.get("framework_id") == "baseline_v1_policy_framework"
    scen_audit = prep["scenarios"][0].get("policy_framework_audit")
    assert scen_audit == audit


def test_extract_scenario_echo_includes_framework() -> None:
    scenarios = build_scenarios_for_recipe("pattern_learning")
    scenarios[0]["manifest_path"] = str(Path(scenarios[0]["manifest_path"]).expanduser().resolve())
    assert attach_policy_framework_audits(scenarios)[0]
    echo = extract_scenario_echo_fields(scenarios[0])
    assert "policy_framework_audit" in echo


def test_build_operator_run_audit_includes_framework() -> None:
    scenarios = build_scenarios_for_recipe("pattern_learning")
    scenarios[0]["manifest_path"] = str(Path(scenarios[0]["manifest_path"]).expanduser().resolve())
    assert attach_policy_framework_audits(scenarios)[0]
    aud = build_operator_run_audit(scenarios[0], {"replay_data_audit": {"slicing_applied": False}})
    assert aud.get("policy_framework_audit", {}).get("framework_id") == "baseline_v1_policy_framework"
