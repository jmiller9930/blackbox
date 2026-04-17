"""Explicit POST /api/v1/renaissance/runtime-policy-checkin — trade-surface → Kitchen handshake."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.kitchen_policy_ledger import ledger_entries_for_target, read_ledger
from renaissance_v4.kitchen_runtime_assignment import (
    apply_runtime_policy_checkin,
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


def test_checkin_rebinds_to_matching_candidate_submission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    _write_pass_jupiter_candidate(tmp_path, "sid_mc", "jup_v4")
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")

    def fake_query(*_a: object, **_k: object):
        return {"ok": True, "active_policy": "jup_v4", "execution_target": "jupiter"}

    monkeypatch.setattr(
        "renaissance_v4.kitchen_runtime_assignment.query_runtime_truth",
        fake_query,
    )
    r = apply_runtime_policy_checkin(
        tmp_path,
        "jupiter",
        "jup_v4",
        change_source="trade_surface_manual",
    )
    assert r.get("ok") is True
    assert r.get("reconcile_linkage") == "candidate_rebound"
    row = get_assignment(tmp_path, "jupiter")
    assert row and row.get("submission_id") == "sid_mc"
    assert row.get("active_runtime_policy_id") == "jup_v4"
    tail = ledger_entries_for_target(tmp_path, "jupiter", limit=5)
    assert any(e.get("source") == "runtime_checkin" for e in tail)


def test_checkin_unlinks_when_approved_runtime_has_no_candidate_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")

    def fake_query(*_a: object, **_k: object):
        return {"ok": True, "active_policy": "jup_v4", "execution_target": "jupiter"}

    monkeypatch.setattr(
        "renaissance_v4.kitchen_runtime_assignment.query_runtime_truth",
        fake_query,
    )
    r = apply_runtime_policy_checkin(tmp_path, "jupiter", "jup_v4")
    assert r.get("ok") is True
    assert r.get("reconcile_linkage") == "external_unlinked"
    row = get_assignment(tmp_path, "jupiter")
    assert row and row.get("submission_id") == ""
    assert row.get("active_runtime_policy_id") == "jup_v4"


def test_checkin_rejects_runtime_verify_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")

    def fake_query(*_a: object, **_k: object):
        return {"ok": True, "active_policy": "jup_v4", "execution_target": "jupiter"}

    monkeypatch.setattr(
        "renaissance_v4.kitchen_runtime_assignment.query_runtime_truth",
        fake_query,
    )
    r = apply_runtime_policy_checkin(tmp_path, "jupiter", "jup_mc2")
    assert r.get("ok") is False
    assert r.get("error") == "runtime_verify_mismatch"


def test_checkin_ledger_entry_runtime_checkin_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")

    def fake_query(*_a: object, **_k: object):
        return {"ok": True, "active_policy": "jup_v4", "execution_target": "jupiter"}

    monkeypatch.setattr(
        "renaissance_v4.kitchen_runtime_assignment.query_runtime_truth",
        fake_query,
    )
    apply_runtime_policy_checkin(tmp_path, "jupiter", "jup_v4", change_source="trade_surface_manual")
    led = read_ledger(tmp_path)
    entries = [e for e in led.get("entries", []) if e.get("execution_target") == "jupiter"]
    assert entries
    last = entries[-1]
    assert last.get("source") == "runtime_checkin"
    assert "runtime_policy_checkin" in str(last.get("detail") or "")


def test_checkin_no_change_when_kitchen_already_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    _minimal_store(tmp_path, "jup_v4")

    def fake_query(*_a: object, **_k: object):
        return {"ok": True, "active_policy": "jup_v4", "execution_target": "jupiter"}

    monkeypatch.setattr(
        "renaissance_v4.kitchen_runtime_assignment.query_runtime_truth",
        fake_query,
    )
    before = get_assignment(tmp_path, "jupiter")
    r = apply_runtime_policy_checkin(tmp_path, "jupiter", "jup_v4")
    assert r.get("ok") is True
    assert r.get("reconcile_linkage") == "no_change"
    after = get_assignment(tmp_path, "jupiter")
    assert (before or {}).get("active_runtime_policy_id") == (after or {}).get("active_runtime_policy_id")


def test_reconcile_production_checkin_tags_ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    _minimal_store(tmp_path, "jup_kitchen_mechanical_v1")
    rt = {"ok": True, "active_policy": "jup_v4", "execution_target": "jupiter"}
    row = get_assignment(tmp_path, "jupiter")
    out = reconcile_assignment_store_to_runtime_truth(
        tmp_path,
        "jupiter",
        rt,
        row,
        ledger_source="runtime_checkin",
        ledger_detail="runtime_policy_checkin:unit",
        reconcile_source_tag="runtime_policy_checkin",
    )
    assert out is not None
    tail = ledger_entries_for_target(tmp_path, "jupiter", limit=3)
    assert tail[-1].get("source") == "runtime_checkin"
    assert tail[-1].get("detail") == "runtime_policy_checkin:unit"
