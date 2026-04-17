"""
DV-071 — BlackBox kitchen policy control plane (parity with Jupiter artifact model).

Runtime state remains file-backed under ``renaissance_v4/state/`` so the same API process can
serve GET/POST without a separate daemon.

**Allowed deployment ids** come only from ``kitchen_policy_deployment_manifest_v1.json``
(``execution_target``: ``blackbox``) — not from ``kitchen_policy_registry_v1.json`` slot lists.
POST validates the deployment id against that manifest; submission id and content hash are taken
from the manifest entry (optional body fields must match when provided).

Engine identity is reported separately from policy deployment id (``engine_display_id`` /
``engine_online``), aligned with Jupiter observability.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.policy_intake.kitchen_policy_manifest import (
    deployment_ids_for_target,
    find_manifest_entry,
)
from renaissance_v4.policy_intake.kitchen_policy_manifest import (
    _normalize_hex_sha256 as _norm_sha256,
)

STATE_FILENAME = "blackbox_kitchen_runtime_policy_v1.json"
STATE_SCHEMA = "blackbox_kitchen_runtime_policy_v1"


def blackbox_runtime_state_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / STATE_FILENAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def engine_display_id() -> str:
    return (os.environ.get("BLACKBOX_ENGINE_DISPLAY_ID") or "BBT_v1").strip() or "BBT_v1"


def engine_slice_enabled() -> bool:
    return not str(os.environ.get("BLACKBOX_ENGINE_SLICE", "1") or "").strip().lower() in (
        "0",
        "false",
        "no",
    )


def read_runtime_state(repo: Path) -> dict[str, Any]:
    p = blackbox_runtime_state_path(repo)
    if not p.is_file():
        return {
            "schema": STATE_SCHEMA,
            "active_policy": "",
            "submission_id": "",
            "content_sha256": "",
            "updated_at_utc": "",
        }
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("schema") == STATE_SCHEMA:
            raw.setdefault("submission_id", "")
            raw.setdefault("content_sha256", "")
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "schema": STATE_SCHEMA,
        "active_policy": "",
        "submission_id": "",
        "content_sha256": "",
        "updated_at_utc": "",
    }


def write_runtime_state(
    repo: Path,
    active_policy: str,
    *,
    submission_id: str = "",
    content_sha256: str = "",
) -> dict[str, Any]:
    p = blackbox_runtime_state_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": STATE_SCHEMA,
        "active_policy": str(active_policy).strip(),
        "submission_id": str(submission_id or "").strip(),
        "content_sha256": str(content_sha256 or "").strip(),
        "updated_at_utc": _utc_now(),
    }
    p.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


def get_policy_observability_payload(repo: Path) -> dict[str, Any]:
    """Shape aligned with Jupiter GET /api/v1/jupiter/policy (manifest-bound)."""
    repo = repo.resolve()
    allowed = deployment_ids_for_target(repo, "blackbox")
    st = read_runtime_state(repo)
    active = str(st.get("active_policy") or "").strip()
    sub = str(st.get("submission_id") or "").strip()
    ch = str(st.get("content_sha256") or "").strip()
    if active and (not sub or not ch):
        e = find_manifest_entry(repo, "blackbox", active)
        if isinstance(e, dict):
            sub = sub or str(e.get("submission_id") or "").strip()
            eh = _norm_sha256(str(e.get("content_sha256") or ""))
            if eh and not ch:
                ch = eh
    bound = bool(sub and ch)
    return {
        "contract": "blackbox_policy_observability_v1",
        "active_policy": active,
        "allowed_policies": allowed,
        "source": "blackbox_kitchen_runtime_file",
        "submission_id": sub if sub else None,
        "content_sha256": ch if ch else None,
        "artifact_binding": "manifest_v1" if bound else "legacy_unbound",
        "engine_display_id": engine_display_id(),
        "engine_online": engine_slice_enabled(),
        "api": {
            "sole_write": "POST /api/v1/blackbox/active-policy",
            "body": {
                "policy": "deployed_runtime_policy_id from kitchen_policy_deployment_manifest_v1 (blackbox)",
                "submission_id": "optional; must match manifest if sent",
                "content_sha256": "optional; must match manifest if sent",
            },
        },
    }


def set_active_policy(
    repo: Path,
    policy_id: str,
    *,
    submission_id: str = "",
    content_sha256: str = "",
) -> tuple[bool, str | None]:
    pid = str(policy_id or "").strip()
    if not pid:
        return False, "missing_policy"
    entry = find_manifest_entry(repo, "blackbox", pid)
    if not isinstance(entry, dict):
        return False, "deployment_not_in_manifest"
    sid_m = str(entry.get("submission_id") or "").strip()
    h_m = _norm_sha256(str(entry.get("content_sha256") or ""))
    if not sid_m or not h_m:
        return False, "manifest_binding_incomplete"
    sub_in = str(submission_id or "").strip()
    csha_in = str(content_sha256 or "").strip()
    if sub_in and sub_in != sid_m:
        return False, "submission_id_manifest_mismatch"
    if csha_in and _norm_sha256(csha_in) != h_m:
        return False, "content_sha256_manifest_mismatch"
    write_runtime_state(repo, pid, submission_id=sid_m, content_sha256=h_m)
    return True, None
