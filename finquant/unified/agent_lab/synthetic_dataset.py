"""
FinQuant Unified Agent Lab — Synthetic Dataset Generator

Builds a deterministic synthetic 15m candle dataset for proving the
Probabilistic Pattern Learning Engine end to end without requiring the
clawbot SQL database.

The generator stitches together regime "blocks":
  - bull_trend  : steady upward drift with expanding volume
  - bear_trend  : steady downward drift
  - chop        : narrow range with low volatility
  - breakout    : sharp move beyond recent range
  - false_break : breakout that immediately reverses

Each block is converted to a finquant_lifecycle_case_v1 case with a
hidden future segment for outcome falsification.

Usage:
  python finquant/unified/agent_lab/synthetic_dataset.py \\
      --out finquant/unified/agent_lab/cases/synthetic_btc_15m \\
      --case-count 60 \\
      --seed 1729
"""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

REGIMES = ["bull_trend", "bear_trend", "chop", "breakout", "false_break", "marginal_long"]


def _candle(
    timestamp: str,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float,
    rsi: float,
    ema: float,
    atr: float,
    resistance: float | None = None,
) -> dict[str, Any]:
    bar = {
        "timestamp": timestamp,
        "open": round(o, 4),
        "high": round(h, 4),
        "low": round(l, 4),
        "close": round(c, 4),
        "volume": round(v, 2),
        "rsi_14": round(rsi, 2),
        "ema_20": round(ema, 4),
        "atr_14": round(atr, 4),
    }
    if resistance is not None:
        bar["resistance_level"] = round(resistance, 4)
    return bar


def _generate_block(
    regime: str,
    *,
    rng: random.Random,
    start_price: float,
    start_time: datetime,
    bar_minutes: int = 15,
) -> tuple[list[dict[str, Any]], float, datetime]:
    """
    Produce a list of bars for a single regime block.
    Returns (bars, end_price, end_time).
    """
    if regime == "bull_trend":
        return _bull_trend(rng, start_price, start_time, bar_minutes)
    if regime == "bear_trend":
        return _bear_trend(rng, start_price, start_time, bar_minutes)
    if regime == "chop":
        return _chop(rng, start_price, start_time, bar_minutes)
    if regime == "breakout":
        return _breakout(rng, start_price, start_time, bar_minutes)
    if regime == "false_break":
        return _false_break(rng, start_price, start_time, bar_minutes)
    if regime == "marginal_long":
        return _marginal_long(rng, start_price, start_time, bar_minutes)
    raise ValueError(f"unknown regime: {regime}")


def _bull_trend(rng, start_price, start_time, bar_minutes):
    bars = []
    price = start_price
    ema = price
    # Start ATR high enough to stay above the stub's atr_expand=1.5 threshold.
    # Floor bar ranges at 2.0 so ATR does not converge below 1.8 by bar 20.
    atr = 2.5 + rng.random() * 0.5
    for i in range(28):
        drift = 0.6 + rng.random() * 0.6
        noise = (rng.random() - 0.45) * 0.6
        new_close = max(1.0, price + drift + noise)
        h = max(price, new_close) + 1.5 + rng.random() * 0.5
        l = min(price, new_close) - 1.2 - rng.random() * 0.3
        # Monotonically increasing volume: trend component (150/bar) dominates noise (100)
        # so current bar always has higher volume than the previous bar.
        v = 2000 + i * 150 + rng.random() * 100
        rsi = min(76, 52 + i * 0.65 + rng.random() * 2)
        ema = ema * 0.85 + new_close * 0.15
        # Keep ATR floored at 2.0 so it stays above the stub's 1.5 threshold.
        atr = atr * 0.9 + max(h - l, 2.0) * 0.1
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr,
        ))
        price = new_close
    return bars, price, start_time + timedelta(minutes=bar_minutes * 28)


def _bear_trend(rng, start_price, start_time, bar_minutes):
    bars = []
    price = start_price
    ema = price
    atr = 1.5 + rng.random() * 0.6
    for i in range(28):
        drift = -(0.4 + rng.random() * 0.5)
        noise = (rng.random() - 0.55) * 0.6
        new_close = max(1.0, price + drift + noise)
        h = max(price, new_close) + abs(rng.random() * 0.25)
        l = min(price, new_close) - abs(rng.random() * 0.3)
        v = 1500 + i * 50 + rng.random() * 400
        rsi = max(22, 48 - i * 0.7 + rng.random() * 2)
        ema = ema * 0.85 + new_close * 0.15
        atr = atr * 0.9 + max(h - l, 0.5) * 0.1
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr,
        ))
        price = new_close
    return bars, price, start_time + timedelta(minutes=bar_minutes * 28)


