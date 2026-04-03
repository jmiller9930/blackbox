#!/usr/bin/env python3
"""Minimal BLACK BOX UI truth API for /api/v1/*."""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

HOST = "0.0.0.0"
PORT = 8080
ROOT = Path("/repo")
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
ARTIFACTS = ROOT / "docs" / "working" / "artifacts"

# Context engine (Pillar 1) — operational store under BLACKBOX_CONTEXT_ROOT or data/context_engine
try:
    from modules.context_engine.status import build_context_engine_status, record_api_probe
except ImportError:
    build_context_engine_status = None  # type: ignore[assignment]
    record_api_probe = None  # type: ignore[assignment]
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


def _training_engagement_payload(st: dict[str, Any], harness: dict[str, Any]) -> dict[str, Any]:
    """Human-readable training story for operators (skill practice + harness path per tick)."""
    sp = st.get("karpathy_last_skill_practice")
    sp = sp if isinstance(sp, dict) else {}
    deck = st.get("grade_12_skills_deck")
    deck = deck if isinstance(deck, dict) else {}
    focus = deck.get("current_focus_requirement") or deck.get("current_focus")

    bullets: list[str] = []
    bullets.append(
        "Each loop tick Anna refreshes Grade-12 gates and the skills deck, runs scheduled tool/skill "
        "practice, logs the learning cycle, and runs the Karpathy paper harness (analysis → execution request → Jack paper when configured)."
    )
    if sp.get("ran"):
        outcome = "passed" if sp.get("passed") else "did not pass"
        sid = sp.get("skill_id") or "skill"
        summ = (sp.get("summary") or "").strip()
        bullets.append(
            f"Last skill practice: {sid} — {outcome}"
            + (f" — {summ}" if summ else "")
            + "."
        )
    else:
        note = (sp.get("note") or "").strip()
        cf = sp.get("current_focus")
        tail = note or (f"Current deck focus: {cf!r}." if cf else "No drill this tick (often numeric cohort or deck complete).")
        bullets.append(f"Last tick — tool practice: none. {tail}")

    h_skipped = harness.get("skipped")
    h_err = harness.get("error")
    if h_skipped:
        bullets.append(f"Paper harness: stopped — {h_skipped}.")
    elif h_err:
        bullets.append(f"Paper harness: error — {h_err}.")
    elif harness.get("enabled") is False:
        bullets.append("Paper harness: off (ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK=0 or disabled).")
    elif harness.get("paper_logged") is True or (harness.get("jack_delegate") or {}).get("ok"):
        rid = harness.get("request_id") or "—"
        bullets.append(
            f"Paper harness: Anna produced a request and execution delegated (request {rid}). "
            "Check paper rows / attempts for fills."
        )
    elif harness.get("request_id"):
        bullets.append(
            f"Paper harness: Anna produced execution request {harness.get('request_id')} "
            "(analysis + handoff succeeded; see skipped/error above if Jack did not run)."
        )
    else:
        bullets.append(
            "Paper harness: no execution request this tick (observation-only or policy blocked — normal some ticks)."
        )

    plain = " ".join(bullets)
    return {
        "plain_english": plain,
        "bullets": bullets,
        "skills_deck_focus": focus,
        "skill_practice_last": sp,
    }


