from __future__ import annotations

import json
import os
import re
import signal
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from foreman_v2.artifact_gate import check_architect_artifacts, check_developer_artifacts
from foreman_v2.audit import append_audit
from foreman_v2.broker import _request_json, close_actor_session, dispatch_to_actor
from foreman_v2.config import ForemanV2Config
from foreman_v2.proof_gate import check_proof_and_handoff
from foreman_v2.progress import append_actor_progress, latest_actor_progress_for_generation
from foreman_v2.protocol import decide_state
from foreman_v2.state import RuntimeState, load_state, make_generation, now_iso, read_directive_fields, read_shared_log_text, save_state


def _session_id_for_actor(config: ForemanV2Config, actor: str) -> str:
    """Resolve OpenClaw session UUID — same precedence as ``broker._session_id_for_actor`` (registry, then env)."""
    roles = _read_role_registry(config.role_registry_path).get("roles", {}) or {}
    row = roles.get(actor) if isinstance(roles, dict) else None
    if isinstance(row, dict):
        sid = str(row.get("session_id") or "").strip()
        if sid:
            return sid
    if actor == "developer":
        return (config.developer_session_id or "").strip()
    return (config.architect_session_id or "").strip()


def handshake_snapshot(config: ForemanV2Config, *, write: bool = True) -> dict:
    """Compute comms presence for orchestrator/architect/developer."""
    now = datetime.now().astimezone().isoformat()
    status = status_snapshot(config)
    orchestrator_online = bool(status.get("running", False))

    dev_sid = _session_id_for_actor(config, "developer")
    arch_sid = _session_id_for_actor(config, "architect")

    health_ok, health_detail, _ = _request_json(
        f"{config.mission_control_url}/api/health",
        "GET",
        config.mc_api_token,
    )

    def _check_actor(sid: str | None) -> tuple[bool, str]:
        if not sid:
            return False, "missing_session_id"
        ok, detail, payload = _request_json(
            f"{config.mission_control_url}/api/openclaw/sessions/{sid}",
            "GET",
            config.mc_api_token,
        )
        if not ok:
            return False, detail
        has_session = isinstance(payload.get("session"), dict)
        return has_session, ("ok" if has_session else "missing_session_payload")

    dev_ok, dev_detail = _check_actor(str(dev_sid or ""))
    arch_ok, arch_detail = _check_actor(str(arch_sid or ""))
    overall_ok = bool(orchestrator_online and health_ok and dev_ok and arch_ok)

    payload = {
        "schema_version": "handshake_state_v1",
        "updated_at": now,
        "overall": "green" if overall_ok else "red",
        "mission_control": {"online": bool(health_ok), "detail": health_detail},
        "players": {
            "orchestrator": {"online": orchestrator_online, "detail": "running" if orchestrator_online else "runtime_not_running"},
            "architect": {"online": bool(arch_ok), "detail": arch_detail, "session_id": str(arch_sid or "")},
            "developer": {"online": bool(dev_ok), "detail": dev_detail, "session_id": str(dev_sid or "")},
        },
    }
    if not write:
        return payload

    state_path = config.docs_working / "handshake_state.json"
    journal_path = config.docs_working / "handshake_journal.jsonl"
    previous = _read_json(state_path)
    changed = (
        previous.get("overall") != payload["overall"]
        or previous.get("players", {}).get("orchestrator", {}).get("online") != payload["players"]["orchestrator"]["online"]
        or previous.get("players", {}).get("architect", {}).get("online") != payload["players"]["architect"]["online"]
        or previous.get("players", {}).get("developer", {}).get("online") != payload["players"]["developer"]["online"]
    )
    state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    if changed:
        row = {"ts": now, "event": "handshake_update", "overall": payload["overall"], "players": payload["players"]}
        with journal_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
        append_audit(config.audit_path, {"event": "handshake_update", "overall": payload["overall"]})
    return payload


