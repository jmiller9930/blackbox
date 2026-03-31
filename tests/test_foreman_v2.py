from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

import foreman_v2.broker as broker_mod
import foreman_v2.app as app_mod
from foreman_v2.app import run_once
from foreman_v2.artifact_gate import check_architect_artifacts, check_developer_artifacts
from foreman_v2.proof_gate import check_proof_and_handoff
from foreman_v2.protocol import decide_state
from foreman_v2.config import ForemanV2Config
from foreman_v2.cycle_log import append_unified_cycle_log
from foreman_v2.control import (
    actor_report,
    bind_sessions,
    operator_broadcast,
    operator_route,
    reconcile,
    reset_to_canonical,
    status_snapshot,
    stick_sync,
    terminate_runtime,
)
from foreman_v2.state import RuntimeState, load_state, save_state


def test_proof_gate_missing():
    r = check_proof_and_handoff("no markers here")
    assert r.has_proof is False
    assert r.architect_verdict == "missing"
    assert r.architect_rejection_count == 0
    assert r.architect_outcome == "missing"
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
    assert r.architect_verdict == "missing"
    assert r.architect_rejection_count == 0


def test_proof_gate_architect_verdict_not_met():
    r = check_proof_and_handoff("ARCHITECT_CANONICAL_VERDICT: not_met")
    assert r.architect_verdict == "not_met"
    assert r.architect_rejection_count == 1
    assert r.reason == "architect_not_met"


def test_proof_gate_uses_latest_architect_verdict_and_outcome():
    text = "\n".join(
        [
            "ARCHITECT_CANONICAL_VERDICT: not_met",
            "ARCHITECT_DIRECTIVE_OUTCOME: blocked",
            "ARCHITECT_CANONICAL_VERDICT: met",
            "ARCHITECT_DIRECTIVE_OUTCOME: accepted",
        ]
    )
    r = check_proof_and_handoff(text)
    assert r.architect_verdict == "met"
    assert r.architect_outcome == "accepted"


def test_proof_gate_parses_architect_outcome():
    r = check_proof_and_handoff("ARCHITECT_DIRECTIVE_OUTCOME: blocked")
    assert r.architect_outcome == "blocked"


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


def test_transition_closed_requires_architect_met():
    d = decide_state(
        directive_closed=True,
        has_proof=True,
        developer_handoff_back=True,
        last_state="architect_action_required",
        architect_verdict="missing",
    )
    assert d.next_actor == "architect"
    assert d.next_state == "architect_action_required"
    assert d.reason == "directive_closed_without_architect_met"


def test_three_strikes_blocks_developer_retry_until_architect_closeout():
    d = decide_state(
        directive_closed=False,
        has_proof=False,
        developer_handoff_back=False,
        last_state="developer_active",
        architect_verdict="not_met",
        architect_rejection_count=3,
        architect_outcome="missing",
    )
    assert d.next_actor == "architect"
    assert d.next_state == "architect_action_required"
    assert d.reason == "three_strikes_architect_closeout_required"


def test_three_strikes_with_outcome_closes_directive_lane():
    d = decide_state(
        directive_closed=False,
        has_proof=True,
        developer_handoff_back=True,
        last_state="architect_action_required",
        architect_verdict="not_met",
        architect_rejection_count=3,
        architect_outcome="blocked",
    )
    assert d.next_actor == "none"
    assert d.next_state == "closed"
    assert d.reason == "three_strikes_closed:blocked"


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
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
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
    assert snapshot.get("directive_status") == ""


