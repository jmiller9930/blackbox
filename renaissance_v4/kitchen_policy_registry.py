"""
DV-074 — Single Kitchen policy registry (shared source of truth for approved runtime policy IDs).

Kitchen, Jupiter operator UI, and BlackBox adapters must only assign policies listed here.

DV-077 — The mechanical slot policy ID must also appear in the live Jupiter runtime
`allowed_policies` (GET /api/v1/jupiter/policy); assignment fails with a clear error if the
registry and runtime sets diverge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REGISTRY_FILENAME = "kitchen_policy_registry_v1.json"


def registry_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "config" / REGISTRY_FILENAME


def load_registry(repo: Path) -> dict[str, Any]:
    """Load registry JSON from repo; raises if missing or invalid."""
    p = registry_path(repo)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != "kitchen_policy_registry_v1":
        raise ValueError("invalid_kitchen_policy_registry")
    return raw


def runtime_policy_approved(repo: Path, execution_target: str, runtime_policy_id: str) -> bool:
    reg = load_registry(repo)
    et = str(execution_target).strip().lower()
    rid = str(runtime_policy_id).strip()
    allowed = reg.get("runtime_policies") or {}
    lst = allowed.get(et) if isinstance(allowed, dict) else None
    if not isinstance(lst, list):
        return False
    return rid in [str(x) for x in lst]


def ensure_runtime_policy_allowlisted(
    repo: Path, execution_target: str, runtime_policy_id: str
) -> tuple[bool, str]:
    """
    Append ``runtime_policy_id`` to ``runtime_policies.<execution_target>`` if missing (sorted list).
    Returns (True, "appended"|"already_present") or (False, error_code).
    """
    et = str(execution_target).strip().lower()
    rid = str(runtime_policy_id).strip()
    if et not in ("jupiter", "blackbox") or not rid:
        return False, "invalid_args"
    try:
        reg = load_registry(repo)
    except (FileNotFoundError, ValueError, OSError):
        return False, "registry_unreadable"
    allowed = reg.get("runtime_policies")
    if not isinstance(allowed, dict):
        return False, "invalid_runtime_policies"
    lst = allowed.get(et)
    if not isinstance(lst, list):
        return False, "invalid_target_list"
    normalized = [str(x).strip() for x in lst if str(x).strip()]
    if rid in normalized:
        return True, "already_present"
    normalized.append(rid)
    normalized.sort()
    allowed[et] = normalized
    reg["runtime_policies"] = allowed
    p = registry_path(repo)
    p.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
    return True, "appended"


def mechanical_slot(repo: Path, execution_target: str) -> dict[str, str] | None:
    reg = load_registry(repo)
    ms = reg.get("mechanical_slot") or {}
    if not isinstance(ms, dict):
        return None
    row = ms.get(str(execution_target).strip().lower())
    return row if isinstance(row, dict) else None


def approved_mechanical_by_target(repo: Path) -> dict[str, dict[str, str]]:
    """Shape compatible with legacy APPROVED_MECHANICAL_BY_TARGET."""
    reg = load_registry(repo)
    out: dict[str, dict[str, str]] = {}
    ms = reg.get("mechanical_slot") or {}
    if not isinstance(ms, dict):
        return out
    for et, row in ms.items():
        if isinstance(row, dict) and "approved_runtime_slot_id" in row:
            out[str(et)] = {
                "approved_runtime_slot_id": str(row["approved_runtime_slot_id"]),
                "active_runtime_policy_id": str(row.get("active_runtime_policy_id") or row["approved_runtime_slot_id"]),
                "runtime_adapter": str(row.get("runtime_adapter") or ""),
            }
    return out


def infer_runtime_policy_id_for_candidate(repo: Path, execution_target: str, candidate_policy_id: str) -> str | None:
    """
    DV-077 — Map a Kitchen candidate_policy_id to the runtime policy id that row represents on Jupiter/BlackBox.

    Used for UI green indicator: ``runtime.active_policy == row.runtime_policy_id``. Returns None if unknown.
    """
    try:
        et = str(execution_target).strip().lower()
        if et not in ("jupiter", "blackbox"):
            return None
        cid = str(candidate_policy_id).strip()
        if not cid:
            return None
        ms = mechanical_slot(repo, et)
        if ms and str(ms.get("candidate_policy_id") or "") == cid:
            rid = str(ms.get("active_runtime_policy_id") or ms.get("approved_runtime_slot_id") or "").strip()
            return rid or None
        reg = load_registry(repo)
        allowed_obj = reg.get("runtime_policies") or {}
        if not isinstance(allowed_obj, dict):
            return None
        lst = allowed_obj.get(et)
        if not isinstance(lst, list):
            return None
        allowed_set = {str(x).strip() for x in lst}
        if cid in allowed_set:
            return cid
        for suf in ("_v1", "_v2", "_v3"):
            if cid.endswith(suf):
                base = cid[: -len(suf)]
                if base in allowed_set:
                    return base
        # Intake-only ids (fixtures, aliases) → deployable runtime id listed in runtime_policies.
        imap_root = reg.get("intake_candidate_runtime_map") or {}
        if isinstance(imap_root, dict):
            et_map = imap_root.get(et)
            if isinstance(et_map, dict):
                mapped = str(et_map.get(cid) or "").strip()
                if mapped and runtime_policy_approved(repo, et, mapped):
                    return mapped
        return None
    except (FileNotFoundError, ValueError, OSError):
        return None
