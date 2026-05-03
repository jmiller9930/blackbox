"""
Sean EMA Bot Signal Backtest

Ports Sean's exact entry logic (from the forwarded code) to Python and runs it
against real SOL-PERP historical data from the clawbot SQLite database.

This is analysis only — no execution, no wallet, no live orders.

Sean's entry conditions (from processSignals + aggregateCandles):
  1. EMA(9) / EMA(21) crossover determines bias (long or short mode)
  2. RSI divergence signal within that bias:
       Long: current_low < prev_low AND current_rsi > prev_rsi (bullish divergence)
       Short: current_high > prev_high AND current_rsi < prev_rsi (bearish divergence)
  3. Confidence score >= 8 (his key filter to remove "7/10 trades")
  4. Bias aligned (signal matches current EMA bias)
  5. Volume >= 115% of average volume
  6. RSI guard: long blocked if RSI > 68, short blocked if RSI < 32
  7. Session filter: skip UTC 00:00–13:00 (Asian session)
  8. Weekend filter: skip Fri 20:00 UTC through Sunday

Exit:
  - Stop loss: 1.5x ATR below entry (long) / above entry (short)
  - Take profit: 1.23R (always, since confidence >= 8)
  - Evaluated against next N bars (forward simulation)

Usage:
  python3 sean_signal_backtest.py --db /path/to/market_data.db
  python3 sean_signal_backtest.py --db /path/to/market_data.db --no-filters
"""

from __future__ import annotations

import argparse
import sqlite3
import math
from datetime import datetime, timezone
from typing import Any


# ── Sean's constants ──────────────────────────────────────────────────────────
EMA_SHORT  = 9
EMA_LONG   = 21
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_LONG_THRESHOLD  = 52
RSI_SHORT_THRESHOLD = 48
ASIAN_START_UTC = 0
ASIAN_END_UTC   = 13
WEEKEND_DISABLE_START = 20  # Friday UTC hour
SPREAD_BUFFER_PCT = 0.002

# Exit geometry
SL_ATR_MULT  = 1.5
TP_R_MULT    = 1.23
ROUND_TRIP_FEE_USD = 0.22

# Collateral simulation (fixed for backtest purity)
SIMULATED_COLLATERAL_USD = 100.0
LEVERAGE = 30


# ── Indicator functions (ported from Sean's TypeScript) ──────────────────────

def ema(series: list[float], period: int) -> list[float]:
    out = [float("nan")] * len(series)
    if len(series) < period:
        return out
    out[period - 1] = sum(series[:period]) / period
    alpha = 2.0 / (period + 1)
    for i in range(period, len(series)):
        out[i] = series[i] * alpha + out[i - 1] * (1 - alpha)
    return out


def rsi(series: list[float], period: int = RSI_PERIOD) -> list[float]:
    out = [float("nan")] * len(series)
    if len(series) < period + 1:
        return out
    gain = loss = 0.0
    for i in range(1, period + 1):
        d = series[i] - series[i - 1]
        if d > 0: gain += d
        else:     loss -= d
    avg_gain = gain / period
    avg_loss = loss / period if loss else 0.001
    out[period - 1] = 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period, len(series)):
        d = series[i] - series[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period or 0.001
        out[i] = 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def atr(closes: list[float], highs: list[float], lows: list[float],
        period: int = ATR_PERIOD) -> list[float]:
    out = [float("nan")] * len(closes)
    if len(closes) < period + 1:
        return out
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i]  - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return out
    atr_val = sum(trs[:period]) / period
    out[period] = atr_val
    for i in range(period + 1, len(closes)):
        atr_val = (atr_val * (period - 1) + trs[i - 1]) / period
        out[i] = atr_val
    return out


# ── Sean's confidence score (ported exactly) ─────────────────────────────────

