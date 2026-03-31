from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import replace
from datetime import datetime

from foreman_v2.artifact_gate import check_architect_artifacts, check_developer_artifacts
from foreman_v2.audit import append_audit
from foreman_v2.cycle_log import append_unified_cycle_log
from foreman_v2.broker import dispatch_to_actor
from foreman_v2.config import ForemanV2Config
from foreman_v2.control import handshake_snapshot
from foreman_v2.proof_gate import check_proof_and_handoff
from foreman_v2.progress import append_actor_progress, latest_actor_progress_for_generation
from foreman_v2.protocol import decide_state
from foreman_v2.state import (
    RuntimeState,
    load_state,
    make_generation,
    now_iso,
    read_directive_fields,
    read_shared_log_text,
    save_state,
)

_ARCHITECT_REDRIVE_SECONDS = 45.0
_DEVELOPER_REDRIVE_SECONDS = 30.0
_COMMAND_TIMEOUT_SECONDS = 90.0
_COMMAND_MAX_ATTEMPTS = 3


def _message_for(actor: str, phrase: str, reason: str, title: str) -> str:
    if actor == "developer":
        return (
            f"[Foreman v2] Directive: {title}\n"
            f"Reason: {reason}\n"
            "Action: implement and record proof in shared docs.\n"
            f"When done, reply with phrase: {phrase}"
        )
    if actor == "architect":
        return (
            f"[Foreman v2] Directive: {title}\n"
            f"Reason: {reason}\n"
            "Action: validate proof and close or amend.\n"
            f"When routing back, use phrase: {phrase}"
        )
    return f"[Foreman v2] {title} | {reason}"


def run_once(config: ForemanV2Config) -> RuntimeState:
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
    generation = make_generation(title, status, decision.next_state, decision.next_actor, proof_status)
    state = RuntimeState(
        generation=generation,
        directive_title=title,
        directive_status=status,
        bridge_state=decision.next_state,
        next_actor=decision.next_actor,
        required_phrase=decision.required_phrase,
        proof_status=proof_status,
        last_transition_reason=decision.reason,
        updated_at=now_iso(),
    )

    holder_before = _read_talking_stick_holder(config)
    if (
        holder_before in {"developer", "architect"}
        and holder_before != state.next_actor
        and prev is not None
        and prev.generation == state.generation
    ):
        state = replace(state, bridge_state="sync_conflict", last_transition_reason="stick_holder_mismatch")

    should_dispatch = prev is None or prev.generation != state.generation
    command_state = _load_command_state(config)
    _apply_actor_progress_to_command(config, state, command_state)
    if should_dispatch and state.next_actor in {"developer", "architect"} and state.bridge_state != "sync_conflict":
        msg = _message_for(state.next_actor, state.required_phrase, state.last_transition_reason, state.directive_title)
        dispatch_key = f"{state.generation}:{state.next_actor}"
        dispatched = dispatch_to_actor(config, state.next_actor, msg, dispatch_key=dispatch_key)
        append_audit(
            config.audit_path,
            {
                "event": "dispatch",
                "generation": state.generation,
                "dispatch_key": dispatch_key,
                "actor": state.next_actor,
                "sent": dispatched.sent,
                "detail": dispatched.detail,
            },
        )
        if not dispatched.sent:
            state = replace(state, bridge_state="sync_conflict", last_transition_reason=f"dispatch_failed:{dispatched.detail}")
        else:
            _record_command_dispatch(config, command_state, state, dispatch_key)
    else:
        # Keep orchestration active for architect gate ownership. If the same generation
        # has been parked too long, redrive a reminder dispatch instead of passively idling.
        command_action = _command_action(config, state, command_state)
        if command_action == "conflict":
            state = _handle_command_timeout(config, state, command_state)
        elif command_action == "redrive" or _should_redrive_dispatch(config, state):
            msg = _redrive_message_for(config, state)
            dispatch_key = f"{state.generation}:{state.next_actor}"
            redrive = dispatch_to_actor(config, state.next_actor, msg, dispatch_key=dispatch_key)
            append_audit(
                config.audit_path,
                {
                    "event": "dispatch_redrive",
                    "generation": state.generation,
                    "dispatch_key": dispatch_key,
                    "actor": state.next_actor,
                    "sent": redrive.sent,
                    "detail": redrive.detail,
                },
            )
            if not redrive.sent:
                state = replace(state, bridge_state="sync_conflict", last_transition_reason=f"dispatch_failed:{redrive.detail}")
            else:
                _record_command_dispatch(config, command_state, state, dispatch_key)
        else:
            append_audit(
                config.audit_path,
                {
                    "event": "dispatch_skipped_dedup",
                    "generation": state.generation,
                    "next_actor": state.next_actor,
                },
            )

    state = _recover_and_reissue_on_failure(config, state, command_state)
    save_state(config.state_path, state)
    _save_command_state(config, command_state)
    _sync_talking_stick(config, state)
    append_audit(
        config.audit_path,
        {
            "event": "state_write",
            "generation": state.generation,
            "bridge_state": state.bridge_state,
            "next_actor": state.next_actor,
            "proof_status": state.proof_status,
            "reason": state.last_transition_reason,
        },
    )
    # Maintain comms presence artifact for monitor green/red indicators.
    handshake_snapshot(config, write=True)
    return state


