"""
DV-074 — Single Kitchen policy registry (shared source of truth for approved runtime policy IDs).

Kitchen, Jupiter operator UI, and BlackBox adapters must only assign policies listed here.
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
