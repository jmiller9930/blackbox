"""Walk-forward splits on daily returns; Monte Carlo bootstrap on trade PnL."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def walk_forward_sharpe_stability(
    daily_returns: pd.Series,
    *,
    train_min: int = 30,
    test_min: int = 10,
    max_splits: int = 8,
) -> dict[str, Any]:
    """
    Expanding window: train Sharpe on prefix, record OOS mean return of next test block.
    Descriptive only — not a full WFO optimizer.
    """
    x = daily_returns.astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    n = len(x)
    if n < train_min + test_min + 5:
        return {"ok": False, "skipped": True, "reason": "insufficient_daily_returns"}
    splits: list[dict[str, float]] = []
    step = max(test_min, (n - train_min) // max_splits)
    t0 = train_min
    while t0 + test_min <= n and len(splits) < max_splits:
        train = x.iloc[:t0]
        test = x.iloc[t0 : t0 + test_min]
        m = float(train.mean())
        s = float(train.std(ddof=1)) or 1e-18
        sh = (m / s) * np.sqrt(252.0)
        splits.append(
            {
                "train_end": float(t0),
                "oos_mean_daily": float(test.mean()),
                "in_sample_sharpe_annualized_proxy": float(sh),
            }
        )
        t0 += step
    return {"ok": True, "splits": splits, "n_daily": n}


def monte_carlo_trade_pnl(
    trade_pnls: list[float],
    *,
    n_sims: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """Bootstrap mean total PnL and Sharpe-like ratio on resampled trades."""
    arr = np.asarray(trade_pnls, dtype=float)
    arr = arr[np.isfinite(arr)]
    m = len(arr)
    if m < 5:
        return {"ok": False, "skipped": True, "reason": "need_at_least_5_trades"}
    rng = np.random.default_rng(seed)
    means: list[float] = []
    sharpes: list[float] = []
    for _ in range(n_sims):
        samp = rng.choice(arr, size=m, replace=True)
        means.append(float(samp.sum()))
        std = float(samp.std(ddof=1)) or 1e-18
        sharpes.append(float(samp.mean() / std * np.sqrt(m)))
    return {
        "ok": True,
        "n_sims": n_sims,
        "bootstrapped_total_pnl_mean": float(np.mean(means)),
        "bootstrapped_total_pnl_std": float(np.std(means)),
        "bootstrapped_sharpe_proxy_mean": float(np.mean(sharpes)),
        "bootstrapped_sharpe_proxy_std": float(np.std(sharpes)),
    }
