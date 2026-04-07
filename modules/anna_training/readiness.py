"""Pre-flight checks: Solana RPC (Jupiter prerequisite), Pyth stream artifacts, market DB."""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
from datetime import datetime, timezone
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from modules.operator_snapshot import artifacts_dir


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _market_data_db_path(repo_root: Path) -> Path:
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (repo_root / "data" / "sqlite" / "market_data.db").resolve()


def _iso_age_seconds_utc(ts: str) -> float | None:
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
    except ValueError:
        return None


def _load_json(p: Path) -> dict[str, Any] | None:
    if not p.is_file():
        return None
    try:
        o = json.loads(p.read_text(encoding="utf-8"))
        return o if isinstance(o, dict) else None
    except json.JSONDecodeError:
        return None


def check_solana_rpc() -> dict[str, Any]:
    """Lightweight JSON-RPC ping — same transport Jack/Jupiter clients need."""
    url = (os.environ.get("SOLANA_RPC_URL") or "").strip() or "https://api.mainnet-beta.solana.com"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getHealth"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            ok = isinstance(data, dict) and data.get("result") == "ok"
            return {
                "ok": ok,
                "rpc_url_host": urllib.parse.urlparse(url).netloc or url[:48],
                "detail": "getHealth returned ok" if ok else str(data)[:200],
            }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return {"ok": False, "rpc_url_host": urllib.parse.urlparse(url).netloc or "?", "detail": str(e)[:200]}


def check_pyth_artifacts(repo_root: Path | None = None) -> dict[str, Any]:
    """Pyth stream status file (same layout as UI API / operator_snapshot)."""
    root = repo_root or _repo_root()
    art = artifacts_dir(root)
    stream = _load_json(art / "pyth_stream_status.json")
    if not stream:
        return {
            "ok": False,
            "status": "unknown",
            "reason": "pyth_stream_status.json missing or unreadable",
            "artifact_dir": str(art),
        }
    st = str(stream.get("status") or stream.get("stream_state") or "unknown")
    ok = st in {"healthy", "connected"}
    return {
        "ok": ok,
        "status": st,
        "reason_code": str(stream.get("reason_code") or ""),
        "last_update_at": stream.get("last_event_at") or stream.get("updated_at"),
        "artifact": str(art / "pyth_stream_status.json"),
    }


def check_market_db(repo_root: Path | None = None) -> dict[str, Any]:
    """Where Anna's analyst path reads ticks/snapshots when wired (`market_data.db`)."""
    root = repo_root or _repo_root()
    p = _market_data_db_path(root)
    exists = p.is_file()
    size = p.stat().st_size if exists else 0
    return {
        "ok": exists and size > 0,
        "path": str(p),
        "db_bytes": size,
        "note": "Anna uses snapshots/ticks from here when analysis flags enable market data.",
    }


def check_pyth_sse_tape(repo_root: Path | None = None) -> dict[str, Any]:
    """``pyth_hermes_sse`` rows in ``market_ticks`` (Hermes SSE ingest) — required for full oracle tape."""
    root = repo_root or _repo_root()
    p = _market_data_db_path(root)
    max_age = float((os.environ.get("ANNA_PYTH_SSE_MAX_AGE_SEC") or "180").strip() or "180")
    if not p.is_file():
        return {
            "ok": False,
            "reason": "db_missing",
            "path": str(p),
            "age_seconds": None,
            "max_age_sec": max_age,
            "sse_tick_count": 0,
        }
    conn = sqlite3.connect(str(p))
    try:
        row = conn.execute(
            """
            SELECT COUNT(*), MAX(inserted_at)
            FROM market_ticks
            WHERE primary_source = ?
            """,
            ("pyth_hermes_sse",),
        ).fetchone()
    finally:
        conn.close()
    n = int(row[0] or 0) if row else 0
    max_ins = row[1] if row else None
    if n == 0 or not max_ins:
        return {
            "ok": False,
            "reason": "no_sse_ticks",
            "path": str(p),
            "age_seconds": None,
            "max_age_sec": max_age,
            "sse_tick_count": 0,
        }
    age = _iso_age_seconds_utc(str(max_ins))
    if age is None:
        return {
            "ok": False,
            "reason": "bad_inserted_at",
            "path": str(p),
            "age_seconds": None,
            "max_age_sec": max_age,
            "sse_tick_count": n,
        }
    ok = age <= max_age
    return {
        "ok": ok,
        "reason": "sse_tape_stale" if not ok else "ok",
        "path": str(p),
        "age_seconds": int(max(0.0, age)),
        "max_age_sec": max_age,
        "sse_tick_count": n,
        "last_sse_inserted_at": str(max_ins),
    }


def check_jupiter_program_note() -> dict[str, Any]:
    """No on-chain account fetch in Python yet — anchors live in trading_core/src/venue/jupiter_perp.ts."""
    return {
        "ok": None,
        "note": "Full Jupiter readiness = Solana RPC + Jupiter program client (Jack path). RPC check above is step 1; program IDs: trading_core/src/venue/jupiter_perp.ts",
    }


