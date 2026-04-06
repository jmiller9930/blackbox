#!/usr/bin/env python3
"""
Jupiter policy v2 — **sandbox** demo: synthetic 5m OHLC, printed like operator logs.

No DB, no daemon, no venue. Comprehension check: same evaluator as production.

Run from repo root::

  PYTHONPATH=scripts/runtime:. python3 scripts/runtime/jupiter_policy_sandbox_demo.py
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.anna_training import sean_jupiter_baseline_signal as sj  # noqa: E402


def _bar(
    i: int,
    *,
    o: float,
    h: float,
    l: float,
    c: float,
    base_minute: int = 0,
) -> dict:
    oi = base_minute + i * 5
    return {
        "canonical_symbol": "SOL-PERP",
        "timeframe": "5m",
        "candle_open_utc": f"2026-04-06T{(oi // 60):02d}:{(oi % 60):02d}:00Z",
        "candle_close_utc": f"2026-04-06T{(oi // 60):02d}:{((oi + 5) % 60):02d}:00Z",
        "market_event_id": f"SANDBOX_SOL_5m_{i:04d}",
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "tick_count": 10,
        "price_source": "sandbox",
        "computed_at": "2026-04-06T12:00:00Z",
    }


def _fmt_candle(b: dict, rsi: float | None) -> None:
    rs = "N/A"
    if rsi is not None and not math.isnan(rsi):
        rs = f"{rsi:.12f}"
    print(
        f"    O={b['open']:.8f}, H={b['high']:.8f}, L={b['low']:.8f}, C={b['close']:.8f}, RSI={rs}"
    )


def pd_ema200_last(closes: list[float]) -> float:
    import pandas as pd

    return float(pd.Series(closes, dtype=float).ewm(span=sj.EMA_PERIOD, adjust=False).mean().iloc[-1])


def print_scenario(title: str, bars: list[dict], sig: sj.SeanJupiterBaselineSignalV1) -> None:
    prev, cur = bars[-2], bars[-1]
    closes = [float(b["close"]) for b in bars]
    rsi_all = sj.rsi_trading_core(closes, sj.RSI_PERIOD)
    i = len(bars) - 1
    pr, cr = rsi_all[i - 1], rsi_all[i]
    st = sj.supertrend_direction_series(
        [float(b["high"]) for b in bars],
        [float(b["low"]) for b in bars],
        closes,
    )[i]
    ema200 = pd_ema200_last(closes)
    st_label = {1: "BULLISH (green)", -1: "BEARISH (red)", 0: "UNKNOWN"}[st]

    print()
    print("=" * 72)
    print(title)
    print("=" * 72)
    print(f'New 5-min candle formed: id={cur["market_event_id"]}')
    _fmt_candle(cur, cr)
    print("Previous candle:")
    _fmt_candle(prev, pr)
    print("Current candle:")
    _fmt_candle(cur, cr)
    print()
    print(f"Supertrend: {st_label} (direction_code={st})")
    print(f"Price vs EMA200: close={float(cur['close']):.6f}  EMA200={ema200:.6f}")
    raw_s, raw_l = sj.aggregate_candles_signal_flags(
        prev_candle={"high": float(prev["high"]), "low": float(prev["low"])},
        curr_candle={"high": float(cur["high"]), "low": float(cur["low"])},
        prev_rsi_raw=pr,
        current_rsi_raw=cr,
    )
    print()
    print("Signals (raw):")
    print(f"  short={raw_s}  long={raw_l}   (RSI current={cr:.8f})")
    print()
    print("Evaluator (production path):")
    print(f"  trade={sig.trade}  side={sig.side}  reason_code={sig.reason_code}")
    if sig.pnl_usd is not None:
        print(f"  pnl_usd_open_to_close_1unit={sig.pnl_usd}")
    print()
    print("features:")
    print(json.dumps(sig.features, indent=2, default=str))


def _random_bars(seed: int, n: int = sj.MIN_BARS) -> list[dict]:
    rng = random.Random(seed)
    out: list[dict] = []
    c = 100.0
    for i in range(n):
        c = max(50.0, c + rng.uniform(-0.4, 0.4))
        w = rng.uniform(0.05, 0.35)
        o = c - rng.uniform(-w, w)
        h = max(o, c) + rng.uniform(0.01, 0.2)
        l = min(o, c) - rng.uniform(0.01, 0.2)
        out.append(_bar(i, o=o, h=h, l=l, c=c))
    return out


def _search(want_side: str, max_seeds: int = 12000) -> tuple[list[dict], sj.SeanJupiterBaselineSignalV1] | None:
    from modules.anna_training.sean_jupiter_baseline_signal import evaluate_sean_jupiter_baseline_v1

    for seed in range(max_seeds):
        bars = _random_bars(seed)
        sig = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
        if sig.trade and sig.side == want_side:
            return (bars, sig)
    return None


def main() -> int:
    print(
        "Jupiter policy v2 SANDBOX — synthetic bars only.\n"
        f"Constants: RSI period {sj.RSI_PERIOD}, long<than {sj.RSI_LONG_THRESHOLD}, "
        f"short>than {sj.RSI_SHORT_THRESHOLD}, MIN_BARS={sj.MIN_BARS}.\n"
    )

    a = _search("long")
    if a:
        print_scenario("Scenario A — search hit: LONG (trade=True)", a[0], a[1])
    else:
        print("Scenario A — no LONG found in 12k seeds (gates are strict).")

    b = _search("short")
    if b:
        print_scenario("Scenario B — search hit: SHORT (trade=True)", b[0], b[1])
    else:
        print("Scenario B — no SHORT found in 12k seeds (gates are strict).")

    print()
    print("Scenario C — fixed seed 4242 (always reproducible)")
    from modules.anna_training.sean_jupiter_baseline_signal import evaluate_sean_jupiter_baseline_v1

    bars = _random_bars(4242)
    sig = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    print_scenario("Seed 4242", bars, sig)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
