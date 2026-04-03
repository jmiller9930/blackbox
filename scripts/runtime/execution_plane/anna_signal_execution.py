"""
Anna strategy signal → execution_request_v1 (Jack downstream after approve + run_execution).

**Trader mode (optional, off by default):** ``ANNA_TRADER_MODE_AUTO_EXECUTE=1`` auto-approves the
pending request and runs ``run_execution`` so Jack can fire immediately after a strategy signal.
Use only in controlled environments; default is human approve.

Contract:
  - ``create_request`` may require a valid ``anna_proposal_v1`` (see ``BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION``).
  - After Anna analysis, non-``OBSERVATION_ONLY`` proposals auto-create a **pending** request so every
    strategy signal is wired to the same Jack path (unless trader mode auto-runs).
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def require_anna_proposal_for_execution_request() -> bool:
    """When True, ``create_request`` rejects proposals that are not Anna-sourced ``anna_proposal_v1``."""
    return _env_bool("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", True)


def auto_execution_request_from_anna_dispatch() -> bool:
    """When True, Anna dispatch creates a pending ``execution_request_v1`` for strategy signals."""
    return _env_bool("ANNA_AUTO_EXECUTION_REQUEST", True)


def validate_anna_proposal_v1(proposal: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(proposal, dict):
        return False, "proposal must be a dict"
    if proposal.get("kind") != "anna_proposal_v1":
        return False, "kind must be anna_proposal_v1"
    sv = proposal.get("schema_version")
    if sv is None:
        return False, "schema_version required"
    try:
        int(sv)
    except (TypeError, ValueError):
        return False, "schema_version must be int-compatible"
    ref = proposal.get("source_analysis_reference")
    if not isinstance(ref, dict):
        return False, "source_analysis_reference must be a dict"
    if ref.get("kind") != "anna_analysis_v1":
        return False, "source_analysis_reference.kind must be anna_analysis_v1"
    ptype = proposal.get("proposal_type")
    if ptype not in ("NO_CHANGE", "RISK_REDUCTION", "CONDITION_TIGHTENING", "OBSERVATION_ONLY"):
        return False, f"invalid proposal_type: {ptype!r}"
    return True, ""


def strategy_signal_wires_to_jack_path(proposal: dict[str, Any]) -> bool:
    """Strategy-affecting proposals (not pure observation) get an execution_request for the Jack pipeline."""
    return proposal.get("proposal_type") != "OBSERVATION_ONLY"


def try_create_execution_request_from_anna_analysis(
    analysis: dict[str, Any],
    *,
    source_task_id: str | None,
    extra_notes: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Build ``anna_proposal_v1`` from analysis; if this is a strategy signal, ``create_request``.

    Returns a small handoff dict for the UI, or None if skipped / failed.
    """
    if not auto_execution_request_from_anna_dispatch():
        return None
    if (analysis.get("pipeline") or {}).get("answer_source") == "preflight_blocked":
        return None
    try:
        from anna_modules.proposal import assemble_anna_proposal_v1
        from execution_plane.approval_manager import create_request
    except Exception as e:  # noqa: BLE001
        logger.warning("anna_signal_execution import failed: %s", e)
        return None

    notes = list(extra_notes or [])
    try:
        proposal = assemble_anna_proposal_v1(analysis, source_task_id=source_task_id, extra_notes=notes)
    except Exception as e:  # noqa: BLE001
        logger.warning("assemble_anna_proposal_v1 failed: %s", e)
        return None

    ok, err = validate_anna_proposal_v1(proposal)
    if not ok:
        logger.warning("anna_proposal validation failed: %s", err)
        return None

    if not strategy_signal_wires_to_jack_path(proposal):
        return None

    try:
        req = create_request(proposal)
    except ValueError as e:
        logger.warning("create_request rejected: %s", e)
        return None
    except Exception as e:  # noqa: BLE001
        logger.exception("create_request failed: %s", e)
        return None

    rid = req.get("request_id")
    return {
        "status": "pending_approval",
        "request_id": rid,
        "proposal_type": proposal.get("proposal_type"),
        "venue_executor": "jack",
        "note": "Anna-sourced strategy signal → execution_request_v1; approve then run_execution to invoke Jack (when configured), or enable ANNA_TRADER_MODE_AUTO_EXECUTE for immediate Jack (lab).",
    }


def maybe_trader_mode_auto_execute(request_id: str) -> dict[str, Any] | None:
    """
    If ``ANNA_TRADER_MODE_AUTO_EXECUTE`` is set, approve the request and ``run_execution`` (→ Jack delegate).

    Anna still only supplied the signal; approval identity is ``ANNA_TRADER_MODE_APPROVER_ID`` or
    ``trader-mode-auto``. Returns execution result dict, or None if disabled.
    """
    if not _env_bool("ANNA_TRADER_MODE_AUTO_EXECUTE", False):
        return None
    try:
        from execution_plane.approval_manager import approve_request
        from execution_plane.execution_engine import run_execution
    except Exception as e:  # noqa: BLE001
        logger.warning("trader_mode_auto_execute import failed: %s", e)
        return None

    approver = (os.environ.get("ANNA_TRADER_MODE_APPROVER_ID") or "trader-mode-auto").strip() or "trader-mode-auto"
    approved = approve_request(request_id, approver)
    if not approved:
        return {"status": "blocked", "reason": "approve_failed", "request_id": request_id}
    return run_execution(request_id)
