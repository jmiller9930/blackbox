"""DV-067 / DV-074 / DV-074A — Kitchen → runtime assignment + ledger."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from renaissance_v4.kitchen_policy_ledger import read_ledger
from renaissance_v4.kitchen_runtime_assignment import (
    assign_mechanical_candidate,
    assign_mechanical_candidate_to_jupiter,
    build_kitchen_runtime_read_payload,
    get_assignment,
    legacy_jupiter_assignment_path,
    maybe_record_external_runtime_change,
    runtime_assignment_store_path,
)

REPO = Path(__file__).resolve().parents[1]


def _copy_registry(root: Path) -> None:
    dest = root / "renaissance_v4" / "config"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json",
        dest / "kitchen_policy_registry_v1.json",
    )


def _write_pass(root: Path, sid: str, *, candidate_policy_id: str = "kitchen_mechanical_always_long_v1") -> None:
    sub = root / "renaissance_v4" / "state" / "policy_intake_submissions" / sid
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "schema": "policy_intake_report_v1",
        "submission_id": sid,
        "pass": True,
        "candidate_policy_id": candidate_policy_id,
        "execution_target": "jupiter",
        "stages": {"stage_1_intake": {"timestamp_utc": "2026-01-01T12:00:00+00:00"}},
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


def test_assign_jupiter_fails_when_runtime_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    monkeypatch.delenv("KITCHEN_JUPITER_CONTROL_BASE", raising=False)
    monkeypatch.delenv("KITCHEN_JUPITER_OPERATOR_TOKEN", raising=False)
    _write_pass(tmp_path, "subabc")
    r = assign_mechanical_candidate_to_jupiter(tmp_path, "subabc")
    assert r.get("ok") is False
    assert r.get("error") == "jupiter_runtime_not_configured"
    assert not runtime_assignment_store_path(tmp_path).is_file()


def test_assign_jupiter_succeeds_when_runtime_post_and_get_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    monkeypatch.setenv("KITCHEN_JUPITER_CONTROL_BASE", "http://sean.test")
    monkeypatch.setenv("KITCHEN_JUPITER_OPERATOR_TOKEN", "tok")
    _write_pass(tmp_path, "subabc")

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "active-policy" in u:
            return _MockResp(
                200,
                b'{"ok":true,"active_policy":"jup_kitchen_mechanical_v1","contract":"jupiter_active_policy_switch_v1"}',
            )
        if "/jupiter/policy" in u:
            return _MockResp(
                200,
                b'{"active_policy":"jup_kitchen_mechanical_v1","allowed_policies":["jup_kitchen_mechanical_v1"],"source":"runtime_config"}',
            )
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = assign_mechanical_candidate_to_jupiter(tmp_path, "subabc")
    assert r.get("ok") is True
    assert r.get("active_runtime_policy_id") == "jup_kitchen_mechanical_v1"
    p = runtime_assignment_store_path(tmp_path)
    assert p.is_file()
    led = read_ledger(tmp_path)
    assert len(led.get("entries") or []) == 1
    assert led["entries"][0]["source"] == "kitchen"
    assert led["entries"][0]["new_policy_id"] == "jup_kitchen_mechanical_v1"


def test_assign_jupiter_non_mechanical_candidate_uses_registry_runtime_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any intake whose candidate_policy_id maps to runtime_policies.jupiter may be assigned."""
    _copy_registry(tmp_path)
    monkeypatch.setenv("KITCHEN_JUPITER_CONTROL_BASE", "http://sean.test")
    monkeypatch.setenv("KITCHEN_JUPITER_OPERATOR_TOKEN", "tok")
    _write_pass(tmp_path, "sub_mc_direct", candidate_policy_id="jup_mc_test")

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "active-policy" in u:
            return _MockResp(
                200,
                b'{"ok":true,"active_policy":"jup_mc_test","contract":"jupiter_active_policy_switch_v1"}',
            )
        if "/jupiter/policy" in u:
            return _MockResp(
                200,
                b'{"active_policy":"jup_mc_test","allowed_policies":["jup_v4","jup_mc_test","jup_kitchen_mechanical_v1"],"source":"runtime_config"}',
            )
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = assign_mechanical_candidate_to_jupiter(tmp_path, "sub_mc_direct")
    assert r.get("ok") is True
    assert r.get("active_runtime_policy_id") == "jup_mc_test"
    assert r.get("candidate_policy_id") == "jup_mc_test"


def test_assign_jupiter_post_ok_but_verify_fails_no_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    monkeypatch.setenv("KITCHEN_JUPITER_CONTROL_BASE", "http://sean.test")
    monkeypatch.setenv("KITCHEN_JUPITER_OPERATOR_TOKEN", "tok")
    _write_pass(tmp_path, "subx")
    policy_n = [0]

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "active-policy" in u:
            return _MockResp(200, b'{"ok":true,"active_policy":"jup_kitchen_mechanical_v1"}')
        if "/jupiter/policy" in u:
            policy_n[0] += 1
            if policy_n[0] == 1:
                return _MockResp(
                    200,
                    b'{"active_policy":"jup_mc_test","allowed_policies":["jup_v4","jup_mc_test","jup_kitchen_mechanical_v1"]}',
                )
            return _MockResp(200, b'{"active_policy":"jup_v4","allowed_policies":["jup_v4"]}')
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = assign_mechanical_candidate_to_jupiter(tmp_path, "subx")
    assert r.get("ok") is False
    assert r.get("error") == "runtime_verify_mismatch"
    assert not runtime_assignment_store_path(tmp_path).is_file()


