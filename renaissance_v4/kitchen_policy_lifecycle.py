"""
DV-069 — Single shared policy lifecycle store (Kitchen ↔ runtime reconciliation).

Registry (``kitchen_policy_registry_v1.json``) lists allowed runtime policy ids.
This module holds per-(submission, execution_target) lifecycle state only.

Frozen lifecycle states (do not rename without migration):
  submitted, failed, candidate, runtime_eligible, assignment_requested,
  assigned_runtime_confirmed, runtime_diverged, external_override, retired
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.execution_targets import normalize_execution_target
from renaissance_v4.kitchen_policy_registry import load_registry, mechanical_slot
from renaissance_v4.kitchen_runtime_assignment import MECHANICAL_CANDIDATE_POLICY_ID

STORE_SCHEMA = "kitchen_policy_lifecycle_v1"
STORE_FILENAME = "kitchen_policy_lifecycle_v1.json"

# Frozen enum — DV-069
STATE_SUBMITTED = "submitted"
STATE_FAILED = "failed"
STATE_CANDIDATE = "candidate"
STATE_RUNTIME_ELIGIBLE = "runtime_eligible"
STATE_ASSIGNMENT_REQUESTED = "assignment_requested"
STATE_ASSIGNED_RUNTIME_CONFIRMED = "assigned_runtime_confirmed"
STATE_RUNTIME_DIVERGED = "runtime_diverged"
STATE_EXTERNAL_OVERRIDE = "external_override"
STATE_RETIRED = "retired"

FROZEN_LIFECYCLE_STATES: tuple[str, ...] = (
    STATE_SUBMITTED,
    STATE_FAILED,
    STATE_CANDIDATE,
    STATE_RUNTIME_ELIGIBLE,
    STATE_ASSIGNMENT_REQUESTED,
    STATE_ASSIGNED_RUNTIME_CONFIRMED,
    STATE_RUNTIME_DIVERGED,
    STATE_EXTERNAL_OVERRIDE,
    STATE_RETIRED,
)


def lifecycle_store_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / STORE_FILENAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store() -> dict[str, Any]:
    return {"schema": STORE_SCHEMA, "entries": {}}


def load_lifecycle_store(repo: Path) -> dict[str, Any]:
    p = lifecycle_store_path(repo)
    if not p.is_file():
        return _empty_store()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("schema") == STORE_SCHEMA:
            raw.setdefault("entries", {})
            if not isinstance(raw["entries"], dict):
                raw["entries"] = {}
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return _empty_store()


def save_lifecycle_store(repo: Path, store: dict[str, Any]) -> None:
    p = lifecycle_store_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")


def lifecycle_key(submission_id: str, execution_target: str) -> str:
    return f"{str(submission_id).strip()}:{normalize_execution_target(execution_target)}"


def get_entry(repo: Path, submission_id: str, execution_target: str) -> dict[str, Any] | None:
    st = load_lifecycle_store(repo)
    row = st.get("entries", {}).get(lifecycle_key(submission_id, execution_target))
    return row if isinstance(row, dict) else None


def _put_entry(repo: Path, entry: dict[str, Any]) -> None:
    st = load_lifecycle_store(repo)
    sid = str(entry.get("submission_id") or "").strip()
    et = normalize_execution_target(str(entry.get("execution_target") or "jupiter"))
    key = lifecycle_key(sid, et)
    entry["submission_id"] = sid
    entry["execution_target"] = et
    entry["updated_at_utc"] = _utc_now()
    st.setdefault("entries", {})[key] = entry
    save_lifecycle_store(repo, st)


def _mechanical_runtime_eligible(repo: Path, candidate_policy_id: str, execution_target: str) -> bool:
    if str(candidate_policy_id).strip() != MECHANICAL_CANDIDATE_POLICY_ID:
        return False
    et = normalize_execution_target(execution_target)
    row = mechanical_slot(repo, et)
    if not row:
        return False
    try:
        reg = load_registry(repo)
        rid = str(row.get("active_runtime_policy_id") or row.get("approved_runtime_slot_id") or "")
        allowed = reg.get("runtime_policies") or {}
        lst = allowed.get(et) if isinstance(allowed, dict) else None
        if not isinstance(lst, list) or rid not in [str(x) for x in lst]:
            return False
    except (OSError, ValueError, FileNotFoundError):
        return False
    return True


def apply_intake_report_to_lifecycle(repo: Path, report: dict[str, Any]) -> None:
    """Call after intake report is written. Maps intake outcome → lifecycle row."""
    repo = repo.resolve()
    if not isinstance(report, dict):
        return
    sid = str(report.get("submission_id") or "").strip()
    if not sid:
        return
    et = normalize_execution_target(str(report.get("execution_target") or "jupiter"))
    cid = str(report.get("candidate_policy_id") or "").strip()

    if report.get("pass") is True and cid:
        state = STATE_RUNTIME_ELIGIBLE if _mechanical_runtime_eligible(repo, cid, et) else STATE_CANDIDATE
        _put_entry(
            repo,
            {
                "submission_id": sid,
                "execution_target": et,
                "candidate_policy_id": cid,
                "state": state,
                "runtime_eligible": state == STATE_RUNTIME_ELIGIBLE,
                "runtime_confirmed_policy_id": None,
                "assignment_intent_runtime_policy_id": None,
                "detail": "intake_pass",
            },
        )
        return

    _put_entry(
        repo,
        {
            "submission_id": sid,
            "execution_target": et,
            "candidate_policy_id": cid or None,
            "state": STATE_FAILED,
            "runtime_eligible": False,
            "runtime_confirmed_policy_id": None,
            "assignment_intent_runtime_policy_id": None,
            "detail": "intake_failed",
        },
    )


def set_retired(repo: Path, submission_id: str, execution_target: str, *, retired: bool) -> None:
    """Archive/restore from candidate list — retired vs candidate/runtime_eligible."""
    repo = repo.resolve()
    et = normalize_execution_target(execution_target)
    ent = get_entry(repo, submission_id, et)
    if not ent:
        return
    if retired:
        ent["state"] = STATE_RETIRED
        ent["detail"] = "archived_by_operator"
    else:
        cid = str(ent.get("candidate_policy_id") or "")
        ent["state"] = STATE_RUNTIME_ELIGIBLE if _mechanical_runtime_eligible(repo, cid, et) else STATE_CANDIDATE
        ent["detail"] = "restored_by_operator"
    _put_entry(repo, ent)


def mark_assignment_requested(
    repo: Path,
    submission_id: str,
    execution_target: str,
    *,
    intent_runtime_policy_id: str,
) -> None:
    ent = get_entry(repo, submission_id, execution_target) or {
        "submission_id": submission_id,
        "execution_target": normalize_execution_target(execution_target),
        "candidate_policy_id": "",
        "state": STATE_CANDIDATE,
        "runtime_eligible": False,
    }
    ent["state"] = STATE_ASSIGNMENT_REQUESTED
    ent["assignment_intent_runtime_policy_id"] = str(intent_runtime_policy_id).strip()
    ent["detail"] = "assignment_post_pending"
    _put_entry(repo, ent)


def mark_assigned_runtime_confirmed(
    repo: Path,
    submission_id: str,
    execution_target: str,
    *,
    runtime_policy_id: str,
    candidate_policy_id: str,
) -> None:
    _put_entry(
        repo,
        {
            "submission_id": submission_id,
            "execution_target": normalize_execution_target(execution_target),
            "candidate_policy_id": str(candidate_policy_id),
            "state": STATE_ASSIGNED_RUNTIME_CONFIRMED,
            "runtime_eligible": True,
            "runtime_confirmed_policy_id": str(runtime_policy_id).strip(),
            "assignment_intent_runtime_policy_id": str(runtime_policy_id).strip(),
            "detail": "runtime_read_back_match",
        },
    )


def mark_assignment_failed(repo: Path, submission_id: str, execution_target: str, *, detail: str) -> None:
    ent = get_entry(repo, submission_id, execution_target)
    if not ent:
        return
    ent["state"] = STATE_RUNTIME_DIVERGED
    ent["detail"] = detail[:2000]
    _put_entry(repo, ent)


def reconcile_with_drift(
    repo: Path,
    execution_target: str,
    kitchen_row: dict[str, Any] | None,
    drift: dict[str, Any],
    runtime_payload: dict[str, Any],
) -> None:
    """
    Update lifecycle for the submission referenced by kitchen_row using drift (read-back).
    """
    if not kitchen_row or not isinstance(drift, dict):
        return
    sid = str(kitchen_row.get("submission_id") or "").strip()
    if not sid:
        return
    et = normalize_execution_target(execution_target)
    ent = get_entry(repo, sid, et)
    prev = str((ent or {}).get("state") or "")
    dstate = str(drift.get("state") or "")
    r_active = ""
    if isinstance(runtime_payload, dict) and runtime_payload.get("ok"):
        r_active = str(runtime_payload.get("active_policy") or "").strip()

    if dstate == "match":
        mark_assigned_runtime_confirmed(
            repo,
            sid,
            et,
            runtime_policy_id=r_active,
            candidate_policy_id=str(kitchen_row.get("candidate_policy_id") or ""),
        )
        return

    if dstate == "runtime_diverged":
        new_state = STATE_EXTERNAL_OVERRIDE if prev == STATE_ASSIGNED_RUNTIME_CONFIRMED else STATE_RUNTIME_DIVERGED
        row = {
            "submission_id": sid,
            "execution_target": et,
            "candidate_policy_id": str(kitchen_row.get("candidate_policy_id") or ""),
            "state": new_state,
            "runtime_eligible": _mechanical_runtime_eligible(
                repo, str(kitchen_row.get("candidate_policy_id") or ""), et
            ),
            "runtime_confirmed_policy_id": r_active or None,
            "assignment_intent_runtime_policy_id": str(kitchen_row.get("active_runtime_policy_id") or ""),
            "detail": drift.get("detail") or ("external_override" if new_state == STATE_EXTERNAL_OVERRIDE else "runtime_diverged"),
        }
        _put_entry(repo, row)
        return

    if dstate in ("runtime_unreachable", "unknown_runtime_policy"):
        row = ent or {
            "submission_id": sid,
            "execution_target": et,
            "candidate_policy_id": str(kitchen_row.get("candidate_policy_id") or ""),
            "state": STATE_RUNTIME_DIVERGED,
            "runtime_eligible": False,
        }
        row["state"] = STATE_RUNTIME_DIVERGED
        row["runtime_confirmed_policy_id"] = r_active or None
        row["detail"] = str(drift.get("detail") or dstate)[:2000]
        _put_entry(repo, row)


def attach_lifecycle_to_candidate_rows(repo: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """API helper: add ``lifecycle`` object to each candidate row."""
    repo = repo.resolve()
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            out.append(r)
            continue
        sid = str(r.get("submission_id") or "")
        et = normalize_execution_target(str(r.get("execution_target") or "jupiter"))
        ent = get_entry(repo, sid, et)
        rr = dict(r)
        rr["lifecycle"] = ent or {
            "submission_id": sid,
            "execution_target": et,
            "state": STATE_CANDIDATE,
            "runtime_eligible": False,
            "detail": "no_lifecycle_row_yet",
        }
        out.append(rr)
    return out


def lifecycle_summary_for_target(repo: Path, execution_target: str) -> dict[str, Any]:
    """Optional compact map for GET kitchen-runtime-assignment."""
    et = normalize_execution_target(execution_target)
    st = load_lifecycle_store(repo)
    out: dict[str, Any] = {}
    for _k, row in (st.get("entries") or {}).items():
        if not isinstance(row, dict):
            continue
        if str(row.get("execution_target") or "").lower() != et:
            continue
        sid = str(row.get("submission_id") or "")
        if sid:
            out[sid] = {k: v for k, v in row.items() if k != "submission_id"}
    return {"schema": "kitchen_policy_lifecycle_summary_v1", "by_submission_id": out}
