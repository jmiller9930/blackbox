"""
FinQuant Unified Agent Lab — Market Data Bridge.

Reads canonical market bars from a SQLite database and packages them as
finquant_lifecycle_case_v1 JSON files for use in the agent lab.

Supports:
  - market_bars_5m schema (canonical 5m bars from Pyth ingest)
  - Roll-up from 5m to any N-minute window (e.g. 15m = 3 bars per window)
  - Computes RSI(14), EMA(20), ATR(14) from bar data
  - Splits data into seed period and held-out test period

No-lookahead guarantee:
  Each lifecycle case exposes only candles up to the decision point.
  Outcome candles are placed beyond hidden_future_start_index.

Usage (from repo root):
  python finquant/unified/agent_lab/market_data_bridge.py \\
    --db /path/to/market_data.db \\
    --symbol SOL-USD \\
    --interval 15 \\
    --months 18 \\
    --seed-months 12 \\
    --cases-dir finquant/unified/agent_lab/cases/market \\
    --context-candles 20 \\
    --decision-steps 3
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Bar fetch
# ---------------------------------------------------------------------------

MARKET_BARS_5M_QUERY = """
SELECT
    candle_open_utc,
    open,
    high,
    low,
    close,
    tick_count,
    volume_base
FROM market_bars_5m
WHERE canonical_symbol = ?
  AND candle_open_utc >= ?
  AND candle_open_utc < ?
ORDER BY candle_open_utc ASC
"""

MARKET_TICKS_QUERY = """
SELECT
    primary_observed_at,
    primary_price,
    primary_price AS close
FROM market_ticks
WHERE symbol = ?
  AND primary_observed_at >= ?
  AND primary_observed_at < ?
ORDER BY primary_observed_at ASC
"""


def fetch_5m_bars(
    db_path: str,
    symbol: str,
    from_utc: str,
    to_utc: str,
) -> list[dict[str, Any]]:
    """Fetch canonical 5m bars from market_bars_5m table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(MARKET_BARS_5M_QUERY, (symbol, from_utc, to_utc))
        rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "timestamp": row["candle_open_utc"],
            "open": float(row["open"] or 0.0),
            "high": float(row["high"] or 0.0),
            "low": float(row["low"] or 0.0),
            "close": float(row["close"] or 0.0),
            "volume": float(row["volume_base"] or row["tick_count"] or 0.0),
        }
        for row in rows
    ]


def fetch_ticks_as_bars(
    db_path: str,
    symbol: str,
    from_utc: str,
    to_utc: str,
    bar_minutes: int = 5,
) -> list[dict[str, Any]]:
    """Aggregate raw ticks into pseudo-bars (fallback for proof DBs)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(MARKET_TICKS_QUERY, (symbol, from_utc, to_utc))
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    buckets: dict[str, list[float]] = {}
    for row in rows:
        ts = row["primary_observed_at"]
        price = float(row["primary_price"] or 0.0)
        if ts and price:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                mins = (dt.hour * 60 + dt.minute) // bar_minutes * bar_minutes
                bucket_key = dt.strftime(f"%Y-%m-%dT%H:{mins:02d}:00Z")
            except Exception:
                bucket_key = str(ts)[:16]
            buckets.setdefault(bucket_key, []).append(price)

    bars = []
    for ts_key in sorted(buckets):
        prices = buckets[ts_key]
        bars.append({
            "timestamp": ts_key,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": float(len(prices)),
        })
    return bars


# ---------------------------------------------------------------------------
# Roll-up 5m → Nm
# ---------------------------------------------------------------------------

def rollup_bars(bars_5m: list[dict], target_minutes: int) -> list[dict[str, Any]]:
    """Aggregate 5m bars into target_minutes bars."""
    if target_minutes <= 5:
        return bars_5m

    step = target_minutes // 5
    rolled: list[dict[str, Any]] = []
    for i in range(0, len(bars_5m), step):
        chunk = bars_5m[i:i + step]
        if not chunk:
            continue
        rolled.append({
            "timestamp": chunk[0]["timestamp"],
            "open": chunk[0]["open"],
            "high": max(b["high"] for b in chunk),
            "low": min(b["low"] for b in chunk),
            "close": chunk[-1]["close"],
            "volume": sum(b["volume"] for b in chunk),
        })
    return rolled


# ---------------------------------------------------------------------------
# Indicator computation
# ---------------------------------------------------------------------------

def compute_indicators(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add rsi_14, ema_20, atr_14 to each bar in place. Returns enriched bars."""
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]

    ema20 = _ema(closes, 20)
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)

    for i, bar in enumerate(bars):
        bar["rsi_14"] = round(rsi14[i], 4) if rsi14[i] is not None else None
        bar["ema_20"] = round(ema20[i], 4) if ema20[i] is not None else None
        bar["atr_14"] = round(atr14[i], 4) if atr14[i] is not None else None

    return bars


