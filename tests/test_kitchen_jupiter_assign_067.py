"""DV-067 — Kitchen → Jupiter assignment persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.kitchen_jupiter_control import (
    JUPITER_MECHANICAL_SLOT,
    MECHANICAL_CANDIDATE_POLICY_ID,
    assign_mechanical_candidate_to_jupiter,
    assignment_json_path,
    read_assignment,
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
    assert r.get("jupiter_policy_slot") == JUPITER_MECHANICAL_SLOT
    assert r.get("jupiter_http_post_ok") is None
    p = assignment_json_path(root)
    assert p.is_file()
    disk = json.loads(p.read_text(encoding="utf-8"))
    assert disk["candidate_policy_id"] == MECHANICAL_CANDIDATE_POLICY_ID
    assert read_assignment(root)["submission_id"] == "subabc"


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
