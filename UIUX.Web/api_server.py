#!/usr/bin/env python3
"""Minimal BLACK BOX UI truth API for /api/v1/*."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

HOST = "0.0.0.0"
PORT = 8080
ROOT = Path("/repo")
ARTIFACTS = ROOT / "docs" / "working" / "artifacts"
STATE_FILE = ARTIFACTS / "ui_runtime_state.json"
PYTH_STREAM_FILE = ARTIFACTS / "pyth_stream_status.json"
PYTH_RECENT_FILE = ARTIFACTS / "pyth_stream_recent.json"
PYTH_SAFETY_FILE = ARTIFACTS / "pyth_storage_safety.json"

ALLOWED_AGENTS = {"anna", "billy", "mia", "chris", "data"}
ALLOWED_ACTIONS = {"start", "pause", "stop", "restart", "reset", "check-in"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def ensure_state() -> dict[str, Any]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    state = load_json(STATE_FILE)
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
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def save_state(state: dict[str, Any]) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def latest_drift_doctor_report() -> tuple[dict[str, Any] | None, Path | None]:
    if not ARTIFACTS.exists():
        return None, None
    candidates = sorted(
        [p for p in ARTIFACTS.iterdir() if p.is_file() and "drift_doctor" in p.name.lower()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        parsed = load_json(path)
        if isinstance(parsed, dict):
            return parsed, path
    return None, candidates[0] if candidates else None


def ledger_health(state: dict[str, Any]) -> dict[str, Any]:
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


def build_status() -> tuple[dict[str, Any], dict[str, Any]]:
    state = ensure_state()
    drift, drift_path = latest_drift_doctor_report()
    billy_conn = "connected" if isinstance(drift, dict) and drift.get("overall_ready") is True else "unknown"
    billy_reason = (
        str(drift.get("drift", {}).get("user_account_state"))
        if isinstance(drift, dict)
        else "no_drift_doctor_artifact"
    )
    runtime_state = "connected" if billy_conn == "connected" else "not_connected"
    state["runtime_state"] = runtime_state
    save_state(state)

    runtime = {
        "runtime_state": runtime_state,
        "last_transition_at": state.get("last_transition_at"),
        "controls_enabled": billy_conn == "connected",
        "paper_enabled": bool(state.get("paper_enabled", False)),
        "live_enabled": bool(state.get("live_enabled", False)),
        "reason_code": "runtime_connected_via_billy" if billy_conn == "connected" else "runtime_not_connected",
        "trace_id": str(uuid.uuid4()),
        "probe_artifact": str(drift_path.relative_to(ROOT)) if drift_path else None,
        "ledger": ledger_health(state),
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


def build_pyth_status() -> dict[str, Any]:
    stream = load_json(PYTH_STREAM_FILE)
    if not isinstance(stream, dict):
        stream = {}
    recent = load_json(PYTH_RECENT_FILE)
    if not isinstance(recent, dict):
        recent = {}
    safety = load_json(PYTH_SAFETY_FILE)
    if not isinstance(safety, dict):
        safety = {}

    status = str(stream.get("status") or stream.get("stream_state") or "unknown")
    reason = str(stream.get("reason_code") or "stream_status_unavailable")
    updated_at = stream.get("last_event_at") or stream.get("updated_at")
    stale_after = int(stream.get("stale_after_seconds") or 120)
    age_seconds = None
    dt = parse_iso(str(updated_at) if updated_at else None)
    if dt is not None:
        age_seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))

    sqlite_path = ROOT / "data" / "sqlite" / "market_data.db"
    resolved_path = sqlite_path.resolve() if sqlite_path.exists() else sqlite_path
    db_bytes = resolved_path.stat().st_size if resolved_path.exists() else 0
    fs = os.statvfs(str(resolved_path.parent if resolved_path.exists() else sqlite_path.parent))
    fs_total = fs.f_blocks * fs.f_frsize
    fs_avail = fs.f_bavail * fs.f_frsize
    fs_used = fs_total - (fs.f_bfree * fs.f_frsize)
    avail_ratio = (fs_avail / fs_total) if fs_total else 0.0
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
        "probe_artifact": str(PYTH_STREAM_FILE.relative_to(ROOT)),
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
        "training_source": {
            "path": str(sqlite_path),
            "resolved_path": str(resolved_path),
            "table": "market_ticks",
            "symbol_filter": "SOL-PERP",
            "source_filter": "pyth_hermes_sse",
        },
        "recent_count": len((recent.get("items") or [])) if isinstance(recent, dict) else 0,
    }


def build_anna_summary() -> dict[str, Any]:
    runtime, agents = build_status()
    pyth = build_pyth_status()
    anna = None
    for item in agents.get("items", []):
        if str(item.get("agent_id")).lower() == "anna":
            anna = item
            break
    pyth_status = str(pyth.get("status") or "unknown")
    training_state = "ready" if pyth_status in {"healthy", "connected"} else "degraded"
    src = pyth.get("training_source") if isinstance(pyth.get("training_source"), dict) else {}
    return {
        "agent_id": "anna",
        "connectivity_state": str((anna or {}).get("connectivity_state") or "unknown"),
        "runtime_state": str((anna or {}).get("lifecycle_state") or "unknown"),
        "reason_code": str((anna or {}).get("reason_code") or "anna_summary_unavailable"),
        "training": {
            "state": training_state,
            "reason_code": "pyth_feed_backing_training",
            "source_path": str(src.get("resolved_path") or src.get("path") or "--"),
            "table": str(src.get("table") or "--"),
            "filters": {
                "symbol": str(src.get("symbol_filter") or "--"),
                "source": str(src.get("source_filter") or "--"),
            },
        },
        "participation": {"state": "not_wired", "reason_code": "training_participation_control_not_wired"},
        "strategy": {"state": "not_wired", "reason_code": "strategy_inventory_not_wired"},
        "trace_id": str(uuid.uuid4()),
        "runtime_trace_id": runtime.get("trace_id"),
    }


def normalize_status(raw: Any) -> str:
    v = str(raw or "unknown").strip().lower()
    if v in {"healthy", "degraded", "error", "unknown"}:
        return v
    if v in {"connected", "up", "on", "ready", "ok"}:
        return "healthy"
    if v in {"warning", "watch", "not_connected", "partial", "stale"}:
        return "degraded"
    if v in {"disconnected", "down", "off", "capacity_risk", "failed", "failure"}:
        return "error"
    return "unknown"


def _fix(headline: str, steps: list[str], commands: list[str] | None = None, docs: list[str] | None = None) -> dict[str, Any]:
    return {
        "headline": headline,
        "steps": steps,
        "commands": commands or [],
        "docs": docs or [],
    }


def build_system_status() -> dict[str, Any]:
    runtime, agents = build_status()
    pyth = build_pyth_status()

    runtime_raw = runtime.get("runtime_state")
    control_status = normalize_status(runtime_raw)
    control_reason = str(runtime.get("reason_code") or "CONTROL_PLANE_STATUS_UNAVAILABLE")

    pyth_raw = pyth.get("status")
    data_status = normalize_status(pyth_raw)
    data_reason = str(pyth.get("reason_code") or "DATA_PLANE_STATUS_UNAVAILABLE")

    ui_api_status = "healthy"
    ui_api_reason = "STATUS_ENDPOINT_RESPONDING"

    agent_items = (agents.get("items") if isinstance(agents, dict) else None) or []
    agent_statuses: list[str] = []
    agents_node: dict[str, Any] = {}

    for item in agent_items:
        agent_id = str(item.get("agent_id") or "").lower()
        if agent_id not in ALLOWED_AGENTS:
            continue
        conn = item.get("connectivity_state") or item.get("lifecycle_state") or item.get("status")
        st = normalize_status(conn)
        reason = str(item.get("reason_code") or "AGENT_STATUS_UNAVAILABLE")
        summary = str(conn or "unknown")
        route = f"#agent-section-{agent_id}"
        label = f"{agent_id.capitalize()} workspace"
        agent_statuses.append(st)
        agents_node[agent_id] = {
            "status": st,
            "reason_code": reason,
            "summary": summary,
            "last_heartbeat_at": item.get("last_check_in_at"),
            "workspace_route": route,
            "workspace_label": label,
        }

    for required_id in sorted(ALLOWED_AGENTS):
        if required_id not in agents_node:
            agents_node[required_id] = {
                "status": "unknown",
                "reason_code": "AGENT_NODE_MISSING",
                "summary": "agent node missing from source",
                "last_heartbeat_at": None,
                "workspace_route": "",
                "workspace_label": f"{required_id.capitalize()} workspace",
            }
            agent_statuses.append("unknown")

    if any(st == "error" for st in agent_statuses):
        workers_status = "error"
    elif any(st == "degraded" for st in agent_statuses):
        workers_status = "degraded"
    elif all(st == "unknown" for st in agent_statuses):
        workers_status = "unknown"
    elif all(st == "healthy" for st in agent_statuses):
        workers_status = "healthy"
    else:
        workers_status = "degraded"

    plane_statuses = [control_status, data_status, ui_api_status, workers_status]
    if any(st == "error" for st in plane_statuses):
        top_status = "error"
    elif any(st == "degraded" for st in plane_statuses):
        top_status = "degraded"
    elif all(st == "unknown" for st in plane_statuses):
        top_status = "unknown"
    elif all(st == "healthy" for st in plane_statuses):
        top_status = "healthy"
    else:
        top_status = "unknown"

    now = now_iso()
    nodes = {
        "control_plane": {
            "status": control_status,
            "reason_code": control_reason,
            "summary": f"Runtime state {runtime_raw or 'unknown'}",
            "last_heartbeat_at": runtime.get("last_transition_at"),
            "fix": _fix(
                "Restore control-plane connectivity",
                ["Check runtime source artifact", "Reconcile drift/engine prerequisites", "Retry runtime probe"],
                ["python3 scripts/trading/drift_doctor.ts"],
                ["docs/working/current_directive.md"],
            ),
        },
        "data_plane": {
            "status": data_status,
            "reason_code": data_reason,
            "summary": f"Pyth status {pyth_raw or 'unknown'}",
            "last_heartbeat_at": pyth.get("last_update_at"),
            "fix": _fix(
                "Restore data-plane ingestion",
                ["Check pyth-stream container", "Verify stream status artifacts", "Confirm sqlite storage path and rails"],
                ["cd UIUX.Web && docker compose ps", "cd UIUX.Web && docker compose logs pyth-stream --tail 120"],
                ["scripts/trading/pyth_stream_probe.py"],
            ),
        },
        "ui_api": {
            "status": ui_api_status,
            "reason_code": ui_api_reason,
            "summary": "System status endpoint responding",
            "last_heartbeat_at": now,
            "fix": _fix(
                "Restore UI/API bridge",
                ["Verify nginx /api/v1 proxy", "Verify api container health", "Rebuild web stack"],
                ["cd UIUX.Web && docker compose up -d --build"],
                ["UIUX.Web/nginx/default.conf", "UIUX.Web/docker-compose.yml"],
            ),
        },
        "agent_workers": {
            "status": workers_status,
            "reason_code": "AGENT_WORKER_ROLLUP",
            "summary": "Aggregate from all required agent nodes",
            "last_heartbeat_at": now,
            "fix": _fix(
                "Bring missing or degraded agents to expected state",
                ["Open each agent workspace", "Review reason codes", "Wire missing routes/probes"],
                [],
                ["UIUX.Web/internal.html"],
            ),
        },
        "agents": agents_node,
    }

    return {
        "status": top_status,
        "reason_code": "SYSTEM_ROLLUP_FROM_PLANES",
        "last_updated_at": now,
        "nodes": nodes,
    }


def run_control(agent_id: str, action: str) -> tuple[str, str]:
    if agent_id in {"mia", "chris", "data"}:
        return "rejected", "not_wired"
    if agent_id == "anna":
        return "rejected", "anna_control_not_wired"
    if action == "check-in":
        drift, _ = latest_drift_doctor_report()
        return ("accepted", "billy_check_in_ok") if isinstance(drift, dict) and drift.get("overall_ready") else ("rejected", "billy_check_in_failed")
    return "rejected", "billy_control_not_wired"


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict[str, Any] | list[Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/v1/runtime/status":
            runtime, _ = build_status()
            self._json(200, runtime)
            return
        if path == "/api/v1/agents/status":
            _, agents = build_status()
            self._json(200, agents)
            return
        if path == "/api/v1/market/pyth/status":
            self._json(200, build_pyth_status())
            return
        if path == "/api/v1/market/pyth/recent":
            recent = load_json(PYTH_RECENT_FILE)
            data = recent if isinstance(recent, dict) else {"items": []}
            q = parse_qs(parsed.query or "")
            limit_raw = (q.get("limit") or ["40"])[0]
            try:
                limit = max(1, min(200, int(limit_raw)))
            except ValueError:
                limit = 40
            items = data.get("items") if isinstance(data.get("items"), list) else []
            self._json(200, {"items": items[-limit:], "trace_id": str(uuid.uuid4())})
            return
        if path == "/api/v1/anna/summary":
            self._json(200, build_anna_summary())
            return
        if path == "/api/v1/system/status":
            self._json(200, build_system_status())
            return
        self._json(404, {"error": "not_found", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) == 5 and parts[:2] == ["api", "v1"] and parts[2] == "agents":
            agent_id = parts[3].lower()
            action = parts[4].lower()
            if agent_id not in ALLOWED_AGENTS:
                self._json(404, {"error": "unknown_agent", "agent_id": agent_id})
                return
            if action not in ALLOWED_ACTIONS:
                self._json(400, {"error": "unsupported_action", "action": action})
                return
            result_state, reason = run_control(agent_id, action)
            self._json(
                200,
                {
                    "agent_id": agent_id,
                    "action": action,
                    "result_state": result_state,
                    "reason_code": reason,
                    "trace_id": str(uuid.uuid4()),
                    "emitted_at": now_iso(),
                },
            )
            return
        self._json(404, {"error": "not_found", "path": parsed.path})

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"UI truth API listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