def _ema(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    k = 2.0 / (period + 1)
    ema_val: float | None = None
    for i, v in enumerate(values):
        if ema_val is None:
            if i + 1 >= period:
                ema_val = sum(values[i - period + 1:i + 1]) / period
                result[i] = ema_val
        else:
            ema_val = v * k + ema_val * (1 - k)
            result[i] = ema_val
    return result


def _rsi(closes: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(closes)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = round(100 - (100 / (1 + rs)), 4)
    return result


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return result
    atr_val = sum(trs[:period]) / period
    result[period] = round(atr_val, 4)
    for i in range(period + 1, len(closes)):
        atr_val = (atr_val * (period - 1) + trs[i - 1]) / period
        result[i] = round(atr_val, 4)
    return result


# ---------------------------------------------------------------------------
# Case packing
# ---------------------------------------------------------------------------

def pack_lifecycle_case(
    bars: list[dict[str, Any]],
    *,
    case_id: str,
    symbol: str,
    timeframe_minutes: int,
    context_candles: int = 20,
    decision_steps: int = 3,
    outcome_candles: int = 5,
    expected_learning_focus: list[str] | None = None,
) -> dict[str, Any]:
    """
    Package a slice of bars as a finquant_lifecycle_case_v1.

    Layout:
      bars[0..context_candles-1]          — context (always visible)
      bars[context_candles..decision_end]  — decision window (revealed step by step)
      bars[decision_end+1..]               — outcome (hidden during decisions)
    """
    total_needed = context_candles + decision_steps + outcome_candles
    if len(bars) < total_needed:
        raise ValueError(
            f"Not enough bars: need {total_needed}, got {len(bars)}"
        )

    decision_start = context_candles
    decision_end = context_candles + decision_steps - 1
    hidden_from = decision_end + 1

    return {
        "schema": "finquant_lifecycle_case_v1",
        "case_id": case_id,
        "symbol": symbol,
        "timeframe_minutes": timeframe_minutes,
        "description": f"Market case from {bars[0]['timestamp']} over {timeframe_minutes}m bars.",
        "decision_start_index": decision_start,
        "decision_end_index": decision_end,
        "hidden_future_start_index": hidden_from,
        "expected_learning_focus_v1": expected_learning_focus or ["entry_quality"],
        "candles": bars[:hidden_from + outcome_candles],
    }


def generate_cases_from_bars(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    timeframe_minutes: int,
    case_prefix: str,
    context_candles: int = 20,
    decision_steps: int = 3,
    outcome_candles: int = 5,
    stride: int | None = None,
    expected_learning_focus: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Slice bars into overlapping lifecycle cases with a stride window."""
    window = context_candles + decision_steps + outcome_candles
    if stride is None:
        stride = decision_steps  # non-overlapping by default

    cases = []
    i = 0
    case_idx = 0
    while i + window <= len(bars):
        bar_slice = bars[i:i + window]
        case_id = f"{case_prefix}_{case_idx:04d}_{bar_slice[0]['timestamp'][:10].replace('-', '')}"
        try:
            case = pack_lifecycle_case(
                bar_slice,
                case_id=case_id,
                symbol=symbol,
                timeframe_minutes=timeframe_minutes,
                context_candles=context_candles,
                decision_steps=decision_steps,
                outcome_candles=outcome_candles,
                expected_learning_focus=expected_learning_focus,
            )
            cases.append(case)
        except ValueError:
            pass
        i += stride
        case_idx += 1

    return cases


# ---------------------------------------------------------------------------
# Main bridge runner
# ---------------------------------------------------------------------------

def run_bridge(
    *,
    db_path: str,
    symbol: str,
    interval_minutes: int,
    months_total: int,
    seed_months: int,
    cases_dir: str,
    context_candles: int = 20,
    decision_steps: int = 3,
    outcome_candles: int = 5,
    stride: int | None = None,
    table: str = "market_bars_5m",
) -> dict[str, Any]:
    """
    Full pipeline: fetch → rollup → indicators → split → pack cases → write JSON.

    Returns a manifest dict describing what was written.
    """
    now = datetime.now(timezone.utc)
    to_dt = now
    from_dt = now - timedelta(days=months_total * 30)
    seed_boundary_dt = now - timedelta(days=(months_total - seed_months) * 30)

    from_str = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_str = to_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    seed_boundary_str = seed_boundary_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"[bridge] fetching {symbol} from {from_str} to {to_str}")

    # Detect table and fetch
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    available_tables = {r[0] for r in cur.fetchall()}
    conn.close()

    if table in available_tables:
        raw_bars = fetch_5m_bars(db_path, symbol, from_str, to_str)
        print(f"[bridge] fetched {len(raw_bars)} 5m bars from {table}")
    elif "market_ticks" in available_tables:
        raw_bars = fetch_ticks_as_bars(db_path, symbol, from_str, to_str, bar_minutes=5)
        print(f"[bridge] fetched {len(raw_bars)} pseudo-bars from market_ticks")
    else:
        raise ValueError(f"No usable table found in {db_path}. Available: {available_tables}")

    if not raw_bars:
        raise ValueError(f"No bars returned for {symbol} in the requested date range.")

    rolled = rollup_bars(raw_bars, interval_minutes)
    print(f"[bridge] rolled to {interval_minutes}m: {len(rolled)} bars")

    enriched = compute_indicators(rolled)
    print(f"[bridge] indicators computed")

    # Split seed vs test
    seed_bars = [b for b in enriched if b["timestamp"] < seed_boundary_str]
    test_bars = [b for b in enriched if b["timestamp"] >= seed_boundary_str]
    print(f"[bridge] seed bars: {len(seed_bars)}  test bars: {len(test_bars)}")

    cases_path = Path(cases_dir)
    cases_path.mkdir(parents=True, exist_ok=True)

    seed_cases = generate_cases_from_bars(
        seed_bars,
        symbol=symbol,
        timeframe_minutes=interval_minutes,
        case_prefix=f"seed_{symbol.lower().replace('-', '')}_{interval_minutes}m",
        context_candles=context_candles,
        decision_steps=decision_steps,
        outcome_candles=outcome_candles,
        stride=stride,
        expected_learning_focus=["entry_quality", "exit_quality"],
    )

    test_cases = generate_cases_from_bars(
        test_bars,
        symbol=symbol,
        timeframe_minutes=interval_minutes,
        case_prefix=f"test_{symbol.lower().replace('-', '')}_{interval_minutes}m",
        context_candles=context_candles,
        decision_steps=decision_steps,
        outcome_candles=outcome_candles,
        stride=stride,
        expected_learning_focus=["entry_quality"],
    )

    seed_paths, test_paths = [], []
    for case in seed_cases:
        p = cases_path / f"{case['case_id']}.json"
        with open(p, "w") as f:
            json.dump(case, f, indent=2)
        seed_paths.append(str(p))

    for case in test_cases:
        p = cases_path / f"{case['case_id']}.json"
        with open(p, "w") as f:
            json.dump(case, f, indent=2)
        test_paths.append(str(p))

    manifest = {
        "schema": "finquant_market_bridge_manifest_v1",
        "db_path": db_path,
        "symbol": symbol,
        "interval_minutes": interval_minutes,
        "months_total": months_total,
        "seed_months": seed_months,
        "from_utc": from_str,
        "to_utc": to_str,
        "seed_boundary_utc": seed_boundary_str,
        "seed_cases_count": len(seed_cases),
        "test_cases_count": len(test_cases),
        "seed_case_paths": seed_paths,
        "test_case_paths": test_paths,
        "cases_dir": str(cases_path),
    }

    manifest_path = cases_path / "bridge_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[bridge] wrote {len(seed_cases)} seed cases and {len(test_cases)} test cases to {cases_path}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant market data bridge — SQL → lifecycle cases")
    parser.add_argument("--db", required=True, help="Path to SQLite market database")
    parser.add_argument("--symbol", default="SOL-USD", help="Symbol (e.g. SOL-USD)")
    parser.add_argument("--interval", type=int, default=15, help="Target candle interval in minutes (default 15)")
    parser.add_argument("--months", type=int, default=18, help="Total months of data to use")
    parser.add_argument("--seed-months", type=int, default=12, help="Months to use for seed period (remainder = test)")
    parser.add_argument("--cases-dir", default="finquant/unified/agent_lab/cases/market", help="Output directory for case JSON files")
    parser.add_argument("--context-candles", type=int, default=20, help="Candles of context before decision window")
    parser.add_argument("--decision-steps", type=int, default=3, help="Number of decision steps per case")
    parser.add_argument("--outcome-candles", type=int, default=5, help="Outcome candles after decision window")
    parser.add_argument("--stride", type=int, default=None, help="Stride between cases (default = decision-steps)")
    parser.add_argument("--table", default="market_bars_5m", help="Source table name")
    args = parser.parse_args()

    manifest = run_bridge(
        db_path=args.db,
        symbol=args.symbol,
        interval_minutes=args.interval,
        months_total=args.months,
        seed_months=args.seed_months,
        cases_dir=args.cases_dir,
        context_candles=args.context_candles,
        decision_steps=args.decision_steps,
        outcome_candles=args.outcome_candles,
        stride=args.stride,
        table=args.table,
    )
    print(json.dumps({
        "seed_cases": manifest["seed_cases_count"],
        "test_cases": manifest["test_cases_count"],
        "cases_dir": manifest["cases_dir"],
    }, indent=2))


if __name__ == "__main__":
    main()
