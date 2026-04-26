"""
GT_DIRECTIVE_026AI — mandatory scenario proof (artifacts + field checks + optional live gateway).

Runs all proof scenarios, writes JSON bundles under docs/proof/reasoning_router_v1/scenario_artifacts_v1/,
and optionally exercises the real OpenAI Responses API when OPENAI_API_KEY is set.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from renaissance_v4.game_theory.unified_agent_v1.gt_directive_026ai_proof_scenarios_v1 import (
    PROOF_BUNDLE_SCHEMA_V1,
    all_mandatory_verification_true_v1,
    run_scenario_01_local_only_external_disabled_v1,
    run_scenario_02_missing_api_key_v1,
    run_scenario_03_insufficient_funds_or_quota_v1,
    run_scenario_03a_quota_exceeded_v1,
    run_scenario_04_budget_exceeded_v1,
    run_scenario_05_successful_escalation_mocked_v1,
    run_scenario_06_schema_validation_failed_v1,
    run_scenario_07_external_disagrees_engine_unchanged_v1,
    run_scenario_08_rate_limited_v1,
    run_scenario_08b_provider_unavailable_v1,
    build_live_026ai_closure_artifact_v1,
    security_scan_serialized_v1,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = (
    REPO_ROOT / "docs" / "proof" / "reasoning_router_v1" / "scenario_artifacts_v1"
)


@pytest.fixture(autouse=True)
def _trace_off_for_proof(monkeypatch):
    monkeypatch.setenv("PATTERN_GAME_LEARNING_TRACE_EVENTS", "0")


def _write_bundle(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


SCENARIOS = [
    ("S01_local_only.json", run_scenario_01_local_only_external_disabled_v1),
    ("S02_missing_api_key.json", run_scenario_02_missing_api_key_v1),
    ("S03_insufficient_funds.json", lambda: run_scenario_03_insufficient_funds_or_quota_v1("insufficient_funds_v1")),
    ("S03a_quota_exceeded.json", run_scenario_03a_quota_exceeded_v1),
    ("S04_budget_exceeded.json", run_scenario_04_budget_exceeded_v1),
    ("S05_success_external_mocked.json", run_scenario_05_successful_escalation_mocked_v1),
    ("S06_schema_failure.json", run_scenario_06_schema_validation_failed_v1),
    ("S07_disagreement_engine_unchanged.json", run_scenario_07_external_disagrees_engine_unchanged_v1),
    ("S08_rate_limited.json", run_scenario_08_rate_limited_v1),
    ("S08b_provider_unavailable.json", run_scenario_08b_provider_unavailable_v1),
]


def test_mandatory_proof_scenarios_json_artifacts_and_fields():
    """Writes one JSON bundle per scenario; each must pass field + security checks."""
    index: dict = {
        "schema": "gt_directive_026ai_proof_index_v1",
        "proof_bundle_schema": PROOF_BUNDLE_SCHEMA_V1,
        "artifacts": [],
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for fname, fn in SCENARIOS:
        bundle = fn()
        assert bundle.get("schema") == PROOF_BUNDLE_SCHEMA_V1
        assert bundle.get("all_required_fields_ok_v1") is True, bundle.get("required_fields_verification_v1")
        assert bundle.get("security_serialized_scan_v1", {}).get("ok") is True
        ver = bundle.get("required_fields_verification_v1") or {}
        assert all_mandatory_verification_true_v1(ver)
        out_path = ARTIFACT_DIR / fname
        _write_bundle(out_path, bundle)
        index["artifacts"].append(
            {
                "file": str(out_path.relative_to(REPO_ROOT)),
                "scenario_id": bundle.get("scenario_id"),
                "final_route_v1": bundle.get("final_route_v1"),
            }
        )
    _write_bundle(ARTIFACT_DIR / "index_v1.json", index)
    for p in (ARTIFACT_DIR / "index_v1.json", ARTIFACT_DIR / "S01_local_only.json"):
        assert p.is_file(), f"expected artifact {p}"


def test_s03_funding_l1_billing_link_present_for_quota_and_funds():
    a = run_scenario_03_insufficient_funds_or_quota_v1("insufficient_funds_v1")
    assert a.get("funding_l1_link_matches_v1") is True
    b = run_scenario_03a_quota_exceeded_v1()
    assert b.get("funding_l1_link_matches_v1") is True


def test_s07_action_unchanged_and_disagree_recorded():
    b = run_scenario_07_external_disagrees_engine_unchanged_v1()
    assert b.get("engine_action_unchanged_v1")
    ext = b.get("external_review_suggested_action_v1")
    assert ext and ext != b.get("engine_action_unchanged_v1")
    ex = b.get("entry_reasoning_excerpt_v1") or {}
    assert ex.get("router_external_influence_v1") == "advisory_no_execution_authority"


@pytest.mark.integration
def test_openai_responses_smoke_uses_key_from_env_and_never_exposes_in_output():
    """
    GT_DIRECTIVE_026AI lab: ``OPENAI_API_KEY`` is read from the process environment only.
    Always writes ``LIVE_SMOKE_openai_responses.json`` (missing/invalid key → blocker recorded, **pytest passes**;
    valid key + API success → same file with ``smoke_ok`` true and full closure checks).
    """
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / "LIVE_SMOKE_openai_responses.json"

    payload = build_live_026ai_closure_artifact_v1()
    assert payload.get("schema") == "gt_directive_026ai_live_smoke_v1"
    scan = payload.get("security_full_artifact_scan_v1") or {}
    assert scan.get("ok") is True, scan
    raw = json.dumps(payload, default=str)
    assert "sk-" not in raw
    assert "Bearer " not in raw
    _write_bundle(out_path, payload)

    smoke = payload.get("adapter_responses_api_smoke_v1") or {}
    if not (os.environ.get("OPENAI_API_KEY") or "").strip():
        assert smoke.get("smoke_ok") is not True
        return
    if not smoke.get("smoke_ok"):
        return

    assert smoke.get("provider") == "openai"
    assert str(smoke.get("model_requested") or "").strip() != ""
    assert str(smoke.get("model_resolved") or "").strip() != ""
    assert smoke.get("input_tokens") is not None
    assert smoke.get("output_tokens") is not None
    assert smoke.get("total_tokens") is not None
    assert smoke.get("latency_ms") is not None

    assert payload.get("closure_complete_v1") is True, payload
    rp = payload.get("reasoning_router_unified_path_v1") or {}
    assert not (rp.get("entry_reasoning_errors") or []), rp.get("entry_reasoning_errors")
    dec_route = str((rp.get("final_route_v1") or ""))
    assert dec_route in (
        "external_review",
        "external_failed_fallback_local",
        "local_only",
    ), dec_route