def status_snapshot(config: ForemanV2Config) -> dict:
    st = load_state(config.state_path)
    if st is None:
        return {"running": False, "state": "not_initialized", "directive_status": ""}
    running = False
    pid = _read_pid(config.pid_path)
    if pid is not None:
        running = _pid_exists(pid)
    progress_path = config.actor_progress_path or (config.docs_working / "actor_progress.jsonl")
    dev_flow = latest_actor_progress_for_generation(progress_path, actor="developer", generation=st.generation)
    arch_flow = latest_actor_progress_for_generation(progress_path, actor="architect", generation=st.generation)
    return {
        "running": running,
        "pid": pid,
        "bridge_state": st.bridge_state,
        "next_actor": st.next_actor,
        "proof_status": st.proof_status,
        "reason": st.last_transition_reason,
        "directive_title": st.directive_title,
        "directive_status": st.directive_status,
        "actor_flow": {
            "developer": dev_flow or {"status": "unknown", "step": "", "detail": "", "generation": st.generation},
            "architect": arch_flow or {"status": "unknown", "step": "", "detail": "", "generation": st.generation},
        },
    }


def terminate_runtime(config: ForemanV2Config) -> tuple[bool, str]:
    remote_results = {}
    for actor in ("developer", "architect"):
        ok_remote, detail_remote = close_actor_session(config, actor)
        remote_results[actor] = {"closed": ok_remote, "detail": detail_remote}
    remote_ok = all(v.get("closed") is True for v in remote_results.values())

    pid = _read_pid(config.pid_path)
    if pid is None:
        append_audit(config.audit_path, {"event": "operator_terminate", "pid": None, "remote": remote_results})
        if remote_ok:
            return True, f"remote_closed_no_local_pid remote={remote_results}"
        return False, f"no_pid_file remote={remote_results}"
    if not _pid_exists(pid):
        append_audit(config.audit_path, {"event": "operator_terminate", "pid": pid, "remote": remote_results})
        if remote_ok:
            return True, f"remote_closed_pid_not_running remote={remote_results}"
        return False, f"pid_not_running remote={remote_results}"
    os.kill(pid, signal.SIGTERM)
    append_audit(config.audit_path, {"event": "operator_terminate", "pid": pid, "remote": remote_results})
    return True, f"terminated_pid_{pid} remote={remote_results}"


def operator_route(config: ForemanV2Config, actor: str, message: str) -> tuple[bool, str]:
    holder = str(_read_json(config.talking_stick_path).get("holder", "none"))
    if holder != actor:
        detail = f"actor_not_holding_stick:holder={holder}"
        append_audit(
            config.audit_path,
            {"event": "operator_route_rejected", "actor": actor, "detail": detail, "message": message},
        )
        return False, detail
    msg = f"[Operator] {message}"
    r = dispatch_to_actor(config, actor, msg)
    append_audit(
        config.audit_path,
        {"event": "operator_route", "actor": actor, "sent": r.sent, "detail": r.detail, "message": message},
    )
    return r.sent, r.detail


def operator_broadcast(config: ForemanV2Config, message: str) -> dict:
    holder = str(_read_json(config.talking_stick_path).get("holder", "none"))
    if holder not in {"developer", "architect"}:
        detail = f"broadcast_rejected_invalid_holder:{holder}"
        append_audit(config.audit_path, {"event": "operator_broadcast_rejected", "detail": detail, "message": message})
        return {
            "developer": {"sent": False, "detail": detail},
            "architect": {"sent": False, "detail": detail},
        }
    ok, detail = operator_route(config, holder, message)
    other = "architect" if holder == "developer" else "developer"
    return {
        holder: {"sent": ok, "detail": detail},
        other: {"sent": False, "detail": f"broadcast_blocked_by_turn_ownership:holder={holder}"},
    }


def print_status(config: ForemanV2Config) -> None:
    print(json.dumps(status_snapshot(config), indent=2, ensure_ascii=True))


def actor_report(config: ForemanV2Config, actor: str, status: str, detail: str = "", step: str = "") -> dict:
    progress_path = config.actor_progress_path or (config.docs_working / "actor_progress.jsonl")
    st = load_state(config.state_path)
    generation = st.generation if st is not None else ""
    payload = append_actor_progress(
        progress_path,
        actor=actor,
        status=status,
        detail=detail,
        generation=generation,
        step=step,
    )
    append_audit(
        config.audit_path,
        {
            "event": "actor_report",
            "actor": actor,
            "status": status,
            "step": step,
            "generation": generation,
            "detail": detail,
        },
    )
    journal_path = config.docs_working / "actor_command_journal.jsonl"
    journal_entry = {
        "ts": datetime.now().astimezone().isoformat(),
        "event": "actor_report",
        "generation": generation,
        "actor": actor,
        "status": status,
        "step": step,
        "detail": detail,
    }
    with journal_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(journal_entry, ensure_ascii=True) + "\n")
    return payload


