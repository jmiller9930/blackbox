"""
Monte Carlo stress layer over a fixed closed-trade population.

Rules (spec): does not invent trades — only reorders or resamples existing PnL events.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

Mode = Literal["shuffle", "bootstrap"]


def _equity_terminal_and_max_dd(pnls: np.ndarray | list[float]) -> tuple[float, float]:
    """Cumulative equity path; return (terminal_equity, max_drawdown)."""
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        eq += float(p)
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    return eq, max_dd


def _percentile(sorted_vals: list[float], p: float) -> float:
    """p in [0, 100]."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(math.floor(k))
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


@dataclass
class MonteCarloConfig:
    n_simulations: int = 10_000
    seed: int = 42
    modes: tuple[Mode, ...] = ("shuffle", "bootstrap")
    """path_length: trades per simulated path (fair comparison across baseline vs candidate)."""
    path_length: int | None = None


@dataclass
class ModeResult:
    mode: str
    n_simulations: int
    path_length: int
    trade_count_source: int
    terminal_pnls: list[float] = field(repr=False)
    max_drawdowns: list[float] = field(repr=False)

    def to_summary_dict(self) -> dict:
        t = np.array(self.terminal_pnls, dtype=np.float64)
        d = np.array(self.max_drawdowns, dtype=np.float64)
        neg = int(np.sum(t < 0))
        sorted_t = sorted(float(x) for x in t.tolist())
        sorted_d = sorted(float(x) for x in d.tolist())
        return {
            "mode": self.mode,
            "n_simulations": self.n_simulations,
            "path_length": self.path_length,
            "trade_count_source": self.trade_count_source,
            "median_terminal_pnl": float(np.median(t)),
            "mean_terminal_pnl": float(np.mean(t)),
            "worst_terminal_pnl": float(np.min(t)),
            "best_terminal_pnl": float(np.max(t)),
            "p5_terminal": _percentile(sorted_t, 5),
            "p25_terminal": _percentile(sorted_t, 25),
            "p50_terminal": _percentile(sorted_t, 50),
            "p75_terminal": _percentile(sorted_t, 75),
            "p95_terminal": _percentile(sorted_t, 95),
            "mean_max_drawdown": float(np.mean(d)),
            "median_max_drawdown": float(np.median(d)),
            "worst_max_drawdown": float(np.max(d)),
            "p95_max_drawdown": _percentile(sorted_d, 95),
            "simulations_terminal_negative": neg,
            "fraction_terminal_negative": neg / self.n_simulations if self.n_simulations else 0.0,
            "risk_of_ruin_proxy": neg / self.n_simulations if self.n_simulations else 0.0,
        }


@dataclass
class MonteCarloRunResult:
    config: MonteCarloConfig
    pnls_source: list[float]
    by_mode: dict[str, ModeResult]

    def all_summaries(self) -> dict[str, dict]:
        return {k: v.to_summary_dict() for k, v in self.by_mode.items()}


def run_monte_carlo(pnls: list[float], config: MonteCarloConfig) -> MonteCarloRunResult:
    if not pnls:
        raise ValueError("Monte Carlo requires a non-empty PnL series (closed trades).")
    arr = np.asarray(pnls, dtype=np.float64)
    n_trades = len(arr)
    path_len = config.path_length if config.path_length is not None else n_trades
    path_len = max(1, min(path_len, n_trades))

    rng = np.random.default_rng(int(config.seed))
    by_mode: dict[str, ModeResult] = {}

    for mode in config.modes:
        terminals: list[float] = []
        dds: list[float] = []
        for _ in range(config.n_simulations):
            if mode == "shuffle":
                perm = rng.permutation(n_trades)
                take = perm[:path_len]
                path = arr[take]
            elif mode == "bootstrap":
                idx = rng.integers(0, n_trades, size=path_len)
                path = arr[idx]
            else:
                raise ValueError(f"Unknown mode: {mode}")
            term, dd = _equity_terminal_and_max_dd(path)
            terminals.append(term)
            dds.append(dd)

        by_mode[mode] = ModeResult(
            mode=mode,
            n_simulations=config.n_simulations,
            path_length=path_len,
            trade_count_source=n_trades,
            terminal_pnls=terminals,
            max_drawdowns=dds,
        )

    return MonteCarloRunResult(config=config, pnls_source=list(arr.tolist()), by_mode=by_mode)