def full_readiness(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or _repo_root()
    return {
        "order": ["solana_rpc", "pyth_stream", "market_data_db", "pyth_sse_tape", "jupiter_note"],
        "solana_rpc": check_solana_rpc(),
        "pyth_stream": check_pyth_artifacts(root),
        "market_data_db": check_market_db(root),
        "pyth_sse_tape": check_pyth_sse_tape(root),
        "jupiter_program": check_jupiter_program_note(),
        "anna_pyth_visibility": {
            "summary": "Oracle tape: `pyth_sse_ingest` (Hermes SSE) → `market_ticks` (`pyth_hermes_sse`); bars refreshed in-ingest; strategies read `market_bars_5m` / ticks from `market_data.db`. Probe JSON reflects SQLite age.",
        },
    }


def _env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _preflight_require_pyth_sse_tape() -> bool:
    """Default on: block Anna preflight if SSE tape is missing/stale (set ANNA_PREFLIGHT_REQUIRE_PYTH_SSE=0 to disable)."""
    v = (os.environ.get("ANNA_PREFLIGHT_REQUIRE_PYTH_SSE") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def preflight_skipped() -> bool:
    """Tests / dev: `ANNA_SKIP_PREFLIGHT=1` bypasses enforcement (not for production)."""
    return _env_truthy("ANNA_SKIP_PREFLIGHT")


def ensure_anna_data_preflight(repo_root: Path | None = None) -> dict[str, Any]:
    """Run before Anna work: Pyth stream artifact + non-empty `market_data.db` must pass.

    Optional: set `ANNA_PREFLIGHT_REQUIRE_SOLANA=1` to also require Solana RPC `getHealth`.

    Returns `ok` True when checks pass, or when `preflight_skipped()`; otherwise `ok` False and `blockers`
    lists which dimensions failed (e.g. ``pyth_stream``, ``market_data_db``, ``solana_rpc``).
    """
    root = repo_root or _repo_root()
    r = full_readiness(root)
    if preflight_skipped():
        return {"ok": True, "skipped": True, "readiness": r, "blockers": []}

    blockers: list[str] = []
    if not (r.get("pyth_stream") or {}).get("ok"):
        blockers.append("pyth_stream")
    if not (r.get("market_data_db") or {}).get("ok"):
        blockers.append("market_data_db")
    if _preflight_require_pyth_sse_tape() and not (r.get("pyth_sse_tape") or {}).get("ok"):
        blockers.append("pyth_sse_tape")
    if _env_truthy("ANNA_PREFLIGHT_REQUIRE_SOLANA") and not (r.get("solana_rpc") or {}).get("ok"):
        blockers.append("solana_rpc")

    return {
        "ok": len(blockers) == 0,
        "skipped": False,
        "readiness": r,
        "blockers": blockers,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_anna_analysis_preflight_blocked(input_text: str, pf: dict[str, Any]) -> dict[str, Any]:
    """Minimal `anna_analysis_v1` when data-source preflight fails (Telegram/CLI safe)."""
    blockers = pf.get("blockers") or []
    rd = pf.get("readiness") or {}
    summary = (
        "Anna’s data-source preflight did not pass. "
        "Fix Pyth stream status, `market_data.db`, and Hermes SSE tape (`pyth_hermes_sse` ticks + `pyth-sse-ingest`), then retry. "
        f"Blocked: {', '.join(blockers) if blockers else 'unknown'}. "
        "Operator: `python3 scripts/runtime/anna_training_cli.py check-readiness`."
    )
    slim = {
        "solana_rpc": rd.get("solana_rpc"),
        "pyth_stream": rd.get("pyth_stream"),
        "market_data_db": rd.get("market_data_db"),
        "pyth_sse_tape": rd.get("pyth_sse_tape"),
    }
    return {
        "kind": "anna_analysis_v1",
        "schema_version": 1,
        "generated_at": _utc_now_iso(),
        "input_text": input_text,
        "interpretation": {
            "headline": "Data sources not ready",
            "summary": summary,
            "signals": ["pipeline:preflight_blocked"],
            "assumptions": [],
        },
        "market_context": {"price": None, "spread": None, "notes": []},
        "risk_assessment": {"level": "low", "factors": []},
        "policy_alignment": {},
        "suggested_action": {"intent": "", "rationale": ""},
        "concepts_used": [],
        "concept_support": {},
        "strategy_awareness": None,
        "caution_flags": [],
        "notes": list(blockers),
        "human_intent": {"intent": "preflight", "topic": "pipeline"},
        "strategy_playbook_applied": False,
        "pipeline": {
            "answer_source": "preflight_blocked",
            "steps": ["preflight", "data_sources", "blocked"],
            "layer_meta": {"blockers": blockers, "readiness": slim},
        },
        "context_assessment": {"is_complete": False, "missing_fields": ["data_sources"]},
    }
