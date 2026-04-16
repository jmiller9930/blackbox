"""
Successful intake candidates for Kitchen registry (DV-ARCH-KITCHEN-CANDIDATE-REGISTRY-061).

Only submissions with pass=true, candidate_policy_id, and persisted canonical spec are listed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from renaissance_v4.execution_targets import LABELS, normalize_execution_target
from renaissance_v4.policy_intake.storage import intake_root, read_json


def list_intake_candidates(repo: Path, *, execution_target: str | None = None) -> list[dict[str, Any]]:
    """
    Return newest-first rows for successful intake only. Optional ``execution_target`` filters
    (``jupiter`` | ``blackbox``); omit to return all targets.
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
    for d in sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
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

        et = str(rep.get("execution_target") or "jupiter").strip().lower()
        if et not in ("jupiter", "blackbox"):
            et = "jupiter"
        if et_filter is not None and et != et_filter:
            continue

        s1 = rep.get("stages", {}).get("stage_1_intake") if isinstance(rep.get("stages"), dict) else {}
        created = ""
        if isinstance(s1, dict):
            created = str(s1.get("timestamp_utc") or "")

        rows.append(
            {
                "submission_id": str(rep.get("submission_id") or d.name),
                "candidate_policy_id": str(cid),
                "original_filename": str(rep.get("original_filename") or "—"),
                "execution_target": et,
                "execution_target_label": LABELS.get(et, et),
                "created_utc": created,
                "intake_status": "pass",
                "baseline_compare_status": "—",
                "evaluation_summary": "—",
            }
        )

    return rows
