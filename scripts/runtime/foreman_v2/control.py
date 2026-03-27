from __future__ import annotations

import json
import os
import signal
from pathlib import Path

from foreman_v2.audit import append_audit
from foreman_v2.broker import close_actor_session, dispatch_to_actor
from foreman_v2.config import ForemanV2Config
from foreman_v2.state import load_state


def status_snapshot(config: ForemanV2Config) -> dict:
    st = load_state(config.state_path)
    if st is None:
        return {"running": False, "state": "not_initialized"}
    running = False
    pid = _read_pid(config.pid_path)
    if pid is not None:
        running = _pid_exists(pid)
    return {
        "running": running,
        "pid": pid,
        "bridge_state": st.bridge_state,
        "next_actor": st.next_actor,
        "proof_status": st.proof_status,
        "reason": st.last_transition_reason,
        "directive_title": st.directive_title,
    }


def terminate_runtime(config: ForemanV2Config) -> tuple[bool, str]:
    remote_results = {}
    for actor in ("developer", "architect"):
        ok_remote, detail_remote = close_actor_session(config, actor)
        remote_results[actor] = {"closed": ok_remote, "detail": detail_remote}

    pid = _read_pid(config.pid_path)
    if pid is None:
        append_audit(config.audit_path, {"event": "operator_terminate", "pid": None, "remote": remote_results})
        return False, f"no_pid_file remote={remote_results}"
    if not _pid_exists(pid):
        append_audit(config.audit_path, {"event": "operator_terminate", "pid": pid, "remote": remote_results})
        return False, f"pid_not_running remote={remote_results}"
    os.kill(pid, signal.SIGTERM)
    append_audit(config.audit_path, {"event": "operator_terminate", "pid": pid, "remote": remote_results})
    return True, f"terminated_pid_{pid} remote={remote_results}"


def operator_route(config: ForemanV2Config, actor: str, message: str) -> tuple[bool, str]:
    msg = f"[Operator] {message}"
    r = dispatch_to_actor(config, actor, msg)
    append_audit(
        config.audit_path,
        {"event": "operator_route", "actor": actor, "sent": r.sent, "detail": r.detail, "message": message},
    )
    return r.sent, r.detail


def operator_broadcast(config: ForemanV2Config, message: str) -> dict:
    out = {}
    for actor in ("developer", "architect"):
        ok, detail = operator_route(config, actor, message)
        out[actor] = {"sent": ok, "detail": detail}
    return out


def print_status(config: ForemanV2Config) -> None:
    print(json.dumps(status_snapshot(config), indent=2, ensure_ascii=True))


def _read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return None


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

