"""BlackBox control plane: deployment ids from manifest only (Jupiter parity)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from renaissance_v4.blackbox_policy_control_plane import (
    get_policy_observability_payload,
    set_active_policy,
)

REPO = Path(__file__).resolve().parents[1]

H = "a" * 64


def _copy_minimal_repo_layout(root: Path) -> None:
    (root / "renaissance_v4" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json",
        root / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json",
    )


def _manifest_bb(root: Path, pid: str, sid: str, content_sha256: str) -> None:
    man = {
        "schema": "kitchen_policy_deployment_manifest_v1",
        "entries": [
            {
                "execution_target": "blackbox",
                "deployed_runtime_policy_id": pid,
                "submission_id": sid,
                "content_sha256": content_sha256,
            }
        ],
    }
    (root / "renaissance_v4" / "config" / "kitchen_policy_deployment_manifest_v1.json").write_text(
        json.dumps(man), encoding="utf-8"
    )


def test_set_active_rejects_id_not_in_manifest(tmp_path: Path) -> None:
    _copy_minimal_repo_layout(tmp_path)
    _manifest_bb(tmp_path, "bb_other_v1", "s1", H)
    ok, err = set_active_policy(tmp_path, "bb_unknown_v1")
    assert ok is False
    assert err == "deployment_not_in_manifest"


def test_set_active_writes_state_from_manifest(tmp_path: Path) -> None:
    _copy_minimal_repo_layout(tmp_path)
    _manifest_bb(tmp_path, "bb_kitchen_mechanical_v1", "sub_x", H)
    ok, err = set_active_policy(tmp_path, "bb_kitchen_mechanical_v1")
    assert ok is True
    assert err is None
    p = tmp_path / "renaissance_v4" / "state" / "blackbox_kitchen_runtime_policy_v1.json"
    assert p.is_file()
    st = json.loads(p.read_text(encoding="utf-8"))
    assert st["active_policy"] == "bb_kitchen_mechanical_v1"
    assert st["submission_id"] == "sub_x"
    assert st["content_sha256"] == H


def test_get_policy_allowed_lists_manifest_only(tmp_path: Path) -> None:
    _copy_minimal_repo_layout(tmp_path)
    man = {
        "schema": "kitchen_policy_deployment_manifest_v1",
        "entries": [
            {
                "execution_target": "blackbox",
                "deployed_runtime_policy_id": "bb_a",
                "submission_id": "s1",
                "content_sha256": H,
            },
            {
                "execution_target": "blackbox",
                "deployed_runtime_policy_id": "bb_b",
                "submission_id": "s2",
                "content_sha256": H,
            },
        ],
    }
    (tmp_path / "renaissance_v4" / "config" / "kitchen_policy_deployment_manifest_v1.json").write_text(
        json.dumps(man), encoding="utf-8"
    )
    pl = get_policy_observability_payload(tmp_path)
    assert pl["allowed_policies"] == ["bb_a", "bb_b"]
    assert pl["engine_display_id"] == "BBT_v1"
    assert pl["engine_online"] is True
    assert "api" in pl