def _chop(rng, start_price, start_time, bar_minutes):
    bars = []
    price = start_price
    ema = price
    atr = 0.6 + rng.random() * 0.3
    for i in range(28):
        new_close = price + (rng.random() - 0.5) * 0.6
        h = max(price, new_close) + abs(rng.random() * 0.2)
        l = min(price, new_close) - abs(rng.random() * 0.2)
        v = 600 + rng.random() * 250
        rsi = 50 + (rng.random() - 0.5) * 6
        ema = ema * 0.9 + new_close * 0.1
        atr = atr * 0.92 + max(h - l, 0.3) * 0.08
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr,
        ))
        price = new_close
    return bars, price, start_time + timedelta(minutes=bar_minutes * 28)


def _breakout(rng, start_price, start_time, bar_minutes):
    bars = []
    price = start_price
    ema = price
    # Start ATR higher so it's above 1.5 when the breakout bars arrive.
    atr = 2.0
    resistance = price + 2.5
    # 18 bars of consolidation — maintain ATR floor at 1.8 to stay above 1.5 at bar 20.
    for i in range(18):
        new_close = price + (rng.random() - 0.5) * 0.5
        h = max(price, new_close) + 1.2
        l = min(price, new_close) - 1.2
        v = 700 + rng.random() * 300
        rsi = 50 + (rng.random() - 0.5) * 4
        ema = ema * 0.9 + new_close * 0.1
        atr = atr * 0.95 + max(h - l, 2.0) * 0.05
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr, resistance=resistance,
        ))
        price = new_close
    # 10 bars of breakout: price clears resistance, volume surges, RSI rises above 58.
    for j in range(10):
        i = 18 + j
        new_close = price + 0.8 + rng.random() * 0.5
        h = new_close + 1.2
        l = price - 0.3
        v = 3500 + rng.random() * 1000
        rsi = min(73, 62 + j * 1.0)
        ema = ema * 0.85 + new_close * 0.15
        atr = atr * 0.85 + max(h - l, 2.0) * 0.15
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr, resistance=resistance,
        ))
        price = new_close
    return bars, price, start_time + timedelta(minutes=bar_minutes * 28)


def _false_break(rng, start_price, start_time, bar_minutes):
    bars = []
    price = start_price
    ema = price
    atr = 1.0
    resistance = price + 2.0
    # 15 bars of consolidation
    for i in range(15):
        new_close = price + (rng.random() - 0.5) * 0.5
        h = max(price, new_close) + 0.2
        l = min(price, new_close) - 0.2
        v = 800 + rng.random() * 300
        rsi = 50 + (rng.random() - 0.5) * 4
        ema = ema * 0.9 + new_close * 0.1
        atr = atr * 0.95 + max(h - l, 0.3) * 0.05
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr, resistance=resistance,
        ))
        price = new_close
    # 3 bars of breakout
    for j in range(3):
        i = 15 + j
        new_close = price + 0.6 + rng.random() * 0.5
        h = new_close + 0.3
        l = price
        v = 3500 + rng.random() * 1000
        rsi = 65 + j * 0.5
        ema = ema * 0.85 + new_close * 0.15
        atr = atr * 0.8 + (h - l) * 0.2
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr, resistance=resistance,
        ))
        price = new_close
    # 10 bars of reversal back below resistance
    for j in range(10):
        i = 18 + j
        new_close = price - 0.5 - rng.random() * 0.5
        h = price + 0.1
        l = new_close - 0.3
        v = 2200 + rng.random() * 800
        rsi = max(35, 60 - j * 2.2)
        ema = ema * 0.85 + new_close * 0.15
        atr = atr * 0.85 + max(h - l, 1.0) * 0.15
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr, resistance=resistance,
        ))
        price = new_close
    return bars, price, start_time + timedelta(minutes=bar_minutes * 28)


def _marginal_long(rng, start_price, start_time, bar_minutes):
    """
    Near-threshold uptrend: ATR converges to ~1.3 (BELOW the 1.5 atr_expand threshold,
    ABOVE the 1.0 chop threshold AND the 1.2 near-threshold floor).
    Volume grows 7%/bar so near_threshold_long volume check (>= prev*1.05) always passes.

    Without retrieved ENTER_LONG memory:
      price_up=T, rsi_ok=T, volume_expand=T, atr_expand=F → main entry fails.
      memory_available=F → memory branch skipped.
      avg_move >= 0.7 (drift floor), atr >= 1.0 → not chop.
      → DEFAULT: NO_TRADE ("Conditions not met").

    With retrieved ENTER_LONG memory (cycle 2+):
      near_threshold_long=T (price_up, ema, rsi>=52, atr>=1.2, vol>=prev*1.05).
      memory_available=T, memory_long>0 → ENTER_LONG.

    This is the core 'memory flip' pattern for the training loop.
    """
    bars = []
    price = start_price
    # EMA starts behind price so close > ema throughout.
    ema = price * 0.97
    # Target ATR: 0.65-0.80% of price — above ATR_NEAR_PCT (0.5%) but below ATR_EXPAND_PCT (1.0%).
    # At start_price=100: ATR target = $0.70.
    atr = start_price * 0.0070
    vol = 1200.0
    for i in range(28):
        # Drift floor 0.25% of price so avg_move is clearly above MOVE_CHOP_PCT (0.2%).
        drift = start_price * 0.0030 + rng.random() * start_price * 0.0010
        new_close = max(1.0, price + drift)
        # Bar range sized to keep ATR at 0.65-0.80% of price.
        bar_range_target = start_price * 0.0070
        h = new_close + bar_range_target * 0.25 + rng.random() * bar_range_target * 0.05
        l = price - bar_range_target * 0.20 - rng.random() * bar_range_target * 0.05
        # Geometric 7% volume growth guarantees >= 5% increase per bar (near_threshold check).
        vol = vol * 1.07 * (1.0 + (rng.random() - 0.5) * 0.01)
        rsi = min(67, 52 + i * 0.55 + rng.random() * 1.0)
        ema = ema * 0.92 + new_close * 0.08
        atr = atr * 0.92 + max(h - l, bar_range_target) * 0.08
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, vol, rsi, ema, atr,
        ))
        price = new_close
    return bars, price, start_time + timedelta(minutes=bar_minutes * 28)