def doctor(config: ForemanV2Config) -> tuple[bool, dict]:
    dev_resolved = _session_id_for_actor(config, "developer")
    arch_resolved = _session_id_for_actor(config, "architect")
    checks: dict[str, object] = {
        "mission_control_url": config.mission_control_url,
        "developer_session_id_present": bool(dev_resolved),
        "architect_session_id_present": bool(arch_resolved),
    }
    ok_health, detail_health, _ = _request_json(
        f"{config.mission_control_url}/api/health",
        "GET",
        config.mc_api_token,
    )
    checks["mission_control_health"] = {"ok": ok_health, "detail": detail_health}
    session_checks = {}
    for actor, sid in (("developer", dev_resolved), ("architect", arch_resolved)):
        if not sid:
            session_checks[actor] = {"ok": False, "detail": "missing_session_id"}
            continue
        ok, detail, payload = _request_json(
            f"{config.mission_control_url}/api/openclaw/sessions/{sid}",
            "GET",
            config.mc_api_token,
        )
        session_checks[actor] = {
            "ok": ok,
            "detail": detail,
            "has_session_payload": isinstance(payload.get("session"), dict),
        }
    checks["session_preflight"] = session_checks
    checks["role_registry"] = _read_role_registry(config.role_registry_path)
    pid = _read_pid(config.pid_path)
    loop_running = bool(pid is not None and _pid_exists(pid))
    checks["foreman_loop"] = {"running": loop_running, "pid": pid}
    all_ok = bool(ok_health) and all(v.get("ok") for v in session_checks.values())
    return all_ok, checks


def repair_comms(config: ForemanV2Config) -> tuple[bool, str, dict[str, Any]]:
    """Rebind stale session UUIDs against Mission Control when possible; refresh config from ``.env.foreman_v2``."""
    from foreman_v2.config import apply_env_file, load_config  # noqa: PLC0415

    ok, checks = doctor(config)
    mc_h = checks.get("mission_control_health")
    mc_ok = isinstance(mc_h, dict) and bool(mc_h.get("ok"))
    if not mc_ok:
        return False, "mission_control_unreachable_fix_url_or_start_mc", {"checks": checks}

    if ok:
        loop = checks.get("foreman_loop") if isinstance(checks.get("foreman_loop"), dict) else {}
        if not loop.get("running"):
            return True, "sessions_ok_foreman_loop_not_running", {
                "checks": checks,
                "start_loop_hint": "cd scripts/runtime && PYTHONPATH=. python3 -m talking_stick loop",
            }
        return True, "already_ok", {"checks": checks}

    sess = checks.get("session_preflight") or {}
    need_bind = False
    if isinstance(sess, dict):
        for actor in ("developer", "architect"):
            row = sess.get(actor)
            if not isinstance(row, dict) or not row.get("ok"):
                need_bind = True
                break

    if need_bind:
        bind_ok, bind_detail = bind_sessions(config)
        if not bind_ok:
            return False, f"bind_failed:{bind_detail}", {"checks": checks, "bind_detail": bind_detail}

        apply_env_file(config.repo_root / ".env.foreman_v2")
        config2 = load_config()
        ok2, checks2 = doctor(config2)
        loop2 = checks2.get("foreman_loop") if isinstance(checks2.get("foreman_loop"), dict) else {}
        out: dict[str, Any] = {"checks_before": checks, "checks_after": checks2, "bind_detail": bind_detail}
        if ok2:
            if not loop2.get("running"):
                out["start_loop_hint"] = "cd scripts/runtime && PYTHONPATH=. python3 -m talking_stick loop"
            return True, "rebound_sessions_ok", out
        return False, "sessions_still_bad_after_bind", out

    return False, "doctor_failed_non_session", {"checks": checks}


