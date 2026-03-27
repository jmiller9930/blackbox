from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

import foreman_v2.broker as broker_mod
from foreman_v2.proof_gate import check_proof_and_handoff
from foreman_v2.protocol import decide_state
from foreman_v2.config import ForemanV2Config
from foreman_v2.control import status_snapshot, terminate_runtime
from foreman_v2.state import RuntimeState, load_state, save_state


def test_proof_gate_missing():
    r = check_proof_and_handoff("no markers here")
    assert r.has_proof is False
    assert r.reason == "proof_missing"


def test_proof_gate_present_with_handoff():
    text = """
    ## Phase implementation proof
    commands: python -m pytest
    tests: 10 passed
    have the architect validate shared-docs
    """
    r = check_proof_and_handoff(text)
    assert r.has_proof is True
    assert r.developer_handoff_back is True


def test_transition_to_developer_when_no_proof():
    d = decide_state(
        directive_closed=False,
        has_proof=False,
        developer_handoff_back=False,
        last_state="idle",
    )
    assert d.next_actor == "developer"
    assert d.next_state == "developer_action_required"


def test_transition_to_architect_when_ready():
    d = decide_state(
        directive_closed=False,
        has_proof=True,
        developer_handoff_back=True,
        last_state="developer_active",
    )
    assert d.next_actor == "architect"
    assert d.next_state == "architect_action_required"


def test_state_round_trip(tmp_path: Path):
    p = tmp_path / "state.json"
    st = RuntimeState(
        generation="g1",
        directive_title="t",
        directive_status="active",
        bridge_state="developer_action_required",
        next_actor="developer",
        required_phrase="have the architect validate shared-docs",
        proof_status="missing",
        last_transition_reason="proof_missing",
        updated_at="2026-01-01T00:00:00Z",
    )
    save_state(p, st)
    loaded = load_state(p)
    assert loaded == st
    parsed = json.loads(p.read_text(encoding="utf-8"))
    assert parsed["bridge_state"] == "developer_action_required"


def test_status_snapshot_when_not_initialized(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    snapshot = status_snapshot(cfg)
    assert snapshot["state"] == "not_initialized"
    assert snapshot["running"] is False


def test_terminate_runtime_without_pid(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    ok, detail = terminate_runtime(cfg)
    assert ok is False
    assert "no_pid_file" in detail


def test_dispatch_writes_session_lock(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=False,
        strict_session_guard=True,
    )

    def fake_request(
        url: str,
        method: str,
        token: str,
        payload: dict | None = None,
        headers: dict | None = None,
    ):
        if method == "GET":
            return True, "http_200", {"session": {"id": "dev-1"}}
        if method == "POST":
            return True, "http_200", {"success": True}
        return False, "unexpected", {}

    monkeypatch.setattr(broker_mod, "_request_json", fake_request)
    res = broker_mod.dispatch_to_actor(cfg, "developer", "hello")
    assert res.sent is True
    lock = json.loads(cfg.session_lock_path.read_text(encoding="utf-8"))
    assert lock["actor_locks"]["developer"] == "dev-1"


def test_dispatch_fails_on_lock_conflict(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-2",
        architect_session_id="arch-1",
        dry_run=False,
        strict_session_guard=True,
    )
    cfg.session_lock_path.write_text(
        json.dumps({"actor_locks": {"developer": "dev-1"}}, ensure_ascii=True),
        encoding="utf-8",
    )

    def fake_request(
        url: str,
        method: str,
        token: str,
        payload: dict | None = None,
        headers: dict | None = None,
    ):
        if method == "GET":
            return True, "http_200", {"session": {"id": "dev-2"}}
        return True, "http_200", {}

    monkeypatch.setattr(broker_mod, "_request_json", fake_request)
    res = broker_mod.dispatch_to_actor(cfg, "developer", "hello")
    assert res.sent is False
    assert "session_lock_conflict" in res.detail

