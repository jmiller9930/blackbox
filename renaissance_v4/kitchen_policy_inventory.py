"""
Kitchen policy inventory — single operator-facing aggregate (DV-ARCH-KITCHEN-INVENTORY).

First paint and refresh must use the same logical source: ``build_kitchen_policy_inventory_payload``
returns registry slice, intake candidates, deployment manifest entries, and runtime read payload
in one response so the dashboard does not merge divergent HTTP calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from renaissance_v4.execution_targets import LABELS, normalize_execution_target
from renaissance_v4.kitchen_policy_registry import load_registry
from renaissance_v4.kitchen_runtime_assignment import build_kitchen_runtime_read_payload
from renaissance_v4.policy_intake.candidates_registry import list_intake_candidates
from renaissance_v4.policy_intake.kitchen_policy_manifest import load_manifest


def _allowlist_for_target(repo: Path, et: str) -> list[str]:
    reg = load_registry(repo)
    rp = reg.get("runtime_policies") or {}
    if not isinstance(rp, dict):
        return []
    lst = rp.get(et)
    if not isinstance(lst, list):
        return []
    out: list[str] = []
    for x in lst:
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
    return out


def _manifest_entries_for_target(repo: Path, et: str) -> list[dict[str, Any]]:
    m = load_manifest(repo)
    etn = str(et).strip().lower()
    out: list[dict[str, Any]] = []
    for e in m.get("entries") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("execution_target") or "").strip().lower() != etn:
            continue
        out.append(dict(e))
    return out


def _legacy_registry_only_ids(allowlist: list[str], manifest_entries: list[dict[str, Any]]) -> list[str]:
    """Registry ids with no deployment manifest entry (built-in / pre-manifest runtime slots)."""
    bound: set[str] = set()
    for e in manifest_entries:
        pid = str(e.get("deployed_runtime_policy_id") or "").strip()
        if pid:
            bound.add(pid)
    legacy = [pid for pid in allowlist if pid not in bound]
    return legacy


def build_kitchen_policy_inventory_payload(
    repo: Path,
    *,
    execution_target: str | None,
    include_archived: bool = False,
    collapse_duplicate_policy_ids: bool = True,
    http_jupiter_base: str | None = None,
    http_jupiter_token: str | None = None,
    http_blackbox_base: str | None = None,
    http_blackbox_token: str | None = None,
) -> dict[str, Any]:
    """
    Aggregate Kitchen policy inventory for one execution target.

    ``kitchen_runtime`` matches GET ``/api/v1/renaissance/kitchen-runtime-assignment`` for the target
    (same ``build_kitchen_runtime_read_payload``).
    """
    repo = repo.resolve()
    et = normalize_execution_target(execution_target)
    allowlist = _allowlist_for_target(repo, et)
    manifest_entries = _manifest_entries_for_target(repo, et)
    legacy_only = _legacy_registry_only_ids(allowlist, manifest_entries)

    candidates = list_intake_candidates(
        repo,
        execution_target=et,
        include_archived=include_archived,
        collapse_duplicate_policy_ids=collapse_duplicate_policy_ids,
    )

    kitchen_runtime = build_kitchen_runtime_read_payload(
        repo,
        et,
        http_jupiter_base=http_jupiter_base,
        http_jupiter_token=http_jupiter_token,
        http_blackbox_base=http_blackbox_base,
        http_blackbox_token=http_blackbox_token,
    )

    assignable_submission_ids = [
        str(c.get("submission_id") or "").strip()
        for c in candidates
        if c.get("artifact_assignable") is True and str(c.get("submission_id") or "").strip()
    ]

    return {
        "schema": "kitchen_policy_inventory_v1",
        "execution_target": et,
        "execution_target_label": LABELS.get(et, et),
        "inventory_model": {
            "description": (
                "Four layers: registry_allowlist (engine may load), intake_candidates (upload history), "
                "manifest_entries (submission→deployed id binding), kitchen_runtime (active + drift)."
            ),
            "single_source_endpoint": True,
        },
        "registry_allowlist": {
            "schema": "kitchen_policy_registry_v1_slice",
            "execution_target": et,
            "runtime_policy_ids": allowlist,
        },
        "legacy_registry_only": {
            "schema": "kitchen_policy_inventory_legacy_v1",
            "runtime_policy_ids": legacy_only,
            "note": (
                "In shared registry allowlist but no deployment manifest entry for this target — "
                "typically built-in or pre-manifest runtime policies; not Kitchen-upload artifacts."
            ),
        },
        "manifest_entries": manifest_entries,
        "candidates": candidates,
        "intake_query": {
            "include_archived": include_archived,
            "collapse_duplicates": collapse_duplicate_policy_ids,
        },
        "assignable_submission_ids": assignable_submission_ids,
        "kitchen_runtime": kitchen_runtime,
    }