def confidence_score(
    is_long: bool,
    cur_rsi: float, prev_rsi: float,
    cur_low: float,  prev_low: float,
    cur_high: float, prev_high: float,
    avg_vol: float,  cur_vol: float,
) -> int:
    score = 3
    rsi_favorable = (is_long and cur_rsi >= RSI_LONG_THRESHOLD) or \
                    (not is_long and cur_rsi <= RSI_SHORT_THRESHOLD)
    if rsi_favorable:
        score += 2
    if is_long:
        if cur_rsi >= 58:   score += 2
        elif cur_rsi >= 54: score += 1
    else:
        if cur_rsi <= 42:   score += 2
        elif cur_rsi <= 46: score += 1
    if is_long and cur_low < prev_low:
        drop = (prev_low - cur_low) / prev_low
        if drop > 0.008:   score += 2
        elif drop > 0.004: score += 1
    elif not is_long and cur_high > prev_high:
        rise = (cur_high - prev_high) / prev_high
        if rise > 0.008:   score += 2
        elif rise > 0.004: score += 1
    if cur_vol > avg_vol * 1.2:
        score += 1
    return min(10, score)


# ── Session / weekend filter ─────────────────────────────────────────────────

def is_blocked_session(ts: datetime) -> tuple[bool, str]:
    h = ts.utctimetuple().tm_hour
    d = ts.utctimetuple().tm_wday  # Monday=0, Sunday=6
    if ASIAN_START_UTC <= h < ASIAN_END_UTC:
        return True, f"asian_session UTC{h:02d}:00"
    # Friday after 20:00 UTC = weekday 4, hour >= 20
    if d == 4 and h >= WEEKEND_DISABLE_START:
        return True, f"friday_late UTC{h:02d}:00"
    # Saturday = weekday 5, Sunday = weekday 6
    if d in (5, 6):
        return True, f"weekend_{'sat' if d==5 else 'sun'}"
    return False, ""


# ── Forward exit simulation ───────────────────────────────────────────────────

def simulate_exit(
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    future_bars: list[dict[str, Any]],
) -> dict[str, Any]:
    """Walk future bars bar-by-bar; return first SL or TP hit."""
    for i, bar in enumerate(future_bars):
        high = bar["high"]
        low  = bar["low"]
        if direction == "long":
            if low  <= sl: return {"exit": sl,  "trigger": "SL", "bars_held": i + 1}
            if high >= tp: return {"exit": tp,  "trigger": "TP", "bars_held": i + 1}
        else:
            if high >= sl: return {"exit": sl,  "trigger": "SL", "bars_held": i + 1}
            if low  <= tp: return {"exit": tp,  "trigger": "TP", "bars_held": i + 1}
    # Horizon close
    last = future_bars[-1]["close"] if future_bars else entry
    return {"exit": last, "trigger": "horizon", "bars_held": len(future_bars)}


# ── Main backtest ─────────────────────────────────────────────────────────────

def load_bars(db_path: str, symbol: str = "SOL-PERP") -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT candle_open_utc, open, high, low, close, tick_count, volume_base "
        "FROM market_bars_5m WHERE canonical_symbol=? ORDER BY candle_open_utc",
        (symbol,)
    ).fetchall()
    conn.close()
    bars = []
    for r in rows:
        bars.append({
            "ts_str": r["candle_open_utc"],
            "ts": datetime.fromisoformat(r["candle_open_utc"].replace("Z", "+00:00")),
            "open":   float(r["open"]  or 0),
            "high":   float(r["high"]  or 0),
            "low":    float(r["low"]   or 0),
            "close":  float(r["close"] or 0),
            "volume": float(r["volume_base"] or r["tick_count"] or 0),
        })
    return bars


