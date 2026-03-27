from __future__ import annotations

import os
import signal
import time
from dataclasses import replace

from foreman_v2.audit import append_audit
from foreman_v2.broker import dispatch_to_actor
from foreman_v2.config import ForemanV2Config
from foreman_v2.proof_gate import check_proof_and_handoff
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

    decision = decide_state(
        directive_closed=closed,
        has_proof=proof.has_proof,
        developer_handoff_back=proof.developer_handoff_back,
        last_state=prev.bridge_state if prev else "idle",
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

    should_dispatch = prev is None or prev.generation != state.generation
    if should_dispatch and state.next_actor in {"developer", "architect"}:
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
        append_audit(
            config.audit_path,
            {
                "event": "dispatch_skipped_dedup",
                "generation": state.generation,
                "next_actor": state.next_actor,
            },
        )

    save_state(config.state_path, state)
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
    return state


def run_loop(config: ForemanV2Config) -> None:
    running = True

    def _handle_stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    config.pid_path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        while running:
            run_once(config)
            time.sleep(config.poll_seconds)
    finally:
        if config.pid_path.exists():
            config.pid_path.unlink()

