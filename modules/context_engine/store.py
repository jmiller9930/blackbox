"""Append-only JSONL store with lock-safe writes and bounded tail reads."""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from modules.context_engine.paths import ContextPathError, resolve_context_root, safe_relative_file, validate_path_under_root

EVENTS_NAME = "events.jsonl"
META_NAME = "heartbeat.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_dir(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    validate_path_under_root(root, root)


def _lock_dir(root: Path) -> Path:
    _ensure_dir(root)
    lock = root / ".context_engine.lock"
    return lock


def _with_file_lock(lock_path: Path, fn: Callable[[], Any]) -> Any:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class AppendResult:
    seq: int
    written_path: str


def _read_seq_from_heartbeat(meta: Path) -> int:
    if not meta.exists():
        return 0
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return int(data.get("last_seq") or 0)
    except (json.JSONDecodeError, TypeError, ValueError, OSError):
        return 0


def append_event(
    root: Path | None,
    kind: str,
    payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> AppendResult:
    """
    Append one JSON object per line (no whole-file rewrite).
    Sequence comes from heartbeat.json (single source of truth).
    """
    r = root or resolve_context_root(repo_root)
    _ensure_dir(r)
    events = safe_relative_file(r, EVENTS_NAME)
    meta = safe_relative_file(r, META_NAME)
    lock = _lock_dir(r)

    def _do() -> AppendResult:
        seq = _read_seq_from_heartbeat(meta) + 1
        record = {
            "seq": seq,
            "kind": kind,
            "emitted_at_utc": _iso_now(),
            "payload": dict(payload),
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        with open(events, "a", encoding="utf-8") as out:
            out.write(line)
            out.flush()
            os.fsync(out.fileno())
        hb = {
            "last_seq": seq,
            "last_event_kind": kind,
            "last_heartbeat_at": record["emitted_at_utc"],
            "events_path": str(events),
        }
        tmp = meta.with_suffix(".tmp")
        tmp.write_text(json.dumps(hb, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, meta)
        return AppendResult(seq=seq, written_path=str(events))

    return _with_file_lock(lock, _do)


def read_recent_events(root: Path, limit: int = 50) -> tuple[list[dict[str, Any]], str | None]:
    """
    Read last N JSONL records. Small files: full read. Large files: tail window only.
    """
    r = root.resolve()
    events = safe_relative_file(r, EVENTS_NAME)
    if not events.exists():
        return [], None
    corruption: str | None = None
    try:
        file_size = events.stat().st_size
    except OSError:
        return [], "events_stat_failed"
    if file_size == 0:
        return [], None
    max_full = 2 * 1024 * 1024
    if file_size <= max_full:
        try:
            lines = events.read_text(encoding="utf-8").splitlines()
        except OSError:
            return [], "events_read_failed"
        out: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                corruption = "jsonl_parse_error_in_tail"
        return out, corruption

    # Large file: bounded tail read (~256kb) then parse last lines
    tail_bytes = min(262144, file_size)
    with open(events, "rb") as f:
        f.seek(file_size - tail_bytes)
        chunk = f.read()
    lines = chunk.split(b"\n")
    out2: list[dict[str, Any]] = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            out2.append(json.loads(raw.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            corruption = "jsonl_parse_error_in_tail"
            break
    return out2[-limit:], corruption


def read_heartbeat(root: Path) -> dict[str, Any] | None:
    r = root.resolve()
    try:
        meta = safe_relative_file(r, META_NAME)
    except ContextPathError:
        return None
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
