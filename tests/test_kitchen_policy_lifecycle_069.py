"""DV-069 — shared policy lifecycle store."""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.kitchen_policy_lifecycle import (
    STATE_ASSIGNED_RUNTIME_CONFIRMED,
    STATE_EXTERNAL_OVERRIDE,
    STATE_FAILED,
    STATE_RETIRED,
    STATE_RUNTIME_ELIGIBLE,
    apply_intake_report_to_lifecycle,
    get_entry,
    lifecycle_store_path,
    reconcile_with_drift,
    set_retired,
)
from renaissance_v4.kitchen_runtime_assignment import MECHANICAL_CANDIDATE_POLICY_ID, drift_status


def _copy_registry(tmp: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json"
    dst = tmp / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def test_intake_pass_mechanical_sets_runtime_eligible(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    rep = {
        "submission_id": "sub_mechanical_01",
        "execution_target": "jupiter",
        "pass": True,
        "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
    }
    apply_intake_report_to_lifecycle(tmp_path, rep)
    e = get_entry(tmp_path, "sub_mechanical_01", "jupiter")
    assert e is not None
    assert e["state"] == STATE_RUNTIME_ELIGIBLE
    assert e.get("runtime_eligible") is True


def test_intake_fail_sets_failed(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    rep = {
        "submission_id": "sub_fail_01",
        "execution_target": "jupiter",
        "pass": False,
        "candidate_policy_id": None,
    }
    apply_intake_report_to_lifecycle(tmp_path, rep)
    e = get_entry(tmp_path, "sub_fail_01", "jupiter")
    assert e is not None
    assert e["state"] == STATE_FAILED


def test_reconcile_match_sets_assigned_confirmed(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    row = {
        "submission_id": "s1",
        "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
        "active_runtime_policy_id": "jup_kitchen_mechanical_v1",
    }
    rt = {"ok": True, "active_policy": "jup_kitchen_mechanical_v1"}
    drift = drift_status(tmp_path, "jupiter", row, rt)
    assert drift["state"] == "match"
    reconcile_with_drift(tmp_path, "jupiter", row, drift, rt)
    e = get_entry(tmp_path, "s1", "jupiter")
    assert e is not None
    assert e["state"] == STATE_ASSIGNED_RUNTIME_CONFIRMED


def test_reconcile_diverged_from_confirmed_is_external_override(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    rep = {
        "submission_id": "s2",
        "execution_target": "jupiter",
        "pass": True,
        "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
    }
    apply_intake_report_to_lifecycle(tmp_path, rep)
    reconcile_with_drift(
        tmp_path,
        "jupiter",
        {
            "submission_id": "s2",
            "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
            "active_runtime_policy_id": "jup_kitchen_mechanical_v1",
        },
        {"state": "match"},
        {"ok": True, "active_policy": "jup_kitchen_mechanical_v1"},
    )
    e = get_entry(tmp_path, "s2", "jupiter")
    assert e["state"] == STATE_ASSIGNED_RUNTIME_CONFIRMED
    drift2 = drift_status(
        tmp_path,
        "jupiter",
        {
            "submission_id": "s2",
            "active_runtime_policy_id": "jup_kitchen_mechanical_v1",
        },
        {"ok": True, "active_policy": "jup_mc_test"},
    )
    assert drift2["state"] == "runtime_diverged"
    reconcile_with_drift(
        tmp_path,
        "jupiter",
        {
            "submission_id": "s2",
            "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
            "active_runtime_policy_id": "jup_kitchen_mechanical_v1",
        },
        drift2,
        {"ok": True, "active_policy": "jup_mc_test"},
    )
    e2 = get_entry(tmp_path, "s2", "jupiter")
    assert e2["state"] == STATE_EXTERNAL_OVERRIDE


def test_archive_sets_retired(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    rep = {
        "submission_id": "s3",
        "execution_target": "jupiter",
        "pass": True,
        "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
    }
    apply_intake_report_to_lifecycle(tmp_path, rep)
    set_retired(tmp_path, "s3", "jupiter", retired=True)
    e = get_entry(tmp_path, "s3", "jupiter")
    assert e is not None
    assert e["state"] == STATE_RETIRED


def test_lifecycle_store_path_under_state(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    p = lifecycle_store_path(tmp_path)
    assert p.name == "kitchen_policy_lifecycle_v1.json"
    assert p.parent.name == "state"