def test_status_snapshot_includes_directive_status(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    st = RuntimeState(
        generation="g",
        directive_title="T",
        directive_status="Active — unit",
        bridge_state="idle",
        next_actor="none",
        required_phrase="",
        proof_status="missing",
        last_transition_reason="",
        updated_at="x",
    )
    save_state(cfg.state_path, st)
    snap = status_snapshot(cfg)
    assert snap["directive_status"] == "Active — unit"


def test_actor_report_writes_progress_event(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
        actor_progress_path=tmp_path / "actor_progress.jsonl",
    )
    save_state(
        cfg.state_path,
        RuntimeState(
            generation="gen-1",
            directive_title="x",
            directive_status="Active",
            bridge_state="developer_active",
            next_actor="developer",
            required_phrase="have the architect validate shared-docs",
            proof_status="missing",
            last_transition_reason="developer_work_in_progress",
            updated_at="now",
        ),
    )
    payload = actor_report(
        cfg,
        actor="developer",
        status="in_progress",
        step="run_tests",
        detail="writing tests",
    )
    assert payload["actor"] == "developer"
    assert payload["status"] == "in_progress"
    assert payload["generation"] == "gen-1"
    assert payload["step"] == "run_tests"
    progress = cfg.actor_progress_path.read_text(encoding="utf-8")
    assert "writing tests" in progress


def test_actor_report_rejects_invalid_step(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
        actor_progress_path=tmp_path / "actor_progress.jsonl",
    )
    try:
        actor_report(cfg, actor="developer", status="in_progress", step="record_verdict", detail="")
    except ValueError as exc:
        assert "invalid_step" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid actor step")


def test_terminate_runtime_without_pid(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
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


def test_close_actor_session_treats_404_as_already_absent(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
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
        return False, "http_error_404", {}

    monkeypatch.setattr(broker_mod, "_request_json", fake_request)
    ok, detail = broker_mod.close_actor_session(cfg, "developer")
    assert ok is True
    assert detail == "remote_already_absent"


def test_dispatch_writes_session_lock(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
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
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
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


def test_dispatch_fallback_on_session_404(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="tok",
        developer_session_id="stale-dev",
        architect_session_id="stale-arch",
        dry_run=False,
        strict_session_guard=True,
        dispatch_fallback_dry_run=True,
    )

    def fake_request(
        url: str,
        method: str,
        token: str,
        payload: dict | None = None,
        headers: dict | None = None,
    ):
        if method == "GET" and "sessions/stale-dev" in url:
            return False, "http_error_404", {}
        return True, "http_200", {"session": {"id": "stale-dev"}}

    monkeypatch.setattr(broker_mod, "_request_json", fake_request)
    res = broker_mod.dispatch_to_actor(cfg, "developer", "hello")
    assert res.sent is True
    assert "dry_run_fallback" in res.detail


def test_dispatch_no_fallback_when_disabled(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="tok",
        developer_session_id="stale-dev",
        architect_session_id="stale-arch",
        dry_run=False,
        strict_session_guard=True,
        dispatch_fallback_dry_run=False,
    )

    def fake_request(
        url: str,
        method: str,
        token: str,
        payload: dict | None = None,
        headers: dict | None = None,
    ):
        if method == "GET" and "sessions/stale-dev" in url:
            return False, "http_error_404", {}
        return True, "http_200", {"session": {"id": "stale-dev"}}

    monkeypatch.setattr(broker_mod, "_request_json", fake_request)
    res = broker_mod.dispatch_to_actor(cfg, "developer", "hello")
    assert res.sent is False


def test_dispatch_prefers_role_registry_session_id(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="stale-dev",
        architect_session_id="stale-arch",
        dry_run=False,
        strict_session_guard=True,
    )
    cfg.role_registry_path.write_text(
        json.dumps(
            {
                "roles": {
                    "developer": {"session_id": "fresh-dev"},
                    "architect": {"session_id": "fresh-arch"},
                }
            },
            ensure_ascii=True,
        ),
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
            assert url.endswith("/fresh-dev")
            return True, "http_200", {"session": {"id": "fresh-dev"}}
        if method == "POST":
            assert url.endswith("/fresh-dev")
            return True, "http_200", {"success": True}
        return False, "unexpected", {}

    monkeypatch.setattr(broker_mod, "_request_json", fake_request)
    res = broker_mod.dispatch_to_actor(cfg, "developer", "hello")
    assert res.sent is True


def test_bind_sessions_writes_env_and_clears_lock(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="tok",
        developer_session_id="",
        architect_session_id="",
        dry_run=False,
        strict_session_guard=True,
    )
    cfg.session_lock_path.write_text("{}", encoding="utf-8")

    def fake_request(
        url: str,
        method: str,
        token: str,
        payload: dict | None = None,
        headers: dict | None = None,
    ):
        return True, "http_200", {
            "sessions": {
                "sessions": [
                    {"sessionId": "main", "key": "agent:main:main"},
                    {"sessionId": "dev", "key": "agent:main:dashboard:1"},
                    {"sessionId": "arch", "key": "agent:main:dashboard:2"},
                ]
            }
        }

    monkeypatch.setattr("foreman_v2.control._request_json", fake_request)
    ok, detail = bind_sessions(cfg)
    assert ok is True
    assert "developer=dev" in detail
    env = (tmp_path / ".env.foreman_v2").read_text(encoding="utf-8")
    assert "FOREMAN_V2_DEVELOPER_SESSION=dev" in env
    assert "FOREMAN_V2_ARCHITECT_SESSION=arch" in env
    assert cfg.session_lock_path.exists() is False
    registry = json.loads(cfg.role_registry_path.read_text(encoding="utf-8"))
    assert registry["roles"]["developer"]["session_id"] == "dev"
    assert registry["roles"]["architect"]["session_id"] == "arch"


def test_stick_sync_updates_holder_from_state(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    save_state(
        cfg.state_path,
        RuntimeState(
            generation="g",
            directive_title="x",
            directive_status="active",
            bridge_state="developer_action_required",
            next_actor="developer",
            required_phrase="have the architect validate shared-docs",
            proof_status="missing",
            last_transition_reason="proof_missing",
            updated_at="now",
        ),
    )
    payload = stick_sync(cfg)
    assert payload["holder"] == "developer"


def test_operator_route_rejects_when_actor_not_holding_stick(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=True,
        strict_session_guard=True,
    )
    cfg.talking_stick_path.write_text(json.dumps({"holder": "architect"}), encoding="utf-8")

    def fail_dispatch(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dispatch should not be called")

    monkeypatch.setattr("foreman_v2.control.dispatch_to_actor", fail_dispatch)
    ok, detail = operator_route(cfg, "developer", "hello")
    assert ok is False
    assert "actor_not_holding_stick" in detail


def test_operator_route_rejects_when_holder_none(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=True,
        strict_session_guard=True,
    )
    cfg.talking_stick_path.write_text(json.dumps({"holder": "none"}), encoding="utf-8")

    def fail_dispatch(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dispatch should not be called")

    monkeypatch.setattr("foreman_v2.control.dispatch_to_actor", fail_dispatch)
    ok, detail = operator_route(cfg, "developer", "hello")
    assert ok is False
    assert "actor_not_holding_stick:holder=none" in detail


def test_operator_broadcast_sends_only_to_holder(monkeypatch, tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=True,
        strict_session_guard=True,
    )
    cfg.talking_stick_path.write_text(json.dumps({"holder": "architect"}), encoding="utf-8")

    def fake_route(config, actor, message):  # noqa: ANN001
        return True, f"sent:{actor}"

    monkeypatch.setattr("foreman_v2.control.operator_route", fake_route)
    out = operator_broadcast(cfg, "interrupt")
    assert out["architect"]["sent"] is True
    assert out["developer"]["sent"] is False
    assert "broadcast_blocked_by_turn_ownership" in out["developer"]["detail"]


def test_reconcile_and_reset_to_canonical(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    (tmp_path / "current_directive.md").write_text(
        "## Title\n**PHASE 5.3C — PRE-TRADE FAST GATE**\n\n**Status:** Active\n",
        encoding="utf-8",
    )
    (tmp_path / "shared_coordination_log.md").write_text("no proof yet", encoding="utf-8")
    cfg.session_lock_path.write_text("{}", encoding="utf-8")
    st = reconcile(cfg)
    assert st.next_actor == "developer"
    stick = json.loads(cfg.talking_stick_path.read_text(encoding="utf-8"))
    assert stick["holder"] == "developer"
    reset_to_canonical(cfg)
    assert cfg.session_lock_path.exists() is False


def test_run_once_enters_sync_conflict_on_stick_mismatch_without_new_generation(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=True,
        strict_session_guard=True,
    )
    (tmp_path / "current_directive.md").write_text(
        "## Title\n**PHASE 5.3C — PRE-TRADE FAST GATE**\n\n**Status:** Active\n",
        encoding="utf-8",
    )
    (tmp_path / "shared_coordination_log.md").write_text("no proof", encoding="utf-8")
    prev = RuntimeState(
        generation="PHASE 5.3C — PRE-TRADE FAST GATE|Active|developer_action_required|developer|missing",
        directive_title="PHASE 5.3C — PRE-TRADE FAST GATE",
        directive_status="Active",
        bridge_state="idle",
        next_actor="none",
        required_phrase="have the architect validate shared-docs",
        proof_status="missing",
        last_transition_reason="proof_missing",
        updated_at="now",
    )
    save_state(cfg.state_path, prev)
    cfg.talking_stick_path.write_text(json.dumps({"holder": "architect"}), encoding="utf-8")
    st = run_once(cfg)
    assert st.bridge_state == "sync_conflict"
    assert st.last_transition_reason == "stick_holder_mismatch"


def test_orchestration_simulation_stick_handoff_and_sync(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=True,
        strict_session_guard=True,
    )

    (tmp_path / "current_directive.md").write_text(
        "## Title\n**PHASE 5.3C — PRE-TRADE FAST GATE**\n\n**Status:** Active\n",
        encoding="utf-8",
    )
    (tmp_path / "developer_handoff.md").write_text(
        "bridge_status: developer_action_required\nnext_actor: developer\n",
        encoding="utf-8",
    )
    (tmp_path / "shared_coordination_log.md").write_text("work not started", encoding="utf-8")
    (tmp_path / "talking_stick.json").write_text(json.dumps({"holder": "none"}), encoding="utf-8")
    import subprocess as _sp
    _sp.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    _sp.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    (tmp_path / "dirty_code.py").write_text("# dev work", encoding="utf-8")
    (tmp_path / "docs" / "architect" / "directives").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "architect" / "directives" / "directive_execution_log.md").write_text("log", encoding="utf-8")
    (tmp_path / "docs" / "architect" / "development_plan.md").write_text(
        "### 5.3 Strategy engine\n- [ ] Add pre-trade fast gate\n",
        encoding="utf-8",
    )

    # Cycle 1: no proof => developer gets stick and can act.
    st1 = reconcile(cfg)
    assert st1.next_actor == "developer"
    stick1 = json.loads(cfg.talking_stick_path.read_text(encoding="utf-8"))
    assert stick1["holder"] == "developer"
    ok_dev, _ = operator_route(cfg, "developer", "start implementation")
    assert ok_dev is True

    # Developer records proof + handoff phrase; architect now owns validation lane.
    (tmp_path / "shared_coordination_log.md").write_text(
        "\n".join(
            [
                "implementation proof",
                "commands: python3 -m pytest tests/test_foreman_v2.py",
                "tests: passing",
                "files changed: dirty_code.py",
                "have the architect validate shared-docs",
            ]
        ),
        encoding="utf-8",
    )
    st2 = reconcile(cfg)
    assert st2.next_actor == "architect"
    stick2 = json.loads(cfg.talking_stick_path.read_text(encoding="utf-8"))
    assert stick2["holder"] == "architect"
    ok_arch, _ = operator_route(cfg, "architect", "perform validation")
    assert ok_arch is True

    # Architect rejects once => architect remains owner, no developer replay.
    (tmp_path / "shared_coordination_log.md").write_text(
        "\n".join(
            [
                "implementation proof",
                "commands: python3 -m pytest tests/test_foreman_v2.py",
                "tests: passing",
                "files changed: dirty_code.py",
                "have the architect validate shared-docs",
                "ARCHITECT_CANONICAL_VERDICT: not_met",
            ]
        ),
        encoding="utf-8",
    )
    st3 = reconcile(cfg)
    assert st3.next_actor == "architect"
    assert st3.bridge_state == "architect_action_required"

    # Architect marks met and closes directive => orchestrator closes lane.
    (tmp_path / "shared_coordination_log.md").write_text(
        "\n".join(
            [
                "implementation proof",
                "commands: python3 -m pytest tests/test_foreman_v2.py",
                "tests: passing",
                "files changed: dirty_code.py",
                "have the architect validate shared-docs",
                "ARCHITECT_CANONICAL_VERDICT: met",
                "Plan/log status sync: PASS",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "current_directive.md").write_text(
        "## Title\n**PHASE 5.3C — PRE-TRADE FAST GATE**\n\n**Status:** Closed\n",
        encoding="utf-8",
    )
    st4 = reconcile(cfg)
    assert st4.bridge_state == "architect_action_required"
    assert st4.next_actor == "architect"
    assert "reconcile_bootstrap_architect_review_required" in st4.last_transition_reason


def test_command_action_conflict_after_timeout_and_max_attempts(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=True,
        strict_session_guard=True,
        actor_progress_path=tmp_path / "actor_progress.jsonl",
    )
    state = RuntimeState(
        generation="g1",
        directive_title="PHASE 5.3C — PRE-TRADE FAST GATE",
        directive_status="Active",
        bridge_state="architect_action_required",
        next_actor="architect",
        required_phrase="have the architect validate shared-docs",
        proof_status="present",
        last_transition_reason="proof_ready_for_architect",
        updated_at="now",
    )
    stale = (datetime.now().astimezone() - timedelta(seconds=500)).isoformat()
    command_state = {
        "command": {
            "generation": "g1",
            "actor": "architect",
            "dispatch_key": "k",
            "attempts": 3,
            "status": "pending",
            "last_dispatch_at": stale,
        }
    }
    action = app_mod._command_action(cfg, state, command_state)
    assert action == "conflict"


def test_command_action_skips_when_started_and_fresh_progress(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=True,
        strict_session_guard=True,
        actor_progress_path=tmp_path / "actor_progress.jsonl",
    )
    state = RuntimeState(
        generation="g2",
        directive_title="PHASE 5.3C — PRE-TRADE FAST GATE",
        directive_status="Active",
        bridge_state="architect_action_required",
        next_actor="architect",
        required_phrase="have the architect validate shared-docs",
        proof_status="present",
        last_transition_reason="proof_ready_for_architect",
        updated_at="now",
    )
    fresh = datetime.now().astimezone().isoformat()
    command_state = {
        "command": {
            "generation": "g2",
            "actor": "architect",
            "dispatch_key": "k",
            "attempts": 2,
            "status": "started",
            "last_dispatch_at": fresh,
            "last_progress_at": fresh,
        }
    }
    action = app_mod._command_action(cfg, state, command_state)
    assert action == "skip"


def test_handle_command_timeout_fail_closed_for_architect(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=True,
        strict_session_guard=True,
        actor_progress_path=tmp_path / "actor_progress.jsonl",
    )
    state = RuntimeState(
        generation="g3",
        directive_title="PHASE 5.3C — PRE-TRADE FAST GATE",
        directive_status="Active",
        bridge_state="architect_action_required",
        next_actor="architect",
        required_phrase="have the architect validate shared-docs",
        proof_status="present",
        last_transition_reason="proof_ready_for_architect",
        updated_at="now",
    )
    out = app_mod._handle_command_timeout(cfg, state, {"command": {"generation": "g3"}})
    assert out.next_actor == "developer"
    assert out.bridge_state == "developer_action_required"
    assert out.proof_status == "missing"
    assert "architect_timeout_fail_closed_reject" in out.last_transition_reason
    log = (tmp_path / "shared_coordination_log.md").read_text(encoding="utf-8")
    assert "ARCHITECT_CANONICAL_VERDICT: not_met" in log
    assert "ARCHITECT_DIRECTIVE_OUTCOME: rejected" in log


def test_run_once_auto_reissues_after_dispatch_failure(tmp_path: Path, monkeypatch):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="dev-1",
        architect_session_id="arch-1",
        dry_run=False,
        strict_session_guard=True,
    )
    (tmp_path / "current_directive.md").write_text(
        "## Title\n**PHASE 5.3C — PRE-TRADE FAST GATE**\n\n**Status:** Active\n",
        encoding="utf-8",
    )
    (tmp_path / "shared_coordination_log.md").write_text("no proof", encoding="utf-8")

    def fail_dispatch(*args, **kwargs):  # noqa: ANN002, ANN003
        return broker_mod.DispatchResult(sent=False, target="developer", detail="session_preflight_failed:error_test")

    monkeypatch.setattr(app_mod, "dispatch_to_actor", fail_dispatch)
    out = run_once(cfg)
    assert out.next_actor == "developer"
    assert out.bridge_state == "developer_action_required"
    assert "auto_reissue_after_failure" in out.last_transition_reason
    stick = json.loads(cfg.talking_stick_path.read_text(encoding="utf-8"))
    assert stick["holder"] == "developer"
    audit = cfg.audit_path.read_text(encoding="utf-8")
    assert '"event": "auto_reissue_after_failure"' in audit


def test_developer_artifact_gate_missing_items(tmp_path: Path):
    result = check_developer_artifacts("no content here", tmp_path, tmp_path)
    assert result.passed is False
    assert "implementation_proof_marker" in result.missing
    assert "test_results_in_proof" in result.missing
    assert "commands_in_proof" in result.missing
    assert "handoff_phrase" in result.missing


def test_developer_artifact_gate_passes_with_full_proof(tmp_path: Path):
    (tmp_path / "dirty.txt").write_text("x", encoding="utf-8")
    Shell_cmd = ["git", "init"]
    import subprocess
    subprocess.run(Shell_cmd, cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    log = "\n".join([
        "implementation proof",
        "tests: 5 passed",
        "commands: python3 -m pytest",
        "files changed: scripts/runtime/foo.py",
        "files: bar.py",
        "have the architect validate shared-docs",
    ])
    result = check_developer_artifacts(log, tmp_path, tmp_path)
    assert result.passed is True


def test_architect_artifact_gate_missing_items(tmp_path: Path):
    result = check_architect_artifacts("no content", tmp_path, tmp_path)
    assert result.passed is False
    assert "architect_verdict" in result.missing
    assert "directive_execution_log" in result.missing
    assert "plan_log_sync_evidence" in result.missing


def test_architect_artifact_gate_passes(tmp_path: Path):
    (tmp_path / "docs" / "architect" / "directives").mkdir(parents=True)
    (tmp_path / "docs" / "architect" / "directives" / "directive_execution_log.md").write_text("log", encoding="utf-8")
    log = "\n".join([
        "ARCHITECT_CANONICAL_VERDICT: met",
        "Plan/log status sync: PASS",
    ])
    result = check_architect_artifacts(log, tmp_path, tmp_path)
    assert result.passed is True


def test_decide_state_developer_gate_blocks_handoff():
    d = decide_state(
        directive_closed=False,
        has_proof=True,
        developer_handoff_back=True,
        last_state="developer_active",
        developer_artifact_gate_passed=False,
        developer_artifact_missing=["implementation_proof_marker", "test_results_in_proof"],
    )
    assert d.next_actor == "developer"
    assert d.reason == "developer_artifact_gate_failed"
    assert "implementation_proof_marker" in d.artifact_missing


def test_decide_state_architect_gate_blocks_closure():
    d = decide_state(
        directive_closed=True,
        has_proof=True,
        developer_handoff_back=True,
        last_state="architect_validating",
        architect_verdict="met",
        architect_artifact_gate_passed=False,
        architect_artifact_missing=["plan_log_sync_evidence"],
    )
    assert d.next_actor == "architect"
    assert d.reason == "architect_artifact_gate_failed_before_close"
    assert "plan_log_sync_evidence" in d.artifact_missing


def test_artifact_gate_redo_feeds_three_strikes(tmp_path: Path):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    (tmp_path / "current_directive.md").write_text(
        "## Title\n**TEST DIRECTIVE**\n\n**Status:** Active\n",
        encoding="utf-8",
    )
    (tmp_path / "shared_coordination_log.md").write_text(
        "\n".join([
            "implementation proof",
            "tests: ok",
            "commands: pytest",
            "files changed: x.py",
            "have the architect validate shared-docs",
            "ARCHITECT_CANONICAL_VERDICT: not_met",
            "ARCHITECT_CANONICAL_VERDICT: not_met",
            "ARCHITECT_CANONICAL_VERDICT: not_met",
        ]),
        encoding="utf-8",
    )
    st = reconcile(cfg)
    assert st.next_actor == "architect"
    assert "three_strikes" in st.last_transition_reason


def test_unified_cycle_log_writes_default_file_and_stdout(tmp_path: Path, capsys):
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    (tmp_path / "talking_stick.json").write_text(json.dumps({"holder": "developer"}), encoding="utf-8")
    (tmp_path / "audit.jsonl").write_text("", encoding="utf-8")
    st = RuntimeState(
        generation="g1",
        directive_title="t",
        directive_status="Active",
        bridge_state="developer_active",
        next_actor="developer",
        required_phrase="",
        proof_status="missing",
        last_transition_reason="developer_work_in_progress",
        updated_at="2026-01-01",
    )
    append_unified_cycle_log(cfg, cycle=3, state=st)
    path = tmp_path / "foreman_v2_cycle_log.jsonl"
    assert path.exists()
    line = path.read_text(encoding="utf-8").strip().splitlines()[0]
    out = json.loads(line)
    assert out["cycle"] == 3
    assert out["iteration"] == 3
    assert out["stick_holder"] == "developer"
    assert out["action"] == "developer_work_in_progress"
    assert out["gap_fields"] == ["structured_exception_from_run_once"]
    assert capsys.readouterr().out.strip() == line


def test_unified_cycle_log_custom_path_and_no_stdout(tmp_path: Path, monkeypatch, capsys):
    custom = tmp_path / "custom_cycle.jsonl"
    monkeypatch.setenv("FOREMAN_V2_UNIFIED_LOG_PATH", str(custom))
    monkeypatch.setenv("FOREMAN_V2_LOOP_STDOUT", "0")
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    (tmp_path / "talking_stick.json").write_text(json.dumps({"holder": "none"}), encoding="utf-8")
    (tmp_path / "audit.jsonl").write_text("", encoding="utf-8")
    st = RuntimeState(
        generation="g1",
        directive_title="t",
        directive_status="Active",
        bridge_state="idle",
        next_actor="none",
        required_phrase="",
        proof_status="missing",
        last_transition_reason="",
        updated_at="2026-01-01",
    )
    append_unified_cycle_log(cfg, cycle=1, state=st)
    assert custom.exists()
    assert not (tmp_path / "foreman_v2_cycle_log.jsonl").exists()
    assert capsys.readouterr().out == ""
    row = json.loads(custom.read_text(encoding="utf-8").strip())
    assert row["action"] == "noop"


def test_unified_cycle_log_file_disable_keeps_stdout(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("FOREMAN_V2_CYCLE_LOG_DISABLE", "1")
    cfg = ForemanV2Config(
        repo_root=tmp_path,
        docs_working=tmp_path,
        state_path=tmp_path / "state.json",
        audit_path=tmp_path / "audit.jsonl",
        pid_path=tmp_path / "foreman_v2.pid",
        session_lock_path=tmp_path / "foreman_v2_session_lock.json",
        role_registry_path=tmp_path / "foreman_v2_role_registry.json",
        talking_stick_path=tmp_path / "talking_stick.json",
        poll_seconds=1.0,
        mission_control_url="http://localhost:4000",
        mc_api_token="",
        developer_session_id="",
        architect_session_id="",
        dry_run=True,
        strict_session_guard=True,
    )
    (tmp_path / "talking_stick.json").write_text("{}", encoding="utf-8")
    (tmp_path / "audit.jsonl").write_text("", encoding="utf-8")
    st = RuntimeState(
        generation="g1",
        directive_title="t",
        directive_status="Active",
        bridge_state="idle",
        next_actor="none",
        required_phrase="",
        proof_status="missing",
        last_transition_reason="x",
        updated_at="2026-01-01",
    )
    append_unified_cycle_log(cfg, cycle=1, state=st)
    assert not (tmp_path / "foreman_v2_cycle_log.jsonl").exists()
    assert capsys.readouterr().out.strip()

