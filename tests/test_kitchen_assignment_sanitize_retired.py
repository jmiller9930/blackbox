"""Retired registry ids are cleared from kitchen_runtime_assignment.json on read (default)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from renaissance_v4.kitchen_runtime_assignment import (
    build_kitchen_runtime_read_payload,
    runtime_assignment_store_path,
    sanitize_assignment_store_retired_policy_ids,
)

REPO = Path(__file__).resolve().parents[1]


def _copy_registry(root: Path) -> None:
    dest = root / "renaissance_v4" / "config"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json",
        dest / "kitchen_policy_registry_v1.json",
    )


def test_sanitize_clears_jup_mc_test_when_not_in_registry(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    p = runtime_assignment_store_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    store = {
        "schema": "kitchen_runtime_assignment_store_v1",
        "assignments_by_target": {
            "jupiter": {
                "schema": "kitchen_runtime_assignment_record_v1",
                "execution_target": "jupiter",
                "submission_id": "sid_x",
                "candidate_policy_id": "x",
                "approved_runtime_slot_id": "jup_mc_test",
                "active_runtime_policy_id": "jup_mc_test",
                "assigned_at_utc": "2026-01-01T00:00:00+00:00",
                "operator_action": "test",
                "runtime_adapter": "seanv3_jupiter_active_policy",
            }
        },
    }
    p.write_text(json.dumps(store), encoding="utf-8")

    out = sanitize_assignment_store_retired_policy_ids(tmp_path)
    assert out.get("changed") is True
    assert any(s.get("retired_id") == "jup_mc_test" for s in (out.get("sanitized") or []))

    raw = json.loads(p.read_text(encoding="utf-8"))
    jup = raw["assignments_by_target"]["jupiter"]
    assert jup.get("active_runtime_policy_id") == ""
    assert jup.get("sanitized_retired_id") == "jup_mc_test"


def test_build_kitchen_runtime_read_triggers_sanitize_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    (tmp_path / "renaissance_v4" / "config" / "kitchen_policy_deployment_manifest_v1.json").write_text(
        '{"schema":"kitchen_policy_deployment_manifest_v1","entries":[]}',
        encoding="utf-8",
    )
    p = runtime_assignment_store_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    store = {
        "schema": "kitchen_runtime_assignment_store_v1",
        "assignments_by_target": {
            "jupiter": {
                "schema": "kitchen_runtime_assignment_record_v1",
                "execution_target": "jupiter",
                "submission_id": "",
                "candidate_policy_id": "",
                "approved_runtime_slot_id": "",
                "active_runtime_policy_id": "jup_mc_test",
                "assigned_at_utc": "2026-01-01T00:00:00+00:00",
                "operator_action": "test",
                "runtime_adapter": "",
            }
        },
    }
    p.write_text(json.dumps(store), encoding="utf-8")

    monkeypatch.delenv("KITCHEN_JUPITER_CONTROL_BASE", raising=False)
    monkeypatch.delenv("KITCHEN_JUPITER_OPERATOR_TOKEN", raising=False)

    build_kitchen_runtime_read_payload(tmp_path, "jupiter")

    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["assignments_by_target"]["jupiter"].get("active_runtime_policy_id") == ""


def test_sanitize_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    (tmp_path / "renaissance_v4" / "config" / "kitchen_policy_deployment_manifest_v1.json").write_text(
        '{"schema":"kitchen_policy_deployment_manifest_v1","entries":[]}',
        encoding="utf-8",
    )
    p = runtime_assignment_store_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    store = {
        "schema": "kitchen_runtime_assignment_store_v1",
        "assignments_by_target": {
            "jupiter": {
                "schema": "kitchen_runtime_assignment_record_v1",
                "execution_target": "jupiter",
                "submission_id": "",
                "candidate_policy_id": "",
                "approved_runtime_slot_id": "",
                "active_runtime_policy_id": "jup_mc_test",
                "assigned_at_utc": "2026-01-01T00:00:00+00:00",
                "operator_action": "test",
                "runtime_adapter": "",
            }
        },
    }
    p.write_text(json.dumps(store), encoding="utf-8")
    monkeypatch.setenv("KITCHEN_SANITIZE_RETIRED_POLICY_IDS", "0")
    monkeypatch.delenv("KITCHEN_JUPITER_CONTROL_BASE", raising=False)
    monkeypatch.delenv("KITCHEN_JUPITER_OPERATOR_TOKEN", raising=False)

    build_kitchen_runtime_read_payload(tmp_path, "jupiter")

    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["assignments_by_target"]["jupiter"].get("active_runtime_policy_id") == "jup_mc_test"
