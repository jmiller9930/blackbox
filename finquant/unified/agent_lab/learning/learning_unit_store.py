"""
FinQuant — Learning Unit Store

Durable, append-only event log + rebuilt-on-demand materialized state.

Why this exists:
  Prior failure mode was `ENGAGEMENT_WITHOUT_STORE_WRITES` —
  decisions and retrieval fired but learning_rows_appended = 0.
  This store fixes that by:
    1. Every change is appended to a write-ahead event log (events.jsonl).
    2. After append: explicit flush + fsync.
    3. After write: read-back verification of the last line.
    4. Materialized state (units.json) is rebuilt by event replay,
       so we never lose units to a corrupted snapshot.
    5. Failures raise — silent dropouts are not allowed.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Iterable

from .learning_unit import (
    SCHEMA_LEARNING_UNIT,
    new_learning_unit,
    record_observation,
    summarize_unit,
    update_status,
    utc_now_iso,
)

EVENTS_FILE = "events.jsonl"
UNITS_FILE = "units.json"
WRITE_RECEIPT_FILE = "last_write_receipt.json"


class StoreWriteError(RuntimeError):
    """Raised when a store write cannot be reliably persisted."""


class LearningUnitStore:
    """
    Append-only learning store.

    Path layout:
      <base_dir>/events.jsonl
      <base_dir>/units.json
      <base_dir>/last_write_receipt.json
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._events_path = self._base / EVENTS_FILE
        self._units_path = self._base / UNITS_FILE
        self._receipt_path = self._base / WRITE_RECEIPT_FILE
        self._lock = threading.Lock()
        # Always rebuild from events for safety
        self._units: dict[str, dict[str, Any]] = self._replay_events()
        self._materialize()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert_unit(
        self,
        *,
        pattern_id: str,
        signature_components: dict[str, Any],
        human_label: str,
        proposed_action: str,
        hypothesis: str,
        expected_outcome: str,
        invalidation_condition: str,
        scope_notes: str = "",
    ) -> dict[str, Any]:
        """Create the unit if it doesn't exist; return current unit."""
        with self._lock:
            existing = self._units.get(pattern_id)
            if existing:
                return dict(existing)
            unit = new_learning_unit(
                pattern_id=pattern_id,
                signature_components=signature_components,
                human_label=human_label,
                proposed_action=proposed_action,
                hypothesis=hypothesis,
                expected_outcome=expected_outcome,
                invalidation_condition=invalidation_condition,
                scope_notes=scope_notes,
            )
            self._append_event({
                "event_type_v1": "create_unit",
                "pattern_id_v1": pattern_id,
                "unit_v1": unit,
                "at_v1": utc_now_iso(),
            })
            self._units[pattern_id] = unit
            self._materialize()
            return dict(unit)

    def record_outcome(
        self,
        *,
        pattern_id: str,
        verdict: str,
        evidence_record_id: str,
        note: str = "",
    ) -> dict[str, Any]:
        """Apply observation. Raises KeyError if the unit doesn't exist."""
        with self._lock:
            if pattern_id not in self._units:
                raise KeyError(f"learning unit not found: {pattern_id}")
            unit = self._units[pattern_id]
            record_observation(
                unit,
                verdict=verdict,
                evidence_record_id=evidence_record_id,
                note=note,
            )
            self._append_event({
                "event_type_v1": "observation",
                "pattern_id_v1": pattern_id,
                "verdict_v1": verdict,
                "evidence_record_id_v1": evidence_record_id,
                "note_v1": note,
                "at_v1": utc_now_iso(),
            })
            self._materialize()
            return dict(unit)

    def transition_status(
        self,
        *,
        pattern_id: str,
        new_status: str,
        reason: str,
    ) -> dict[str, Any]:
        with self._lock:
            if pattern_id not in self._units:
                raise KeyError(f"learning unit not found: {pattern_id}")
            unit = self._units[pattern_id]
            update_status(unit, new_status=new_status, reason=reason)
            self._append_event({
                "event_type_v1": "status_change",
                "pattern_id_v1": pattern_id,
                "to_v1": new_status,
                "reason_v1": reason,
                "at_v1": utc_now_iso(),
            })
            self._materialize()
            return dict(unit)

    def get_unit(self, pattern_id: str) -> dict[str, Any] | None:
        u = self._units.get(pattern_id)
        return dict(u) if u else None

    def all_units(self) -> list[dict[str, Any]]:
        return [dict(u) for u in self._units.values()]

    def units_by_status(self, statuses: Iterable[str]) -> list[dict[str, Any]]:
        wanted = set(statuses)
        return [dict(u) for u in self._units.values() if u.get("status_v1") in wanted]

    def units_by_pattern(self, pattern_id: str) -> list[dict[str, Any]]:
        u = self._units.get(pattern_id)
        return [dict(u)] if u else []

    def summary_stats(self) -> dict[str, Any]:
        total = len(self._units)
        by_status: dict[str, int] = {}
        for u in self._units.values():
            s = str(u.get("status_v1", "unknown"))
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total_units_v1": total,
            "by_status_v1": by_status,
            "events_path_v1": str(self._events_path),
            "units_path_v1": str(self._units_path),
        }

    def get_paths(self) -> dict[str, str]:
        return {
            "events_path": str(self._events_path),
            "units_path": str(self._units_path),
            "receipt_path": str(self._receipt_path),
        }

    # ------------------------------------------------------------------
    # Reliability internals — explicit flush, fsync, read-back verify
    # ------------------------------------------------------------------

    def _append_event(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, separators=(",", ":")) + "\n"

        # Append + flush + fsync
        with open(self._events_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        # Read-back verify last line matches what we wrote
        with open(self._events_path, "rb") as f:
            try:
                f.seek(-len(line.encode("utf-8")), os.SEEK_END)
                last = f.read().decode("utf-8")
            except OSError:
                # File smaller than expected — total read
                f.seek(0)
                content = f.read().decode("utf-8")
                last = content.splitlines(keepends=True)[-1] if content else ""

        if last != line:
            raise StoreWriteError(
                f"Read-back verification failed. expected={line!r} got={last!r}"
            )

        # Write a receipt so callers can prove the append succeeded
        receipt = {
            "last_event_v1": event.get("event_type_v1"),
            "pattern_id_v1": event.get("pattern_id_v1"),
            "at_v1": event.get("at_v1"),
            "events_path_v1": str(self._events_path),
            "byte_size_v1": self._events_path.stat().st_size,
        }
        self._atomic_write_json(self._receipt_path, receipt)

    def _atomic_write_json(self, path: Path, obj: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _materialize(self) -> None:
        """Rewrite the materialized snapshot atomically from current state."""
        snapshot = {
            "schema": "finquant_learning_unit_snapshot_v1",
            "generated_at_v1": utc_now_iso(),
            "unit_count_v1": len(self._units),
            "units_v1": list(self._units.values()),
        }
        self._atomic_write_json(self._units_path, snapshot)

    def _replay_events(self) -> dict[str, dict[str, Any]]:
        """Rebuild materialized state by replaying the events log."""
        units: dict[str, dict[str, Any]] = {}
        if not self._events_path.exists():
            return units

        with open(self._events_path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                etype = event.get("event_type_v1")
                pid = event.get("pattern_id_v1")
                if not pid:
                    continue
                if etype == "create_unit":
                    if pid not in units:
                        units[pid] = dict(event["unit_v1"])
                elif etype == "observation" and pid in units:
                    record_observation(
                        units[pid],
                        verdict=event.get("verdict_v1", "inconclusive"),
                        evidence_record_id=event.get("evidence_record_id_v1", ""),
                        note=event.get("note_v1", ""),
                    )
                elif etype == "status_change" and pid in units:
                    update_status(
                        units[pid],
                        new_status=event.get("to_v1", "candidate"),
                        reason=event.get("reason_v1", "replay"),
                    )
        return units
