"""Baseline → execution_ledger: **Jupiter_2 Sean policy** (signal-gated) or legacy mechanical row.

Default **signal mode** env value is still ``sean_jupiter_v1`` (historic name; do not read as “old Jupiter policy”).
The evaluator is **only** ``modules/anna_training/jupiter_2_sean_policy.evaluate_jupiter_2_sean`` via
``sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v1`` (adapter over Jupiter_2).

**Execution trades:** still **at most one** baseline ``execution_trades`` row per ``market_event_id`` when the policy fires.

**Policy evaluations:** every evaluated tick writes/upserts ``policy_evaluations`` (including ``trade=false``),
for backtest joins to ``market_bars_5m``. Disable with ``BASELINE_POLICY_EVALUATION_LOG=0``.

**Ingest alignment:** :func:`market_data.canonical_bar_refresh.refresh_last_closed_bar_from_ticks` calls this after
each successful ``market_bars_5m`` upsert when ``BASELINE_LEDGER_AFTER_CANONICAL_BAR`` is on (default), so the
ledger stays aligned with Hermes/Pyth ingest without relying only on the Karpathy loop. Disable with
``BASELINE_LEDGER_AFTER_CANONICAL_BAR=0`` (e.g. unit tests).

Legacy: ``BASELINE_LEDGER_SIGNAL_MODE=legacy_mechanical_long`` — old open→close long every bar (lab only).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _policy_evaluation_log_enabled() -> bool:
    return _env_bool("BASELINE_POLICY_EVALUATION_LOG", True)


def _legacy_mechanical_allowed() -> bool:
    """Lab-only OHLC-long-every-bar path. Off by default (integrity: Sean policy is authoritative)."""
    return _env_bool("BASELINE_LEGACY_MECHANICAL_ALLOWED", False)


def _runtime_scripts() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "runtime"


def _ensure_runtime_path() -> None:
    rt = _runtime_scripts()
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))


def verify_market_event_id_matches_canonical_bar(bar: dict[str, Any]) -> str:
    """
    Recompute ``market_event_id`` via :func:`make_market_event_id` from the bar's open time
    and assert it equals the stored ``market_event_id`` (no divergence from Anna path).
    """
    _ensure_runtime_path()
    from market_data.market_event_id import make_market_event_id
    from market_data.canonical_time import parse_iso_zulu_to_utc

    stored = str(bar.get("market_event_id") or "").strip()
    sym = str(bar.get("canonical_symbol") or "").strip()
    tf = str(bar.get("timeframe") or "").strip()
    op_s = str(bar.get("candle_open_utc") or "").strip()
    if not stored or not sym or not tf or not op_s:
        raise ValueError("bar_missing_identity_fields")
    op = parse_iso_zulu_to_utc(op_s)
    computed = make_market_event_id(canonical_symbol=sym, candle_open_utc=op, timeframe=tf)
    if computed != stored:
        raise ValueError(f"market_event_id_divergence stored={stored!r} recomputed={computed!r}")
    return stored


def _baseline_trade_id(market_event_id: str, mode: str) -> str:
    h = hashlib.sha256(f"baseline|{market_event_id}|{mode}|v1".encode()).hexdigest()[:24]
    return f"bl_{h}"


def _baseline_lifecycle_trade_id(entry_market_event_id: str, mode: str) -> str:
    h = hashlib.sha256(f"baseline_lc|{entry_market_event_id}|{mode}|v1".encode()).hexdigest()[:24]
    return f"bl_lc_{h}"


def _signal_mode() -> str:
    raw = (os.environ.get("BASELINE_LEDGER_SIGNAL_MODE") or "sean_jupiter_v1").strip().lower()
    if raw in ("legacy", "legacy_mechanical", "legacy_mechanical_long", "mechanical"):
        return "legacy_mechanical_long"
    return "sean_jupiter_v1"


def run_baseline_ledger_bridge_tick(
    *,
    market_data_db_path: Path | None = None,
    execution_ledger_db_path: Path | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """
    Append **at most one** baseline row per ``market_event_id`` when Sean Jupiter signal (or legacy) fires.

    Env:
      BASELINE_LEDGER_BRIDGE — default **on**; ``0`` disables all baseline writes.
      BASELINE_LEDGER_SIGNAL_MODE — ``sean_jupiter_v1`` (default) | ``legacy_mechanical_long``.
      BASELINE_LEGACY_MECHANICAL_ALLOWED — default **off**; ``1`` required for ``legacy_mechanical_long`` (lab only).
      BASELINE_LEDGER_MODE — ``paper`` (default) or ``live``.
      BASELINE_POLICY_EVALUATION_LOG — default **on**; ``0`` skips ``policy_evaluations`` upserts only.

      Ingest invokes this after each canonical 5m upsert when ``BASELINE_LEDGER_AFTER_CANONICAL_BAR`` is on
      (see :func:`market_data.canonical_bar_refresh.refresh_last_closed_bar_from_ticks`).
    """
    if not _env_bool("BASELINE_LEDGER_BRIDGE", True):
        return {"enabled": False, "reason": "BASELINE_LEDGER_BRIDGE off"}

    _ensure_runtime_path()
    from market_data.bar_lookup import fetch_latest_bar_row, fetch_recent_bars_asc

    m = (mode or os.environ.get("BASELINE_LEDGER_MODE") or "paper").strip().lower()
    if m not in ("live", "paper"):
        m = "paper"

    sm = _signal_mode()
    if sm == "legacy_mechanical_long" and not _legacy_mechanical_allowed():
        return {
            "ok": False,
            "reason": "legacy_mechanical_long_disabled",
            "detail": "Mechanical OHLC baseline is quarantined. Set BASELINE_LEGACY_MECHANICAL_ALLOWED=1 for lab-only use.",
            "signal_mode": sm,
        }

    bar = fetch_latest_bar_row(db_path=market_data_db_path)
    if not bar:
        return {"ok": False, "reason": "no_canonical_bar"}

    mid = verify_market_event_id_matches_canonical_bar(bar)
    o = bar.get("open")
    c = bar.get("close")
    if o is None or c is None:
        return {"ok": False, "reason": "bar_missing_ohlc", "market_event_id": mid}
    if sm == "legacy_mechanical_long":
        return _run_legacy_mechanical_long(
            bar=bar,
            mid=mid,
            mode=m,
            execution_ledger_db_path=execution_ledger_db_path,
        )

    bars_asc = fetch_recent_bars_asc(limit=280, db_path=market_data_db_path)
    if not bars_asc or str(bars_asc[-1].get("market_event_id") or "") != mid:
        return {"ok": False, "reason": "bar_history_mismatch", "market_event_id": mid}

    from modules.anna_training.jupiter_2_baseline_lifecycle import (
        BaselineOpenPosition,
        open_position_from_signal,
        process_holding_bar,
        unrealized_pnl_usd,
    )
    from modules.anna_training.jupiter_2_sean_policy import (
        CATALOG_ID as baseline_catalog_id,
        POLICY_ENGINE_ID,
        calculate_atr,
    )
    from modules.anna_training.sean_jupiter_baseline_signal import evaluate_sean_jupiter_baseline_v1
    from modules.anna_training.store import load_state

    from modules.anna_training.execution_ledger import (
        append_position_event,
        baseline_jupiter_open_position_key,
        connect_ledger,
        ensure_execution_ledger_schema,
        fetch_baseline_jupiter_open_state_json,
        upsert_baseline_jupiter_open_state,
        upsert_policy_evaluation,
    )

    sym = str(bar.get("canonical_symbol") or "SOL-PERP").strip() or "SOL-PERP"
    tf = str(bar.get("timeframe") or "5m").strip() or "5m"
    pos_key = baseline_jupiter_open_position_key(symbol=sym, timeframe=tf, mode=m)

    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    for b in bars_asc:
        try:
            closes.append(float(b["close"]))
            highs.append(float(b["high"]))
            lows.append(float(b["low"]))
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "reason": "bar_history_ohlc_parse_error", "market_event_id": mid}

    conn_chk = connect_ledger(execution_ledger_db_path)
    try:
        ensure_execution_ledger_schema(conn_chk)
        raw_open = fetch_baseline_jupiter_open_state_json(conn_chk, position_key=pos_key)
    finally:
        conn_chk.close()

    st = load_state()
    sig = evaluate_sean_jupiter_baseline_v1(
        bars_asc=bars_asc,
        training_state=st,
        ledger_db_path=execution_ledger_db_path,
    )
    policy_eval_write_error: str | None = None

    def _log_eval(
        *,
        trade: bool,
        reason_code: str,
        features: dict[str, Any],
        side: str,
        pnl_hint: float | None,
    ) -> None:
        nonlocal policy_eval_write_error
        if not _policy_evaluation_log_enabled():
            return
        try:
            upsert_policy_evaluation(
                market_event_id=mid,
                signal_mode=sm,
                tick_mode=m,
                trade=trade,
                reason_code=reason_code,
                features=features,
                side=side,
                pnl_usd=pnl_hint,
                db_path=execution_ledger_db_path,
            )
        except sqlite3.OperationalError as exc:
            policy_eval_write_error = str(exc)
            print(
                f"baseline_ledger_bridge: policy_evaluations write failed: {exc!r} market_event_id={mid}",
                file=sys.stderr,
                flush=True,
            )

    catalog_id = baseline_catalog_id

    if raw_open:
        pos = BaselineOpenPosition.from_json_dict(json.loads(raw_open))
        if pos.last_processed_market_event_id == mid:
            feat = dict(sig.features) if sig.features else {}
            feat["lifecycle"] = "holding"
            feat["open_position"] = pos.to_json_dict()
            _log_eval(
                trade=False,
                reason_code="jupiter_2_baseline_holding",
                features=feat,
                side=str(pos.side),
                pnl_usd=None,
            )
            out: dict[str, Any] = {
                "ok": True,
                "lifecycle_idempotent": True,
                "market_event_id": mid,
                "signal_mode": sm,
                "open_position": pos.to_json_dict(),
            }
            if policy_eval_write_error:
                out["policy_evaluation_write_error"] = policy_eval_write_error
            return out

        np, ex = process_holding_bar(
            pos,
            market_event_id=mid,
            closes=closes,
            highs=highs,
            lows=lows,
            bar=bar,
        )
        if ex is not None:
            er = str(ex.get("exit_reason") or "")
            xprice = float(ex["exit_price"])
            pnl_exit = float(ex["pnl_usd"])
            tid = pos.trade_id
            ctx = {
                "source": "baseline_ledger_bridge_sean_jupiter_v1",
                "policy_engine": POLICY_ENGINE_ID,
                "trade_policy": "jupiter_perps",
                "catalog_strategy_id": catalog_id,
                "signal_mode": sm,
                "lifecycle": "exit",
                "exit_record": ex,
                "entry_market_event_id": pos.entry_market_event_id,
                "side": pos.side,
                "initial_stop_loss": float(pos.initial_stop_loss),
                "initial_take_profit": float(pos.initial_take_profit),
            }
            feat_x = dict(sig.features) if sig.features else {}
            feat_x["lifecycle"] = "exit"
            feat_x["exit"] = ex
            _log_eval(
                trade=False,
                reason_code="jupiter_2_baseline_exit",
                features=feat_x,
                side=str(pos.side),
                pnl_usd=None,
            )
            from .decision_trace import persist_baseline_lifecycle_close

            try:
                out = persist_baseline_lifecycle_close(
                    market_event_id=mid,
                    bar=bar,
                    mode=m,
                    trade_id=tid,
                    pnl_usd=pnl_exit,
                    side=pos.side,
                    size=float(pos.size),
                    entry_price=float(pos.entry_price),
                    exit_price=xprice,
                    exit_reason=er,
                    entry_time=str(pos.entry_candle_open_utc or bar.get("candle_open_utc") or ""),
                    position_key=pos_key,
                    context_snapshot=ctx,
                    notes=f"baseline — Jupiter_2 lifecycle exit {er} ({catalog_id})",
                    db_path=execution_ledger_db_path,
                    signal_snapshot=dict(sig.features) if sig.features else None,
                )
            except sqlite3.IntegrityError:
                return {
                    "ok": True,
                    "idempotent_skip": True,
                    "market_event_id": mid,
                    "trade_id": tid,
                }
            except sqlite3.OperationalError as exc:
                print(
                    f"baseline_ledger_bridge: lifecycle close write failed: {exc!r} market_event_id={mid}",
                    file=sys.stderr,
                    flush=True,
                )
                return {
                    "ok": False,
                    "reason": "execution_ledger_write_failed",
                    "error": str(exc),
                    "market_event_id": mid,
                    "trade_id": tid,
                }
            row = out.get("execution_trade")
            trace_meta = {k: v for k, v in out.items() if k != "execution_trade"}
            ret = {
                "ok": True,
                "lifecycle_exit": ex,
                "market_event_id": mid,
                "trade_id": tid,
                "mode": m,
                "execution_trade": row,
                "decision_trace": trace_meta,
                "signal_mode": sm,
                "side": pos.side,
            }
            if policy_eval_write_error:
                ret["policy_evaluation_write_error"] = policy_eval_write_error
            return ret

        assert np is not None
        ur = unrealized_pnl_usd(
            entry=np.entry_price,
            mark=float(bar["close"]),
            size=np.size,
            side=np.side,
        )
        feat_h = dict(sig.features) if sig.features else {}
        feat_h["lifecycle"] = "holding"
        feat_h["open_position"] = np.to_json_dict()
        feat_h["unrealized_pnl_usd"] = round(float(ur), 8)
        _log_eval(
            trade=False,
            reason_code="jupiter_2_baseline_holding",
            features=feat_h,
            side=str(np.side),
            pnl_usd=None,
        )
        conn_u = connect_ledger(execution_ledger_db_path)
        try:
            ensure_execution_ledger_schema(conn_u)
            upsert_baseline_jupiter_open_state(
                conn_u,
                position_key=pos_key,
                trade_id=np.trade_id,
                state_json=json.dumps(np.to_json_dict(), default=str),
            )
            conn_u.commit()
        except sqlite3.OperationalError as exc:
            print(
                f"baseline_ledger_bridge: open state upsert failed: {exc!r} market_event_id={mid}",
                file=sys.stderr,
                flush=True,
            )
            return {
                "ok": False,
                "reason": "baseline_open_state_write_failed",
                "error": str(exc),
                "market_event_id": mid,
            }
        finally:
            conn_u.close()

        ret_h: dict[str, Any] = {
            "ok": True,
            "lifecycle": "holding",
            "market_event_id": mid,
            "trade_id": np.trade_id,
            "mode": m,
            "open_position": np.to_json_dict(),
            "unrealized_pnl_usd": round(float(ur), 8),
            "signal_mode": sm,
            "side": np.side,
        }
        if policy_eval_write_error:
            ret_h["policy_evaluation_write_error"] = policy_eval_write_error
        return ret_h

    feat0 = dict(sig.features) if sig.features else {}
    _log_eval(
        trade=bool(sig.trade),
        reason_code=str(sig.reason_code or ""),
        features=feat0,
        side=str(sig.side) if sig.trade else "flat",
        pnl_usd=None,
    )

    if not sig.trade:
        out_nt: dict[str, Any] = {
            "ok": True,
            "no_trade": True,
            "market_event_id": mid,
            "reason_code": sig.reason_code,
            "features": sig.features,
            "signal_mode": sm,
        }
        if policy_eval_write_error:
            out_nt["policy_evaluation_write_error"] = policy_eval_write_error
        return out_nt

    atr_e = calculate_atr(closes, highs, lows)
    tid = _baseline_lifecycle_trade_id(mid, m)
    npos = open_position_from_signal(
        trade_id=tid,
        market_event_id=mid,
        bar=bar,
        side=sig.side,
        atr_entry=float(atr_e),
        reason_code=str(sig.reason_code or ""),
        signal_features=dict(sig.features) if sig.features else {},
    )

    feat_open = dict(sig.features) if sig.features else {}
    fc_usd = feat_open.get("free_collateral_usd")
    try:
        fc_f = float(fc_usd) if fc_usd is not None else None
    except (TypeError, ValueError):
        fc_f = None

    conn_o = connect_ledger(execution_ledger_db_path)
    try:
        ensure_execution_ledger_schema(conn_o)
        upsert_baseline_jupiter_open_state(
            conn_o,
            position_key=pos_key,
            trade_id=npos.trade_id,
            state_json=json.dumps(npos.to_json_dict(), default=str),
        )
        append_position_event(
            conn_o,
            trade_id=npos.trade_id,
            market_event_id=mid,
            event_type="position_open",
            payload={
                "phase": "position_open",
                "entry_price": npos.entry_price,
                "side": npos.side,
                "size": float(npos.size),
                "notional_usd": npos.notional_usd,
                "size_source": npos.size_source,
                "virtual_sl": npos.stop_loss,
                "virtual_tp": npos.take_profit,
                "initial_stop_loss": float(npos.initial_stop_loss),
                "initial_take_profit": float(npos.initial_take_profit),
                "leverage": npos.leverage,
                "risk_pct": npos.risk_pct,
                "collateral_usd": npos.collateral_usd,
                "free_collateral_usd": fc_f,
                "atr_entry": npos.atr_entry,
                "economic_basis": "jupiter_2_sean_lifecycle",
                "note": "Paper baseline — lifecycle entry at bar close; exits are SL/TP only.",
            },
            sequence_num=0,
        )
        conn_o.commit()
    except sqlite3.OperationalError as exc:
        print(
            f"baseline_ledger_bridge: lifecycle open write failed: {exc!r} market_event_id={mid}",
            file=sys.stderr,
            flush=True,
        )
        return {
            "ok": False,
            "reason": "baseline_open_state_write_failed",
            "error": str(exc),
            "market_event_id": mid,
        }
    finally:
        conn_o.close()

    ret_o: dict[str, Any] = {
        "ok": True,
        "lifecycle": "opened",
        "market_event_id": mid,
        "trade_id": npos.trade_id,
        "mode": m,
        "open_position": npos.to_json_dict(),
        "signal_mode": sm,
        "side": npos.side,
    }
    if policy_eval_write_error:
        ret_o["policy_evaluation_write_error"] = policy_eval_write_error
    return ret_o


def _run_legacy_mechanical_long(
    *,
    bar: dict[str, Any],
    mid: str,
    mode: str,
    execution_ledger_db_path: Path | None,
) -> dict[str, Any]:
    from .decision_trace import persist_baseline_trade_with_trace
    from .execution_ledger import compute_pnl_usd, upsert_policy_evaluation

    o = bar.get("open")
    c = bar.get("close")
    size = 1.0
    tid = _baseline_trade_id(mid, mode)
    pnl = compute_pnl_usd(entry_price=float(o), exit_price=float(c), size=size, side="long")

    tm = mode if mode in ("live", "paper") else "paper"
    if _policy_evaluation_log_enabled():
        try:
            upsert_policy_evaluation(
                market_event_id=mid,
                signal_mode="legacy_mechanical_long",
                tick_mode=tm,
                trade=True,
                reason_code="legacy_mechanical_long",
                features={
                    "source": "baseline_ledger_bridge_v1",
                    "economic_basis": "canonical_bar_open_to_close_long_1unit",
                    "price_source": bar.get("price_source"),
                    "tick_count": bar.get("tick_count"),
                },
                side="long",
                pnl_usd=pnl,
                db_path=execution_ledger_db_path,
            )
        except sqlite3.OperationalError as exc:
            print(
                f"baseline_ledger_bridge: policy_evaluations write failed (legacy): {exc!r} "
                f"market_event_id={mid}",
                file=sys.stderr,
                flush=True,
            )

    try:
        out = persist_baseline_trade_with_trace(
            market_event_id=mid,
            bar=bar,
            mode=mode,
            trade_id=tid,
            pnl_usd=pnl,
            context_snapshot={
                "source": "baseline_ledger_bridge_v1",
                "price_source": bar.get("price_source"),
                "tick_count": bar.get("tick_count"),
                "economic_basis": "canonical_bar_open_to_close_long_1unit",
            },
            notes="legacy mechanical baseline — OHLC long 1 unit (not Sean signal)",
            db_path=execution_ledger_db_path,
            side="long",
            economic_basis="canonical_bar_open_to_close_long_1unit",
            signal_snapshot=None,
        )
        from .execution_ledger import (
            connect_ledger as _conn_ledger,
            ensure_execution_ledger_schema as _ensure_el,
            insert_baseline_paper_lifecycle_events,
        )

        _c = _conn_ledger(execution_ledger_db_path)
        try:
            _ensure_el(_c)
            insert_baseline_paper_lifecycle_events(
                _c,
                trade_id=tid,
                market_event_id=mid,
                bar=bar,
                side="long",
                pnl_usd=float(pnl),
                mode=mode,
            )
            _c.commit()
        finally:
            _c.close()
    except sqlite3.IntegrityError:
        return {
            "ok": True,
            "idempotent_skip": True,
            "market_event_id": mid,
            "trade_id": tid,
        }

    row = out.get("execution_trade")
    trace_meta = {k: v for k, v in out.items() if k != "execution_trade"}

    return {
        "ok": True,
        "market_event_id": mid,
        "trade_id": tid,
        "mode": mode,
        "execution_trade": row,
        "decision_trace": trace_meta,
        "signal_mode": "legacy_mechanical_long",
    }
