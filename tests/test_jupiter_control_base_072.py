"""DV-072 — Jupiter control base must point at Sean, not BlackBox api :8080."""

from __future__ import annotations

import pytest

from renaissance_v4.kitchen_runtime_assignment import (
    assign_mechanical_candidate,
    jupiter_control_plane_warnings,
)


def test_warnings_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KITCHEN_JUPITER_CONTROL_BASE", raising=False)
    w = jupiter_control_plane_warnings(None)
    assert len(w) == 1
    assert "unset" in w[0].lower()


def test_warnings_localhost_8080() -> None:
    w = jupiter_control_plane_warnings("http://127.0.0.1:8080")
    assert len(w) == 1
    assert "8080" in w[0] and "BlackBox" in w[0]


def test_warnings_ok_for_lab_internal() -> None:
    w = jupiter_control_plane_warnings("http://clawbot.a51.corp:707")
    assert w == []


def test_assign_jupiter_blocked_when_base_is_localhost_8080(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import shutil
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    dest = tmp_path / "renaissance_v4" / "config"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        repo / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json",
        dest / "kitchen_policy_registry_v1.json",
    )
    sub = tmp_path / "renaissance_v4" / "state" / "policy_intake_submissions" / "subx"
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "schema": "policy_intake_report_v1",
        "submission_id": "subx",
        "pass": True,
        "candidate_policy_id": "kitchen_mechanical_always_long_v1",
        "execution_target": "jupiter",
        "stages": {},
    }
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("KITCHEN_JUPITER_CONTROL_BASE", "http://127.0.0.1:8080")
    monkeypatch.setenv("KITCHEN_JUPITER_OPERATOR_TOKEN", "tok")
    r = assign_mechanical_candidate(tmp_path, "subx", "jupiter")
    assert r.get("ok") is False
    assert r.get("error") == "jupiter_control_base_misconfigured"
