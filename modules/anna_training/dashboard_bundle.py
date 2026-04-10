"""
Aggregated operator dashboard payload: trade chain, sequential status, wallet subset, system mode.

Trade chain: horizontal event axis (columns) × vertical chains (baseline, Anna test, Anna strategy rows).

**Baseline row:** WIN/LOSS is bound to ``policy_evaluations`` (``signal_mode=sean_jupiter_v1`` is the **historic env
label** for “Sean baseline path”; the **engine** is always **Jupiter_2**, see ``jupiter_2_sean_policy``) plus
a matching execution row when ``trade=1``. Missing policy or ``trade=0`` renders NO TRADE even if
``execution_trades`` contains a baseline row (non-authoritative artifacts are not displayed as outcomes).

**Jupiter policy snapshot:** ``evaluate_sean_jupiter_baseline_v1`` → ``evaluate_jupiter_2_sean`` (bar-derived; paper).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Operator-visible cadence (must match dashboard.html poll interval and docker-compose defaults).
DASHBOARD_CLIENT_POLL_INTERVAL_MS = 1500
SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT = 5
PYTH_STREAM_PROBE_INTERVAL_SEC_DEFAULT = 15


def _parse_iso_ts(ts: str | None) -> datetime | None:
    if not ts or not str(ts).strip():
        return None
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _pyth_probe_snapshot(repo: Path) -> dict[str, Any]:
    p = repo / "docs" / "working" / "artifacts" / "pyth_stream_status.json"
    out: dict[str, Any] = {"status": None, "last_event_at": None, "age_seconds": None, "reason_code": None}
    if not p.is_file():
        out["reason_code"] = "pyth_artifact_missing"
        return out
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        out["reason_code"] = "pyth_artifact_bad_json"
        return out
    if not isinstance(raw, dict):
        return out
    out["status"] = raw.get("status") or raw.get("stream_state")
    out["reason_code"] = raw.get("reason_code")
    lu = raw.get("last_event_at") or raw.get("updated_at")
    out["last_event_at"] = lu
    dt = _parse_iso_ts(str(lu) if lu else None)
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        out["age_seconds"] = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    return out


def _sequential_tick_staleness(
    *,
    ui_state: str,
    events_remaining: int,
    last_tick_at: str | None,
    now: datetime,
) -> dict[str, Any]:
    """
    Operator-facing: distinguish live advancing vs running-but-stalled.
    Thresholds: degraded >45s, stalled >90s with queue > 0.
    """
    if ui_state != "running":
        return {
            "level": "not_running",
            "label": "IDLE",
            "detail": "Sequential learning is not in running state.",
        }
    if events_remaining <= 0:
        return {
            "level": "queue_empty",
            "label": "RUNNING · IDLE QUEUE",
            "detail": "No events left in file — last tick may not advance until new events.",
        }
    dt = _parse_iso_ts(last_tick_at)
    if dt is None:
        return {
            "level": "unknown",
            "label": "RUNNING · NO TICK YET",
            "detail": "Queue has events but no last_tick_at — wait for first tick.",
        }
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = max(0, int((now - dt).total_seconds()))
    if age > 90:
        return {
            "level": "stalled",
            "label": "STALLED",
            "detail": f"Last sequential tick was {age}s ago with {events_remaining} events still queued — check tick sidecar or API.",
        }
    if age > 45:
        return {
            "level": "degraded",
            "label": "LIVE (SLOW)",
            "detail": f"Last tick {age}s ago — expect ~{SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT}s when sidecar is up.",
        }
    return {
        "level": "live",
        "label": "LIVE",
        "detail": f"Last tick {age}s ago · {events_remaining} events remaining in queue.",
    }


def compute_next_tick_eta(
    *,
    ui_state: str,
    events_remaining: int,
    last_tick_at: str | None,
    interval_sec: float | None = None,
) -> dict[str, Any]:
    """
    Estimated time of next sequential batch tick (sidecar cadence), for operator countdown.
    When stalled, ETA rolls forward from now so the countdown stays meaningful.
    """
    sec = float(interval_sec or SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT)
    if ui_state != "running" or events_remaining <= 0:
        return {
            "available": False,
            "reason": "idle_or_queue_empty",
            "interval_sec": sec,
            "eta_at": None,
            "seconds_until_eta": None,
        }
    now = datetime.now(timezone.utc)
    base = _parse_iso_ts(last_tick_at) if last_tick_at else None
    if base is None:
        eta = now + timedelta(seconds=sec)
    else:
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        eta = base + timedelta(seconds=sec)
        if eta < now:
            eta = now + timedelta(seconds=sec)
    delta = max(0.0, (eta - now).total_seconds())
    eta_iso = eta.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "available": True,
        "reason": None,
        "interval_sec": sec,
        "eta_at": eta_iso,
        "seconds_until_eta": round(delta, 1),
    }


from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    connect_ledger,
    default_execution_ledger_path,
    ensure_execution_ledger_schema,
    fetch_policy_evaluation_for_market_event,
)
from modules.anna_training.quantitative_evaluation_layer.constants import (
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_CANDIDATE,
    LIFECYCLE_EXPERIMENT,
    LIFECYCLE_PROMOTED,
    LIFECYCLE_PROMOTION_READY,
    LIFECYCLE_TEST,
    LIFECYCLE_VALIDATED_STRATEGY,
)
from modules.anna_training.sequential_engine.mae_v1 import compute_mae_usd_v1

_MARKET_DB: Path | None = None


def _market_db_path() -> Path | None:
    global _MARKET_DB
    if _MARKET_DB is not None:
        return _MARKET_DB if _MARKET_DB.is_file() else None
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or os.environ.get("BLACKBOX_MARKET_DATA_DB") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        _MARKET_DB = p
        return p if p.is_file() else None
    repo = Path(__file__).resolve().parents[2]
    for candidate in (
        repo / "data" / "sqlite" / "market_data.db",
        repo / "data" / "sqlite" / "market_data.sqlite",
    ):
        if candidate.is_file():
            _MARKET_DB = candidate
            return candidate
    return None


def _ensure_runtime_for_market_imports() -> None:
    rt = _REPO_ROOT / "scripts" / "runtime"
    s = str(rt)
    if s not in sys.path:
        sys.path.insert(0, s)


def _count_pyth_sse_ticks_since_minutes(minutes: float) -> int | None:
    """Count ``pyth_hermes_sse`` rows with ``inserted_at`` in the last ``minutes`` (UTC)."""
    import sqlite3

    mpath = _market_db_path()
    if not mpath or not mpath.is_file():
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    cutoff = cutoff.replace(microsecond=0)
    cs = cutoff.isoformat()
    conn = sqlite3.connect(str(mpath))
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM market_ticks
            WHERE primary_source = ? AND inserted_at >= ?
            """,
            ("pyth_hermes_sse", cs),
        ).fetchone()
        return int(row[0] or 0) if row else 0
    except (OSError, sqlite3.Error):
        return None
    finally:
        conn.close()


