"""DV-067 — Kitchen → Jupiter assignment persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.kitchen_runtime_assignment import (
    APPROVED_MECHANICAL_BY_TARGET,
    MECHANICAL_CANDIDATE_POLICY_ID,
    assign_mechanical_candidate,
    assign_mechanical_candidate_to_jupiter,
    get_assignment,
    legacy_jupiter_assignment_path,
    read_store,
    runtime_assignment_store_path,
)


def _write_pass(root: Path, sid: str) -> None:
    sub = root / "renaissance_v4" / "state" / "policy_intake_submissions" / sid
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "schema": "policy_intake_report_v1",
        "submission_id": sid,
        "pass": True,
        "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
        "execution_target": "jupiter",
        "stages": {"stage_1_intake": {"timestamp_utc": "2026-01-01T12:00:00+00:00"}},
    }
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")


def test_assign_writes_json_without_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KITCHEN_JUPITER_CONTROL_BASE", raising=False)
    monkeypatch.delenv("KITCHEN_JUPITER_OPERATOR_TOKEN", raising=False)
    root = tmp_path
    _write_pass(root, "subabc")
    r = assign_mechanical_candidate_to_jupiter(root, "subabc")
    assert r.get("ok") is True
    assert r.get("approved_runtime_slot_id") == APPROVED_MECHANICAL_BY_TARGET["jupiter"]["approved_runtime_slot_id"]
    assert r.get("runtime_http_post_ok") is None
    p = runtime_assignment_store_path(root)
    assert p.is_file()
    disk = json.loads(p.read_text(encoding="utf-8"))
    assert disk["assignments_by_target"]["jupiter"]["candidate_policy_id"] == MECHANICAL_CANDIDATE_POLICY_ID
    assert get_assignment(root, "jupiter")["submission_id"] == "subabc"


def test_assign_rejects_wrong_candidate_id(tmp_path: Path) -> None:
    root = tmp_path
    sub = root / "renaissance_v4" / "state" / "policy_intake_submissions" / "x"
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
    r = assign_mechanical_candidate_to_jupiter(root, "x")
    assert r.get("ok") is False


def test_assign_blackbox_persists_separate_from_jupiter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KITCHEN_JUPITER_CONTROL_BASE", raising=False)
    root = tmp_path
    sub = root / "renaissance_v4" / "state" / "policy_intake_submissions" / "bb1"
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "pass": True,
        "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
        "execution_target": "blackbox",
        "submission_id": "bb1",
        "stages": {},
    }
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")
    r = assign_mechanical_candidate(root, "bb1", "blackbox")
    assert r.get("ok") is True
    assert r.get("execution_target") == "blackbox"
    st = read_store(root)
    assert "jupiter" not in st.get("assignments_by_target", {}) or st["assignments_by_target"].get("jupiter") is None
    assert st["assignments_by_target"]["blackbox"]["approved_runtime_slot_id"] == "bb_kitchen_mechanical_v1"


def test_legacy_kitchen_jupiter_json_migrates_into_store(tmp_path: Path) -> None:
    root = tmp_path
    p = legacy_jupiter_assignment_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "submission_id": "legacy_sid",
                "candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
                "jupiter_policy_slot": "jup_kitchen_mechanical_v1",
            }
        ),
        encoding="utf-8",
    )
    row = get_assignment(root, "jupiter")
    assert row is not None
    assert row["submission_id"] == "legacy_sid"
