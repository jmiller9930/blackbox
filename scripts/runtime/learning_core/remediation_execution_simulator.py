"""4.6.3.2 Part B DATA Twig 5 — simulation-first remediation execution (sandbox-only).

Models how a remediation **pattern** would be applied using **synthetic state only**.
Does **not** execute real remediation, mutate production systems, call services, or integrate
with DATA output generation. **Simulation results are never permission to execute.**

Imports are limited to `learning_core` — no `telegram_interface`, runtime dispatch, or execution hooks.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from learning_core.remediation_pattern_registry import (
    STATUS_DEPRECATED,
    STATUS_REJECTED,
    get_pattern,
)
from learning_core.remediation_validation import get_candidate

_SIM_PHASE = "simulation_phase_no_real_execution_hook"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def evaluate_simulation_policy(validation_context: dict[str, Any] | None) -> dict[str, Any]:
    """
    Deterministic policy gate simulation for “would real execution be allowed?”.

    In this phase `would_allow_real_execution` is **always** False — real hooks do not exist.
    """
    ctx = dict(validation_context or {})
    maintenance_window_required = bool(ctx.get("maintenance_window_required", True))
    maintenance_window_active = bool(ctx.get("maintenance_window_active", False))
    hypothetical_approval = bool(ctx.get("hypothetical_approval_granted", False))
    reasons: list[str] = []
    if not hypothetical_approval:
        reasons.append("approval_required_not_granted")
    if maintenance_window_required and not maintenance_window_active:
        reasons.append("maintenance_window_not_active")
    reasons.append(_SIM_PHASE)
    return {
        "approval_required": True,
        "maintenance_window_required": maintenance_window_required,
        "maintenance_window_active": maintenance_window_active,
        "hypothetical_approval_granted": hypothetical_approval,
        "execution_blocked_reason": ";".join(reasons),
        "would_allow_real_execution": False,
    }


def _rollback_simulation_flags(
    *,
    synthetic_apply_succeeds: bool,
    synthetic_rollback_failure: bool,
) -> tuple[bool, bool]:
    """Deterministic rollback model: no real revert; flags only."""
    if not synthetic_apply_succeeds:
        return False, False
    return True, not synthetic_rollback_failure


def simulate_and_record_remediation_execution(
    conn: sqlite3.Connection,
    *,
    pattern_id: str,
    remediation_id: str,
    validation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Simulate application of a pattern on synthetic inputs; persist one sandbox row.

    Contract: `pattern_id` must belong to `remediation_id` via `source_remediation_id`.
    """
    pat = get_pattern(conn, pattern_id)
    if pat is None:
        raise LookupError(f"pattern not found: {pattern_id}")
    if pat.source_remediation_id != remediation_id:
        raise ValueError("remediation_id does not match pattern source_remediation_id")

    cand = get_candidate(conn, remediation_id)
    if cand is None:
        raise LookupError(f"remediation candidate not found: {remediation_id}")
    action_desc = f"{cand.description[:512]} | {cand.proposed_action[:512]}".strip()

    ctx = dict(validation_context or {})
    policy = evaluate_simulation_policy(ctx)

    synthetic_apply_ok = bool(ctx.get("synthetic_apply_succeeds", True))
    synthetic_rb_fail = bool(ctx.get("synthetic_rollback_failure", False))

    failure_reason = ""
    failure_class = ""
    result = "fail"
    rb_att, rb_ok = False, False

    if pat.pattern_status == STATUS_REJECTED:
        failure_reason = "pattern_rejected_not_executable"
        failure_class = "functional"
    elif pat.pattern_status == STATUS_DEPRECATED:
        failure_reason = "pattern_deprecated_not_executable"
        failure_class = "stability"
    elif not synthetic_apply_ok:
        failure_reason = "synthetic_apply_failed"
        failure_class = "functional"
        rb_att, rb_ok = _rollback_simulation_flags(
            synthetic_apply_succeeds=False, synthetic_rollback_failure=False
        )
    elif synthetic_rb_fail:
        failure_reason = "synthetic_rollback_failed"
        failure_class = "regression"
        result = "fail"
        rb_att, rb_ok = _rollback_simulation_flags(
            synthetic_apply_succeeds=True, synthetic_rollback_failure=True
        )
    else:
        result = "success"
        rb_att, rb_ok = _rollback_simulation_flags(
            synthetic_apply_succeeds=True, synthetic_rollback_failure=False
        )

    sim_id = str(uuid.uuid4())
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO remediation_execution_simulations (
          execution_simulation_id, pattern_id, remediation_id, simulated_action_description,
          result, failure_reason, failure_class, rollback_attempted, rollback_success,
          simulation_timestamp, policy_json, validation_context_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sim_id,
            pattern_id,
            remediation_id,
            action_desc,
            result,
            failure_reason,
            failure_class,
            int(rb_att),
            int(rb_ok),
            now,
            json.dumps(policy, sort_keys=True, ensure_ascii=False),
            json.dumps(ctx, sort_keys=True, ensure_ascii=False),
        ),
    )
    conn.commit()

    return {
        "execution_simulation_id": sim_id,
        "pattern_id": pattern_id,
        "remediation_id": remediation_id,
        "simulated_action_description": action_desc,
        "result": result,
        "failure_reason": failure_reason,
        "failure_class": failure_class,
        "rollback_attempted": rb_att,
        "rollback_success": rb_ok,
        "simulation_timestamp": now,
        "policy": policy,
        "simulation_disclaimer": "Simulation is not permission to execute real remediation.",
    }