def rollup_to_15m(bars_5m: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate 5m bars into 15m bars."""
    buckets: dict[str, list] = {}
    for b in bars_5m:
        dt = b["ts"]
        mins = (dt.minute // 15) * 15
        key = dt.strftime(f"%Y-%m-%dT%H:{mins:02d}:00Z")
        buckets.setdefault(key, []).append(b)
    result = []
    for key in sorted(buckets):
        chunk = buckets[key]
        result.append({
            "ts_str": key,
            "ts": datetime.fromisoformat(key.replace("Z", "+00:00")),
            "open":   chunk[0]["open"],
            "high":   max(b["high"]   for b in chunk),
            "low":    min(b["low"]    for b in chunk),
            "close":  chunk[-1]["close"],
            "volume": sum(b["volume"] for b in chunk),
        })
    return result


def run_backtest(
    bars: list[dict[str, Any]],
    apply_filters: bool = True,
    min_confidence: int = 8,
    horizon_bars: int = 20,
) -> dict[str, Any]:
    closes  = [b["close"]  for b in bars]
    highs   = [b["high"]   for b in bars]
    lows    = [b["low"]    for b in bars]
    volumes = [b["volume"] for b in bars]

    ema9_vals  = ema(closes, EMA_SHORT)
    ema21_vals = ema(closes, EMA_LONG)
    rsi_vals   = rsi(closes, RSI_PERIOD)
    atr_vals   = atr(closes, highs, lows, ATR_PERIOD)

    avg_vol = sum(v for v in volumes if v > 0) / max(1, sum(1 for v in volumes if v > 0))

    # Rolling 50-bar average volume
    def rolling_avg_vol(i: int) -> float:
        window = [volumes[j] for j in range(max(0, i - 50), i) if volumes[j] > 0]
        return sum(window) / max(1, len(window))

    long_bias: bool | None = None
    trades: list[dict[str, Any]] = []
    signals_found = 0
    blocked = {"confidence": 0, "bias": 0, "volume": 0, "session": 0, "rsi_guard": 0, "no_bias": 0}

    warmup = max(EMA_LONG, RSI_PERIOD, ATR_PERIOD) + 5

    for i in range(warmup, len(bars) - horizon_bars):
        e9   = ema9_vals[i]
        e21  = ema21_vals[i]
        e9p  = ema9_vals[i - 1]
        e21p = ema21_vals[i - 1]
        if any(math.isnan(v) for v in [e9, e21, e9p, e21p]):
            continue

        # Update bias on crossover
        if e9p <= e21p and e9 > e21:
            long_bias = True
        elif e9p >= e21p and e9 < e21:
            long_bias = False

        # Divergence signal
        cur_rsi  = rsi_vals[i]
        prev_rsi = rsi_vals[i - 1]
        cur_atr  = atr_vals[i]
        if any(math.isnan(v) for v in [cur_rsi, prev_rsi, cur_atr]):
            continue

        bull_div = (lows[i] < lows[i - 1]) and (cur_rsi > prev_rsi)
        bear_div = (highs[i] > highs[i - 1]) and (cur_rsi < prev_rsi)

        long_sig  = (long_bias is True)  and bull_div
        short_sig = (long_bias is False) and bear_div

        if not long_sig and not short_sig:
            continue

        signals_found += 1
        direction = "long" if long_sig else "short"
        ts = bars[i]["ts"]
        entry = closes[i]

        if not apply_filters:
            # Raw signal — no filters
            pass
        else:
            # Filter: session / weekend
            blocked_sess, sess_reason = is_blocked_session(ts)
            if blocked_sess:
                blocked["session"] += 1
                continue

            # Filter: bias not established
            if long_bias is None:
                blocked["no_bias"] += 1
                continue

            # Filter: confidence score
            avg_v = rolling_avg_vol(i)
            conf = confidence_score(
                long_sig,
                cur_rsi, prev_rsi,
                lows[i], lows[i - 1],
                highs[i], highs[i - 1],
                avg_v, volumes[i],
            )
            if conf < min_confidence:
                blocked["confidence"] += 1
                continue

            # Filter: volume >= 115% of avg
            if avg_v > 0 and volumes[i] < avg_v * 1.15:
                blocked["volume"] += 1
                continue

            # Filter: RSI guard
            if long_sig and cur_rsi > 68:
                blocked["rsi_guard"] += 1
                continue
            if short_sig and cur_rsi < 32:
                blocked["rsi_guard"] += 1
                continue
        else:
            conf = confidence_score(
                long_sig, cur_rsi, prev_rsi,
                lows[i], lows[i - 1],
                highs[i], highs[i - 1],
                rolling_avg_vol(i), volumes[i],
            )

        # Position sizing
        min_dist = entry * 0.007
        sl_dist  = max(cur_atr * SL_ATR_MULT, min_dist)
        if direction == "long":
            sl = entry - sl_dist - SPREAD_BUFFER_PCT * entry
            tp = entry + TP_R_MULT * sl_dist
        else:
            sl = entry + sl_dist + SPREAD_BUFFER_PCT * entry
            tp = entry - TP_R_MULT * sl_dist

        r_multiple = (abs(tp - entry) / abs(sl - entry)) if abs(sl - entry) > 0 else 0

        future = bars[i + 1: i + 1 + horizon_bars]
        exit_info = simulate_exit(direction, entry, sl, tp, future)
        exit_price = exit_info["exit"]
        trigger    = exit_info["trigger"]

        if direction == "long":
            pnl_pct = (exit_price - entry) / entry
        else:
            pnl_pct = (entry - exit_price) / entry

        gross_pnl = pnl_pct * LEVERAGE * SIMULATED_COLLATERAL_USD
        net_pnl   = gross_pnl - ROUND_TRIP_FEE_USD
        won = trigger == "TP"

        trades.append({
            "timestamp":  bars[i]["ts_str"],
            "direction":  direction,
            "entry":      round(entry, 6),
            "sl":         round(sl, 6),
            "tp":         round(tp, 6),
            "r_multiple": round(r_multiple, 3),
            "atr":        round(cur_atr, 6),
            "rsi":        round(cur_rsi, 2),
            "confidence": conf if apply_filters else conf,
            "exit_price": round(exit_price, 6),
            "trigger":    trigger,
            "bars_held":  exit_info["bars_held"],
            "gross_pnl":  round(gross_pnl, 4),
            "net_pnl":    round(net_pnl, 4),
            "win":        won,
        })

    return {
        "bars_analyzed": len(bars) - warmup - horizon_bars,
        "signals_found": signals_found,
        "blocked": blocked,
        "trades": trades,
    }


def print_report(result: dict[str, Any], label: str) -> None:
    trades = result["trades"]
    n = len(trades)
    wins   = sum(1 for t in trades if t["win"])
    losses = n - wins
    win_rate = wins / n if n else 0.0
    gross_total = sum(t["gross_pnl"] for t in trades)
    net_total   = sum(t["net_pnl"]   for t in trades)
    avg_win_pnl  = sum(t["net_pnl"] for t in trades if t["win"])  / max(wins, 1)
    avg_loss_pnl = sum(t["net_pnl"] for t in trades if not t["win"]) / max(losses, 1)
    expectancy   = (win_rate * avg_win_pnl) + ((1 - win_rate) * avg_loss_pnl)
    avg_r = sum(t["r_multiple"] for t in trades) / max(n, 1)
    breakeven_wr = 1 / (1 + avg_r) if avg_r > 0 else 0.5
    avg_bars = sum(t["bars_held"] for t in trades) / max(n, 1)
    tp_exits = sum(1 for t in trades if t["trigger"] == "TP")
    sl_exits = sum(1 for t in trades if t["trigger"] == "SL")
    hz_exits = sum(1 for t in trades if t["trigger"] == "horizon")

    longs  = [t for t in trades if t["direction"] == "long"]
    shorts = [t for t in trades if t["direction"] == "short"]
    long_wr  = sum(1 for t in longs  if t["win"]) / max(len(longs),  1)
    short_wr = sum(1 for t in shorts if t["win"]) / max(len(shorts), 1)

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Bars analyzed    : {result['bars_analyzed']:,}")
    print(f"  Raw signals      : {result['signals_found']:,}")
    if result["blocked"]:
        b = result["blocked"]
        print(f"  Blocked (session): {b.get('session',0)}")
        print(f"  Blocked (conf<8) : {b.get('confidence',0)}")
        print(f"  Blocked (volume) : {b.get('volume',0)}")
        print(f"  Blocked (bias)   : {b.get('no_bias',0)}")
        print(f"  Blocked (rsi grd): {b.get('rsi_guard',0)}")
    print(f"  Trades taken     : {n}")
    if n == 0:
        print("  No trades — cannot compute stats.")
        return
    print(f"")
    print(f"  ── Outcomes ──────────────────────────────")
    print(f"  Wins             : {wins}  ({win_rate:.1%})")
    print(f"  Losses           : {losses}")
    print(f"  TP exits         : {tp_exits}")
    print(f"  SL exits         : {sl_exits}")
    print(f"  Horizon exits    : {hz_exits}")
    print(f"  Avg hold (bars)  : {avg_bars:.1f} x15m = {avg_bars*15/60:.1f}h")
    print(f"")
    print(f"  ── P&L (simulated ${SIMULATED_COLLATERAL_USD} collateral, {LEVERAGE}x) ──")
    print(f"  Gross PnL total  : ${gross_total:+.2f}")
    print(f"  Net PnL total    : ${net_total:+.2f}")
    print(f"  Avg win  (net)   : ${avg_win_pnl:+.2f}")
    print(f"  Avg loss (net)   : ${avg_loss_pnl:+.2f}")
    print(f"  Expectancy/trade : ${expectancy:+.2f}")
    print(f"")
    print(f"  ── Risk/Reward ───────────────────────────")
    print(f"  Avg R-multiple   : {avg_r:.2f}")
    print(f"  Breakeven WR     : {breakeven_wr:.1%}  (at avg R={avg_r:.2f})")
    print(f"  Actual WR        : {win_rate:.1%}  {'✓ ABOVE breakeven' if win_rate > breakeven_wr else '✗ BELOW breakeven'}")
    print(f"")
    print(f"  ── By direction ──────────────────────────")
    print(f"  Long  : {len(longs):3d} trades | WR {long_wr:.1%}")
    print(f"  Short : {len(shorts):3d} trades | WR {short_wr:.1%}")
    print(f"")
    print(f"  ── Verdict ───────────────────────────────")
    if net_total > 0 and win_rate > breakeven_wr:
        print(f"  POSITIVE EXPECTANCY — signal has historical edge")
    elif net_total > 0:
        print(f"  NET PROFITABLE but win rate below breakeven (fee drag or skewed R)")
    else:
        print(f"  NEGATIVE EXPECTANCY — signal does NOT have historical edge at this threshold")
    if n < 30:
        print(f"  ⚠️  SAMPLE SIZE WARNING: {n} trades is too small for statistical significance")
        print(f"     Need 30+ trades. Current result could be luck in either direction.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sean EMA Bot Signal Backtest")
    parser.add_argument("--db", required=True, help="Path to SQLite market_data.db")
    parser.add_argument("--symbol", default="SOL-PERP")
    parser.add_argument("--no-filters", action="store_true",
                        help="Run without session/confidence/volume filters")
    parser.add_argument("--min-confidence", type=int, default=8,
                        help="Minimum confidence score threshold (default: 8)")
    parser.add_argument("--horizon", type=int, default=20,
                        help="Max bars to hold before horizon exit (default: 20 = 5 hours)")
    args = parser.parse_args()

    print(f"Loading {args.symbol} bars from {args.db}...")
    bars_5m = load_bars(args.db, args.symbol)
    print(f"Loaded {len(bars_5m)} 5m bars → rolling up to 15m...")
    bars_15m = rollup_to_15m(bars_5m)
    print(f"Got {len(bars_15m)} 15m bars | "
          f"{bars_15m[0]['ts_str'] if bars_15m else '?'} → "
          f"{bars_15m[-1]['ts_str'] if bars_15m else '?'}")

    # Run with all filters (Sean's production mode)
    result_filtered = run_backtest(
        bars_15m,
        apply_filters=True,
        min_confidence=args.min_confidence,
        horizon_bars=args.horizon,
    )
    print_report(result_filtered, f"Sean's signal — FILTERED (confidence >= {args.min_confidence})")

    if not args.no_filters:
        # Also run without session/weekend filters to see the underlying signal
        result_raw = run_backtest(
            bars_15m,
            apply_filters=False,
            min_confidence=0,  # all signals
            horizon_bars=args.horizon,
        )
        print_report(result_raw, "Sean's signal — RAW (no filters, all divergence signals)")

        # Run at confidence >= 7 to compare his old threshold
        result_7 = run_backtest(
            bars_15m,
            apply_filters=True,
            min_confidence=7,
            horizon_bars=args.horizon,
        )
        print_report(result_7, "Sean's signal — confidence >= 7 (old threshold for comparison)")


if __name__ == "__main__":
    main()
