"""DV-070 — Kitchen assignment store collapses to runtime read-back."""

from __future__ import annotations

from pathlib import Path

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
    row2 = get_assignment(tmp_path, "jupiter")
    assert row2 and row2["active_runtime_policy_id"] == "jup_mc_test"


def test_build_payload_has_match_after_reconcile(tmp_path: Path, monkeypatch) -> None:
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
    assert p.get("drift", {}).get("state") == "match"
    assert p.get("assignment", {}).get("active_runtime_policy_id") == "jup_mc_test"