def test_assign_fails_when_jupiter_allowed_policies_omit_registry_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DV-077 — no POST if Jupiter GET allowed_policies does not include registry slot."""
    _copy_registry(tmp_path)
    monkeypatch.setenv("KITCHEN_JUPITER_CONTROL_BASE", "http://sean.test")
    monkeypatch.setenv("KITCHEN_JUPITER_OPERATOR_TOKEN", "tok")
    _write_pass(tmp_path, "sub_nom")

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "active-policy" in u:
            raise AssertionError("POST must not run when policy set mismatches")
        if "/jupiter/policy" in u:
            return _MockResp(
                200,
                b'{"active_policy":"jup_mc_test","allowed_policies":["jup_v4","jup_mc_test","jup_mc2"]}',
            )
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = assign_mechanical_candidate_to_jupiter(tmp_path, "sub_nom")
    assert r.get("ok") is False
    assert r.get("error") == "jupiter_runtime_policy_set_mismatch"
    assert "jup_kitchen_mechanical_v1" not in (r.get("jupiter_allowed_policies") or [])


def test_assign_rejects_wrong_candidate_id(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    sub = tmp_path / "renaissance_v4" / "state" / "policy_intake_submissions" / "x"
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "pass": True,
        "candidate_policy_id": "other",
        "execution_target": "jupiter",
        "submission_id": "x",
        "stages": {},
    }
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")
    r = assign_mechanical_candidate_to_jupiter(tmp_path, "x")
    assert r.get("ok") is False
    assert r.get("error") == "candidate_not_deployable"


def test_assign_blackbox_fails_until_runtime_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _copy_registry(tmp_path)
    monkeypatch.delenv("KITCHEN_BLACKBOX_CONTROL_BASE", raising=False)
    monkeypatch.delenv("KITCHEN_BLACKBOX_OPERATOR_TOKEN", raising=False)
    sub = tmp_path / "renaissance_v4" / "state" / "policy_intake_submissions" / "bb1"
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "pass": True,
        "candidate_policy_id": "kitchen_mechanical_always_long_v1",
        "execution_target": "blackbox",
        "submission_id": "bb1",
        "stages": {},
    }
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")
    r = assign_mechanical_candidate(tmp_path, "bb1", "blackbox")
    assert r.get("ok") is False
    assert r.get("error") == "blackbox_runtime_not_configured"


def test_legacy_kitchen_jupiter_json_migrates_into_store(tmp_path: Path) -> None:
    root = tmp_path
    p = legacy_jupiter_assignment_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "submission_id": "legacy_sid",
                "candidate_policy_id": "kitchen_mechanical_always_long_v1",
                "jupiter_policy_slot": "jup_kitchen_mechanical_v1",
            }
        ),
        encoding="utf-8",
    )
    row = get_assignment(root, "jupiter")
    assert row is not None
    assert row["submission_id"] == "legacy_sid"


def test_read_payload_includes_drift_when_runtime_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    monkeypatch.delenv("KITCHEN_JUPITER_CONTROL_BASE", raising=False)
    monkeypatch.delenv("KITCHEN_JUPITER_OPERATOR_TOKEN", raising=False)
    p = build_kitchen_runtime_read_payload(tmp_path, "jupiter")
    assert p.get("schema") == "kitchen_runtime_assignment_read_v5"
    assert p.get("authoritative_active_policy") == ""
    assert p.get("runtime", {}).get("ok") is False
    assert p.get("drift", {}).get("state") == "runtime_unreachable"


def test_read_payload_match_when_mocked_runtime_agrees_with_kitchen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_registry(tmp_path)
    monkeypatch.setenv("KITCHEN_JUPITER_CONTROL_BASE", "http://sean.test")
    monkeypatch.setenv("KITCHEN_JUPITER_OPERATOR_TOKEN", "tok")
    _write_pass(tmp_path, "s2")

    def fake_urlopen(req: object, timeout: float | None = None) -> _MockResp:
        u = getattr(req, "full_url", "")
        if "active-policy" in u:
            return _MockResp(200, b'{"ok":true,"active_policy":"jup_kitchen_mechanical_v1"}')
        if "/jupiter/policy" in u:
            return _MockResp(
                200,
                b'{"active_policy":"jup_kitchen_mechanical_v1","allowed_policies":["jup_kitchen_mechanical_v1"],"source":"runtime_config"}',
            )
        raise AssertionError(u)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assign_mechanical_candidate_to_jupiter(tmp_path, "s2")
    p = build_kitchen_runtime_read_payload(tmp_path, "jupiter")
    assert p.get("drift", {}).get("state") == "match"
    assert p.get("authoritative_active_policy") == "jup_kitchen_mechanical_v1"
    assert isinstance(p.get("ledger_tail"), list)


def test_external_ledger_deduped_on_repeated_poll(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    row = {"active_runtime_policy_id": "jup_kitchen_mechanical_v1"}
    rt = {"ok": True, "active_policy": "jup_v4", "unknown_runtime_policy": False}
    maybe_record_external_runtime_change(tmp_path, "jupiter", row, rt)
    maybe_record_external_runtime_change(tmp_path, "jupiter", row, rt)
    led = read_ledger(tmp_path)
    assert len(led.get("entries") or []) == 1
    assert led["entries"][0]["source"] == "external"
    assert led["entries"][0]["new_policy_id"] == "jup_v4"