def bind_sessions(config: ForemanV2Config) -> tuple[bool, str]:
    ok, detail, payload = _request_json(
        f"{config.mission_control_url}/api/openclaw/sessions",
        "GET",
        config.mc_api_token,
    )
    if not ok:
        return False, f"sessions_list_failed:{detail}"
    sessions_root = payload.get("sessions", {})
    if not isinstance(sessions_root, dict):
        return False, "sessions_list_failed:bad_payload"
    sessions = sessions_root.get("sessions", [])
    if not isinstance(sessions, list):
        return False, "sessions_list_failed:bad_sessions"

    candidates = []
    for s in sessions:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("sessionId", "")).strip() or str(s.get("id", "")).strip()
        key = str(s.get("key", "")).strip()
        if not sid or not key:
            continue
        if key == "agent:main:main":
            continue
        candidates.append((sid, key))
    if len(candidates) < 2:
        return False, "bind_failed:not_enough_non_main_sessions"

    dev_sid, _ = candidates[0]
    arch_sid, _ = candidates[1]
    env_path = config.repo_root / ".env.foreman_v2"
    _upsert_env(env_path, "MISSION_CONTROL_URL", config.mission_control_url)
    _upsert_env(env_path, "MC_API_TOKEN", config.mc_api_token)
    _upsert_env(env_path, "FOREMAN_V2_DEVELOPER_SESSION", dev_sid)
    _upsert_env(env_path, "FOREMAN_V2_ARCHITECT_SESSION", arch_sid)
    _write_role_registry(config.role_registry_path, config.mission_control_url, dev_sid, arch_sid)
    if config.session_lock_path.exists():
        config.session_lock_path.unlink()
    return True, f"bound developer={dev_sid} architect={arch_sid}"


def reconcile(config: ForemanV2Config) -> RuntimeState:
    prev = load_state(config.state_path)
    title, status, closed = read_directive_fields(config.docs_working)
    shared_log = read_shared_log_text(config.docs_working)
    proof = check_proof_and_handoff(shared_log)
    dev_gate = check_developer_artifacts(shared_log, config.docs_working, config.repo_root, directive_title=title)
    arch_gate = check_architect_artifacts(shared_log, config.docs_working, config.repo_root)
    decision = decide_state(
        directive_closed=closed,
        has_proof=proof.has_proof,
        developer_handoff_back=proof.developer_handoff_back,
        last_state=prev.bridge_state if prev else "idle",
        architect_verdict=proof.architect_verdict,
        architect_rejection_count=proof.architect_rejection_count,
        architect_outcome=proof.architect_outcome,
        developer_artifact_gate_passed=dev_gate.passed,
        developer_artifact_missing=dev_gate.missing,
        architect_artifact_gate_passed=arch_gate.passed,
        architect_artifact_missing=arch_gate.missing,
    )
    proof_status = "present" if proof.has_proof else "missing"
    st = RuntimeState(
        generation=make_generation(title, status, decision.next_state, decision.next_actor, proof_status),
        directive_title=title,
        directive_status=status,
        bridge_state=decision.next_state,
        next_actor=decision.next_actor,
        required_phrase=decision.required_phrase,
        proof_status=proof_status,
        last_transition_reason=f"reconcile:{decision.reason}",
        updated_at=now_iso(),
    )
    save_state(config.state_path, st)
    # Reconcile is an operator recovery action; clear stale command debt so
    # recovered state does not instantly fall back into timeout conflict.
    cmd_path = config.docs_working / "actor_command_state.json"
    if cmd_path.exists():
        cmd_path.unlink()
    # Reconcile should re-bootstrap flow control, not auto-advance plan authority.
    # If runtime is closed, explicitly return floor to architect via orchestrator.
    if st.bridge_state == "closed":
        st = replace(
            st,
            bridge_state="architect_action_required",
            next_actor="architect",
            required_phrase="have cursor validate shared-docs",
            last_transition_reason="reconcile_bootstrap_architect_review_required",
            generation=make_generation(
                st.directive_title,
                st.directive_status,
                "architect_action_required",
                "architect",
                st.proof_status,
            ),
            updated_at=now_iso(),
        )
        save_state(config.state_path, st)
        stick_sync(
            config,
            actor_override="architect",
            required_phrase=st.required_phrase,
            directive_title=st.directive_title,
            reason_override="reconcile bootstrap: orchestrator returned floor to architect",
        )
    else:
        stick_sync(config, actor_override=st.next_actor, required_phrase=st.required_phrase, directive_title=st.directive_title)
    append_audit(
        config.audit_path,
        {"event": "reconcile", "generation": st.generation, "next_actor": st.next_actor, "bridge_state": st.bridge_state},
    )
    return st


