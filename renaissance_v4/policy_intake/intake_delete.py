"""Permanent delete of a policy intake submission (filesystem + manifest + registry scrub)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from renaissance_v4.kitchen_policy_registry import remove_runtime_policy_from_allowlist
from renaissance_v4.kitchen_runtime_assignment import (
    get_assignment,
    query_blackbox_runtime_truth,
    query_jupiter_runtime_truth,
    query_runtime_truth,
)
from renaissance_v4.policy_intake.kitchen_policy_manifest import (
    artifact_identity_for_submission,
    remove_manifest_entries_for_submission,
)
from renaissance_v4.policy_intake.storage import submission_dir


def _blocked_by_runtime(repo: Path, submission_id: str) -> tuple[bool, str]:
    sid = str(submission_id or "").strip()
    rt_j = query_jupiter_runtime_truth(repo)
    if rt_j.get("ok"):
        raw = rt_j.get("raw") or {}
        if str(raw.get("submission_id") or "").strip() == sid:
            return True, "jupiter_runtime_reports_this_submission"
        live_j = str(raw.get("active_policy") or "").strip()
        if live_j:
            ident = artifact_identity_for_submission(repo, "jupiter", sid)
            if ident and str(ident.get("deployed_runtime_policy_id") or "").strip() == live_j:
                return True, "jupiter_active_policy_matches_this_submission"

    rt_b = query_blackbox_runtime_truth(repo)
    if rt_b.get("ok"):
        raw_b = rt_b.get("raw") or {}
        if str(raw_b.get("submission_id") or "").strip() == sid:
            return True, "blackbox_runtime_reports_this_submission"
        live_b = str(raw_b.get("active_policy") or "").strip()
        if live_b:
            ident_b = artifact_identity_for_submission(repo, "blackbox", sid)
            if ident_b and str(ident_b.get("deployed_runtime_policy_id") or "").strip() == live_b:
                return True, "blackbox_active_policy_matches_this_submission"

    return False, ""


def delete_intake_submission_forever(repo: Path, submission_id: str) -> dict[str, Any]:
    """
    Remove submission directory and scrub manifest/registry hooks.

    Blocks when Jupiter or BlackBox runtime GET ties an active deployment to this submission.
    """
    repo = repo.resolve()
    sid = str(submission_id or "").strip()
    base = submission_dir(repo, sid)
    if not base.is_dir():
        return {"ok": False, "error": "unknown_submission", "submission_id": sid}

    for et in ("jupiter", "blackbox"):
        row = get_assignment(repo, et)
        if not isinstance(row, dict):
            continue
        if str(row.get("submission_id") or "").strip() != sid:
            continue
        if str(row.get("active_runtime_policy_id") or "").strip():
            rt = query_runtime_truth(repo, et)
            if not rt.get("ok"):
                return {
                    "ok": False,
                    "error": "kitchen_assignment_uncertain_clear_first",
                    "detail": "Kitchen has an assignment for this submission; runtime could not be verified.",
                    "execution_target": et,
                    "submission_id": sid,
                }
            live = str((rt.get("raw") or {}).get("active_policy") or "").strip()
            if live:
                return {
                    "ok": False,
                    "error": "runtime_active_clear_first",
                    "detail": "Kitchen/runtime still reference an active policy for this submission.",
                    "execution_target": et,
                    "submission_id": sid,
                }

    blocked, why = _blocked_by_runtime(repo, sid)
    if blocked:
        return {
            "ok": False,
            "error": "runtime_active_clear_first",
            "detail": why,
            "submission_id": sid,
        }

    scrub: list[tuple[str, str]] = []
    for et in ("jupiter", "blackbox"):
        ident = artifact_identity_for_submission(repo, et, sid)
        if ident:
            pid = str(ident.get("deployed_runtime_policy_id") or "").strip()
            if pid:
                scrub.append((et, pid))

    remove_manifest_entries_for_submission(repo, sid)
    for et, pid in scrub:
        remove_runtime_policy_from_allowlist(repo, et, pid)

    shutil.rmtree(base)
    return {"ok": True, "submission_id": sid, "scrubbed_registry_ids": [{"execution_target": a, "id": b} for a, b in scrub]}