def build_anna_training_dashboard() -> dict[str, Any]:
    """Fixed-layout JSON for web UI: same facts as `anna status` / compact dashboard (read-only)."""
    tid = str(uuid.uuid4())
    try:
        from modules.anna_training.gates import evaluate_grade12_gates
        from modules.anna_training.paper_trades import load_paper_trades_for_gates, summarize_trades, trades_path
        from modules.anna_training.store import anna_training_dir, load_state, state_path
        from modules.anna_training.trade_attempts import (
            attempts_path,
            load_trade_attempts,
            summarize_trade_activity,
        )
        from modules.anna_training.report_card_text import learning_signal_verdict
    except ImportError as e:
        return {
            "schema": "anna_training_dashboard_v1",
            "ok": False,
            "error": "import_failed",
            "detail": str(e),
            "trace_id": tid,
        }
    try:
        st = load_state()
        g12 = evaluate_grade12_gates()
        trades = load_paper_trades_for_gates()
        s = summarize_trades(trades)
        act = summarize_trade_activity()
        recent = sorted(trades, key=lambda x: x.get("ts_utc") or "")[-20:]
        ph = st.get("karpathy_last_paper_harness")
        if isinstance(ph, dict):
            harness = ph
        else:
            harness = {}
        engagement = _training_engagement_payload(st, harness)
        snap = harness.get("analysis_snapshot")
        analysis_snapshot = snap if isinstance(snap, dict) else {}
        sp_last = st.get("karpathy_last_skill_practice")
        skill_practice_last = sp_last if isinstance(sp_last, dict) else {}
        deck = st.get("grade_12_skills_deck")
        deck = deck if isinstance(deck, dict) else {}
        ls = learning_signal_verdict(g12, st)
        att_rows = load_trade_attempts()
        recent_attempts = []
        for e in att_rows[-18:]:
            if not isinstance(e, dict):
                continue
            rid = e.get("request_id")
            recent_attempts.append(
                {
                    "ts_utc": str(e.get("ts_utc") or "")[:22],
                    "phase": e.get("phase"),
                    "status": e.get("status"),
                    "request_id": (str(rid)[:14] + "…") if rid and len(str(rid)) > 14 else rid,
                }
            )
        lp = st.get("karpathy_last_llm_preflight")
        llm_preflight = lp if isinstance(lp, dict) else {}
        dp = st.get("karpathy_last_data_preflight")
        data_preflight = dp if isinstance(dp, dict) else {}
        pol = st.get("karpathy_last_preflight_policy")
        preflight_policy = pol if isinstance(pol, dict) else {}

        semantics = {
            "loop_tick_means": (
                "Each supervisor tick: **data preflight** (Pyth stream + market_data.db; optional Solana) → "
                "**LLM probe** (GET Ollama /api/tags when ANNA_USE_LLM is on — informational in state/heartbeat) → "
                "then iteration++ → skills deck → tool drill when deck focus is a Grade-12 tool ID → paper harness "
                "(analyze_to_dict → execution request → Jack paper if BLACKBOX_JACK_EXECUTOR_CMD is set). "
                "A bad Ollama probe does not skip school; fix OLLAMA_BASE_URL / model for real LLM analysis."
            ),
            "attempt_log_vs_tick": (
                "The attempt log file counts delegate/manual events (jack_handoff, paper_manual, etc.) — "
                "not one line per tick. The harness still runs every tick; that is the repeated analysis "
                "and handoff attempt."
            ),
            "paper_ledger_vs_tick": (
                "Paper ledger rows append when a paper trade is logged to paper_trades.jsonl — not every tick."
            ),
        }
        return {
            "schema": "anna_training_dashboard_v1",
            "ok": True,
            "trace_id": tid,
            "at_utc": now_iso(),
            "semantics": semantics,
            "data_preflight": data_preflight,
            "preflight_policy": preflight_policy,
            "llm_preflight": llm_preflight,
            "training_engagement": engagement,
            "analysis_snapshot": analysis_snapshot,
            "skill_practice_last": skill_practice_last,
            "skills_deck_focus": deck.get("current_focus_requirement") or deck.get("current_focus"),
            "learning_signal": {
                "verdict": ls.get("verdict"),
                "headline": ls.get("headline"),
                "detail": (ls.get("detail") or "")[:900],
            },
            "attempt_events_recent": recent_attempts,
            "enrollment": {
                "curriculum_id": st.get("curriculum_id"),
                "training_method_id": st.get("training_method_id"),
            },
            "paths": {
                "state_json": str(state_path()),
                "paper_trades_jsonl": str(trades_path()),
                "attempts_jsonl": str(attempts_path()),
                "heartbeat_jsonl": str(anna_training_dir() / "karpathy_loop_heartbeat.jsonl"),
            },
            "loop": {
                "karpathy_loop_iteration": st.get("karpathy_loop_iteration"),
                "karpathy_loop_last_tick_utc": st.get("karpathy_loop_last_tick_utc"),
            },
            "gates": {
                "pass": bool(g12.get("pass")),
                "curriculum_tools_pass": bool(g12.get("curriculum_tools_pass")),
                "numeric_gate_pass": bool(g12.get("numeric_gate_pass")),
                "decisive_trades": g12.get("decisive_trades"),
                "min_decisive_trades": g12.get("min_decisive_trades"),
                "win_rate": g12.get("win_rate"),
                "total_pnl_usd": g12.get("total_pnl_usd"),
                "paper_goal_met": g12.get("paper_goal_met"),
                "paper_goal_rationale": g12.get("paper_goal_rationale"),
            },
            "paper_cohort": {
                "row_count": s.trade_count,
                "wins": s.wins,
                "losses": s.losses,
                "total_pnl_usd": s.total_pnl_usd,
            },
            "attempts": {
                "total_events": act.total_events,
                "jack_delegate_started": act.jack_delegate_started,
                "jack_delegate_failed": act.jack_delegate_failed,
                "jack_ok_with_paper": act.jack_delegate_ok_with_paper,
                "jack_ok_no_paper": act.jack_delegate_ok_no_paper,
                "paper_manual_recorded": act.paper_manual_recorded,
                "failed_or_blocked": act.failed_or_blocked,
            },
            "paper_harness_last": harness,
            "recent_trades": recent,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "schema": "anna_training_dashboard_v1",
            "ok": False,
            "error": "build_failed",
            "detail": str(e),
            "trace_id": tid,
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


TRAINING_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Anna training — live</title>
  <style>
    :root { --bg:#0d1117; --card:#161b22; --text:#e6edf3; --muted:#8b949e; --ok:#3fb950; --bad:#f85149; --accent:#58a6ff; }
    * { box-sizing: border-box; }
    body { font-family: ui-sans-serif, system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1rem; }
    h1 { font-size: 1.15rem; font-weight: 600; margin: 0 0 0.35rem; }
    .lead { font-size: 0.8rem; color: var(--muted); margin: 0 0 1rem; max-width: 52rem; line-height: 1.45; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; }
    .card { background: var(--card); border: 1px solid #30363d; border-radius: 8px; padding: 0.75rem 1rem; }
    .card h2 { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin: 0 0 0.5rem; }
    .val { font-size: 1.25rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .sub { font-size: 0.75rem; color: var(--muted); margin-top: 0.35rem; word-break: break-word; line-height: 1.35; }
    .ok { color: var(--ok); } .bad { color: var(--bad); }
    table.data { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    table.data th, table.data td { text-align: left; padding: 0.35rem 0.45rem; border-bottom: 1px solid #30363d; vertical-align: top; }
    table.data th { color: var(--muted); font-weight: 500; width: 38%; }
    #err { color: var(--bad); font-size: 0.85rem; margin-bottom: 1rem; display: none; }
    #meta { font-size: 0.72rem; color: var(--muted); margin-top: 1rem; }
    .ls { font-size: 0.85rem; line-height: 1.45; margin: 0 0 0.5rem; }
    .ls-detail { font-size: 0.78rem; color: var(--muted); margin: 0 0 0.75rem; }
    .chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.35rem; }
    .chip { font-size: 0.72rem; padding: 0.15rem 0.45rem; background: #21262d; border-radius: 4px; border: 1px solid #30363d; }
    details.raw { margin-top: 0.5rem; font-size: 0.75rem; color: var(--muted); }
    details.raw pre { white-space: pre-wrap; word-break: break-word; margin: 0.35rem 0 0; }
    .llm-bad { border-color: var(--bad) !important; background: #22191c; }
    .llm-warn { border-color: #9e6a03 !important; background: #1c1a12; }
    .llm-good { border-color: var(--ok) !important; background: #0d1f14; }
    #v_preflight_banner .sub { white-space: normal; word-break: break-word; }
  </style>
</head>
<body>
  <h1>Anna training — live</h1>
  <div id="v_preflight_banner" class="card llm-good" style="margin-bottom:0.75rem;display:none">
    <h2>Preflight (data + LLM — same order as the daemon)</h2>
    <p class="sub" style="font-size:0.72rem;color:var(--muted);margin:0 0 0.5rem">Red/warn here means a <strong>probe</strong> failed (feeds or Ollama), not a corrupt <code>state.json</code> file.</p>
    <p class="sub" id="v_data_pf">—</p>
    <p class="sub" id="v_llm_pf" style="margin-top:0.45rem">—</p>
    <p class="sub" id="v_pf_policy" style="margin-top:0.45rem;font-size:0.72rem;color:var(--muted)"></p>
  </div>
  <div class="card" style="margin-bottom:0.75rem;border-color:#484f58">
    <h2>One loop tick vs paper rows vs attempt-file lines</h2>
    <p class="sub" id="v_sem1"></p>
    <p class="sub" id="v_sem2"></p>
    <p class="sub" id="v_sem3"></p>
  </div>
  <div id="err"></div>
  <div class="card" style="margin-bottom:0.75rem;border-color:#30363d">
    <h2>Grade-12 learning signal (gates)</h2>
    <p class="ls" id="v_ls_head">—</p>
    <p class="ls-detail" id="v_ls_detail">—</p>
    <p class="sub" id="v_enroll"></p>
  </div>
  <div class="card" style="margin-bottom:0.75rem;border-color:var(--accent)">
    <h2>Last tick — Anna analysis (same stack as messaging Anna)</h2>
    <p class="sub" id="v_snap_hint">Persisted from the Karpathy harness: strategy, concepts, policy, risk, suggested action — refreshed every tick the daemon runs.</p>
    <div class="chips" id="v_steps"></div>
    <table class="data" id="v_analysis_tbl"><tbody id="v_analysis_body"></tbody></table>
  </div>
  <div class="card" style="margin-bottom:0.75rem">
    <h2>Last tick — Grade-12 tool drill (classroom)</h2>
    <p class="sub">When deck focus is <code>numeric_paper_cohort</code>, there is no four-tool drill that tick — focus is the paper cohort gate, not a tool ID.</p>
    <table class="data" id="v_sp_tbl"><tbody id="v_sp_body"></tbody></table>
  </div>
  <div class="grid">
    <div class="card"><h2>Supervisor ticks</h2><div class="val" id="v_iter">—</div><div class="sub" id="v_tick"></div></div>
    <div class="card"><h2>Grade-12 gates (numeric)</h2><div class="val" id="v_gate">—</div><div class="sub" id="v_gdetail"></div></div>
    <div class="card"><h2>Paper ledger (scored rows)</h2><div class="val" id="v_rows">—</div><div class="sub">Rows in <code>paper_trades.jsonl</code> — appended only when a paper trade is logged.</div><div class="val" id="v_pnl" style="font-size:1rem;margin-top:0.35rem">—</div></div>
    <div class="card"><h2>Attempt log (event lines)</h2><div class="val" id="v_attempts">—</div><div class="sub" id="v_jack"></div></div>
  </div>
  <div class="card" style="margin-top:0.75rem">
    <h2>Paper ledger — recent rows (same strip as TUI)</h2>
    <table class="data"><thead><tr><th>UTC</th><th>Sym</th><th>Side</th><th>Res</th><th>P&amp;L</th><th>Src</th></tr></thead><tbody id="tb"></tbody></table>
  </div>
  <div class="card" style="margin-top:0.75rem">
    <h2>Attempt log — recent lines</h2>
    <table class="data"><thead><tr><th>UTC</th><th>Phase</th><th>Status</th><th>Request</th></tr></thead><tbody id="tb_att"></tbody></table>
  </div>
  <div class="card" style="margin-top:0.75rem">
    <h2>Harness state (execution bridge)</h2>
    <p class="sub" id="v_harness_line">—</p>
    <details class="raw"><summary>Raw JSON (debug)</summary><pre id="v_harness">—</pre></details>
  </div>
  <p id="meta"></p>
  <script>
  const pollMs = 4000;
  function harnessLine(h) {
    if (!h || typeof h !== 'object') return '—';
    if (h.enabled === false) return String(h.reason || 'harness off');
    if (h.error) return 'error: ' + h.error;
    if (h.skipped) return 'stopped: ' + h.skipped + (h.request_id ? ' · request_id=' + String(h.request_id).slice(0,12) : '');
    if (h.paper_logged === true) return 'paper_logged · execution=' + String(h.execution_status||'') + ' · req=' + String(h.request_id||'').slice(0,12);
    if (h.request_id) return 'request_id=' + String(h.request_id).slice(0,12) + '… (see skipped/stopped above if no fill)';
    return '—';
  }
  function row(tbl, k, v) {
    var tr = document.createElement('tr');
    var th = document.createElement('th'); th.textContent = k;
    var td = document.createElement('td'); td.textContent = v == null || v === '' ? '—' : String(v);
    tr.appendChild(th); tr.appendChild(td); tbl.appendChild(tr);
  }
  async function tick() {
    const err = document.getElementById('err');
    try {
      const r = await fetch('/api/v1/anna/training-dashboard', { cache: 'no-store' });
      const j = await r.json();
      err.style.display = 'none';
      if (!j.ok) { err.textContent = (j.error || 'error') + ': ' + (j.detail || ''); err.style.display = 'block'; return; }
      var sem = j.semantics || {};
      document.getElementById('v_sem1').textContent = sem.loop_tick_means || '—';
      document.getElementById('v_sem2').textContent = sem.attempt_log_vs_tick || '—';
      document.getElementById('v_sem3').textContent = sem.paper_ledger_vs_tick || '—';
      (function preflightBanner() {
        var d = j.data_preflight || {};
        var l = j.llm_preflight || {};
        var pol = j.preflight_policy || {};
        function dataLine() {
          if (!d || typeof d !== 'object' || Object.keys(d).length === 0) {
            return { tier: 1, text: 'No saved data-preflight row yet — run the Karpathy daemon once so training state is updated.' };
          }
          if (d.skipped) return { tier: 1, text: 'Skipped (ANNA_SKIP_PREFLIGHT) — enforcement bypassed.' };
          if (d.ok) return { tier: 0, text: 'OK — Pyth stream + market_data.db (and optional Solana) passed this tick.' };
          var blockers = (d.blockers || []).join(', ');
          return { tier: 2, text: 'Blocked — ' + (blockers || 'unknown') + '. Fix feeds; see readiness in heartbeat JSONL or anna_training_dir.' };
        }
        function llmLine() {
          if (!l || typeof l !== 'object' || Object.keys(l).length === 0) {
            return { tier: 1, text: 'No LLM probe row yet — daemon has not finished a tick that saved llm_preflight.' };
          }
          if (l.skipped) return { tier: 0, text: 'Skipped (' + (l.reason || 'ANNA_USE_LLM off') + ').' };
          if (l.ok === false) {
            return { tier: 2, text: 'Ollama probe failed — ' + (l.error || 'error') + (l.base_url ? ' · base ' + l.base_url : '') };
          }
          if (l.model_present_in_tags === false) {
            return { tier: 1, text: 'Ollama up but model ' + (l.ollama_model_configured || '') + ' not listed in /api/tags (ollama pull).' };
          }
          return { tier: 0, text: 'OK — ' + (l.ollama_model_configured || '') + ' present · ' + (l.base_url || '') };
        }
        var dataPf = dataLine();
        var llmPf = llmLine();
        document.getElementById('v_data_pf').textContent = 'Data: ' + dataPf.text;
        document.getElementById('v_llm_pf').textContent = 'LLM: ' + llmPf.text;
        var worst = 0;
        if (dataPf.tier >= llmPf.tier) worst = dataPf.tier; else worst = llmPf.tier;
        var ban = document.getElementById('v_preflight_banner');
        ban.className = 'card ' + (worst >= 2 ? 'llm-bad' : (worst >= 1 ? 'llm-warn' : 'llm-good'));
        ban.style.display = 'block';
        document.getElementById('v_pf_policy').textContent = (pol.llm_probe_never_blocks_school !== false)
          ? 'Policy: the LLM line is informational — the loop does not skip school on Ollama errors. Fix OLLAMA_BASE_URL and model for real generations.'
          : 'Policy: see preflight_policy in JSON.';
      })();
      var ls = j.learning_signal || {};
      document.getElementById('v_ls_head').textContent = ls.headline || '—';
      document.getElementById('v_ls_detail').textContent = ls.detail || '';
      var enr = j.enrollment || {};
      document.getElementById('v_enroll').textContent =
        'Curriculum: ' + (enr.curriculum_id || '—') + ' · Method: ' + (enr.training_method_id || '—') +
        (j.skills_deck_focus ? ' · Deck focus: ' + j.skills_deck_focus : '');
      var as = j.analysis_snapshot || {};
      var ab = document.getElementById('v_analysis_body');
      ab.innerHTML = '';
      document.getElementById('v_snap_hint').style.display = Object.keys(as).length ? 'block' : 'none';
      var stel = document.getElementById('v_steps');
      stel.innerHTML = '';
      if (as.answer_source) {
        var c0 = document.createElement('span');
        c0.className = 'chip';
        c0.textContent = 'answer_source: ' + as.answer_source;
        stel.appendChild(c0);
      }
      (as.pipeline_steps || []).forEach(function(s) {
        var c = document.createElement('span');
        c.className = 'chip';
        c.textContent = s;
        stel.appendChild(c);
      });
      if (Object.keys(as).length) {
        row(ab, 'Generated (UTC)', as.generated_at || '—');
        row(ab, 'Headline', as.interpretation_headline);
        row(ab, 'Summary', as.interpretation_summary);
        row(ab, 'Concepts used', (as.concepts_used || []).join(', ') || '—');
        row(ab, 'Policy guardrail mode', as.policy_guardrail_mode || '—');
        row(ab, 'Policy alignment', as.policy_alignment || '—');
        row(ab, 'Strategy playbook applied', as.strategy_playbook_applied != null ? String(as.strategy_playbook_applied) : '—');
        row(ab, 'Strategy concepts (detected)', (as.strategy_concepts_detected || []).join(', ') || '—');
        row(ab, 'Strategy explanation', as.strategy_explanation || '—');
        row(ab, 'Strategy risks', (as.strategy_risks || []).join(' · ') || '—');
        row(ab, 'Trading-core signal snapshot', as.trading_core_signal_snapshot || '—');
        row(ab, 'Math engine (snapshot)', as.math_engine_snapshot || '—');
        row(ab, 'Risk level', as.risk_level);
        row(ab, 'Risk factors', (as.risk_factors || []).join(' · ') || '—');
        row(ab, 'Suggested intent', as.suggested_intent);
        row(ab, 'Suggested rationale', as.suggested_rationale || '—');
        var mps = (as.market_price != null ? as.market_price : '—') + ' / ' + (as.market_spread != null ? as.market_spread : '—');
        if (as.market_price == null && as.market_spread == null) {
          mps += ' — (no price in snapshot: market snapshot / DB tasks may be empty; see Notes)';
        }
        row(ab, 'Market price / spread', mps);
        row(ab, 'Regime', as.regime || '—');
        row(ab, 'Signals', (as.interpretation_signals || []).join(', ') || '—');
        row(ab, 'Cumulative log entries (school)', as.cumulative_log_entries != null ? String(as.cumulative_log_entries) : '—');
        row(ab, 'Notes (tail)', (as.analysis_notes_tail || []).join(' | ') || '—');
      } else {
        var tr = document.createElement('tr');
        var td = document.createElement('td');
        td.colSpan = 2;
        td.textContent = 'No analysis snapshot yet — upgrade Karpathy daemon after deploy (harness must persist analysis_snapshot).';
        tr.appendChild(td);
        ab.appendChild(tr);
      }
      var sp = j.skill_practice_last || {};
      var sb = document.getElementById('v_sp_body');
      sb.innerHTML = '';
      row(sb, 'Drill ran this tick', sp.ran ? 'yes' : 'no');
      row(sb, 'Deck focus (snapshot)', sp.current_focus || j.skills_deck_focus || '—');
      var noteText = sp.note || '—';
      if (sp.ran) noteText = '(n/a — tool drill ran this tick)';
      row(sb, 'Why no tool drill / note', noteText);
      row(sb, 'Skill id', sp.skill_id || '—');
      row(sb, 'Passed', sp.passed != null ? (sp.passed ? 'yes' : 'no') : '—');
      row(sb, 'Summary', sp.summary || '—');
      row(sb, 'Practice kind', sp.practice_kind || '—');
      var det = sp.detail;
      if (det != null && typeof det === 'object') {
        row(sb, 'Detail', JSON.stringify(det));
      } else {
        row(sb, 'Detail', det != null && det !== '' ? String(det) : '—');
      }
      document.getElementById('v_iter').textContent = j.loop.karpathy_loop_iteration ?? '—';
      document.getElementById('v_tick').textContent = j.loop.karpathy_loop_last_tick_utc ? 'last tick ' + j.loop.karpathy_loop_last_tick_utc : '';
      const gp = j.gates.pass;
      const ge = document.getElementById('v_gate');
      ge.textContent = gp ? 'PASS' : 'NOT PASS';
      ge.className = 'val ' + (gp ? 'ok' : 'bad');
      document.getElementById('v_gdetail').textContent = 'decisive ' + (j.gates.decisive_trades||0) + '/' + (j.gates.min_decisive_trades||'—') +
        (j.gates.win_rate != null ? ' · WR ' + (100*j.gates.win_rate).toFixed(0) + '%' : '');
      document.getElementById('v_rows').textContent = j.paper_cohort.row_count;
      document.getElementById('v_pnl').textContent = 'W'+j.paper_cohort.wins+' L'+j.paper_cohort.losses+' · $'+Number(j.paper_cohort.total_pnl_usd||0).toFixed(2);
      document.getElementById('v_attempts').textContent = j.attempts.total_events;
      var aj = j.attempts || {};
      document.getElementById('v_jack').textContent =
        'Jack delegate started ' + (aj.jack_delegate_started||0) +
        ' · ok+paper ' + (aj.jack_ok_with_paper||0) +
        ' · ok no paper ' + (aj.jack_ok_no_paper||0) +
        ' · manual log ' + (aj.paper_manual_recorded||0) +
        ' · failed ' + (aj.jack_delegate_failed||0);
      document.getElementById('v_harness_line').textContent = harnessLine(j.paper_harness_last);
      document.getElementById('v_harness').textContent = JSON.stringify(j.paper_harness_last || {}, null, 2);
      const tb = document.getElementById('tb');
      tb.innerHTML = '';
      (j.recent_trades || []).forEach(function(row) {
        const tr = document.createElement('tr');
        [ 'ts_utc','symbol','side','result','pnl_usd','source' ].forEach(function(k) {
          const td = document.createElement('td');
          let v = row[k];
          if (k === 'ts_utc' && v) v = String(v).slice(0,19);
          if (k === 'pnl_usd') v = v != null ? Number(v).toFixed(2) : '—';
          td.textContent = v != null && v !== '' ? v : '—';
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
      var tba = document.getElementById('tb_att');
      tba.innerHTML = '';
      (j.attempt_events_recent || []).forEach(function(ev) {
        var tr = document.createElement('tr');
        ['ts_utc','phase','status','request_id'].forEach(function(k) {
          var td = document.createElement('td');
          td.textContent = ev[k] != null && ev[k] !== '' ? String(ev[k]) : '—';
          tr.appendChild(td);
        });
        tba.appendChild(tr);
      });
      document.getElementById('meta').textContent = 'Updated ' + (j.at_utc || '') + ' · trace ' + (j.trace_id||'').slice(0,8);
    } catch (e) {
      err.textContent = String(e);
      err.style.display = 'block';
    }
  }
  tick();
  setInterval(tick, pollMs);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict[str, Any] | list[Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _html(self, code: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
        if path == "/api/v1/anna/training-dashboard":
            self._json(200, build_anna_training_dashboard())
            return
        if path in ("/anna/training", "/anna/training/"):
            self._html(200, TRAINING_DASHBOARD_HTML)
            return
        if path == "/api/v1/system/status":
            self._json(200, build_system_status())
            return
        if path == "/api/v1/context-engine/status":
            if build_context_engine_status is None or record_api_probe is None:
                self._json(
                    200,
                    {
                        "status": "error",
                        "reason_code": "CTX-ENGINE-IMPORT-FAIL",
                        "last_heartbeat_at": None,
                        "freshness_seconds": None,
                        "last_event_kind": None,
                        "record_count_hint": None,
                        "storage_path": None,
                        "trace_id": str(uuid.uuid4()),
                    },
                )
                return
            try:
                record_api_probe(ROOT)
                body = dict(build_context_engine_status(ROOT))
                body["trace_id"] = str(uuid.uuid4())
                self._json(200, body)
            except Exception as e:  # noqa: BLE001 — fail-closed surface for API
                self._json(
                    200,
                    {
                        "status": "error",
                        "reason_code": "CTX-STATUS-EXCEPTION",
                        "last_heartbeat_at": None,
                        "freshness_seconds": None,
                        "last_event_kind": None,
                        "record_count_hint": None,
                        "storage_path": None,
                        "detail": str(e),
                        "trace_id": str(uuid.uuid4()),
                    },
                )
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
