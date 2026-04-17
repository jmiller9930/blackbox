"""
Successful intake candidates for Kitchen registry (DV-ARCH-KITCHEN-CANDIDATE-REGISTRY-061).

Only submissions with pass=true, candidate_policy_id, and persisted canonical spec are listed.

DV-066: ``is_active`` on ``intake_report.json`` (default true for legacy rows); archive sets false.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from renaissance_v4.execution_targets import LABELS, normalize_execution_target
from renaissance_v4.kitchen_policy_registry import infer_runtime_policy_id_for_candidate
from renaissance_v4.kitchen_policy_lifecycle import attach_lifecycle_to_candidate_rows, set_retired
from renaissance_v4.policy_intake.kitchen_policy_manifest import artifact_identity_for_submission
from renaissance_v4.policy_intake.storage import intake_root, read_json, submission_dir, write_json


def _enrich_artifact_identity(repo: Path, rows: list[dict[str, Any]]) -> None:
    """
    Artifact-bound assignment (Path A): ``runtime_policy_id`` is the manifest
    ``deployed_runtime_policy_id`` for this submission. No registry-slot inference for
    assignability — legacy ``infer_runtime_policy_id_for_candidate`` is only exposed as
    ``legacy_runtime_policy_id`` for diagnostics.
    """
    for r in rows:
        et = str(r.get("execution_target") or "jupiter").strip().lower()
        cid = str(r.get("candidate_policy_id") or "").strip()
        sid = str(r.get("submission_id") or "").strip()
        ident = artifact_identity_for_submission(repo, et, sid) if sid else None
        if ident:
            r["runtime_policy_id"] = ident["deployed_runtime_policy_id"]
            r["artifact_assignable"] = True
            r["artifact_binding"] = "manifest_v1"
        else:
            r["runtime_policy_id"] = ""
            r["artifact_assignable"] = False
            r["artifact_binding"] = "none"
        legacy = infer_runtime_policy_id_for_candidate(repo, et, cid)
        r["legacy_runtime_policy_id"] = legacy if legacy else ""


def _parse_created_sort_key(created_utc: str) -> float:
    s = (created_utc or "").strip()
    if not s:
        return 0.0
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError, OSError):
        return 0.0


def set_intake_candidate_active(repo: Path, submission_id: str, *, is_active: bool) -> dict[str, Any]:
    """
    Soft-archive or restore a passing candidate (mutates ``report/intake_report.json`` only).
    """
    repo = repo.resolve()
    rep_path = submission_dir(repo, submission_id) / "report" / "intake_report.json"
    rep = read_json(rep_path)
    if not isinstance(rep, dict) or not rep.get("pass"):
        return {"ok": False, "error": "not_a_passing_candidate", "submission_id": submission_id}
    if not rep.get("candidate_policy_id"):
        return {"ok": False, "error": "missing_candidate_policy_id", "submission_id": submission_id}
    rep["is_active"] = bool(is_active)
    write_json(rep_path, rep)
    et = normalize_execution_target(str(rep.get("execution_target") or "jupiter"))
    set_retired(repo, submission_id, et, retired=(rep["is_active"] is False))
    return {"ok": True, "submission_id": submission_id, "is_active": rep["is_active"]}


def list_intake_candidates(
    repo: Path,
    *,
    execution_target: str | None = None,
    include_archived: bool = False,
    collapse_duplicate_policy_ids: bool = True,
) -> list[dict[str, Any]]:
    """
    Return rows for successful intake only. Optional ``execution_target`` filters
    (``jupiter`` | ``blackbox``); omit to return all targets.

    Sorted **newest first** by ``stage_1_intake.timestamp_utc``.

    * ``include_archived``: when False (default), rows with ``is_active is False`` are omitted.
    * ``collapse_duplicate_policy_ids``: when True (default), only the **newest** submission per
      ``candidate_policy_id`` is returned (reduces repeated fixture uploads); see
      ``same_policy_submission_count`` on each row.
    """
    repo = repo.resolve()
    root = intake_root(repo)
    if not root.is_dir():
        return []

    et_filter: str | None = None
    if execution_target is not None and str(execution_target).strip():
        et_filter = normalize_execution_target(execution_target)

    rows: list[dict[str, Any]] = []
    dirs = [p for p in root.iterdir() if p.is_dir()]
    for d in dirs:
        rep_path = d / "report" / "intake_report.json"
        canon_path = d / "canonical" / "policy_spec_v1.json"
        rep = read_json(rep_path)
        if not isinstance(rep, dict) or not rep.get("pass"):
            continue
        cid = rep.get("candidate_policy_id")
        if not cid:
            continue
        if not canon_path.is_file():
            continue

        active = rep.get("is_active")
        if active is False and not include_archived:
            continue

        et = str(rep.get("execution_target") or "jupiter").strip().lower()
        if et not in ("jupiter", "blackbox"):
            et = "jupiter"
        if et_filter is not None and et != et_filter:
            continue

        s1 = rep.get("stages", {}).get("stage_1_intake") if isinstance(rep.get("stages"), dict) else {}
        created = ""
        content_sha256 = ""
        if isinstance(s1, dict):
            created = str(s1.get("timestamp_utc") or "")
            content_sha256 = str(s1.get("content_sha256") or "").strip()

        rows.append(
            {
                "submission_id": str(rep.get("submission_id") or d.name),
                "candidate_policy_id": str(cid),
                "original_filename": str(rep.get("original_filename") or "—"),
                "execution_target": et,
                "execution_target_label": LABELS.get(et, et),
                "created_utc": created,
                "content_sha256": content_sha256,
                "intake_status": "pass",
                "is_active": False if active is False else True,
                "baseline_compare_status": "—",
                "evaluation_summary": "—",
            }
        )

    rows.sort(key=lambda r: _parse_created_sort_key(str(r.get("created_utc") or "")), reverse=True)

    pid_counts = Counter(str(r["candidate_policy_id"]) for r in rows)
    for r in rows:
        r["same_policy_submission_count"] = pid_counts[str(r["candidate_policy_id"])]

    _enrich_artifact_identity(repo, rows)

    if collapse_duplicate_policy_ids and rows:
        seen: set[str] = set()
        collapsed: list[dict[str, Any]] = []
        for r in rows:
            pid = str(r["candidate_policy_id"])
            if pid in seen:
                continue
            seen.add(pid)
            collapsed.append(r)
        return attach_lifecycle_to_candidate_rows(repo, collapsed)

    return attach_lifecycle_to_candidate_rows(repo, rows)


def find_best_submission_for_runtime_policy(
    repo: Path,
    execution_target: str,
    runtime_policy_id: str,
) -> dict[str, str] | None:
    """
    Reverse lookup (DV-070B): prefer deployment manifest (submission tied to
    ``deployed_runtime_policy_id``), else legacy inference from registry maps.
    """
    from renaissance_v4.policy_intake.kitchen_policy_manifest import load_manifest

    repo = repo.resolve()
    et = normalize_execution_target(execution_target)
    rpid = str(runtime_policy_id).strip()
    if not rpid or et not in ("jupiter", "blackbox"):
        return None
    root = intake_root(repo)
    if not root.is_dir():
        return None
    m = load_manifest(repo)
    manifest_sids: list[str] = []
    for e in m.get("entries") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("execution_target") or "").strip().lower() != et:
            continue
        if str(e.get("deployed_runtime_policy_id") or "").strip() != rpid:
            continue
        sid = str(e.get("submission_id") or "").strip()
        if sid:
            manifest_sids.append(sid)
    matches: list[tuple[float, str, str]] = []
    for sid in manifest_sids:
        d = root / sid
        if not d.is_dir():
            continue
        rep_path = d / "report" / "intake_report.json"
        canon_path = d / "canonical" / "policy_spec_v1.json"
        rep = read_json(rep_path)
        if not isinstance(rep, dict) or not rep.get("pass"):
            continue
        if not canon_path.is_file():
            continue
        if rep.get("is_active") is False:
            continue
        rep_et = normalize_execution_target(str(rep.get("execution_target") or "jupiter"))
        if rep_et != et:
            continue
        cid = str(rep.get("candidate_policy_id") or "").strip()
        if not cid:
            continue
        s1 = rep.get("stages", {}).get("stage_1_intake") if isinstance(rep.get("stages"), dict) else {}
        created = str(s1.get("timestamp_utc") or "") if isinstance(s1, dict) else ""
        ts = _parse_created_sort_key(created)
        matches.append((ts, sid, cid))
    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        best = matches[0]
        return {"submission_id": best[1], "candidate_policy_id": best[2]}
    matches = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        rep_path = d / "report" / "intake_report.json"
        canon_path = d / "canonical" / "policy_spec_v1.json"
        rep = read_json(rep_path)
        if not isinstance(rep, dict) or not rep.get("pass"):
            continue
        cid_raw = rep.get("candidate_policy_id")
        if not cid_raw:
            continue
        if not canon_path.is_file():
            continue
        if rep.get("is_active") is False:
            continue
        rep_et = normalize_execution_target(str(rep.get("execution_target") or "jupiter"))
        if rep_et != et:
            continue
        cid = str(cid_raw).strip()
        inferred = infer_runtime_policy_id_for_candidate(repo, et, cid)
        if inferred != rpid:
            continue
        sid = str(rep.get("submission_id") or d.name).strip()
        if not sid:
            continue
        s1 = rep.get("stages", {}).get("stage_1_intake") if isinstance(rep.get("stages"), dict) else {}
        created = str(s1.get("timestamp_utc") or "") if isinstance(s1, dict) else ""
        ts = _parse_created_sort_key(created)
        matches.append((ts, sid, cid))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0], reverse=True)
    best = matches[0]
    return {"submission_id": best[1], "candidate_policy_id": best[2]}
