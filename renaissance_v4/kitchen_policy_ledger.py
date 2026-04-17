"""
DV-074A — Append-only policy assignment ledger (Kitchen ↔ runtime).

Every forward assign and detected external/runtime drift is recorded with source:
``kitchen`` | ``external`` | ``reconciliation`` | ``runtime_checkin`` (explicit trade-surface handshake).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

LEDGER_SCHEMA = "kitchen_policy_assignment_ledger_v1"
LEDGER_FILENAME = "kitchen_policy_assignment_ledger.json"
SYNC_STATE_SCHEMA = "kitchen_runtime_external_sync_state_v1"
SYNC_STATE_FILENAME = "kitchen_runtime_external_sync.json"


def ledger_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / LEDGER_FILENAME


def sync_state_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / SYNC_STATE_FILENAME


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def read_ledger(repo: Path) -> dict[str, Any]:
    p = ledger_path(repo)
    if not p.is_file():
        return {"schema": LEDGER_SCHEMA, "entries": []}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("schema") == LEDGER_SCHEMA:
            raw.setdefault("entries", [])
            if not isinstance(raw["entries"], list):
                raw["entries"] = []
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema": LEDGER_SCHEMA, "entries": []}


def write_ledger(repo: Path, ledger: dict[str, Any]) -> None:
    p = ledger_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def append_ledger_entry(
    repo: Path,
    *,
    execution_target: str,
    previous_policy_id: str,
    new_policy_id: str,
    source: str,
    detail: str | None = None,
) -> dict[str, Any]:
    """
    Append one ledger row. ``source``: ``kitchen`` | ``external`` | ``reconciliation`` | ``runtime_checkin``.
    """
    repo = repo.resolve()
    ledger = read_ledger(repo)
    entry: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "execution_target": str(execution_target).strip().lower(),
        "previous_policy_id": str(previous_policy_id or "").strip(),
        "new_policy_id": str(new_policy_id or "").strip(),
        "timestamp_utc": _utc_now(),
        "source": str(source).strip().lower(),
    }
    if detail:
        entry["detail"] = str(detail)[:2000]
    ledger.setdefault("entries", []).append(entry)
    write_ledger(repo, ledger)
    return entry


def read_sync_state(repo: Path) -> dict[str, Any]:
    p = sync_state_path(repo)
    if not p.is_file():
        return {"schema": SYNC_STATE_SCHEMA, "by_target": {}}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("schema") == SYNC_STATE_SCHEMA:
            raw.setdefault("by_target", {})
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema": SYNC_STATE_SCHEMA, "by_target": {}}


def write_sync_state(repo: Path, state: dict[str, Any]) -> None:
    p = sync_state_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def ledger_entries_for_target(repo: Path, execution_target: str, *, limit: int = 50) -> list[dict[str, Any]]:
    et = str(execution_target).strip().lower()
    entries = list(read_ledger(repo).get("entries") or [])
    filtered = [e for e in entries if isinstance(e, dict) and str(e.get("execution_target") or "").lower() == et]
    filtered.sort(key=lambda e: str(e.get("timestamp_utc") or ""), reverse=True)
    return filtered[:limit]


def set_external_dedupe_fingerprint(repo: Path, execution_target: str, fingerprint: str) -> None:
    st = read_sync_state(repo)
    st.setdefault("by_target", {})
    et = str(execution_target).strip().lower()
    st["by_target"][et] = {
        "last_external_ledger_fp": str(fingerprint)[:500],
        "updated_at_utc": _utc_now(),
    }
    write_sync_state(repo, st)


def get_external_dedupe_fingerprint(repo: Path, execution_target: str) -> str | None:
    st = read_sync_state(repo)
    row = (st.get("by_target") or {}).get(str(execution_target).strip().lower())
    if isinstance(row, dict):
        return str(row.get("last_external_ledger_fp") or "") or None
    return None