def _recover_and_reissue_on_failure(config: ForemanV2Config, state: RuntimeState, command_state: dict) -> RuntimeState:
    """Keep orchestration moving by reissuing the active lane after dispatch failures."""
    if state.bridge_state != "sync_conflict":
        return state
    reason = str(state.last_transition_reason or "")
    if not reason.startswith("dispatch_failed:"):
        return state
    target = state.next_actor if state.next_actor in {"developer", "architect"} else "architect"
    next_state = "developer_action_required" if target == "developer" else "architect_action_required"
    detail = reason.split("dispatch_failed:", 1)[1].strip() or "unknown_dispatch_failure"
    command_state.pop("command", None)
    append_audit(
        config.audit_path,
        {
            "event": "auto_reissue_after_failure",
            "failed_reason": detail,
            "target_actor": target,
            "target_state": next_state,
        },
    )
    return replace(
        state,
        generation=make_generation(
            state.directive_title,
            state.directive_status,
            next_state,
            target,
            state.proof_status,
        ),
        bridge_state=next_state,
        next_actor=target,
        last_transition_reason=f"auto_reissue_after_failure:{detail}",
    )


def _sync_talking_stick(config: ForemanV2Config, state: RuntimeState) -> None:
    path = config.talking_stick_path
    payload = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    holder_before = str(payload.get("holder", "none"))
    holder_after = state.next_actor if state.next_actor in {"developer", "architect", "none"} else "none"
    payload.update(
        {
            "schema_version": "talking_stick_v1",
            "generation": state.generation,
            "holder": holder_after,
            "handed_from": holder_before,
            "handed_to": holder_after,
            "reason": f"foreman_v2 state sync:{state.last_transition_reason}",
            "required_phrase": state.required_phrase,
            "directive_title": state.directive_title,
        }
    )
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _read_talking_stick_holder(config: ForemanV2Config) -> str:
    path = config.talking_stick_path
    if not path.exists():
        return "none"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return str(payload.get("holder", "none"))
    except Exception:  # noqa: BLE001
        return "none"
    return "none"


def _should_redrive_dispatch(config: ForemanV2Config, state: RuntimeState) -> bool:
    if state.next_actor not in {"developer", "architect"}:
        return False
    if state.bridge_state == "sync_conflict":
        return False
    if state.bridge_state not in {"developer_action_required", "developer_active", "architect_action_required"}:
        return False
    cadence = _ARCHITECT_REDRIVE_SECONDS if state.next_actor == "architect" else _DEVELOPER_REDRIVE_SECONDS
    last = _last_dispatch_ts(config.audit_path, state.generation, "architect")
    if state.next_actor == "developer":
        last = _last_dispatch_ts(config.audit_path, state.generation, "developer")
    if last is None:
        return True
    return (datetime.now().astimezone() - last).total_seconds() >= cadence