def _advance_to_next_plan_directive(config: ForemanV2Config) -> bool:
    plan_path = config.repo_root / "docs" / "architect" / "development_plan.md"
    if not plan_path.exists():
        return False
    text = plan_path.read_text(encoding="utf-8", errors="ignore")
    tasks = _unchecked_plan_tasks(text)
    if not tasks:
        return False
    section, task = tasks[0]
    directive_title = f"PHASE {section} - {task}".strip()
    cur_path = config.docs_working / "current_directive.md"
    cur_text = cur_path.read_text(encoding="utf-8", errors="ignore") if cur_path.exists() else ""
    updated = cur_text
    if "**Status:**" in updated:
        updated = re.sub(r"^\*\*Status:\*\*.*$", "**Status:** Active", updated, count=1, flags=re.M)
    else:
        updated = f"**Status:** Active\n\n{updated}"
    if "## Title" in updated:
        updated = re.sub(r"(?ms)^## Title\s*\n\s*\*\*.+?\*\*", f"## Title\n\n**{directive_title}**", updated, count=1)
    else:
        updated = f"{updated}\n\n## Title\n\n**{directive_title}**\n"
    if updated != cur_text:
        cur_path.write_text(updated, encoding="utf-8")
    log_path = config.docs_working / "shared_coordination_log.md"
    ts = datetime.now().astimezone().isoformat()
    entry = (
        f"\n- {ts} - Orchestrator: auto-advanced to next plan task\n"
        f"  - DIRECTIVE_CONTEXT: {directive_title}\n"
        f"  - next_directive: {directive_title}\n"
        "  - source: docs/architect/development_plan.md (first unchecked task)\n"
    )
    prev = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + entry, encoding="utf-8")
    return True


def _unchecked_plan_tasks(plan_text: str) -> list[tuple[str, str]]:
    tasks: list[tuple[str, str]] = []
    section = ""
    for raw in plan_text.splitlines():
        line = raw.strip()
        m = re.match(r"^###\s+([0-9]+\.[0-9]+)\b", line)
        if m:
            section = m.group(1)
            continue
        t = re.match(r"^- \[ \]\s+(.+)$", line)
        if t and section.startswith("5."):
            task = t.group(1).strip()
            if task:
                tasks.append((section, task))
    return tasks


def reset_to_canonical(config: ForemanV2Config) -> RuntimeState:
    if config.session_lock_path.exists():
        config.session_lock_path.unlink()
    st = reconcile(config)
    append_audit(config.audit_path, {"event": "reset_to_canonical", "generation": st.generation})
    return st


def stick_sync(
    config: ForemanV2Config,
    actor_override: str | None = None,
    required_phrase: str | None = None,
    directive_title: str | None = None,
    reason_override: str | None = None,
) -> dict:
    target_actor = actor_override
    if target_actor is None:
        st = load_state(config.state_path)
        target_actor = st.next_actor if st else "none"
        required_phrase = required_phrase or (st.required_phrase if st else "have cursor validate shared-docs")
        directive_title = directive_title or (st.directive_title if st else "unknown")
    if target_actor not in {"developer", "architect", "none"}:
        target_actor = "none"
    data = _read_json(config.talking_stick_path)
    holder_before = str(data.get("holder", "none"))
    data.update(
        {
            "schema_version": "talking_stick_v1",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M "),
            "holder": target_actor,
            "handed_from": holder_before,
            "handed_to": target_actor,
            "reason": reason_override or "foreman_v2 stick sync",
            "required_phrase": required_phrase or "have cursor validate shared-docs",
            "directive_title": directive_title or "unknown",
        }
    )
    config.talking_stick_path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    append_audit(
        config.audit_path,
        {"event": "stick_sync", "holder_before": holder_before, "holder_after": target_actor},
    )
    return data


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


def _upsert_env(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    replaced = False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _write_role_registry(path: Path, mission_control_url: str, developer_session_id: str, architect_session_id: str) -> None:
    payload = {
        "schema_version": "foreman_v2_role_registry_v1",
        "mission_control_url": mission_control_url,
        "roles": {
            "developer": {"session_id": developer_session_id},
            "architect": {"session_id": architect_session_id},
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _read_role_registry(path: Path) -> dict:
    if not path.exists():
        return {"present": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"present": True, "valid": False}
        return {"present": True, "valid": True, "roles": data.get("roles", {})}
    except Exception:  # noqa: BLE001
        return {"present": True, "valid": False}

