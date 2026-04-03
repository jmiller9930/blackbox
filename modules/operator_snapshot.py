"""
Repo-relative operator status snapshots for Slack/DATA hashtags.

Mirrors the JSON shape produced by `UIUX.Web/api_server.py` `build_status` / `build_pyth_status`
when artifacts live under `<repo>/docs/working/artifacts/` (same layout as docker `/repo`).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def artifacts_dir(repo_root: Path) -> Path:
    return (repo_root / "docs" / "working" / "artifacts").resolve()


def latest_drift_doctor(repo_root: Path) -> tuple[dict[str, Any] | None, Path | None]:
    root = artifacts_dir(repo_root)
    if not root.exists():
        return None, None
    candidates = sorted(
        [p for p in root.iterdir() if p.is_file() and "drift_doctor" in p.name.lower()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        parsed = _load_json(path)
        if isinstance(parsed, dict):
            return parsed, path
    return None, candidates[0] if candidates else None


def _ledger_health(state: dict[str, Any]) -> dict[str, Any]:
    lag = state.get("ledger_lag_seconds")
    rate = state.get("write_success_rate_5m")
    if rate is None or lag is None:
        health = "not_wired"
    elif rate >= 0.99 and lag <= 10:
        health = "healthy"
    elif rate >= 0.95 and lag <= 60:
        health = "degraded"
    elif lag > 60:
        health = "stalled"
    else:
        health = "error"
    return {
        "health": health,
        "last_event_at": state.get("last_event_at"),
        "write_success_rate_5m": rate,
        "ledger_lag_seconds": lag,
        "last_error_code": state.get("last_error_code"),
    }


def ensure_ui_state(repo_root: Path) -> dict[str, Any]:
    art = artifacts_dir(repo_root)
    art.mkdir(parents=True, exist_ok=True)
    p = art / "ui_runtime_state.json"
    state = _load_json(p)
    if isinstance(state, dict):
        return state
    state = {
        "paper_enabled": True,
        "live_enabled": False,
        "runtime_state": "not_connected",
        "last_transition_at": None,
        "last_event_at": None,
        "write_success_rate_5m": None,
        "ledger_lag_seconds": None,
        "last_error_code": "ledger_not_wired",
    }
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def build_runtime_and_agents(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Same structure as `UIUX.Web.api_server.build_status` but repo-rooted."""
    state = ensure_ui_state(repo_root)
    drift, drift_path = latest_drift_doctor(repo_root)
    billy_conn = "connected" if isinstance(drift, dict) and drift.get("overall_ready") is True else "unknown"
    billy_reason = (
        str(drift.get("drift", {}).get("user_account_state"))
        if isinstance(drift, dict)
        else "no_drift_doctor_artifact"
    )
    runtime_state = "connected" if billy_conn == "connected" else "not_connected"
    state["runtime_state"] = runtime_state
    p = artifacts_dir(repo_root) / "ui_runtime_state.json"
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    runtime = {
        "runtime_state": runtime_state,
        "last_transition_at": state.get("last_transition_at"),
        "controls_enabled": billy_conn == "connected",
        "paper_enabled": bool(state.get("paper_enabled", False)),
        "live_enabled": bool(state.get("live_enabled", False)),
        "reason_code": "runtime_connected_via_billy" if billy_conn == "connected" else "runtime_not_connected",
        "trace_id": str(uuid.uuid4()),
        "probe_artifact": str(drift_path.relative_to(repo_root)) if drift_path else None,
        "ledger": _ledger_health(state),
    }

    def item(agent_id: str, label: str, conn: str, reason: str, lifecycle: str) -> dict[str, Any]:
        return {
            "agent_id": agent_id,
            "agent_label": label,
            "connectivity_state": conn,
            "lifecycle_state": lifecycle,
            "reason_code": reason,
            "last_check_in_at": drift.get("timestamp_utc") if agent_id == "billy" and isinstance(drift, dict) else None,
            "control_capabilities": {
                "start": False,
                "pause": False,
                "stop": False,
                "restart": False,
                "reset": False,
                "check_in": agent_id == "billy",
            },
        }

    agents = {
        "items": [
            item("anna", "Anna", "unknown", "anna_runtime_probe_not_configured", "unknown"),
            item("billy", "Billy", billy_conn, billy_reason, "on" if billy_conn == "connected" else "unknown"),
            item("mia", "Mia", "not_wired", "mia_not_wired", "not_wired"),
            item("chris", "Chris", "not_wired", "chris_not_wired", "not_wired"),
            item("data", "Data", "not_wired", "data_not_wired", "not_wired"),
        ],
        "trace_id": str(uuid.uuid4()),
    }
    return runtime, agents


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def build_pyth_status(repo_root: Path) -> dict[str, Any]:
    art = artifacts_dir(repo_root)
    stream = _load_json(art / "pyth_stream_status.json")
    if not isinstance(stream, dict):
        stream = {}
    recent = _load_json(art / "pyth_stream_recent.json")
    if not isinstance(recent, dict):
        recent = {}
    safety = _load_json(art / "pyth_storage_safety.json")
    if not isinstance(safety, dict):
        safety = {}

    status = str(stream.get("status") or stream.get("stream_state") or "unknown")
    reason = str(stream.get("reason_code") or "stream_status_unavailable")
    updated_at = stream.get("last_event_at") or stream.get("updated_at")
    stale_after = int(stream.get("stale_after_seconds") or 120)
    age_seconds = None
    dt = _parse_iso(str(updated_at) if updated_at else None)
    if dt is not None:
        age_seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))

    sqlite_path = repo_root / "data" / "sqlite" / "market_data.db"
    resolved_path = sqlite_path.resolve() if sqlite_path.exists() else sqlite_path
    db_bytes = resolved_path.stat().st_size if resolved_path.exists() else 0
    try:
        fs = os.statvfs(str(resolved_path.parent if resolved_path.exists() else sqlite_path.parent))
        fs_total = fs.f_blocks * fs.f_frsize
        fs_avail = fs.f_bavail * fs.f_frsize
        fs_used = fs_total - (fs.f_bfree * fs.f_frsize)
        avail_ratio = (fs_avail / fs_total) if fs_total else 0.0
    except OSError:
        fs_total = fs_avail = fs_used = 0
        avail_ratio = 0.0
    max_db = int(safety.get("max_db_bytes") or (40 * 1024**3))
    target_db = int(safety.get("target_db_bytes") or int(max_db * 0.9))
    if db_bytes >= max_db or avail_ratio < 0.10:
        db_color, db_state = "red", "capacity_risk"
    elif db_bytes >= target_db or avail_ratio < 0.25:
        db_color, db_state = "yellow", "watch"
    else:
        db_color, db_state = "green", "healthy"

    return {
        "source": "pyth",
        "status": status,
        "reason_code": reason,
        "last_update_at": updated_at,
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after,
        "trace_id": str(uuid.uuid4()),
        "probe_artifact": str((art / "pyth_stream_status.json").relative_to(repo_root)) if art.exists() else None,
        "db_storage": {
            "health_color": db_color,
            "health_state": db_state,
            "sqlite_path": str(sqlite_path),
            "sqlite_resolved_path": str(resolved_path),
            "db_bytes": db_bytes,
            "fs_total_bytes": fs_total,
            "fs_used_bytes": fs_used,
            "fs_avail_bytes": fs_avail,
            "max_db_bytes": max_db,
            "target_db_bytes": target_db,
            "avail_ratio": round(avail_ratio, 4),
        },
        "recent_count": len((recent.get("items") or [])) if isinstance(recent.get("items"), list) else 0,
    }


