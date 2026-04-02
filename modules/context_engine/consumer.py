"""Fail-closed context bundle consumption for training/runtime (registry + policy)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_BUNDLE_AGE_SEC = float(os.environ.get("BLACKBOX_CONTEXT_BUNDLE_MAX_AGE_SEC", str(7 * 24 * 3600)))


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_registry(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("registry root must be object")
    return raw


def validate_bundle_for_agent(
    bundle: dict[str, Any],
    *,
    agent_id: str,
    registry: dict[str, Any],
) -> tuple[bool, str]:
    """Return (ok, reason). Fail closed on policy mismatch or stale bundle."""
    agents = registry.get("agents")
    if not isinstance(agents, dict):
        return False, "registry_agents_missing"
    prof_block = agents.get(agent_id)
    if not isinstance(prof_block, dict):
        return False, "agent_not_in_registry"
    cp = prof_block.get("contextProfile")
    if not isinstance(cp, dict):
        return False, "context_profile_missing"
    allowed = cp.get("allowedContextClasses")
    if not isinstance(allowed, list):
        return False, "allowedContextClasses_missing"

    if str(bundle.get("kind") or "") != "context_bundle_v1":
        return False, "bundle_kind_mismatch"
    state = str(bundle.get("validation_state") or "")
    if state != "approved":
        return False, f"validation_state_not_approved:{state}"
    rclass = str(bundle.get("record_class") or "")
    if not rclass or rclass not in allowed:
        return False, f"record_class_not_allowed:{rclass}"

    issued = _parse_iso(str(bundle.get("issued_at_utc") or ""))
    if issued is None:
        return False, "issued_at_missing_or_invalid"
    age = (datetime.now(timezone.utc) - issued).total_seconds()
    if age > MAX_BUNDLE_AGE_SEC:
        return False, "bundle_stale"

    return True, ""


def load_bundle_dict(*, bundle_json: str | None, bundle_path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if bundle_path is not None:
        p = bundle_path.expanduser().resolve()
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            return None, f"bundle_read_error:{e}"
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None, "bundle_json_invalid"
        return (data if isinstance(data, dict) else None), None
    if bundle_json:
        try:
            data = json.loads(bundle_json)
        except json.JSONDecodeError:
            return None, "bundle_json_invalid"
        return (data if isinstance(data, dict) else None), None
    return None, None