def build_case_from_block(
    *,
    bars: list[dict[str, Any]],
    case_id: str,
    regime: str,
    symbol: str = "BTC-PERP",
    timeframe_minutes: int = 15,
    decision_steps: int = 1,
    context_candles: int = 20,
    outcome_candles: int = 7,
) -> dict[str, Any]:
    expected_focus = {
        "bull_trend": ["entry_quality"],
        # Bear trend: stub has no short logic; standing down is correct.
        "bear_trend": ["no_trade_quality"],
        "chop": ["no_trade_quality"],
        "breakout": ["entry_quality"],
        # False breakout reverses; standing down after chop is correct.
        "false_break": ["no_trade_quality"],
        # Marginal: memory-needed entry; evaluation expects entry_quality.
        "marginal_long": ["entry_quality"],
    }.get(regime, ["entry_quality"])

    decision_start = context_candles
    decision_end = context_candles + decision_steps - 1
    hidden_from = decision_end + 1
    end = hidden_from + outcome_candles
    return {
        "schema": "finquant_lifecycle_case_v1",
        "case_id": case_id,
        "symbol": symbol,
        "timeframe_minutes": timeframe_minutes,
        "regime_v1": regime,
        "description": f"Synthetic {regime} case @ 15m. Generated for PPLE proof.",
        "decision_start_index": decision_start,
        "decision_end_index": decision_end,
        "hidden_future_start_index": hidden_from,
        "expected_learning_focus_v1": expected_focus,
        "candles": bars[:end],
    }


def generate_dataset(
    *,
    out_dir: Path,
    case_count: int = 60,
    seed: int = 1729,
    symbol: str = "BTC-PERP",
    start_price: float | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    # Default start price: 100 so ATR values (2-4) are 2-4% of price —
    # compatible with the price-relative ATR thresholds in lifecycle_engine.
    price = start_price if start_price is not None else 100.0

    cases: list[dict[str, Any]] = []
    paths: list[str] = []
    regime_counts: dict[str, int] = {r: 0 for r in REGIMES}

    for i in range(case_count):
        regime = REGIMES[i % len(REGIMES)]
        bars, price, start_time = _generate_block(
            regime, rng=rng, start_price=price, start_time=start_time,
        )
        case_id = f"syn_{symbol.lower().replace('-', '')}_{regime}_{i:04d}"
        case = build_case_from_block(
            bars=bars,
            case_id=case_id,
            regime=regime,
            symbol=symbol,
            timeframe_minutes=15,
        )
        path = out_dir / f"{case_id}.json"
        with open(path, "w") as f:
            json.dump(case, f, indent=2)
        cases.append(case)
        paths.append(str(path))
        regime_counts[regime] += 1

    manifest = {
        "schema": "finquant_synthetic_dataset_manifest_v1",
        "symbol": symbol,
        "case_count": case_count,
        "seed": seed,
        "start_price_v1": price,
        "regime_counts_v1": regime_counts,
        "case_paths_v1": paths,
        "out_dir": str(out_dir),
    }
    manifest_path = out_dir / "synthetic_dataset_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant synthetic dataset generator")
    parser.add_argument("--out", required=True, help="Output directory for case JSON files")
    parser.add_argument("--case-count", type=int, default=60, help="Number of cases to generate")
    parser.add_argument("--seed", type=int, default=1729, help="Deterministic RNG seed")
    parser.add_argument("--symbol", default="BTC-PERP")
    parser.add_argument("--start-price", type=float, default=None,
                        help="Starting price for synthetic bars (default 100.0)")
    args = parser.parse_args()

    manifest = generate_dataset(
        out_dir=Path(args.out),
        case_count=args.case_count,
        seed=args.seed,
        symbol=args.symbol,
        start_price=args.start_price,
    )
    print(json.dumps({
        "case_count": manifest["case_count"],
        "regime_counts": manifest["regime_counts_v1"],
        "out_dir": manifest["out_dir"],
    }, indent=2))


if __name__ == "__main__":
    main()
