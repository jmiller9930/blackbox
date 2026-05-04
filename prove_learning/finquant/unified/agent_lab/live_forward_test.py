"""
FinQuant — Live Forward Test Loop

Runs RMv2 continuously on live Pyth SOL-PERP data. Every 15 minutes
a new case is generated from the latest bars, RMv2 decides, and the
decision is logged with full reasoning trail.

This is the honest forward test — genuinely new bars every 15 minutes,
not batch replay on historical data.

Architecture:
  Every 15 minutes:
    1. Pull latest bars from market_data.db (live Pyth feed)
    2. Generate a single case from the last 28 bars
    3. RMv2 decides (LLM + quality-gated memory)
    4. Log decision to ledger (JSON + running CSV)
    5. After 7 bars (1h45m), falsify the prior decision
    6. Update pattern memory with outcome
    7. Promote/retire patterns as evidence accumulates

Metrics reported every 24 hours:
  - Decision quality rate (good / total)
  - Win rate on entries
  - Pattern promotion state
  - Any memory improvements vs prior day

Usage (on clawbot, runs continuously):
  cd /home/jmiller/blackbox
  python3 prove_learning/finquant/unified/agent_lab/live_forward_test.py \\
    --db data/sqlite/market_data.db \\
    --config prove_learning/finquant/unified/agent_lab/configs/default_lab_config.json \\
    --output-dir prove_learning/finquant/unified/agent_lab/outputs/live_forward \\
    --symbol SOL-PERP \\
    --interval-minutes 15

  Or run once (for testing):
  python3 live_forward_test.py --db ... --config ... --output-dir ... --once
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

_LAB_ROOT = Path(__file__).parent
sys.path.insert(0, str(_LAB_ROOT))

CONTEXT_BARS    = 22   # bars of context before decision point
OUTCOME_BARS    = 7    # bars after decision to falsify outcome
STOP_ATR_MULT   = 1.6
TARGET_ATR_MULT = 4.0

# Circuit breaker — halts signal generation when consecutive losses or
# drawdown exceeds threshold. Resumes after cooldown period.
CB_MAX_CONSECUTIVE_LOSSES = 3      # halt after 3 losses in a row
CB_COOLDOWN_BARS          = 8      # wait 8 bars (2 hours) before resuming
CB_MAX_SESSION_DRAWDOWN   = -0.05  # halt if simulated session PnL < -5%


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_latest_bars(
    db_path: str,
    symbol: str,
    n_bars: int = 35,
    interval_minutes: int = 15,
) -> list[dict[str, Any]]:
    """Pull the most recent N bars from the live DB, rolled up to interval."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Fetch enough 5m bars to build N interval bars
    bars_5m_needed = n_bars * (interval_minutes // 5) + 20
    rows = conn.execute(
        "SELECT candle_open_utc, open, high, low, close, tick_count, volume_base "
        "FROM market_bars_5m WHERE canonical_symbol=? ORDER BY candle_open_utc DESC LIMIT ?",
        (symbol, bars_5m_needed)
    ).fetchall()
    conn.close()

    bars_5m = []
    for r in reversed(rows):
        bars_5m.append({
            "ts": r["candle_open_utc"],
            "open":   float(r["open"]  or 0),
            "high":   float(r["high"]  or 0),
            "low":    float(r["low"]   or 0),
            "close":  float(r["close"] or 0),
            "volume": float(r["volume_base"] or r["tick_count"] or 0),
        })

    # Roll up to target interval
    rolled = _rollup(bars_5m, interval_minutes)
    return rolled[-n_bars:]


def _rollup(bars_5m: list[dict], target_minutes: int) -> list[dict]:
    step = target_minutes // 5
    rolled = []
    for i in range(0, len(bars_5m) - step + 1, step):
        chunk = bars_5m[i:i + step]
        if not chunk:
            continue
        rolled.append({
            "timestamp": chunk[0]["ts"],
            "open":   chunk[0]["open"],
            "high":   max(b["high"]   for b in chunk),
            "low":    min(b["low"]    for b in chunk),
            "close":  chunk[-1]["close"],
            "volume": sum(b["volume"] for b in chunk),
        })
    return rolled


def compute_indicators(bars: list[dict]) -> list[dict]:
    """Add rsi_14, ema_20, atr_14 to bars in place."""
    from market_data_bridge import _ema, _rsi, _atr
    closes = [b["close"] for b in bars]
    highs  = [b["high"]  for b in bars]
    lows   = [b["low"]   for b in bars]
    ema20  = _ema(closes, 20)
    rsi14  = _rsi(closes, 14)
    atr14  = _atr(highs, lows, closes, 14)
    for i, bar in enumerate(bars):
        bar["rsi_14"] = round(rsi14[i], 4) if rsi14[i] is not None else None
        bar["ema_20"] = round(ema20[i], 4) if ema20[i] is not None else None
        bar["atr_14"] = round(atr14[i], 4) if atr14[i] is not None else None
    return bars


# ---------------------------------------------------------------------------
# Decision and falsification
# ---------------------------------------------------------------------------

def make_decision(
    bars: list[dict],
    symbol: str,
    config: dict,
    learning_store,
    output_dir: Path,
    *,
    lab_config_path: str | None = None,
) -> dict[str, Any]:
    """Run RMv2 on the current bars and return the decision."""
    from retrieval import companion_memory_sqlite_path
    from rmv2 import ReasoningModule, RMConfig
    from rmv2.memory_tiers import insert_stm

    cfg_path = lab_config_path or str(_LAB_ROOT / "configs" / "default_lab_config.json")
    rm_config = RMConfig.from_file(cfg_path)
    rm_config.memory_store_path = str(output_dir / "live_memory.jsonl")
    rm_config.retrieval_enabled = True

    rm = ReasoningModule(config=rm_config)
    decision = rm.decide(
        bars=bars,
        symbol=symbol,
        timeframe_minutes=15,
    )

    ts_now = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    current_bar = bars[-1]

    record = {
        "timestamp_decision": ts_now,
        "bar_timestamp": current_bar.get("timestamp"),
        "symbol": symbol,
        "close": current_bar.get("close"),
        "rsi_14": current_bar.get("rsi_14"),
        "atr_14": current_bar.get("atr_14"),
        "atr_pct": round(float(current_bar["atr_14"]) / float(current_bar["close"]) * 100, 4)
                   if current_bar.get("atr_14") and current_bar.get("close") else None,
        "regime": decision.regime,
        "action": decision.action,
        "confidence": decision.confidence,
        "source": decision.source,
        "thesis": decision.thesis,
        "invalidation": decision.invalidation,
        "guard_reason": decision.guard_reason,
        "h1_confidence": decision.memory_quality.get("avg_win_rate"),
        "memory_records_used": len(decision.memory_used),
        "memory_record_ids": decision.memory_used,
        # Risk context — context IS risk management
        "risk_pct": decision.risk_pct,
        "risk_context": decision.risk_context,
        # Compute stop/target
        "planned_stop": None,
        "planned_target": None,
        # To be filled at falsification time
        "outcome_kind": None,
        "pnl": None,
        "exit_price": None,       # actual price at exit/horizon
        "realized_r": None,       # (exit_price - entry) / stop_distance
        "falsified_at": None,
        "is_good_decision": None,
        "context_narrative_v1": (decision.context_narrative_v1 or "")[:8000],
        "vector_memory_id_v1": None,
    }

    # Compute stop/target
    atr = current_bar.get("atr_14")
    close = current_bar.get("close", 0)
    if atr and close and float(close) > 0:
        atr_f = float(atr)
        close_f = float(close)
        if decision.action == "ENTER_LONG":
            record["planned_stop"]   = round(close_f - STOP_ATR_MULT * atr_f, 6)
            record["planned_target"] = round(close_f + TARGET_ATR_MULT * atr_f, 6)
        elif decision.action == "ENTER_SHORT":
            record["planned_stop"]   = round(close_f + STOP_ATR_MULT * atr_f, 6)
            record["planned_target"] = round(close_f - TARGET_ATR_MULT * atr_f, 6)

    exec_cfg = rm_config.to_execution_config()
    vdb = companion_memory_sqlite_path(rm_config.memory_store_path)
    if (
        vdb is not None
        and rm_config.memory_vector_enabled
        and (decision.context_narrative_v1 or "").strip()
    ):
        mid = insert_stm(
            vdb,
            symbol=symbol,
            regime_v1=decision.regime,
            bar_timestamp=str(current_bar.get("timestamp") or ""),
            narrative_text=decision.context_narrative_v1,
            config=exec_cfg,
            decision_action=decision.action,
        )
        record["vector_memory_id_v1"] = mid

    return record


def falsify_decision(record: dict, future_bars: list[dict]) -> dict:
    """Fill in outcome once future bars are available."""
    from learning.outcome_simulator import simulate_outcome

    action = record["action"]
    if action not in ("ENTER_LONG", "ENTER_SHORT"):
        # NO_TRADE: check if market moved significantly
        if future_bars:
            entry_close = record["close"] or 0
            last_close  = future_bars[-1].get("close", entry_close)
            atr = record.get("atr_14") or 1
            move = abs(last_close - entry_close)
            no_trade_correct = move < atr * 1.5
            record["outcome_kind"] = "no_trade_correct" if no_trade_correct else "no_trade_missed"
            record["pnl"] = 0.0
        else:
            record["outcome_kind"] = "no_trade_correct"
            record["pnl"] = 0.0
        record["is_good_decision"] = record["outcome_kind"] == "no_trade_correct"
        record["falsified_at"] = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return record

    if not future_bars:
        return record

    entry_close = record["close"] or 0
    atr = record.get("atr_14") or 0
    if entry_close <= 0 or atr <= 0:
        return record

    stop   = record.get("planned_stop")
    target = record.get("planned_target")
    if stop is None or target is None:
        return record

    pnl = 0.0
    outcome = "no_result"
    for bar in future_bars:
        high = bar.get("high", entry_close)
        low  = bar.get("low",  entry_close)
        close = bar.get("close", entry_close)
        if action == "ENTER_LONG":
            if low <= stop:
                pnl = stop - entry_close; outcome = "loss"; break
            if high >= target:
                pnl = target - entry_close; outcome = "win"; break
            pnl = close - entry_close
        else:  # SHORT
            if high >= stop:
                pnl = entry_close - stop; outcome = "loss"; break
            if low <= target:
                pnl = entry_close - target; outcome = "win"; break
            pnl = entry_close - close

    if outcome == "no_result":
        outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "no_result"

    record["outcome_kind"] = outcome
    record["pnl"] = round(pnl, 6)
    record["exit_price"] = round(exit_price, 6)
    # Realized R = actual gain / stop distance (positive = win, negative = loss)
    stop = record.get("planned_stop")
    if stop is not None and float(stop) != 0 and entry_close > 0:
        stop_distance = abs(entry_close - float(stop))
        if stop_distance > 0:
            if action == "ENTER_LONG":
                record["realized_r"] = round((exit_price - entry_close) / stop_distance, 4)
            else:
                record["realized_r"] = round((entry_close - exit_price) / stop_distance, 4)
    record["is_good_decision"] = outcome == "win"
    record["falsified_at"] = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return record


# ---------------------------------------------------------------------------
# Daily summary
# ---------------------------------------------------------------------------

def daily_summary(decisions: list[dict]) -> dict[str, Any]:
    """Compute 24-hour rolling metrics."""
    falsified = [d for d in decisions if d.get("outcome_kind")]
    wins   = sum(1 for d in falsified if d["outcome_kind"] == "win")
    losses = sum(1 for d in falsified if d["outcome_kind"] == "loss")
    ntc    = sum(1 for d in falsified if d["outcome_kind"] == "no_trade_correct")
    ntm    = sum(1 for d in falsified if d["outcome_kind"] == "no_trade_missed")
    good   = wins + ntc
    total  = len(falsified)
    entries = wins + losses
    pnl = sum(float(d.get("pnl") or 0) for d in falsified)

    return {
        "total_opportunities": total,
        "entries_taken": entries,
        "wins": wins,
        "losses": losses,
        "no_trade_correct": ntc,
        "no_trade_missed": ntm,
        "decision_quality_rate": round(good / total, 4) if total else 0,
        "win_rate_on_entries": round(wins / entries, 4) if entries else 0,
        "total_pnl": round(pnl, 4),
        "pending_falsification": len(decisions) - len(falsified),
    }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_live(
    *,
    db_path: str,
    config_path: str,
    output_dir: str,
    symbol: str,
    interval_minutes: int,
    run_once: bool = False,
) -> None:
    from config import load_config
    from learning.learning_unit_store import LearningUnitStore

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    decisions_path = out / "live_decisions.jsonl"
    summary_path   = out / "daily_summary.json"
    units_dir      = out / "learning_units"
    learning_store = LearningUnitStore(units_dir)

    from retrieval import companion_memory_sqlite_path
    from rmv2.memory_index import ensure_db, ingest_jsonl
    from rmv2.memory_tiers import prune_expired_stm

    live_jsonl = out / "live_memory.jsonl"
    live_db = companion_memory_sqlite_path(live_jsonl)
    if live_db is not None:
        ensure_db(live_db)

    config = load_config(config_path)
    config["memory_store_path"] = str(live_jsonl)
    config["retrieval_enabled_default_v1"] = True
    config["auto_promote_learning_v1"] = True

    if live_jsonl.is_file() and live_db is not None:
        n_backfill = ingest_jsonl(live_jsonl, live_db)
        if n_backfill:
            print(f"[live] RMv2 memory DB: indexed {n_backfill} rows from {live_jsonl.name}")

    print(f"[live] symbol={symbol} | interval={interval_minutes}m | db={db_path}")
    print(f"[live] output={out}")
    print(f"[live] Starting live forward test. Ctrl+C to stop.")

    pending: list[dict] = []   # decisions awaiting falsification
    all_decisions: list[dict] = []

    # Circuit breaker state
    consecutive_losses = 0
    cb_cooldown_remaining = 0
    session_pnl = 0.0

    while True:
        now = datetime.datetime.now(timezone.utc)
        print(f"\n[live] {now.strftime('%Y-%m-%dT%H:%M:%SZ')} — making decision...")

        # ── Weekend skip — no decisions Fri 20:00 UTC through Sunday ────
        now_utc = datetime.datetime.now(timezone.utc)
        weekday = now_utc.weekday()   # Monday=0, Sunday=6
        hour = now_utc.hour
        is_weekend = (
            (weekday == 4 and hour >= 20) or  # Friday after 20:00 UTC
            weekday == 5 or                    # Saturday
            weekday == 6                       # Sunday
        )
        if is_weekend:
            day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][weekday]
            print(f"[live] WEEKEND — skipping ({day_name} UTC {hour:02d}:00). No decision.")
            if not run_once:
                time.sleep(interval_minutes * 60)
            continue

        # ── Circuit breaker check ────────────────────────────────────────
        if cb_cooldown_remaining > 0:
            cb_cooldown_remaining -= 1
            print(f"[live] CIRCUIT BREAKER ACTIVE — cooldown {cb_cooldown_remaining} bars remaining. No signal.")
            if not run_once:
                sleep_seconds = interval_minutes * 60
                time.sleep(sleep_seconds)
            continue

        try:
            mem_db = companion_memory_sqlite_path(Path(config["memory_store_path"]))
            if mem_db is not None:
                prune_expired_stm(mem_db)

            bars_raw = load_latest_bars(db_path, symbol, n_bars=CONTEXT_BARS + OUTCOME_BARS + 2, interval_minutes=interval_minutes)
            bars_with_ind = compute_indicators(bars_raw)
            decision_bars = bars_with_ind[:CONTEXT_BARS + 1]

            record = make_decision(
                bars=decision_bars,
                symbol=symbol,
                config=config,
                learning_store=learning_store,
                output_dir=out,
                lab_config_path=config_path,
            )

            print(f"[live] Decision: {record['action']} | regime={record['regime']} | conf={record['confidence']:.2f} | source={record['source']}")
            if record.get("guard_reason"):
                print(f"[live] Guard: {record['guard_reason']}")
            print(f"[live] Thesis: {record['thesis'][:100]}")

            pending.append(record)
            all_decisions.append(record)

            # Append to rolling JSONL
            with open(decisions_path, "a") as f:
                f.write(json.dumps(record) + "\n")

        except Exception as e:
            print(f"[live] Decision error: {e}")

        # Falsify decisions that have enough future bars
        try:
            bars_for_falsify = load_latest_bars(db_path, symbol, n_bars=CONTEXT_BARS + OUTCOME_BARS + 10, interval_minutes=interval_minutes)
            bars_for_falsify = compute_indicators(bars_for_falsify)

            still_pending = []
            for d in pending:
                bar_ts = d.get("bar_timestamp", "")
                decision_idx = None
                for i, b in enumerate(bars_for_falsify):
                    if b.get("timestamp", "") >= bar_ts:
                        decision_idx = i
                        break
                if decision_idx is not None and len(bars_for_falsify) - decision_idx >= OUTCOME_BARS:
                    future = bars_for_falsify[decision_idx + 1: decision_idx + 1 + OUTCOME_BARS]
                    d = falsify_decision(d, future)
                    outcome = d.get("outcome_kind", "")
                    pnl = float(d.get("pnl") or 0)
                    session_pnl += pnl
                    print(f"[live] Falsified: {d['action']} → {outcome} | pnl={pnl:+.4f} | session_pnl={session_pnl:+.4f}")

                    vid = d.get("vector_memory_id_v1")
                    if vid:
                        from retrieval import companion_memory_sqlite_path
                        from rmv2.memory_tiers import promote_stm_to_ltm

                        vdb = companion_memory_sqlite_path(Path(config["memory_store_path"]))
                        if vdb is not None:
                            promote_stm_to_ltm(vdb, str(vid), outcome_hint=str(outcome))

                    # ── Circuit breaker: update on entry outcomes only ──
                    if outcome == "loss":
                        consecutive_losses += 1
                        print(f"[live] Consecutive losses: {consecutive_losses}/{CB_MAX_CONSECUTIVE_LOSSES}")
                    elif outcome == "win":
                        consecutive_losses = 0  # reset on win

                    # Trigger circuit breaker
                    triggered = False
                    reason = ""
                    if consecutive_losses >= CB_MAX_CONSECUTIVE_LOSSES:
                        triggered = True
                        reason = f"{CB_MAX_CONSECUTIVE_LOSSES} consecutive losses"
                    elif session_pnl < CB_MAX_SESSION_DRAWDOWN:
                        triggered = True
                        reason = f"session drawdown {session_pnl:.4f} < {CB_MAX_SESSION_DRAWDOWN}"

                    if triggered:
                        cb_cooldown_remaining = CB_COOLDOWN_BARS
                        consecutive_losses = 0
                        print(f"[live] *** CIRCUIT BREAKER TRIGGERED: {reason} ***")
                        print(f"[live] Halting signals for {CB_COOLDOWN_BARS} bars ({CB_COOLDOWN_BARS * interval_minutes} minutes)")
                else:
                    still_pending.append(d)
            pending = still_pending
        except Exception as e:
            print(f"[live] Falsification error: {e}")

        # Daily summary every ~96 decisions (24h at 15m intervals)
        falsified_count = sum(1 for d in all_decisions if d.get("outcome_kind"))
        if falsified_count > 0 and falsified_count % 96 == 0:
            summary = daily_summary(all_decisions)
            print(f"\n[live] === 24-HOUR SUMMARY ===")
            print(f"[live] Decision quality: {summary['decision_quality_rate']:.1%}")
            print(f"[live] Win rate: {summary['win_rate_on_entries']:.1%} | PnL: {summary['total_pnl']:+.2f}")
            print(f"[live] Entries: {summary['entries_taken']} | Correct stand-downs: {summary['no_trade_correct']}")
            with open(summary_path, "w") as f:
                json.dump({**summary, "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ")}, f, indent=2)

        if run_once:
            print(f"\n[live] --once mode: exiting after one decision.")
            break

        # Wait until next 15m boundary
        sleep_seconds = interval_minutes * 60 - (now.second + now.minute % interval_minutes * 60)
        if sleep_seconds <= 0:
            sleep_seconds = interval_minutes * 60
        print(f"[live] Sleeping {sleep_seconds}s until next bar...")
        time.sleep(sleep_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant live forward test loop")
    parser.add_argument("--db", required=True, help="Path to market_data.db")
    parser.add_argument("--config", required=True, help="Path to lab config JSON")
    parser.add_argument("--output-dir", required=True, help="Output directory for live decisions")
    parser.add_argument("--symbol", default="SOL-PERP")
    parser.add_argument("--interval-minutes", type=int, default=15)
    parser.add_argument("--once", action="store_true", help="Run once and exit (test mode)")
    args = parser.parse_args()

    run_live(
        db_path=args.db,
        config_path=args.config,
        output_dir=args.output_dir,
        symbol=args.symbol,
        interval_minutes=args.interval_minutes,
        run_once=args.once,
    )


if __name__ == "__main__":
    main()
