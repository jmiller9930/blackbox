"""DV-070 — Kitchen assignment store collapses to runtime read-back."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.kitchen_runtime_assignment import (
    build_kitchen_runtime_read_payload,
    get_assignment,
    reconcile_assignment_store_to_runtime_truth,
    write_store,
)


def _copy_registry(tmp: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json"
    dst = tmp / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _minimal_store(tmp: Path, active: str) -> None:
    write_store(
        tmp,
        {
            "schema": "kitchen_runtime_assignment_store_v1",
            "assignments_by_target": {
                "jupiter": {
                    "schema": "kitchen_runtime_assignment_record_v1",
                    "execution_target": "jupiter",
                    "submission_id": "sid070",
                    "candidate_policy_id": "kitchen_mechanical_always_long_v1",
                    "approved_runtime_slot_id": "jup_kitchen_mechanical_v1",
                    "active_runtime_policy_id": active,
                    "assigned_at_utc": "2026-01-01T00:00:00+00:00",
                    "operator_action": "kitchen_dashboard_assign",
                    "runtime_adapter": "seanv3_jupiter_active_policy",
                }
            },
        },
    )


def test_reconcile_collapses_kitchen_to_runtime(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")
    rt = {"ok": True, "active_policy": "jup_mc_test", "execution_target": "jupiter"}
    row = get_assignment(tmp_path, "jupiter")
    assert row is not None
    out = reconcile_assignment_store_to_runtime_truth(tmp_path, "jupiter", rt, row)
    assert out is not None
    assert out["active_runtime_policy_id"] == "jup_mc_test"
    assert out.get("reconcile_linkage") == "external_unlinked"
    assert out.get("submission_id") == ""
    row2 = get_assignment(tmp_path, "jupiter")
    assert row2 and row2["active_runtime_policy_id"] == "jup_mc_test"
    assert row2.get("submission_id") == ""


def _write_pass_jupiter_candidate(tmp_path: Path, sid: str, candidate_policy_id: str) -> None:
    sub = tmp_path / "renaissance_v4" / "state" / "policy_intake_submissions" / sid
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "schema": "policy_intake_report_v1",
        "submission_id": sid,
        "pass": True,
        "candidate_policy_id": candidate_policy_id,
        "execution_target": "jupiter",
        "stages": {"stage_1_intake": {"timestamp_utc": "2026-02-01T12:00:00+00:00"}},
    }
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")


def test_reconcile_rebinds_submission_when_intake_matches_runtime(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    _write_pass_jupiter_candidate(tmp_path, "sid_mc", "jup_mc_test")
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")
    rt = {"ok": True, "active_policy": "jup_mc_test", "execution_target": "jupiter"}
    row = get_assignment(tmp_path, "jupiter")
    assert row is not None
    out = reconcile_assignment_store_to_runtime_truth(tmp_path, "jupiter", rt, row)
    assert out is not None
    assert out.get("reconcile_linkage") == "candidate_rebound"
    assert out.get("submission_id") == "sid_mc"
    assert out.get("candidate_policy_id") == "jup_mc_test"
    assert out["active_runtime_policy_id"] == "jup_mc_test"


def test_build_payload_drift_uses_pre_reconcile_so_divergence_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")

    def fake_query(*_a: object, **_k: object):
        return {"ok": True, "active_policy": "jup_mc_test", "execution_target": "jupiter"}

    monkeypatch.setattr(
        "renaissance_v4.kitchen_runtime_assignment.query_runtime_truth",
        fake_query,
    )
    monkeypatch.setenv("KITCHEN_JUPITER_CONTROL_BASE", "http://x")
    monkeypatch.setenv("KITCHEN_JUPITER_OPERATOR_TOKEN", "t")
    p = build_kitchen_runtime_read_payload(tmp_path, "jupiter")
    assert p.get("drift", {}).get("state") == "runtime_diverged"
    assert p.get("drift_basis") == "pre_reconcile_assignment_row"
    assert p.get("assignment", {}).get("active_runtime_policy_id") == "jup_mc_test"
    assert p.get("schema") == "kitchen_runtime_assignment_read_v4"


def test_build_payload_lifecycle_external_override_when_pre_row_was_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DV-069 — drift/lifecycle use pre-reconcile row so external_override is visible after reconcile."""
    _copy_registry(tmp_path)
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")
    from renaissance_v4.kitchen_policy_lifecycle import get_entry, mark_assigned_runtime_confirmed

    mark_assigned_runtime_confirmed(
        tmp_path,
        "sid070",
        "jupiter",
        runtime_policy_id="jup_kitchen_mechanical_v1",
        candidate_policy_id="kitchen_mechanical_always_long_v1",
    )

    def fake_query(*_a: object, **_k: object):
        return {"ok": True, "active_policy": "jup_mc_test", "execution_target": "jupiter"}

    monkeypatch.setattr(
        "renaissance_v4.kitchen_runtime_assignment.query_runtime_truth",
        fake_query,
    )
    monkeypatch.setenv("KITCHEN_JUPITER_CONTROL_BASE", "http://x")
    monkeypatch.setenv("KITCHEN_JUPITER_OPERATOR_TOKEN", "t")
    build_kitchen_runtime_read_payload(tmp_path, "jupiter")
    ent = get_entry(tmp_path, "sid070", "jupiter")
    assert ent is not None
    assert ent.get("state") == "external_override"