def run_billy_checkin_probe(repo_root: Path) -> tuple[str, str]:
    """Same decision as `api_server.run_control(billy, check-in)` — read-only."""
    drift, _ = latest_drift_doctor(repo_root)
    if isinstance(drift, dict) and drift.get("overall_ready") is True:
        return "accepted", "billy_check_in_ok"
    return "rejected", "billy_check_in_failed"


def format_runtime_text(repo_root: Path) -> str:
    runtime, _ = build_runtime_and_agents(repo_root)
    lines = [
        "🧭 Runtime / control plane",
        f"runtime_state: {runtime.get('runtime_state')}",
        f"reason_code: {runtime.get('reason_code')}",
        f"controls_enabled: {runtime.get('controls_enabled')}",
        f"paper_enabled: {runtime.get('paper_enabled')}  live_enabled: {runtime.get('live_enabled')}",
        f"probe_artifact: {runtime.get('probe_artifact') or '—'}",
    ]
    led = runtime.get("ledger") or {}
    lines.append(
        f"ledger: health={led.get('health')} lag_s={led.get('ledger_lag_seconds')} rate={led.get('write_success_rate_5m')}",
    )
    return "\n".join(lines)


def format_agents_text(repo_root: Path) -> str:
    _, agents = build_runtime_and_agents(repo_root)
    lines = ["🤖 Agents"]
    for it in agents.get("items") or []:
        aid = it.get("agent_id")
        lines.append(
            f"• {aid}: {it.get('connectivity_state')} ({it.get('reason_code')}) lifecycle={it.get('lifecycle_state')}",
        )
    return "\n".join(lines)


def format_pyth_text(repo_root: Path) -> str:
    p = build_pyth_status(repo_root)
    db = p.get("db_storage") or {}
    lines = [
        "📡 Pyth / data plane",
        f"status: {p.get('status')}  reason: {p.get('reason_code')}",
        f"last_update_at: {p.get('last_update_at')}  age_seconds: {p.get('age_seconds')}",
        f"db: {db.get('health_color')} / {db.get('health_state')}  bytes={db.get('db_bytes')}",
        f"sqlite: {db.get('sqlite_resolved_path')}",
        f"recent_ticks_buffered: {p.get('recent_count')}",
    ]
    return "\n".join(lines)


def format_system_rollup_text(repo_root: Path) -> str:
    """Human text aligned with UI system status rollup (planes + agents)."""
    runtime, agents = build_runtime_and_agents(repo_root)
    pyth = build_pyth_status(repo_root)
    parts = [
        format_runtime_text(repo_root),
        "",
        format_pyth_text(repo_root),
        "",
        format_agents_text(repo_root),
        "",
        f"Artifacts: {artifacts_dir(repo_root)}",
    ]
    return "\n".join(parts)


def format_billy_checkin_text(repo_root: Path) -> str:
    verdict, code = run_billy_checkin_probe(repo_root)
    emoji = "🟢" if verdict == "accepted" else "🔴"
    return (
        f"{emoji} Billy check-in probe ({verdict})\n"
        f"reason_code: {code}\n"
        "Same gate as API control action `check-in` for Billy (drift doctor artifact + overall_ready)."
    )


def format_ops_restart_help() -> str:
    return (
        "🔧 Restart / operations (not auto-executed from Slack)\n"
        "Slack cannot safely start systemd/docker for you. Use these on the **host**:\n"
        "• Messaging (Socket Mode): `cd <repo> && python3 -m messaging_interface` (config backend=slack)\n"
        "• UI stack: `cd UIUX.Web && docker compose up -d --build`\n"
        "• Sentinel stack: `python3 sentinel.py --status` / `--restart` from repo root\n"
        "Future: gated `#op_confirm …` + allowlist may post to control API — not yet wired."
    )
