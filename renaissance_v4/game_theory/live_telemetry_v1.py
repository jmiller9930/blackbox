"""
Live run telemetry v1 — worker processes write JSON snapshots; the Flask UI polls and aggregates.

Uses atomic replace writes under ``PATTERN_GAME_TELEMETRY_DIR`` (default: system temp
``pattern_game_telemetry/``). One file per scenario: ``{job_id}__{scenario_slug}.json``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


SCHEMA = "pattern_game_live_telemetry_v1"


def default_telemetry_dir() -> Path:
    root = os.environ.get("PATTERN_GAME_TELEMETRY_DIR", "").strip()
    if root:
        return Path(root).expanduser().resolve()
    return Path(tempfile.gettempdir()) / "pattern_game_telemetry"


def scenario_slug(scenario_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "_", scenario_id.strip() or "unknown")[:80]
    return s or "unknown"


def telemetry_file_path(job_id: str, scenario_id: str, *, base: Path | None = None) -> Path:
    d = base or default_telemetry_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{job_id}__{scenario_slug(scenario_id)}.json"


def write_telemetry_snapshot(path: Path, payload: dict[str, Any]) -> None:
    """Atomic JSON write (best-effort)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def build_live_telemetry_callback(meta: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    """
    Throttled writer (~1s or every 500 decision windows): merges ``meta`` (job, scenario,
    recipe, framework, window, phase) with per-tick snapshot keys from replay.
    """
    path = Path(str(meta["file_path"]))
    last_mono = [0.0]
    last_pw = [-1]

    def cb(snap: dict[str, Any]) -> None:
        now = time.monotonic()
        pw = int(snap.get("decision_windows_processed") or 0)
        if now - last_mono[0] < 1.0 and pw % 500 != 0 and pw == last_pw[0]:
            return
        last_mono[0] = now
        last_pw[0] = pw
        full: dict[str, Any] = {
            "schema": SCHEMA,
            "updated_at_unix": time.time(),
            **meta,
            **snap,
        }
        try:
            write_telemetry_snapshot(path, full)
        except OSError:
            pass

    return cb


def read_job_telemetry_v1(job_id: str, *, base: Path | None = None) -> dict[str, Any]:
    """Return all telemetry files for ``job_id`` (one per scenario worker)."""
    d = base or default_telemetry_dir()
    if not d.is_dir():
        return {"schema": SCHEMA, "job_id": job_id, "scenarios": [], "read_at_unix": time.time()}
    prefix = f"{job_id}__"
    rows: list[dict[str, Any]] = []
    for p in sorted(d.iterdir()):
        if not p.is_file() or not p.name.startswith(prefix) or not p.suffix == ".json":
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                rows.append(raw)
        except (json.JSONDecodeError, OSError):
            continue
    rows.sort(key=lambda r: float(r.get("updated_at_unix") or 0.0), reverse=True)
    return {
        "schema": SCHEMA,
        "job_id": job_id,
        "read_at_unix": time.time(),
        "scenarios": rows,
    }


def clear_job_telemetry_files(job_id: str, *, base: Path | None = None) -> int:
    """Remove telemetry JSON for a job (best-effort). Returns files removed."""
    d = base or default_telemetry_dir()
    if not d.is_dir():
        return 0
    prefix = f"{job_id}__"
    n = 0
    for p in list(d.iterdir()):
        if p.is_file() and p.name.startswith(prefix) and p.suffix == ".json":
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n


__all__ = [
    "SCHEMA",
    "build_live_telemetry_callback",
    "clear_job_telemetry_files",
    "default_telemetry_dir",
    "read_job_telemetry_v1",
    "telemetry_file_path",
    "write_telemetry_snapshot",
]
