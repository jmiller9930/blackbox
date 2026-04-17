"""
DV-071 — BlackBox kitchen policy control plane (parity with Jupiter operator contract).

Runtime state is file-backed under ``renaissance_v4/state/`` so the same API process can
serve GET/POST without a separate BlackBox daemon. Allowed policy IDs always come from
``kitchen_policy_registry_v1.json`` (``runtime_policies.blackbox``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.kitchen_policy_registry import load_registry, runtime_policy_approved

STATE_FILENAME = "blackbox_kitchen_runtime_policy_v1.json"
STATE_SCHEMA = "blackbox_kitchen_runtime_policy_v1"


def blackbox_runtime_state_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / STATE_FILENAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def allowed_blackbox_policy_ids(repo: Path) -> list[str]:
    reg = load_registry(repo)
    raw = reg.get("runtime_policies") or {}
    lst = raw.get("blackbox") if isinstance(raw, dict) else None
    if not isinstance(lst, list):
        return []
    return [str(x).strip() for x in lst if str(x).strip()]


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
    """Shape aligned with Jupiter GET /api/v1/jupiter/policy (subset)."""
    repo = repo.resolve()
    allowed = allowed_blackbox_policy_ids(repo)
    st = read_runtime_state(repo)
    active = str(st.get("active_policy") or "").strip()
    sub = str(st.get("submission_id") or "").strip()
    ch = str(st.get("content_sha256") or "").strip()
    if active and (not sub or not ch):
        from renaissance_v4.policy_intake.kitchen_policy_manifest import find_manifest_entry

        e = find_manifest_entry(repo, "blackbox", active)
        if isinstance(e, dict):
            sub = sub or str(e.get("submission_id") or "").strip()
            eh = str(e.get("content_sha256") or "").strip()
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
    if not runtime_policy_approved(repo, "blackbox", pid):
        return False, "policy_not_in_registry"
    write_runtime_state(repo, pid, submission_id=submission_id, content_sha256=content_sha256)
    return True, None