def _redrive_message_for(config: ForemanV2Config, state: RuntimeState) -> str:
    actor = state.next_actor
    progress_path = config.actor_progress_path or (config.docs_working / "actor_progress.jsonl")
    latest = latest_actor_progress_for_generation(progress_path, actor=actor, generation=state.generation)
    status = ""
    detail = ""
    step = ""
    if isinstance(latest, dict):
        status = str(latest.get("status", "")).strip().lower()
        detail = str(latest.get("detail", "")).strip()
        step = str(latest.get("step", "")).strip().lower()
    guidance = state.last_transition_reason
    if status in {"blocked", "failed"}:
        guidance = f"{guidance}; actor_reported_{status}:{detail or 'no_detail'}"
    elif status in {"ready_for_handoff", "success"} and "artifact_gate_failed" in state.last_transition_reason:
        guidance = f"{guidance}; actor_reported_ready_but_artifacts_missing"
    elif status:
        guidance = f"{guidance}; actor_status:{status}"
    if step:
        guidance = f"{guidance}; actor_step:{step}"
    if not status:
        guidance = f"{guidance}; actor_status:unknown"
    return _message_for(actor, state.required_phrase, guidance, state.directive_title)


def _last_dispatch_ts(audit_path, generation: str, actor: str):  # noqa: ANN001
    if not audit_path.exists():
        return None
    lines = audit_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in reversed(lines):
        if '"event": "dispatch"' not in line and '"event": "dispatch_redrive"' not in line:
            continue
        try:
            payload = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if payload.get("generation") != generation or payload.get("actor") != actor:
            continue
        ts = str(payload.get("ts", "")).strip()
        if not ts:
            continue
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            continue
    return None


def _command_state_path(config: ForemanV2Config):
    return config.docs_working / "actor_command_state.json"


def _load_command_state(config: ForemanV2Config) -> dict:
    path = _command_state_path(config)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _save_command_state(config: ForemanV2Config, payload: dict) -> None:
    path = _command_state_path(config)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _record_command_dispatch(config: ForemanV2Config, command_state: dict, state: RuntimeState, dispatch_key: str) -> None:
    now = datetime.now().astimezone().isoformat()
    existing = command_state.get("command", {})
    attempts = 1
    if (
        isinstance(existing, dict)
        and str(existing.get("generation", "")) == state.generation
        and str(existing.get("actor", "")) == state.next_actor
    ):
        attempts = int(existing.get("attempts", 0)) + 1
    command_state["command"] = {
        "generation": state.generation,
        "actor": state.next_actor,
        "command_id": dispatch_key,
        "dispatch_key": dispatch_key,
        "attempts": attempts,
        "status": "pending",
        "last_dispatch_at": now,
    }
    _append_command_journal(
        config,
        "command_dispatched",
        {
            "generation": state.generation,
            "actor": state.next_actor,
            "command_id": dispatch_key,
            "attempts": attempts,
        },
    )


def _apply_actor_progress_to_command(config: ForemanV2Config, state: RuntimeState, command_state: dict) -> None:
    cmd = command_state.get("command", {})
    if not isinstance(cmd, dict):
        return
    if str(cmd.get("generation", "")) != state.generation:
        return
    actor = str(cmd.get("actor", "")).strip().lower()
    if actor not in {"developer", "architect"}:
        return
    progress_path = config.actor_progress_path or (config.docs_working / "actor_progress.jsonl")
    latest = latest_actor_progress_for_generation(progress_path, actor=actor, generation=state.generation)
    if not isinstance(latest, dict):
        return
    status = str(latest.get("status", "")).strip().lower()
    now = datetime.now().astimezone().isoformat()
    if status == "received":
        cmd["status"] = "received"
        cmd["last_ack_at"] = now
    elif status in {"started", "in_progress"}:
        cmd["status"] = "started"
        cmd["last_progress_at"] = now
    elif status in {"ready_for_handoff", "success"}:
        cmd["status"] = "completed"
        cmd["last_progress_at"] = now
    elif status in {"blocked", "failed"}:
        cmd["status"] = status
        cmd["last_progress_at"] = now
    command_state["command"] = cmd
    _append_command_journal(
        config,
        "actor_progress_ack",
        {
            "generation": state.generation,
            "actor": actor,
            "status": cmd.get("status", ""),
            "reported_status": status,
            "step": latest.get("step", ""),
        },
    )