def _compact_baseline_ledger_last(raw: Any) -> dict[str, Any] | None:
    """Last Karpathy tick bridge result — small keys only (state.json may hold full dict)."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {"schema": "baseline_ledger_tick_compact_v1"}
    for k in (
        "ok",
        "enabled",
        "no_trade",
        "reason_code",
        "market_event_id",
        "trade_id",
        "side",
        "signal_mode",
        "error",
        "idempotent_skip",
        "reason",
    ):
        if k in raw:
            out[k] = raw[k]
    feat = raw.get("features")
    if isinstance(feat, dict):
        out["features"] = feat
    return out if len(out) > 1 else None


def build_jupiter_policy_snapshot(
    *,
    market_db_path: Path | None = None,
    training_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Live **paper** Jupiter_2 baseline policy view: same evaluator as ``baseline_ledger_bridge``.

    Not a price tape; not venue execution. Refreshes every dashboard bundle request.
    """
    from modules.anna_training.jupiter_2_sean_policy import (
        CATALOG_ID as JUPITER_2_CATALOG_ID,
        POLICY_ENGINE_ID,
        POLICY_SPEC_VERSION,
    )
    from modules.anna_training.sean_jupiter_baseline_signal import (
        MIN_BARS,
        evaluate_sean_jupiter_baseline_v1,
        format_jupiter_tile_narrative_v1,
    )

    mpath = market_db_path if market_db_path is not None else _market_db_path()
    out: dict[str, Any] = {
        "schema": "jupiter_policy_snapshot_v1",
        # Explicit engine identity — always Jupiter_2 for this snapshot (not legacy Wilder/ST paths).
        "policy_engine": POLICY_ENGINE_ID,
        "policy_catalog_id": JUPITER_2_CATALOG_ID,
        "policy_spec_version": POLICY_SPEC_VERSION,
        "baseline_signal_mode_env": "sean_jupiter_v1",
        "baseline_signal_mode_note": (
            "Env BASELINE_LEDGER_SIGNAL_MODE default is still named sean_jupiter_v1 for compatibility; "
            "evaluator is jupiter_2_sean_policy.evaluate_jupiter_2_sean."
        ),
        "what_this_is": (
            "Bar-derived Jupiter_2 Sean policy (Supertrend 10/3, EMA200, RSI 14, simple TR ATR ratio). "
            "Shows whether the latest closed bar would fire a paper baseline trade and which features aligned."
        ),
        "market_db_path": str(mpath) if mpath else None,
        "market_db_ok": bool(mpath and mpath.is_file()),
    }
    st = training_state if isinstance(training_state, dict) else {}
    bl = st.get("baseline_ledger_last")
    cbl = _compact_baseline_ledger_last(bl)
    if cbl:
        out["last_daemon_bridge_tick"] = cbl

    if not mpath or not mpath.is_file():
        out["error"] = "market_db_missing"
        out["hint"] = "Set BLACKBOX_MARKET_DATA_PATH or ingest market_bars_5m."
        return out

    try:
        _ensure_runtime_for_market_imports()
        from market_data.bar_lookup import fetch_recent_bars_asc

        bars = fetch_recent_bars_asc(limit=280, db_path=mpath)
    except Exception as e:
        out["error"] = f"fetch_bars_failed:{e!s}"[:240]
        return out

    out["bars_fetched"] = len(bars)
    out["min_bars_required"] = MIN_BARS
    if len(bars) < MIN_BARS:
        out["error"] = "insufficient_history"
        out["hint"] = (
            f"Need at least {MIN_BARS} closed bars (Jupiter_2: EMA200 + Supertrend(10,3) + RSI, ATR ratio)."
        )
        return out

    last = bars[-1]
    out["evaluated_bar"] = {
        "market_event_id": str(last.get("market_event_id") or ""),
        "candle_open_utc": str(last.get("candle_open_utc") or ""),
        "candle_close_utc": str(last.get("candle_close_utc") or ""),
        "open": last.get("open"),
        "high": last.get("high"),
        "low": last.get("low"),
        "close": last.get("close"),
        "tick_count": last.get("tick_count"),
        "price_source": str(last.get("price_source") or "") or None,
    }

    sig = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    out["would_trade"] = bool(sig.trade)
    out["side"] = sig.side
    out["reason_code"] = sig.reason_code
    out["pnl_usd_open_to_close_hint"] = sig.pnl_usd
    out["features"] = dict(sig.features) if isinstance(sig.features, dict) else sig.features
    sf = out["features"] if isinstance(out["features"], dict) else {}
    pb_list = sf.get("policy_blockers")
    pbl = [str(x) for x in pb_list] if isinstance(pb_list, list) else None
    out["operator_tile_narrative"] = format_jupiter_tile_narrative_v1(
        features=sf,
        reason_code=str(sig.reason_code or ""),
        trade=bool(sig.trade),
        side=str(sig.side or "flat"),
        policy_blockers=pbl,
    )

    # Explicit alignment chips for UI (same booleans as in features)
    feat = out["features"] if isinstance(out["features"], dict) else {}
    out["alignment"] = {
        "short_signal": bool(feat.get("short_signal")),
        "long_signal": bool(feat.get("long_signal")),
        "prev_rsi": feat.get("prev_rsi"),
        "current_rsi": feat.get("current_rsi"),
    }
    return out


def _outcome_from_pnl(pnl: float | None, *, mode: str) -> str:
    m = (mode or "").strip().lower()
    if m == "paper_stub":
        return "STUB"  # internal code; UI uses outcome_display (operator-friendly)
    if pnl is None:
        return "—"
    try:
        p = float(pnl)
    except (TypeError, ValueError):
        return "—"
    if p > 1e-9:
        return "WIN"
    if p < -1e-9:
        return "LOSS"
    return "FLAT"


def _economic_authority(*, chain_kind: str, mode: str | None) -> str:
    """Baseline = full. Anna live/paper = full economic W/L. Other modes = muted."""
    if chain_kind == "baseline":
        return "full"
    m = (mode or "").strip().lower()
    if m in ("live", "paper"):
        return "full"
    return "muted"


def _outcome_display(outcome: str) -> str:
    if outcome == "STUB":
        return "Eval"
    return outcome


def _lifecycle_short_label(lifecycle_state: str | None) -> str:
    s = (lifecycle_state or "").strip().lower()
    return {
        LIFECYCLE_EXPERIMENT: "Experiment",
        LIFECYCLE_TEST: "Test",
        LIFECYCLE_CANDIDATE: "Candidate",
        LIFECYCLE_VALIDATED_STRATEGY: "Validated",
        LIFECYCLE_PROMOTION_READY: "Promo-ready",
        LIFECYCLE_PROMOTED: "Promoted",
        LIFECYCLE_ARCHIVED: "Archived",
    }.get(s, s.replace("_", " ").title() if s else "—")


