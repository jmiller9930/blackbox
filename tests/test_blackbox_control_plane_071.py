"""DV-071 — BlackBox Kitchen policy control plane (parity with Jupiter)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from renaissance_v4.kitchen_policy_ledger import read_ledger
from renaissance_v4.kitchen_runtime_assignment import (
    assign_mechanical_candidate,
    build_kitchen_runtime_read_payload,
    query_blackbox_runtime_truth,
    read_store,
    reconcile_assignment_store_to_runtime_truth,
    runtime_assignment_store_path,
    write_store,
)

REPO = Path(__file__).resolve().parents[1]

H_BB = "c" * 64


def _copy_registry(root: Path) -> None:
    dest = root / "renaissance_v4" / "config"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json",
        dest / "kitchen_policy_registry_v1.json",
    )


def _write_manifest_bb(root: Path, sid: str, content_sha256: str) -> None:
    dest = root / "renaissance_v4" / "config"
    dest.mkdir(parents=True, exist_ok=True)
    man = {
        "schema": "kitchen_policy_deployment_manifest_v1",
        "entries": [
            {
                "execution_target": "blackbox",
                "deployed_runtime_policy_id": "bb_kitchen_mechanical_v1",
                "submission_id": sid,
                "content_sha256": content_sha256,
            }
        ],
    }
    (dest / "kitchen_policy_deployment_manifest_v1.json").write_text(json.dumps(man), encoding="utf-8")


def _write_pass_blackbox(root: Path, sid: str, *, content_sha256: str = H_BB) -> None:
    sub = root / "renaissance_v4" / "state" / "policy_intake_submissions" / sid
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "schema": "policy_intake_report_v1",
        "submission_id": sid,
        "pass": True,
        "candidate_policy_id": "kitchen_mechanical_always_long_v1",
        "execution_target": "blackbox",
        "stages": {
            "stage_1_intake": {
                "timestamp_utc": "2026-01-01T12:00:00+00:00",
                "content_sha256": content_sha256,
            }
        },
    }
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")


class _MockResp:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._b = body

    def read(self) -> bytes:
        return self._b

    def __enter__(self) -> _MockResp:
        return self

    def __exit__(self, *a: object) -> None:
        return None


def test_query_blackbox_runtime_truth_parses_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    _write_manifest_bb(tmp_path, "bb_sub", H_BB)
    monkeypatch.setenv("KITCHEN_BLACKBOX_CONTROL_BASE", "http://bb.test")
    monkeypatch.setenv("KITCHEN_BLACKBOX_OPERATOR_TOKEN", "tok")

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "/blackbox/policy" in u:
            return _MockResp(
                200,
                b'{"active_policy":"bb_kitchen_mechanical_v1","allowed_policies":["bb_kitchen_mechanical_v1"],"source":"x","submission_id":null,"content_sha256":null}',
            )
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = query_blackbox_runtime_truth(tmp_path)
    assert r.get("ok") is True
    assert r.get("active_policy") == "bb_kitchen_mechanical_v1"
    assert r.get("execution_target") == "blackbox"
    assert r.get("unknown_runtime_policy") is False


def test_assign_blackbox_succeeds_when_runtime_post_and_get_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    _write_manifest_bb(tmp_path, "bb_sub", H_BB)
    monkeypatch.setenv("KITCHEN_BLACKBOX_CONTROL_BASE", "http://bb.test")
    monkeypatch.setenv("KITCHEN_BLACKBOX_OPERATOR_TOKEN", "tok")
    _write_pass_blackbox(tmp_path, "bb_sub")

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "blackbox/active-policy" in u:
            return _MockResp(
                200,
                b'{"ok":true,"active_policy":"bb_kitchen_mechanical_v1","contract":"blackbox_active_policy_switch_v1"}',
            )
        if "/blackbox/policy" in u:
            pol = {
                "active_policy": "bb_kitchen_mechanical_v1",
                "allowed_policies": ["bb_kitchen_mechanical_v1"],
                "source": "blackbox_kitchen_runtime_file",
                "submission_id": "bb_sub",
                "content_sha256": H_BB,
            }
            return _MockResp(200, json.dumps(pol).encode("utf-8"))
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = assign_mechanical_candidate(tmp_path, "bb_sub", "blackbox")
    assert r.get("ok") is True
    assert r.get("active_runtime_policy_id") == "bb_kitchen_mechanical_v1"
    assert runtime_assignment_store_path(tmp_path).is_file()
    led = read_ledger(tmp_path)
    entries = led.get("entries") or []
    assert any(e.get("source") == "kitchen" and e.get("new_policy_id") == "bb_kitchen_mechanical_v1" for e in entries)


def test_reconcile_blackbox_collapses_kitchen_row_to_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    monkeypatch.setenv("KITCHEN_BLACKBOX_CONTROL_BASE", "http://bb.test")
    monkeypatch.setenv("KITCHEN_BLACKBOX_OPERATOR_TOKEN", "tok")
    store = read_store(tmp_path)
    store.setdefault("assignments_by_target", {})["blackbox"] = {
        "schema": "kitchen_runtime_assignment_record_v1",
        "execution_target": "blackbox",
        "submission_id": "bb_sub",
        "candidate_policy_id": "kitchen_mechanical_always_long_v1",
        "approved_runtime_slot_id": "bb_kitchen_mechanical_v1",
        "active_runtime_policy_id": "",
        "assigned_at_utc": "2026-01-01T12:00:00+00:00",
        "operator_action": "kitchen_dashboard_assign",
        "runtime_adapter": "reserved_blackbox_control_plane",
    }
    write_store(tmp_path, store)

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "/blackbox/policy" in u:
            return _MockResp(
                200,
                b'{"active_policy":"bb_kitchen_mechanical_v1","allowed_policies":["bb_kitchen_mechanical_v1"],"source":"blackbox_kitchen_runtime_file"}',
            )
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    row_before = store["assignments_by_target"]["blackbox"]
    rt = query_blackbox_runtime_truth(tmp_path)
    out = reconcile_assignment_store_to_runtime_truth(tmp_path, "blackbox", rt, row_before)
    assert out is not None
    assert out.get("active_runtime_policy_id") == "bb_kitchen_mechanical_v1"
    st2 = read_store(tmp_path)
    assert st2["assignments_by_target"]["blackbox"]["active_runtime_policy_id"] == "bb_kitchen_mechanical_v1"


def test_read_payload_match_blackbox_when_mocked_runtime_agrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    _write_manifest_bb(tmp_path, "bb2", H_BB)
    monkeypatch.setenv("KITCHEN_BLACKBOX_CONTROL_BASE", "http://bb.test")
    monkeypatch.setenv("KITCHEN_BLACKBOX_OPERATOR_TOKEN", "tok")
    _write_pass_blackbox(tmp_path, "bb2")

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "blackbox/active-policy" in u:
            return _MockResp(200, b'{"ok":true,"active_policy":"bb_kitchen_mechanical_v1"}')
        if "/blackbox/policy" in u:
            pol = {
                "active_policy": "bb_kitchen_mechanical_v1",
                "allowed_policies": ["bb_kitchen_mechanical_v1"],
                "source": "t",
                "submission_id": "bb2",
                "content_sha256": H_BB,
            }
            return _MockResp(200, json.dumps(pol).encode("utf-8"))
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assign_mechanical_candidate(tmp_path, "bb2", "blackbox")
    p = build_kitchen_runtime_read_payload(tmp_path, "blackbox")
    assert p.get("drift", {}).get("state") == "match"