def _command_action(config: ForemanV2Config, state: RuntimeState, command_state: dict) -> str:
    if state.next_actor not in {"developer", "architect"}:
        return "skip"
    cmd = command_state.get("command", {})
    if not isinstance(cmd, dict):
        return "redrive"
    if str(cmd.get("generation", "")) != state.generation or str(cmd.get("actor", "")) != state.next_actor:
        return "redrive"
    status = str(cmd.get("status", "")).strip().lower()
    if status in {"completed", "success"}:
        return "skip"
    if status in {"blocked", "failed"}:
        return "redrive"
    last_dispatch_at = str(cmd.get("last_dispatch_at", "")).strip()
    last_progress_at = str(cmd.get("last_progress_at", "")).strip()
    attempts = int(cmd.get("attempts", 0))
    if status in {"received", "started"} and last_progress_at:
        try:
            progress_ts = datetime.fromisoformat(last_progress_at)
            if (datetime.now().astimezone() - progress_ts).total_seconds() < _COMMAND_TIMEOUT_SECONDS:
                return "skip"
        except ValueError:
            pass
    if not last_dispatch_at:
        return "redrive"
    try:
        last_ts = datetime.fromisoformat(last_dispatch_at)
    except ValueError:
        return "redrive"
    age = (datetime.now().astimezone() - last_ts).total_seconds()
    if age < _COMMAND_TIMEOUT_SECONDS:
        return "skip"
    if attempts >= _COMMAND_MAX_ATTEMPTS:
        _append_command_journal(
            config,
            "command_timeout",
            {"generation": state.generation, "actor": state.next_actor, "attempts": attempts},
        )
        return "conflict"
    return "redrive"


def _append_command_journal(config: ForemanV2Config, event: str, payload: dict) -> None:
    path = config.docs_working / "actor_command_journal.jsonl"
    row = {"ts": datetime.now().astimezone().isoformat(), "event": event}
    row.update(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def _handle_command_timeout(config: ForemanV2Config, state: RuntimeState, command_state: dict) -> RuntimeState:
    actor = state.next_actor
    if actor == "architect":
        _append_timeout_reject_artifact(config, state)
        progress_path = config.actor_progress_path or (config.docs_working / "actor_progress.jsonl")
        append_actor_progress(
            progress_path,
            actor="architect",
            status="failed",
            step="record_verdict",
            detail="timeout_fail_closed_reject",
            generation=state.generation,
        )
        _append_command_journal(
            config,
            "timeout_fail_closed_reject",
            {"generation": state.generation, "actor": actor},
        )
        command_state.pop("command", None)
        reason = "architect_timeout_fail_closed_reject"
        new_generation = make_generation(
            state.directive_title,
            state.directive_status,
            "developer_action_required",
            "developer",
            "missing",
        )
        return replace(
            state,
            generation=new_generation,
            bridge_state="developer_action_required",
            next_actor="developer",
            proof_status="missing",
            last_transition_reason=reason,
        )
    return replace(state, bridge_state="sync_conflict", last_transition_reason="command_timeout_no_ack")


def _append_timeout_reject_artifact(config: ForemanV2Config, state: RuntimeState) -> None:
    path = config.docs_working / "shared_coordination_log.md"
    ts = datetime.now().astimezone().isoformat()
    line = (
        f"\n- {ts} - Architect timeout fail-closed\n"
        "  - ARCHITECT_CANONICAL_VERDICT: not_met\n"
        "  - ARCHITECT_DIRECTIVE_OUTCOME: rejected\n"
        "  - timeout_policy: fail_closed_reject\n"
    )
    existing = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    path.write_text(existing.rstrip() + "\n" + line, encoding="utf-8")
    append_audit(
        config.audit_path,
        {
            "event": "architect_timeout_fail_closed",
            "generation": state.generation,
            "actor": "architect",
        },
    )


def run_loop(config: ForemanV2Config) -> None:
    running = True
    cycle = 0

    def _handle_stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    config.pid_path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        while running:
            cycle += 1
            state = run_once(config)
            try:
                append_unified_cycle_log(config, cycle=cycle, state=state)
            except Exception:  # noqa: BLE001 — never break loop on log failure
                pass
            time.sleep(config.poll_seconds)
    finally:
        if config.pid_path.exists():
            config.pid_path.unlink()