def _anna_row_accent_slot(strategy_id: str) -> int:
    h = hashlib.md5(strategy_id.encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(h[:2], 16) % 4


def _latest_symbol_from_ledger(conn: Any) -> str | None:
    try:
        cur = conn.execute(
            "SELECT symbol FROM execution_trades ORDER BY created_at_utc DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip() or None
    except Exception:
        pass
    return None


def _market_clock_for_symbol(symbol: str | None) -> dict[str, Any]:
    """
    Display timezone for operator-facing clocks (market-context, not browser local).
    Heuristic: US-listed symbols → America/New_York; crypto/24h → IANA UTC (labels avoid spelling Zulu/UTC).
    """
    s = (symbol or "").strip().upper()
    if not s:
        return {
            "iana_timezone": "UTC",
            "label": "Market time (settle when ledger has a symbol)",
            "primary_symbol": None,
        }
    if s in ("SPY", "QQQ", "IWM", "DIA") or "-US" in s or s.endswith(".US"):
        return {
            "iana_timezone": "America/New_York",
            "label": "US cash session (Eastern)",
            "primary_symbol": symbol,
        }
    if any(
        x in s
        for x in (
            "BTC",
            "ETH",
            "SOL",
            "PERP",
            "USDC",
            "USDT",
            "-USD",
            "USD-",
            "/USD",
        )
    ):
        return {
            "iana_timezone": "UTC",
            "label": "24h perpetual / crypto (market clock)",
            "primary_symbol": symbol,
        }
    return {
        "iana_timezone": "UTC",
        "label": "Global market (clock)",
        "primary_symbol": symbol,
    }


def _notional_usd(entry_price: float | None, size: float | None) -> float | None:
    if entry_price is None or size is None:
        return None
    try:
        ep = float(entry_price)
        sz = float(size)
    except (TypeError, ValueError):
        return None
    if ep != ep or sz != sz or sz <= 0:
        return None
    return round(ep * sz, 4)


def _pair_vs_baseline_for_cells(
    baseline_cell: dict[str, Any],
    anna_cell: dict[str, Any],
    *,
    epsilon: float,
) -> dict[str, Any]:
    """
    Same rule as sequential paired_outcomes + MAE gate (display / operator clarity).
    Baseline leg must be live/paper. Anna leg may be paper_stub when PnL + MAE are present
    so operator sees WIN/NOT vs baseline alongside eval/stub mode labeling.
    """
    if baseline_cell.get("empty") or anna_cell.get("empty"):
        return {"vs_baseline": None, "vs_baseline_excl": "empty_cell"}
    bm = str(baseline_cell.get("mode") or "").strip().lower()
    am = str(anna_cell.get("mode") or "").strip().lower()
    if bm not in ("live", "paper"):
        return {"vs_baseline": "EXCLUDED", "vs_baseline_excl": "baseline_not_economic"}
    # Anna: include paper_stub when PnL+MAE exist so trial/candidate rows can show WIN/NOT vs baseline
    # (mode line may still read eval/stub; pairing uses the same MAE gate as paper.)
    if am not in ("live", "paper", "paper_stub"):
        return {"vs_baseline": "EXCLUDED", "vs_baseline_excl": "anna_not_economic"}
    pb = baseline_cell.get("pnl_usd")
    pa = anna_cell.get("pnl_usd")
    if pb is None or pa is None:
        return {"vs_baseline": "EXCLUDED", "vs_baseline_excl": "missing_pnl"}
    mae_b = baseline_cell.get("mae_usd")
    mae_a = anna_cell.get("mae_usd")
    if mae_b is None or mae_a is None:
        return {"vs_baseline": "EXCLUDED", "vs_baseline_excl": "missing_mae"}
    try:
        mb = float(mae_b)
        ma = float(mae_a)
        fpb = float(pb)
        fpa = float(pa)
    except (TypeError, ValueError):
        return {"vs_baseline": "EXCLUDED", "vs_baseline_excl": "invalid_numbers"}
    if mb < 0:
        return {"vs_baseline": "EXCLUDED", "vs_baseline_excl": "invalid_mae_baseline"}
    cap = (1.0 + float(epsilon)) * mb
    passes_risk = ma <= cap + 1e-12
    if not passes_risk:
        return {"vs_baseline": "NOT_WIN", "vs_baseline_excl": "risk_gate"}
    if fpa > fpb:
        return {"vs_baseline": "WIN", "vs_baseline_excl": None}
    return {"vs_baseline": "NOT_WIN", "vs_baseline_excl": "pnl_not_above"}


def _event_axis_jupiter_tile_narratives(
    conn: Any,
    event_axis: list[str],
    market_db_path: Path | None,
) -> dict[str, str]:
    """
    Per-``market_event_id`` multi-line Jupiter / Sean policy tile (operator requirement).

    When a ``policy_evaluations`` row exists for the event, the narrative is **always** derived
    from persisted ``features_json`` (and row trade/side/reason_code) — never recomputed from
    bars. Recompute from ``market_bars_5m`` only when **no** policy row is present.
    """
    from modules.anna_training.execution_ledger import (
        RESERVED_STRATEGY_BASELINE,
        fetch_policy_evaluation_for_market_event,
    )
    from modules.anna_training.sean_jupiter_baseline_signal import (
        MIN_BARS,
        evaluate_sean_jupiter_baseline_v1,
        format_jupiter_tile_narrative_v1,
    )

    out: dict[str, str] = {}
    if not event_axis:
        return out

    mpath = market_db_path
    _ensure_runtime_for_market_imports()
    from market_data.bar_lookup import fetch_recent_bars_asc

    for mid in event_axis:
        mid_s = str(mid or "").strip()
        if not mid_s:
            continue
        row = fetch_policy_evaluation_for_market_event(
            conn,
            mid_s,
            lane=RESERVED_STRATEGY_BASELINE,
            strategy_id=RESERVED_STRATEGY_BASELINE,
            signal_mode="sean_jupiter_v1",
        )
        if row:
            f = dict(row["features"]) if isinstance(row.get("features"), dict) else {}
            pb = f.get("policy_blockers")
            pbl = [str(x) for x in pb] if isinstance(pb, list) else None
            out[mid_s] = format_jupiter_tile_narrative_v1(
                features=f,
                reason_code=str(row.get("reason_code") or ""),
                trade=bool(row.get("trade")),
                side=str(row.get("side") or "flat"),
                policy_blockers=pbl,
            )
            continue
        if not mpath or not mpath.is_file():
            out[mid_s] = format_jupiter_tile_narrative_v1(
                features={},
                reason_code="market_db_unavailable",
                trade=False,
                side="flat",
            )
            continue
        try:
            bars = fetch_recent_bars_asc(limit=280, db_path=mpath)
            idx = next(
                (
                    j
                    for j, b in enumerate(bars)
                    if str(b.get("market_event_id") or "").strip() == mid_s
                ),
                None,
            )
            if idx is None or len(bars[: idx + 1]) < MIN_BARS:
                out[mid_s] = format_jupiter_tile_narrative_v1(
                    features={},
                    reason_code="bar_not_in_window_or_short_history",
                    trade=False,
                    side="flat",
                )
                continue
            sub = bars[: idx + 1]
            sig = evaluate_sean_jupiter_baseline_v1(bars_asc=sub)
            sf = dict(sig.features) if isinstance(sig.features, dict) else {}
            pb = sf.get("policy_blockers")
            pbl = [str(x) for x in pb] if isinstance(pb, list) else None
            out[mid_s] = format_jupiter_tile_narrative_v1(
                features=sf,
                reason_code=sig.reason_code,
                trade=sig.trade,
                side=sig.side,
                policy_blockers=pbl,
            )
        except Exception as e:
            out[mid_s] = (
                "Jupiter tile (event column): build failed — "
                + str(e)[:400]
                + "\n(Check BLACKBOX_MARKET_DATA_PATH, execution_ledger policy_evaluations, API restart after deploy.)"
            )
    return out


def _compact_cell(
    row: dict[str, Any] | None,
    *,
    market_db_path: Path | None,
    chain_kind: str = "baseline",
) -> dict[str, Any]:
    if not row:
        return {
            "empty": True,
            "market_event_id": None,
            "trade_id": None,
            "trace_id": None,
            "symbol": None,
            "timeframe": None,
            "side": None,
            "exit_reason": None,
            "entry": None,
            "exit": None,
            "entry_time": None,
            "exit_time": None,
            "size": None,
            "notional_usd_approx": None,
            "pnl_usd": None,
            "mae_usd": None,
            "outcome": "NO_TRADE",
            "outcome_display": "no trade",
            "economic_authority": "full" if chain_kind == "baseline" else "muted",
            "mode": None,
        }
    mode = str(row.get("mode") or "")
    pnl = row.get("pnl_usd")
    pnl_f = float(pnl) if pnl is not None else None
    sym = str(row.get("symbol") or "").strip()
    mae_val: float | None = None
    if sym and market_db_path and market_db_path.is_file():
        mae_val, _ = compute_mae_usd_v1(
            canonical_symbol=sym,
            side=row.get("side"),
            entry_price=row.get("entry_price"),
            size=row.get("size"),
            entry_time=row.get("entry_time"),
            exit_time=row.get("exit_time"),
            market_db_path=market_db_path,
        )
    raw_out = _outcome_from_pnl(pnl_f, mode=mode)
    econ = _economic_authority(chain_kind=chain_kind, mode=mode)
    return {
        "empty": False,
        "market_event_id": row.get("market_event_id"),
        "trade_id": row.get("trade_id"),
        "trace_id": row.get("trace_id"),
        "symbol": row.get("symbol"),
        "timeframe": row.get("timeframe"),
        "side": row.get("side"),
        "exit_reason": row.get("exit_reason"),
        "entry": row.get("entry_price"),
        "exit": row.get("exit_price"),
        "entry_time": row.get("entry_time"),
        "exit_time": row.get("exit_time"),
        "size": row.get("size"),
        "notional_usd_approx": _notional_usd(row.get("entry_price"), row.get("size")),
        "pnl_usd": pnl_f,
        "mae_usd": round(mae_val, 6) if mae_val is not None else None,
        "outcome": raw_out,
        "outcome_display": _outcome_display(raw_out),
        "economic_authority": econ,
        "mode": mode,
    }


def _fetch_trade(
    conn: Any,
    market_event_id: str,
    *,
    lane: str,
    strategy_id: str,
) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
               side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
               pnl_usd, context_snapshot_json, notes, trace_id, created_at_utc
        FROM execution_trades
        WHERE market_event_id = ? AND lane = ? AND strategy_id = ?
        ORDER BY created_at_utc DESC, trade_id DESC
        LIMIT 1
        """,
        (market_event_id.strip(), lane.strip().lower(), strategy_id.strip()),
    )
    r = cur.fetchone()
    if not r:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, r))


def _strip_outcome_from_pnl(pnl: Any) -> str:
    """Compact label for main-dashboard baseline strip (PnL sign).

    WIN/LOSS require PnL strictly outside a tiny band around zero (same epsilon as
    ``_outcome_from_pnl``) — zero or dust PnL is **FLAT**, never WIN.
    """
    if pnl is None:
        return "—"
    try:
        v = float(pnl)
    except (TypeError, ValueError):
        return "—"
    if v > 1e-9:
        return "WIN"
    if v < -1e-9:
        return "LOSS"
    return "FLAT"


def _recent_baseline_trades_for_dashboard_strip(
    conn: sqlite3.Connection,
    *,
    limit: int = 3,
    market_db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Newest-first baseline lane rows from ``execution_trades`` (not limited to visible chain columns).

    Used for the “Recent baseline trades” block on ``dashboard.html`` so operators always see
    ledger-backed activity when rows exist. Includes ``mae_usd`` (v1) when market bars and inputs allow.
    """
    lim = max(1, min(200, int(limit)))
    mpath = market_db_path
    cur = conn.execute(
        """
        SELECT market_event_id, side, symbol, timeframe, entry_time, entry_price, exit_price,
               exit_reason, exit_time, size, pnl_usd, created_at_utc, trade_id
        FROM execution_trades
        WHERE lane = 'baseline' AND strategy_id = ?
        ORDER BY COALESCE(created_at_utc, entry_time, '') DESC, trade_id DESC
        LIMIT ?
        """,
        (RESERVED_STRATEGY_BASELINE, lim),
    )
    cols = [d[0] for d in cur.description]
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        row = dict(zip(cols, r))
        t = row.get("entry_time") or row.get("created_at_utc")
        t_iso = _normalize_utc_iso_for_axis(t) if t else None
        pnl = row.get("pnl_usd")
        ep = row.get("entry_price")
        xp = row.get("exit_price")
        sym = str(row.get("symbol") or "").strip()
        tf = str(row.get("timeframe") or "").strip()
        mae_val: float | None = None
        if sym and mpath and mpath.is_file():
            mae_val, _ = compute_mae_usd_v1(
                canonical_symbol=sym,
                side=row.get("side"),
                entry_price=row.get("entry_price"),
                size=row.get("size"),
                entry_time=row.get("entry_time"),
                exit_time=row.get("exit_time"),
                market_db_path=mpath,
            )
        out.append(
            {
                "market_event_id": str(row.get("market_event_id") or ""),
                "side": str(row.get("side") or "").strip().lower(),
                "symbol": sym or None,
                "timeframe": tf or None,
                "time_utc_iso": t_iso or "",
                "outcome": _strip_outcome_from_pnl(pnl),
                "pnl_usd": float(pnl) if pnl is not None else None,
                "entry": float(ep) if ep is not None else None,
                "exit": float(xp) if xp is not None else None,
                "size": float(row["size"]) if row.get("size") is not None else None,
                "exit_reason": str(row.get("exit_reason") or "").strip() or None,
                "trade_id": str(row.get("trade_id") or "").strip() or None,
                "mae_usd": round(mae_val, 6) if mae_val is not None else None,
            }
        )
    return out


def _recent_baseline_policy_trade_rows_for_strip(
    conn: sqlite3.Connection,
    *,
    limit: int = 3,
    scan_cap: int = 400,
    market_db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Newest-first baseline executions that are **policy TRADE** (``policy_approved_execution``).

    Scans up to ``scan_cap`` recent ledger rows until ``limit`` authoritative trades are found.
    Matches the baseline report when scoped to **trade** only — unlike raw ledger strips.
    """
    lim = max(1, min(10, int(limit)))
    cap = max(lim, min(2000, int(scan_cap)))
    mpath = market_db_path
    cur = conn.execute(
        """
        SELECT market_event_id, side, symbol, timeframe, entry_time, entry_price, exit_price,
               exit_reason, exit_time, size, pnl_usd, created_at_utc, trade_id, mode
        FROM execution_trades
        WHERE lane = 'baseline' AND strategy_id = ?
        ORDER BY COALESCE(created_at_utc, entry_time, '') DESC, trade_id DESC
        LIMIT ?
        """,
        (RESERVED_STRATEGY_BASELINE, cap),
    )
    cols = [d[0] for d in cur.description]
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        ledger_row = dict(zip(cols, r))
        mid = str(ledger_row.get("market_event_id") or "").strip()
        if not mid:
            continue
        cell = _compact_baseline_cell_policy_bound(
            conn, mid, ledger_row, market_db_path=mpath
        )
        if str(cell.get("baseline_display_reason") or "") != "policy_approved_execution":
            continue
        t = ledger_row.get("entry_time") or ledger_row.get("created_at_utc")
        t_iso = _normalize_utc_iso_for_axis(t) if t else None
        pnl = ledger_row.get("pnl_usd")
        ep = ledger_row.get("entry_price")
        xp = ledger_row.get("exit_price")
        sym = str(ledger_row.get("symbol") or "").strip()
        tf = str(ledger_row.get("timeframe") or "").strip()
        mae_val: float | None = None
        if sym and mpath and mpath.is_file():
            mae_val, _ = compute_mae_usd_v1(
                canonical_symbol=sym,
                side=ledger_row.get("side"),
                entry_price=ledger_row.get("entry_price"),
                size=ledger_row.get("size"),
                entry_time=ledger_row.get("entry_time"),
                exit_time=ledger_row.get("exit_time"),
                market_db_path=mpath,
            )
        out.append(
            {
                "market_event_id": mid,
                "side": str(ledger_row.get("side") or "").strip().lower(),
                "symbol": sym or None,
                "timeframe": tf or None,
                "mode": str(ledger_row.get("mode") or "").strip() or None,
                "time_utc_iso": t_iso or "",
                "outcome": _strip_outcome_from_pnl(pnl),
                "pnl_usd": float(pnl) if pnl is not None else None,
                "entry": float(ep) if ep is not None else None,
                "exit": float(xp) if xp is not None else None,
                "size": float(ledger_row["size"]) if ledger_row.get("size") is not None else None,
                "exit_reason": str(ledger_row.get("exit_reason") or "").strip() or None,
                "trade_id": str(ledger_row.get("trade_id") or "").strip() or None,
                "mae_usd": round(mae_val, 6) if mae_val is not None else None,
                "baseline_authority": "TRADE",
            }
        )
        if len(out) >= lim:
            break
    return out


BASELINE_TRADES_REPORT_SCHEMA = "blackbox_baseline_trades_report_v1"


def build_baseline_trades_report(
    *,
    db_path: Path | None = None,
    market_db_path: Path | None = None,
    from_utc_iso: str | None = None,
    to_utc_iso: str | None = None,
    limit: int = 50,
    scope: str = "all",
    max_scan: int = 20000,
) -> dict[str, Any]:
    """
    Filtered baseline ledger report with policy-authoritative **TRADE** vs **NO_TRADE** per row.

    ``scope``: ``all`` | ``trade`` | ``no_trade`` — filters rows after policy classification.

    Time window uses ``COALESCE(entry_time, created_at_utc)`` compared in UTC. Rows without a
    parseable timestamp are excluded when any bound is set.
    """
    db_path = db_path or default_execution_ledger_path()
    mpath = market_db_path if market_db_path is not None else _market_db_path()
    lim = max(1, min(500, int(limit)))
    scan_cap = max(100, min(100000, int(max_scan)))
    sc = str(scope or "all").strip().lower()
    if sc not in ("all", "trade", "no_trade"):
        sc = "all"

    from_dt = _parse_iso_ts(from_utc_iso) if (from_utc_iso and str(from_utc_iso).strip()) else None
    to_dt = _parse_iso_ts(to_utc_iso) if (to_utc_iso and str(to_utc_iso).strip()) else None
    if from_dt and to_dt and from_dt > to_dt:
        from_dt, to_dt = to_dt, from_dt

    def _utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    conn = connect_ledger(db_path)
    rows_out: list[dict[str, Any]] = []
    scanned = 0
    try:
        ensure_execution_ledger_schema(conn)
        # When a time window is set, scan enough history that older days are not cut off by
        # "newest first" limits; cap total fetch for safety.
        wide_history = bool(from_dt or to_dt)
        fetch_limit = 500000 if wide_history else scan_cap
        cur = conn.execute(
            """
            SELECT market_event_id, side, symbol, timeframe, entry_time, entry_price, exit_price,
                   exit_reason, exit_time, size, pnl_usd, created_at_utc, trade_id, mode
            FROM execution_trades
            WHERE lane = 'baseline' AND strategy_id = ?
            ORDER BY COALESCE(created_at_utc, entry_time, '') DESC
            LIMIT ?
            """,
            (RESERVED_STRATEGY_BASELINE, fetch_limit),
        )
        cols = [d[0] for d in cur.description]
        candidates: list[tuple[datetime, dict[str, Any]]] = []
        for r in cur.fetchall():
            scanned += 1
            row = dict(zip(cols, r))
            raw_t = row.get("entry_time") or row.get("created_at_utc")
            ts = _parse_iso_ts(str(raw_t) if raw_t is not None else None)
            if ts is not None:
                ts = ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            if from_dt or to_dt:
                if ts is None:
                    continue
                tsu = _utc(ts)
                if from_dt and tsu < _utc(from_dt):
                    continue
                if to_dt and tsu > _utc(to_dt):
                    continue
            candidates.append((ts or datetime(1970, 1, 1, tzinfo=timezone.utc), row))

        candidates.sort(key=lambda x: x[0], reverse=True)

        mids_for_tiles: list[str] = []
        for _ts, ledger_row in candidates:
            mid = str(ledger_row.get("market_event_id") or "").strip()
            cell = _compact_baseline_cell_policy_bound(
                conn, mid, ledger_row, market_db_path=mpath
            )
            reason = str(cell.get("baseline_display_reason") or "")
            is_trade = reason == "policy_approved_execution"
            authority = "TRADE" if is_trade else "NO_TRADE"
            if sc == "trade" and authority != "TRADE":
                continue
            if sc == "no_trade" and authority != "NO_TRADE":
                continue

            sym = str(ledger_row.get("symbol") or "").strip()
            tf = str(ledger_row.get("timeframe") or "").strip()
            t_iso = _normalize_utc_iso_for_axis(
                ledger_row.get("entry_time") or ledger_row.get("created_at_utc")
            )
            pnl = ledger_row.get("pnl_usd")
            ep = ledger_row.get("entry_price")
            xp = ledger_row.get("exit_price")
            mae_val: float | None = None
            if sym and mpath and mpath.is_file():
                mae_val, _ = compute_mae_usd_v1(
                    canonical_symbol=sym,
                    side=ledger_row.get("side"),
                    entry_price=ledger_row.get("entry_price"),
                    size=ledger_row.get("size"),
                    entry_time=ledger_row.get("entry_time"),
                    exit_time=ledger_row.get("exit_time"),
                    market_db_path=mpath,
                )

            rows_out.append(
                {
                    "market_event_id": mid,
                    "side": str(ledger_row.get("side") or "").strip().lower(),
                    "symbol": sym or None,
                    "timeframe": tf or None,
                    "mode": str(ledger_row.get("mode") or "").strip() or None,
                    "time_utc_iso": t_iso or "",
                    "outcome": _strip_outcome_from_pnl(pnl),
                    "pnl_usd": float(pnl) if pnl is not None else None,
                    "entry": float(ep) if ep is not None else None,
                    "exit": float(xp) if xp is not None else None,
                    "size": float(ledger_row["size"]) if ledger_row.get("size") is not None else None,
                    "exit_reason": str(ledger_row.get("exit_reason") or "").strip() or None,
                    "trade_id": str(ledger_row.get("trade_id") or "").strip() or None,
                    "mae_usd": round(mae_val, 6) if mae_val is not None else None,
                    "baseline_authority": authority,
                    "baseline_authority_reason": reason,
                    "policy_outcome_display": str(cell.get("outcome_display") or ""),
                    "policy_outcome": str(cell.get("outcome") or ""),
                }
            )
            mids_for_tiles.append(mid)
            if len(rows_out) >= lim:
                break

        tile_narr: dict[str, str] = {}
        if mids_for_tiles:
            tile_narr = _event_axis_jupiter_tile_narratives(conn, mids_for_tiles, mpath)
        for r in rows_out:
            mk = str(r.get("market_event_id") or "").strip()
            r["jupiter_tile_narrative"] = tile_narr.get(mk, "") if mk else ""
    finally:
        conn.close()

    return {
        "schema": BASELINE_TRADES_REPORT_SCHEMA,
        "rows": rows_out,
        "meta": {
            "from_utc_iso": from_utc_iso,
            "to_utc_iso": to_utc_iso,
            "limit": lim,
            "scope": sc,
            "scanned_execution_rows": scanned,
            "max_scan_cap": scan_cap,
            "ledger_path": str(db_path),
        },
    }


def _normalize_utc_iso_for_axis(ts: Any) -> str | None:
    """Normalize ledger timestamp to UTC ISO for browser (canonical column instant)."""
    if ts is None:
        return None
    s = str(ts).strip()
    if not s:
        return None
    dt = _parse_iso_ts(s)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _distinct_event_axis_with_times(conn: Any, *, limit: int) -> tuple[list[str], list[str | None]]:
    """Distinct market_event_ids (oldest→newest) with parallel UTC instants from MAX(created_at_utc)."""
    lim = max(4, min(48, int(limit)))
    cur = conn.execute(
        """
        SELECT market_event_id, MAX(created_at_utc) AS mx
        FROM execution_trades
        GROUP BY market_event_id
        ORDER BY mx DESC
        LIMIT ?
        """,
        (lim,),
    )
    rows = list(reversed(cur.fetchall()))
    mids: list[str] = []
    times: list[str | None] = []
    for r in rows:
        if not r or not r[0]:
            continue
        mids.append(str(r[0]))
        times.append(_normalize_utc_iso_for_axis(r[1]))
    return mids, times


def _event_axis_from_market_bars(mpath: Path | None, *, limit: int) -> tuple[list[str], list[str | None]]:
    """Recent closed 5m bars (oldest→newest) — preferred column axis for policy-aligned dashboard."""
    if not mpath or not mpath.is_file():
        return [], []
    lim = max(4, min(48, int(limit)))
    conn = sqlite3.connect(str(mpath))
    try:
        cur = conn.execute(
            """
            SELECT market_event_id, candle_open_utc
            FROM market_bars_5m
            WHERE timeframe = '5m'
            ORDER BY candle_open_utc DESC
            LIMIT ?
            """,
            (lim,),
        )
        rows = list(reversed(cur.fetchall()))
    except Exception:
        return [], []
    finally:
        conn.close()
    mids: list[str] = []
    times: list[str | None] = []
    for r in rows:
        if not r or not r[0]:
            continue
        mids.append(str(r[0]))
        times.append(_normalize_utc_iso_for_axis(r[1]))
    return mids, times


def _baseline_policy_no_trade_cell(
    *,
    market_event_id: str,
    policy_row: dict[str, Any] | None,
    ledger_row: dict[str, Any] | None,
    reason: str,
) -> dict[str, Any]:
    """Baseline display when policy forbids or omits a trade — execution_trades must not imply WIN/LOSS."""
    return {
        "empty": True,
        "market_event_id": market_event_id,
        "trade_id": None,
        "trace_id": None,
        "symbol": None,
        "timeframe": None,
        "side": None,
        "exit_reason": None,
        "entry": None,
        "exit": None,
        "entry_time": None,
        "exit_time": None,
        "size": None,
        "notional_usd_approx": None,
        "pnl_usd": None,
        "mae_usd": None,
        "outcome": "NO_TRADE",
        "outcome_display": "no trade",
        "economic_authority": "policy_gated",
        "mode": None,
        "policy_authoritative": True,
        "policy_trade": (bool(policy_row.get("trade")) if policy_row is not None else None),
        "policy_reason_code": (str(policy_row.get("reason_code") or "") if policy_row else None),
        "policy_missing": policy_row is None,
        "ledger_row_ignored": ledger_row is not None,
        "baseline_display_reason": reason,
    }


def _compact_baseline_cell_policy_bound(
    conn: Any,
    market_event_id: str,
    ledger_row: dict[str, Any] | None,
    *,
    market_db_path: Path | None,
) -> dict[str, Any]:
    """
    Baseline WIN/LOSS only when ``policy_evaluations`` (Sean Jupiter) has ``trade=1`` and a matching ledger row.
    Missing policy, ``trade=0``, or missing execution all render NO_TRADE (ledger artifacts are non-authoritative).
    """
    pol = fetch_policy_evaluation_for_market_event(
        conn,
        market_event_id,
        lane=RESERVED_STRATEGY_BASELINE,
        strategy_id=RESERVED_STRATEGY_BASELINE,
        signal_mode="sean_jupiter_v1",
    )
    mid = str(market_event_id).strip()
    if pol is None:
        return _baseline_policy_no_trade_cell(
            market_event_id=mid,
            policy_row=None,
            ledger_row=ledger_row,
            reason="policy_missing",
        )
    if not pol.get("trade"):
        return _baseline_policy_no_trade_cell(
            market_event_id=mid,
            policy_row=pol,
            ledger_row=ledger_row,
            reason="policy_trade_false",
        )
    if not ledger_row:
        return _baseline_policy_no_trade_cell(
            market_event_id=mid,
            policy_row=pol,
            ledger_row=None,
            reason="execution_missing",
        )
    cell = _compact_cell(ledger_row, market_db_path=market_db_path, chain_kind="baseline")
    cell["policy_authoritative"] = True
    cell["policy_trade"] = True
    cell["policy_reason_code"] = pol.get("reason_code")
    cell["policy_missing"] = False
    cell["ledger_row_ignored"] = False
    cell["baseline_display_reason"] = "policy_approved_execution"
    cell["economic_authority"] = "full"
    return cell


def _ledger_has_live_anna(conn: Any) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM execution_trades
        WHERE lane = 'anna' AND mode = 'live' LIMIT 1
        """
    ).fetchone()
    return bool(row)


def _ledger_lane_mode_summary(conn: Any) -> dict[str, Any]:
    """Baseline / Anna execution modes observed in ledger (capital-risk display)."""
    baseline_modes: list[str] = []
    anna_modes: list[str] = []
    try:
        cur = conn.execute(
            "SELECT DISTINCT mode FROM execution_trades WHERE lane = 'baseline' ORDER BY mode"
        )
        baseline_modes = [str(r[0]) for r in cur.fetchall() if r and r[0]]
    except Exception:
        pass
    try:
        cur = conn.execute(
            "SELECT DISTINCT mode FROM execution_trades WHERE lane = 'anna' ORDER BY mode"
        )
        anna_modes = [str(r[0]) for r in cur.fetchall() if r and r[0]]
    except Exception:
        pass

    def _disp(modes: list[str], lane: str) -> str:
        if not modes:
            return "paper_only" if lane == "anna" else "none"
        economic = [m for m in modes if m in ("live", "paper")]
        if lane == "baseline":
            if "live" in economic and "paper" in economic:
                return "mixed"
            if "live" in economic:
                return "live"
            if "paper" in economic:
                return "paper"
            return "stub" if "paper_stub" in modes else "mixed"
        # anna
        if "live" in economic:
            return "live_present"
        return "paper_only"

    return {
        "baseline_modes_observed": baseline_modes,
        "anna_modes_observed": anna_modes,
        "baseline_display": _disp(baseline_modes, "baseline"),
        "anna_display": _disp(anna_modes, "anna"),
    }


def _compact_last_decision(row: dict[str, Any] | None) -> str:
    if not row:
        return "—"
    for k in ("decision", "sprt_decision", "outcome", "status", "reason_code"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()[:100]
    tid = row.get("test_id") or row.get("strategy_id")
    if tid:
        return str(tid)[:80]
    return str(row)[:100]


def _strategy_buckets(conn: Any) -> tuple[list[str], list[str], str | None]:
    """
    Returns (test_strategy_ids, strategy_row_ids, note).
    Test = lifecycle in {test, experiment} OR listed in active survival tests.
    Strategy row = candidate / validated / promotion_ready / promoted.
    """
    survival: set[str] = set()
    try:
        cur = conn.execute(
            "SELECT strategy_id FROM anna_survival_tests WHERE status = 'active'"
        )
        survival = {str(r[0]) for r in cur.fetchall() if r and r[0]}
    except Exception:
        pass

    test_lc = frozenset({LIFECYCLE_TEST, LIFECYCLE_EXPERIMENT})
    strat_lc = frozenset(
        {
            LIFECYCLE_CANDIDATE,
            LIFECYCLE_VALIDATED_STRATEGY,
            LIFECYCLE_PROMOTION_READY,
            LIFECYCLE_PROMOTED,
        }
    )

    tests: list[str] = []
    strats: list[str] = []
    try:
        cur = conn.execute(
            """
            SELECT strategy_id, lifecycle_state FROM strategy_registry
            WHERE strategy_id != ?
            ORDER BY strategy_id ASC
            """,
            (RESERVED_STRATEGY_BASELINE,),
        )
        for sid, lc in cur.fetchall():
            s = str(sid).strip()
            lc_s = str(lc or LIFECYCLE_EXPERIMENT)
            if s in survival or lc_s in test_lc:
                tests.append(s)
            elif lc_s in strat_lc:
                strats.append(s)
    except Exception:
        pass

    tests = sorted(set(tests))[:4]
    strats = sorted(set(strats))[:4]
    note = None
    if not tests and not strats:
        note = "No Anna strategies in registry with test/strategy lifecycles — baseline row only until strategies are registered."
    return tests, strats, note


def _lifecycle_by_strategy(conn: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        cur = conn.execute(
            """
            SELECT strategy_id, COALESCE(lifecycle_state, '') FROM strategy_registry
            WHERE strategy_id != ?
            """,
            (RESERVED_STRATEGY_BASELINE,),
        )
        for sid, lc in cur.fetchall():
            if sid:
                out[str(sid).strip()] = str(lc or "").strip()
    except Exception:
        pass
    return out


def _build_trade_chain_scorecard(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-row WIN / NOT_WIN / EXCLUDED counts for the current event window (from cell vs_baseline)."""
    out: list[dict[str, Any]] = []
    for r in rows:
        ck = str(r.get("chain_kind") or "")
        sid = str(r.get("strategy_id") or "")
        if ck == "baseline":
            out.append(
                {
                    "chain_kind": "baseline",
                    "strategy_id": sid,
                    "row_label": str(r.get("label") or ""),
                    "vs_baseline_wins": None,
                    "vs_baseline_not_wins": None,
                    "vs_baseline_excluded": None,
                    "events_with_comparison": None,
                }
            )
            continue
        cells = r.get("cells") or {}
        wins = not_wins = exc = 0
        if isinstance(cells, dict):
            for _mid, c in cells.items():
                if not isinstance(c, dict):
                    continue
                vs = c.get("vs_baseline")
                if vs == "WIN":
                    wins += 1
                elif vs == "NOT_WIN":
                    not_wins += 1
                elif vs == "EXCLUDED":
                    exc += 1
        n = wins + not_wins + exc
        out.append(
            {
                "chain_kind": ck,
                "strategy_id": sid,
                "row_label": str(r.get("label") or ""),
                "lifecycle_label": str(r.get("lifecycle_label") or ""),
                "vs_baseline_wins": wins,
                "vs_baseline_not_wins": not_wins,
                "vs_baseline_excluded": exc,
                "events_with_comparison": n,
            }
        )
    return out


def _anna_vs_baseline_aggregate(scorecard: list[dict[str, Any]]) -> dict[str, int]:
    w = nw = exc = 0
    for r in scorecard:
        if str(r.get("chain_kind") or "") == "baseline":
            continue
        try:
            w += int(r.get("vs_baseline_wins") or 0)
        except (TypeError, ValueError):
            pass
        try:
            nw += int(r.get("vs_baseline_not_wins") or 0)
        except (TypeError, ValueError):
            pass
        try:
            exc += int(r.get("vs_baseline_excluded") or 0)
        except (TypeError, ValueError):
            pass
    return {"wins": w, "not_wins": nw, "excluded": exc}


def build_trade_chain_payload(
    *,
    db_path: Path | None = None,
    max_events: int = 24,
    market_db_path: Path | None = None,
) -> dict[str, Any]:
    """Horizontal chains × vertical event axis; baseline column is policy-authoritative (policy_evaluations)."""
    db_path = db_path or default_execution_ledger_path()
    mpath = market_db_path if market_db_path is not None else _market_db_path()

    pair_eps = 0.05
    recent_strip: list[dict[str, Any]] = []
    baseline_trades_report_rows: list[dict[str, Any]] = []
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        event_axis, event_axis_time_utc_iso = _event_axis_from_market_bars(mpath, limit=max_events)
        event_axis_source = "market_bars_5m"
        if not event_axis:
            event_axis, event_axis_time_utc_iso = _distinct_event_axis_with_times(conn, limit=max_events)
            event_axis_source = "execution_trades_fallback"
        tile_narr = _event_axis_jupiter_tile_narratives(conn, event_axis, mpath)
        baseline_ledger = _recent_baseline_trades_for_dashboard_strip(
            conn, limit=50, market_db_path=mpath
        )
        recent_strip = _recent_baseline_policy_trade_rows_for_strip(
            conn, limit=3, market_db_path=mpath
        )
        for rs in recent_strip:
            mid_rs = str(rs.get("market_event_id") or "").strip()
            rs["jupiter_tile_narrative"] = tile_narr.get(mid_rs, "") if mid_rs else ""
        for br in baseline_ledger:
            mid_k = str(br.get("market_event_id") or "").strip()
            br["jupiter_tile_narrative"] = tile_narr.get(mid_k, "") if mid_k else ""
        baseline_trades_report_rows = baseline_ledger
        tests, strats, note = _strategy_buckets(conn)
        lc_map = _lifecycle_by_strategy(conn)
        primary_sym = _latest_symbol_from_ledger(conn)
        market_clock = _market_clock_for_symbol(primary_sym)

        row_defs: list[dict[str, Any]] = [
            {
                "chain_kind": "baseline",
                "label": "Baseline",
                "lane": "baseline",
                "strategy_id": RESERVED_STRATEGY_BASELINE,
                "lifecycle_state": None,
                "lifecycle_label": "Economic anchor",
                "row_tier": "primary",
                "accent_slot": None,
                "account_note": (
                    "Baseline display is policy-authoritative: WIN/LOSS only when policy_evaluations "
                    "(Sean Jupiter) approves a trade and a matching execution row exists; otherwise NO TRADE."
                ),
            }
        ]
        for sid in tests:
            lc = lc_map.get(sid, "")
            row_defs.append(
                {
                    "chain_kind": "anna_test",
                    "label": f"Anna · {sid}",
                    "lane": "anna",
                    "strategy_id": sid,
                    "lifecycle_state": lc or None,
                    "lifecycle_label": _lifecycle_short_label(lc),
                    "row_tier": "secondary_test",
                    "accent_slot": _anna_row_accent_slot(sid),
                    "account_note": "Test / experiment / survival — secondary to baseline.",
                }
            )
        for sid in strats:
            lc = lc_map.get(sid, "")
            row_defs.append(
                {
                    "chain_kind": "anna_strategy",
                    "label": f"Anna · {sid}",
                    "lane": "anna",
                    "strategy_id": sid,
                    "lifecycle_state": lc or None,
                    "lifecycle_label": _lifecycle_short_label(lc),
                    "row_tier": "secondary_strategy",
                    "accent_slot": _anna_row_accent_slot(sid),
                    "account_note": "Strategy maturity lane — secondary to baseline.",
                }
            )

        rows_out: list[dict[str, Any]] = []
        for rd in row_defs:
            cells: dict[str, Any] = {}
            ck = str(rd.get("chain_kind") or "baseline")
            for mid in event_axis:
                tr = _fetch_trade(conn, mid, lane=rd["lane"], strategy_id=rd["strategy_id"])
                if ck == "baseline":
                    cells[mid] = _compact_baseline_cell_policy_bound(
                        conn, mid, tr, market_db_path=mpath
                    )
                else:
                    cells[mid] = _compact_cell(tr, market_db_path=mpath, chain_kind=ck)
            rows_out.append(
                {
                    **rd,
                    "cells": cells,
                }
            )

        pair_eps = 0.05
        try:
            pair_eps = float(str(os.environ.get("BLACKBOX_PAIR_DISPLAY_EPSILON", "0.05")).strip() or "0.05")
        except (TypeError, ValueError):
            pair_eps = 0.05
        bi = next((i for i, r in enumerate(rows_out) if r.get("chain_kind") == "baseline"), None)
        if bi is not None and event_axis:
            bcells = rows_out[bi]["cells"]
            for r in rows_out:
                ck = str(r.get("chain_kind") or "")
                if ck not in ("anna_test", "anna_strategy"):
                    continue
                for mid in event_axis:
                    ac = dict(r["cells"].get(mid) or {})
                    pair = _pair_vs_baseline_for_cells(
                        bcells.get(mid) or {},
                        ac,
                        epsilon=pair_eps,
                    )
                    r["cells"][mid] = {**ac, **pair}
        for r in rows_out:
            for mid in event_axis:
                d = dict(r["cells"].get(mid) or {})
                d["jupiter_tile_narrative"] = tile_narr.get(str(mid).strip(), "")
                r["cells"][mid] = d
    finally:
        conn.close()

    scorecard = _build_trade_chain_scorecard(rows_out)
    anna_agg = _anna_vs_baseline_aggregate(scorecard)

    return {
        "schema": "blackbox_trade_chain_v1",
        "ledger_path": str(db_path),
        "market_db_path": str(mpath) if mpath else None,
        "event_axis": event_axis,
        "event_axis_time_utc_iso": event_axis_time_utc_iso,
        "event_axis_source": event_axis_source,
        "event_axis_note": (
            "Columns are distinct market_event_id values (oldest left → newest right). "
            "Axis prefers recent rows from market_bars_5m when available; else execution_trades. "
            "Baseline WIN/LOSS is bound to policy_evaluations (Sean Jupiter), not ledger row presence alone."
        ),
        "jupiter_tile_narrative_schema": "jupiter_tile_narrative_v1",
        "recency": {
            "axis_order": "oldest_left_newest_right",
            "newest_market_event_id": event_axis[-1] if event_axis else None,
        },
        "market_clock": market_clock,
        "strategy_selection_note": note,
        "visual_hierarchy_note": (
            "Chain identity is lane + strategy_id (chips on the left). "
            "Anna cells show vs baseline WIN / NOT WIN / n/a when baseline is paper/live and Anna has PnL+MAE; "
            "Anna may be paper_stub and still pair for display when those numbers exist. "
            "MAE gate uses epsilon="
            + str(round(pair_eps, 6))
            + " (env BLACKBOX_PAIR_DISPLAY_EPSILON)."
        ),
        "paired_comparison_epsilon": round(pair_eps, 6),
        "scorecard": scorecard,
        "anna_vs_baseline_aggregate": anna_agg,
        "rows": rows_out,
        "recent_baseline_trades": recent_strip,
        "baseline_trades_report_rows": baseline_trades_report_rows,
    }


def _wallet_subset(full: dict[str, Any] | None) -> dict[str, Any]:
    if not full:
        return {
            "wallet_configured": False,
            "wallet_connected": False,
            "solana_rpc_ok": False,
            "detail": "wallet_unavailable",
        }
    sig = full.get("signing_proof")
    wc = bool(full.get("wallet_connected"))
    addr = str(full.get("public_address") or "").strip()
    # Operator “configured” = keypair+pubkey path succeeded or we still expose an address (identity on file).
    # Distinct from ``solana_rpc_ok`` (live RPC read) — see dashboard banner vs RPC column.
    wallet_configured = wc or bool(addr)
    return {
        "wallet_configured": wallet_configured,
        "wallet_connected": wc,
        "public_address": full.get("public_address"),
        "balance_sol": full.get("balance_sol"),
        "balance_usd_approx": full.get("balance_usd_approx"),
        "solana_rpc_ok": bool((full.get("solana_rpc") or {}).get("ok")),
        "jupiter_quote_ok": bool((full.get("jupiter_quote_sample") or {}).get("ok")),
        "live_trading_blocked": bool(full.get("live_trading_blocked")),
        "signing_ok": bool(isinstance(sig, dict) and sig.get("ok")),
    }


def _system_mode_label(
    *,
    wallet: dict[str, Any] | None,
    ledger_has_live_anna: bool,
) -> dict[str, Any]:
    blocked = bool((wallet or {}).get("live_trading_blocked"))
    if blocked:
        return {
            "label": "PAPER",
            "reason": "Live trading blocked by policy until governance and wallet/Jupiter proof are satisfied.",
        }
    if ledger_has_live_anna:
        return {
            "label": "LIVE",
            "reason": "Execution ledger contains Anna lane rows with mode=live.",
        }
    return {
        "label": "PAPER",
        "reason": "No live Anna ledger rows; operational default is paper.",
    }


def build_dashboard_bundle(
    *,
    db_path: Path | None = None,
    max_events: int = 24,
) -> dict[str, Any]:
    """Single JSON for /api/v1/dashboard/bundle — operator surface."""
    tid = uuid.uuid4().hex
    db_path = db_path or default_execution_ledger_path()

    wallet_full: dict[str, Any] | None = None
    try:
        from modules.wallet import build_wallet_status_payload

        wallet_full = build_wallet_status_payload()
    except Exception:
        wallet_full = None

    wallet = _wallet_subset(wallet_full)

    try:
        from modules.anna_training.sequential_engine.ui_control import build_operator_status

        seq = build_operator_status()
    except Exception as e:
        seq = {"schema": "sequential_operator_status_v1", "ui_state": "unknown", "detail": str(e)[:200]}

    ledger_live = False
    capital_modes: dict[str, Any] = {
        "baseline_modes_observed": [],
        "anna_modes_observed": [],
        "baseline_display": "none",
        "anna_display": "paper_only",
    }
    try:
        conn = connect_ledger(db_path)
        try:
            ensure_execution_ledger_schema(conn)
            ledger_live = _ledger_has_live_anna(conn)
            capital_modes = _ledger_lane_mode_summary(conn)
        finally:
            conn.close()
    except Exception:
        pass

    mode = _system_mode_label(wallet=wallet_full, ledger_has_live_anna=ledger_live)

    tc = build_trade_chain_payload(db_path=db_path, max_events=max_events)

    operator_trading: dict[str, Any] = {}
    try:
        from modules.anna_training.operator_trading_strategy import build_operator_trading_bundle_part

        operator_trading = build_operator_trading_bundle_part(db_path)
    except Exception:
        operator_trading = {
            "schema": "operator_trading_strategy_v1",
            "designated_strategy_id": None,
            "cookie_jar": [],
            "eligible_strategy_ids": [],
            "default_system_strategy_id": RESERVED_STRATEGY_BASELINE,
        }

    ui_state = str((seq or {}).get("ui_state") or "idle")
    ev_rem = 0
    try:
        total = int((seq or {}).get("events_total_lines") or 0)
        cur = int((seq or {}).get("events_cursor_line") or 0)
        ev_rem = max(0, total - cur)
    except (TypeError, ValueError):
        pass

    learning_active = ui_state == "running"
    tick_banner = None
    if ui_state == "running" and ev_rem > 0:
        tick_banner = (
            f"Sequential learning advances via batch ticks (~every {SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT}s "
            "when the `sequential-tick` sidecar is running) or manual Tick / POST tick."
        )
    elif ui_state == "running" and ev_rem == 0:
        tick_banner = "Running — event queue empty (end of file or cursor at end)."

    now_utc = datetime.now(timezone.utc)
    pyth_snap = _pyth_probe_snapshot(_REPO_ROOT)
    try:
        from modules.anna_training.readiness import check_pyth_sse_tape

        pyth_sse_tape = check_pyth_sse_tape(_REPO_ROOT)
    except Exception:
        pyth_sse_tape = {"ok": False, "reason": "check_failed"}
    sse_ticks_5m = _count_pyth_sse_ticks_since_minutes(5.0)
    tick_stale = _sequential_tick_staleness(
        ui_state=ui_state,
        events_remaining=ev_rem,
        last_tick_at=str((seq or {}).get("last_tick_at") or "") or None,
        now=now_utc,
    )
    next_tick = compute_next_tick_eta(
        ui_state=ui_state,
        events_remaining=ev_rem,
        last_tick_at=str((seq or {}).get("last_tick_at") or "") or None,
    )
    snap_iso = now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    liveness: dict[str, Any] = {
        "bundle_snapshot_at": snap_iso,
        "bundle_generated_at_utc": snap_iso,
        "methodology_one_liner": (
            "Dashboard: REST poll of aggregated bundle; sequential: discrete batch ticks over a cursor; "
            "market: Hermes SSE → SQLite tape (pyth-sse-ingest) + probe JSON — not an exchange order-book stream."
        ),
        "update_model": {
            "dashboard_ui": "poll_driven",
            "dashboard_poll_interval_ms": DASHBOARD_CLIENT_POLL_INTERVAL_MS,
            "bundle_source": "GET /api/v1/dashboard/bundle (server builds snapshot each request)",
            "sequential_engine": "tick_driven_batch",
            "sequential_tick_interval_sec_expected": SEQUENTIAL_TICK_SIDECAR_INTERVAL_SEC_DEFAULT,
            "market_price_probe": "pyth_stream_probe SQLite market_ticks (no Hermes HTTP)",
            "pyth_probe_interval_sec_default": PYTH_STREAM_PROBE_INTERVAL_SEC_DEFAULT,
        },
        "operator_signals": {
            "sequential_events_processed_total": (seq or {}).get("events_processed_total"),
            "sequential_events_remaining_in_queue": ev_rem,
            "sequential_last_tick_at": (seq or {}).get("last_tick_at"),
            "last_processed_market_event_id": (seq or {}).get("last_processed_market_event_id"),
            "pyth_status": pyth_snap.get("status"),
            "pyth_last_event_at": pyth_snap.get("last_event_at"),
            "pyth_age_seconds": pyth_snap.get("age_seconds"),
            "pyth_sse_tape_ok": bool((pyth_sse_tape or {}).get("ok")),
            "pyth_sse_age_seconds": (pyth_sse_tape or {}).get("age_seconds"),
            "pyth_sse_total_ticks": (pyth_sse_tape or {}).get("sse_tick_count"),
            "pyth_sse_ticks_5m": sse_ticks_5m,
            "pyth_sse_last_inserted_at": (pyth_sse_tape or {}).get("last_sse_inserted_at"),
            "tick_staleness": tick_stale,
        },
        "next_tick": next_tick,
        "not_exchange_tick_stream": (
            "This dashboard is not a live order-book or millisecond tape. "
            "Liveness is: (1) bundle timestamp advancing every poll, (2) sequential last_tick_at advancing while queue>0, "
            "(3) Pyth probe age staying bounded, (4) STALLED label if ticks stop while queue remains."
        ),
    }

    last_dec = (seq or {}).get("last_decision_row")
    last_dec_s = None
    if isinstance(last_dec, dict):
        last_dec_s = json.dumps(last_dec, default=str)[:800]
    elif last_dec is not None:
        last_dec_s = str(last_dec)[:800]
    last_dec_banner = _compact_last_decision(last_dec if isinstance(last_dec, dict) else None)

    sprt = (seq or {}).get("last_sprt_decision")
    if sprt is None and isinstance((seq or {}).get("last_tick_summary"), dict):
        sprt = ((seq or {}).get("last_tick_summary") or {}).get("last_sprt")

    live_policy_blocked = bool(wallet.get("live_trading_blocked"))

    mc = tc.get("market_clock") if isinstance(tc, dict) else None
    paper_cap: dict[str, Any] | None = None
    training_st: dict[str, Any] | None = None
    try:
        from modules.anna_training.paper_capital import build_paper_capital_summary
        from modules.anna_training.store import load_state

        training_st = load_state()
        paper_cap = build_paper_capital_summary(training_state=training_st, ledger_db_path=db_path)
    except Exception:
        paper_cap = None

    jupiter_policy_snapshot: dict[str, Any] = {}
    try:
        jupiter_policy_snapshot = build_jupiter_policy_snapshot(
            market_db_path=None,
            training_state=training_st,
        )
    except Exception as e:
        jupiter_policy_snapshot = {
            "schema": "jupiter_policy_snapshot_v1",
            "error": str(e)[:400],
        }

    learning_summary_for_vis: dict[str, Any] = {
        "ui_state": ui_state,
        "learning_active": learning_active,
        "events_remaining_in_queue": ev_rem,
        "last_processed_market_event_id": (seq or {}).get("last_processed_market_event_id"),
        "last_tick_at": (seq or {}).get("last_tick_at"),
        "last_error": (seq or {}).get("last_error"),
        "sprt_or_compact": sprt,
        "last_decision_compact": last_dec_s,
        "tick_ux_banner": tick_banner,
        "tick_required": ui_state == "running" and ev_rem > 0,
        "events_processed_total": (seq or {}).get("events_processed_total"),
    }

    intelligence_visibility: dict[str, Any] | None = None
    try:
        from modules.anna_training.intelligence_visibility import build_intelligence_visibility

        llm_pf = (training_st or {}).get("karpathy_last_llm_preflight")
        if not isinstance(llm_pf, dict):
            llm_pf = {}
        mdb_s = str((tc.get("market_db_path") or "") or "").strip() or None
        intelligence_visibility = build_intelligence_visibility(
            repo_root=_REPO_ROOT,
            seq=seq if isinstance(seq, dict) else {},
            trade_chain=tc if isinstance(tc, dict) else {},
            operator_trading=operator_trading if isinstance(operator_trading, dict) else {},
            learning_summary=learning_summary_for_vis,
            pyth_snapshot=pyth_snap if isinstance(pyth_snap, dict) else {},
            market_db_path=mdb_s,
            training_state=training_st if isinstance(training_st, dict) else {},
            llm_preflight_from_state=llm_pf,
        )
    except Exception as e:
        intelligence_visibility = {
            "schema": "anna_intelligence_visibility_v1",
            "error": str(e)[:400],
        }

    learning_proof: dict[str, Any] | None = None
    try:
        from modules.anna_training.learning_proof import build_learning_proof_bundle

        learning_proof = build_learning_proof_bundle(trade_chain=tc, db_path=db_path)
    except Exception as e:
        learning_proof = {
            "schema": "learning_proof_bundle_v1",
            "error": str(e)[:400],
        }

    return {
        "schema": "blackbox_dashboard_bundle_v1",
        "trace_id": tid,
        "market_clock": mc,
        "paper_capital": paper_cap,
        "banner": {
            "ui_state": ui_state.upper(),
            "mode_label": str((mode or {}).get("label") or "PAPER"),
            "last_decision_compact": last_dec_banner,
            "last_processed_market_event_id": (seq or {}).get("last_processed_market_event_id"),
        },
        "capital_modes": capital_modes,
        "live_execution": {
            "live_trading_blocked_by_policy": live_policy_blocked,
            "ledger_anna_has_live_rows": ledger_live,
            "anna_lane_hint": "paper_only_until_unlocked" if live_policy_blocked else str(capital_modes.get("anna_display") or ""),
        },
        "operational_boundary": {
            "what_runs_now": [
                "UI/API (this dashboard, /api/v1/*)",
                "Sequential learning engine when ui_state=running and Tick advances the cursor",
                "Wallet status probe (RPC, optional Jupiter quote sample, signing proof script)",
            ],
            "shadow_only": [
                "Strategy evaluation overlays vs baseline (QEL) when ledger rows exist — not separate execution",
            ],
            "paper_only": [
                "Jupiter policy truth: `jupiter_policy_snapshot` — same evaluator as baseline ledger (bar-derived; not live venue)",
                "Anna training execution ledger defaults to paper unless rows are explicitly mode=live",
                "Live trading remains blocked until governance clears wallet + Jupiter path",
            ],
            "not_yet_automated": [
                "Jupiter swap transaction submission from this dashboard",
                "Continuous event ingestion without Tick",
                "Drift/Jupiter perp bot — separate trading_core runtime",
            ],
        },
        "system_mode": mode,
        "wallet": wallet,
        "sequential": seq,
        "learning_summary": {
            "ui_state": ui_state,
            "learning_active": learning_active,
            "events_remaining_in_queue": ev_rem,
            "last_processed_market_event_id": (seq or {}).get("last_processed_market_event_id"),
            "last_tick_at": (seq or {}).get("last_tick_at"),
            "last_error": (seq or {}).get("last_error"),
            "sprt_or_compact": sprt,
            "last_decision_compact": last_dec_s,
            "tick_ux_banner": tick_banner,
            "tick_required": ui_state == "running" and ev_rem > 0,
            "events_processed_total": (seq or {}).get("events_processed_total"),
        },
        "trade_chain": tc,
        "operator_trading": operator_trading,
        "liveness": liveness,
        "intelligence_visibility": intelligence_visibility,
        "learning_proof": learning_proof,
        "jupiter_policy_snapshot": jupiter_policy_snapshot,
    }
