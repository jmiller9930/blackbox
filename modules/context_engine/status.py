"""Bounded status model for GET /api/v1/context-engine/status."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.context_engine.paths import ContextPathError, resolve_context_root
from modules.context_engine.store import append_event, read_heartbeat, read_recent_events

STALE_AFTER_SEC = float(os.environ.get("BLACKBOX_CONTEXT_ENGINE_STALE_SEC", "120"))


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


def record_api_probe(repo_root: Path | None = None) -> None:
    """Runtime producer: record a real engine event (used by status endpoint)."""
    if os.environ.get("BLACKBOX_CONTEXT_ENGINE_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return
    root = resolve_context_root(repo_root)
    throttle = float(os.environ.get("BLACKBOX_CONTEXT_ENGINE_PROBE_MIN_SEC", "45"))
    hb = read_heartbeat(root)
    if hb and throttle > 0:
        dt = _parse_iso(str(hb.get("last_heartbeat_at") or ""))
        if dt is not None:
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            if age < throttle:
                return
    append_event(
        root,
        "runtime_api_probe",
        {"source": "api_server", "reason": "context_engine_status_tick"},
        repo_root=repo_root,
    )


def build_context_engine_status(repo_root: Path | None = None) -> dict[str, Any]:
    """
    status: healthy | degraded | error | unknown
    Fail-closed: unknown/error when store unavailable or policy rejects.
    """
    if os.environ.get("BLACKBOX_CONTEXT_ENGINE_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return {
            "status": "unknown",
            "reason_code": "CTX-ENGINE-DISABLED",
            "last_heartbeat_at": None,
            "freshness_seconds": None,
            "last_event_kind": None,
            "record_count_hint": None,
            "storage_path": None,
        }

    try:
        root = resolve_context_root(repo_root)
        root.mkdir(parents=True, exist_ok=True)
    except (OSError, ContextPathError) as e:
        return {
            "status": "error",
            "reason_code": "CTX-ROOT-UNAVAILABLE",
            "last_heartbeat_at": None,
            "freshness_seconds": None,
            "last_event_kind": None,
            "record_count_hint": None,
            "storage_path": None,
            "detail": str(e),
        }

    storage_path = str(root)
    hb = read_heartbeat(root)
    _, corruption = read_recent_events(root, limit=3)

    if corruption:
        return {
            "status": "error",
            "reason_code": "CTX-STORE-CORRUPT",
            "last_heartbeat_at": (hb or {}).get("last_heartbeat_at"),
            "freshness_seconds": None,
            "last_event_kind": (hb or {}).get("last_event_kind"),
            "record_count_hint": (hb or {}).get("last_seq"),
            "storage_path": storage_path,
        }

    last_ts = (hb or {}).get("last_heartbeat_at") if isinstance(hb, dict) else None
    dt = _parse_iso(str(last_ts) if last_ts else None)
    now = datetime.now(timezone.utc)
    freshness = None if dt is None else max(0.0, (now - dt).total_seconds())

    if hb is None:
        return {
            "status": "unknown",
            "reason_code": "CTX-NO-HEARTBEAT",
            "last_heartbeat_at": None,
            "freshness_seconds": None,
            "last_event_kind": None,
            "record_count_hint": None,
            "storage_path": storage_path,
        }

    if freshness is not None and freshness > STALE_AFTER_SEC:
        return {
            "status": "degraded",
            "reason_code": "CTX-HEARTBEAT-STALE",
            "last_heartbeat_at": last_ts,
            "freshness_seconds": freshness,
            "last_event_kind": hb.get("last_event_kind"),
            "record_count_hint": hb.get("last_seq"),
            "storage_path": storage_path,
        }

    return {
        "status": "healthy",
        "reason_code": "CTX-ENGINE-OK",
        "last_heartbeat_at": last_ts,
        "freshness_seconds": freshness,
        "last_event_kind": hb.get("last_event_kind"),
        "record_count_hint": hb.get("last_seq"),
        "storage_path": storage_path,
    }
