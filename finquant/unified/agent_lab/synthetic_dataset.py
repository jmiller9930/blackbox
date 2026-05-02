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

REGIMES = ["bull_trend", "bear_trend", "chop", "breakout", "false_break"]


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
    raise ValueError(f"unknown regime: {regime}")


def _bull_trend(rng, start_price, start_time, bar_minutes):
    bars = []
    price = start_price
    ema = price
    atr = 1.5 + rng.random() * 0.6
    for i in range(28):
        drift = 0.4 + rng.random() * 0.5
        noise = (rng.random() - 0.45) * 0.6
        new_close = max(1.0, price + drift + noise)
        h = max(price, new_close) + abs(rng.random() * 0.3)
        l = min(price, new_close) - abs(rng.random() * 0.25)
        v = 1500 + i * 60 + rng.random() * 400
        rsi = min(78, 52 + i * 0.7 + rng.random() * 2)
        ema = ema * 0.85 + new_close * 0.15
        atr = atr * 0.9 + max(h - l, 0.5) * 0.1
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
    atr = 1.0
    resistance = price + 2.5
    # 18 bars of consolidation
    for i in range(18):
        new_close = price + (rng.random() - 0.5) * 0.5
        h = max(price, new_close) + 0.2
        l = min(price, new_close) - 0.2
        v = 700 + rng.random() * 300
        rsi = 50 + (rng.random() - 0.5) * 4
        ema = ema * 0.9 + new_close * 0.1
        atr = atr * 0.95 + max(h - l, 0.3) * 0.05
        bars.append(_candle(
            (start_time + timedelta(minutes=bar_minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            price, h, l, new_close, v, rsi, ema, atr, resistance=resistance,
        ))
        price = new_close
    # 10 bars of breakout
    for j in range(10):
        i = 18 + j
        new_close = price + 0.7 + rng.random() * 0.6
        h = new_close + 0.3
        l = price - 0.1
        v = 3000 + rng.random() * 1500
        rsi = min(75, 60 + j * 1.2)
        ema = ema * 0.85 + new_close * 0.15
        atr = atr * 0.85 + max(h - l, 1.0) * 0.15
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
        "bear_trend": ["entry_quality"],
        "chop": ["no_trade_quality"],
        "breakout": ["entry_quality"],
        "false_break": ["entry_quality", "exit_quality"],
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
) -> dict[str, Any]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    price = 42000.0

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
    args = parser.parse_args()

    manifest = generate_dataset(
        out_dir=Path(args.out),
        case_count=args.case_count,
        seed=args.seed,
        symbol=args.symbol,
    )
    print(json.dumps({
        "case_count": manifest["case_count"],
        "regime_counts": manifest["regime_counts_v1"],
        "out_dir": manifest["out_dir"],
    }, indent=2))


if __name__ == "__main__":
    main()
