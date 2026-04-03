"""execution_request_v1 lifecycle: create → approve/reject → (engine). File-backed state."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anna_modules.util import PROPOSAL_SCHEMA_VERSION, utc_now
from _paths import repo_root

from .audit_logger import log_audit

REQUESTS_PATH = repo_root() / "data" / "runtime" / "execution_plane" / "requests.json"


def _load_requests() -> dict[str, Any]:
    if not REQUESTS_PATH.is_file():
        return {}
    return json.loads(REQUESTS_PATH.read_text(encoding="utf-8"))


def _save_requests(data: dict[str, Any]) -> None:
    REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    REQUESTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _minimal_proposal() -> dict[str, Any]:
    """Valid ``anna_proposal_v1`` for tests/CLI when no file is passed (OBSERVATION_ONLY — Jack path idle)."""
    now = utc_now()
    return {
        "kind": "anna_proposal_v1",
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "generated_at": now,
        "source_analysis_reference": {"task_id": None, "kind": "anna_analysis_v1"},
        "proposal_type": "OBSERVATION_ONLY",
        "proposal_summary": "Synthetic Anna-sourced placeholder for execution plane (tests/CLI default).",
        "proposed_effect": {
            "paper_mode_intent": "unknown",
            "guardrail_interaction": "Synthetic; not from live analysis.",
            "reasoning_scope": [],
        },
        "validation_plan": {"what_to_watch": [], "success_signals": [], "failure_signals": []},
        "supporting_reasoning": {
            "interpretation_summary": "",
            "risk_level": "low",
            "policy_alignment": "synthetic",
            "concepts_used": [],
        },
        "caution_flags": [],
        "notes": ["synthetic_minimal_proposal_v1"],
    }


def create_request(
    proposal: dict[str, Any] | None = None,
    *,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    from .anna_signal_execution import require_anna_proposal_for_execution_request, validate_anna_proposal_v1

    rid = str(uuid.uuid4())
    prop = proposal or _minimal_proposal()
    if require_anna_proposal_for_execution_request():
        ok, err = validate_anna_proposal_v1(prop)
        if not ok:
            raise ValueError(f"BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION: {err}")
    prop_id = proposal_id
    if prop_id is None:
        ref = prop.get("source_analysis_reference") or {}
        prop_id = ref.get("task_id") if isinstance(ref, dict) else None
    if prop_id is None:
        prop_id = f"proposal-{rid[:8]}"
    now = utc_now()
    req: dict[str, Any] = {
        "kind": "execution_request_v1",
        "schema_version": 1,
        "request_id": rid,
        "proposal_id": prop_id,
        "proposal_snapshot": prop,
        "approval_status": "pending",
        "approver_id": None,
        "created_at": now,
        "updated_at": now,
    }
    data = _load_requests()
    data[rid] = req
    _save_requests(data)
    log_audit("request_created", {"request_id": rid, "proposal_id": prop_id})
    return req


def approve_request(request_id: str, approver_id: str) -> dict[str, Any] | None:
    data = _load_requests()
    req = data.get(request_id)
    if not req:
        return None
    req["approval_status"] = "approved"
    req["approver_id"] = approver_id
    req["updated_at"] = utc_now()
    data[request_id] = req
    _save_requests(data)
    log_audit("request_approved", {"request_id": request_id, "approver_id": approver_id})
    return req


def reject_request(request_id: str, approver_id: str) -> dict[str, Any] | None:
    data = _load_requests()
    req = data.get(request_id)
    if not req:
        return None
    req["approval_status"] = "rejected"
    req["approver_id"] = approver_id
    req["updated_at"] = utc_now()
    data[request_id] = req
    _save_requests(data)
    log_audit("request_rejected", {"request_id": request_id, "approver_id": approver_id})
    return req


def get_request(request_id: str) -> dict[str, Any] | None:
    return _load_requests().get(request_id)


def latest_request_id() -> str | None:
    data = _load_requests()
    if not data:
        return None
    return max(data.items(), key=lambda kv: kv[1].get("created_at") or "")[0]
