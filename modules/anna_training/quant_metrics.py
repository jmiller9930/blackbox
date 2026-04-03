"""
Paper-trade quantitative metrics (training / math engine extension).

Pure Python — no SciPy. These are **descriptive** statistics on logged paper P&L USD per trade.
Sharpe/Sortino here are **per-trade proxies** (not annualized time-series Sharpe unless you
supply time-aware scaling elsewhere). Use for harness honesty, not regulatory reporting.

See also: ``anna_modules.analysis_math`` (Wilson intervals, spreads).
"""
from __future__ import annotations

import math
from typing import Any


QUANT_METRICS_VERSION = "1"


def ordered_trade_pnls(trades: list[dict[str, Any]]) -> list[float]:
    """PnL USD in chronological order (by ts_utc when present)."""
    rows = sorted(
        [t for t in trades if isinstance(t, dict)],
        key=lambda t: str(t.get("ts_utc") or ""),
    )
    return [float(t.get("pnl_usd") or 0) for t in rows]


def equity_curve(pnls: list[float]) -> list[float]:
    out: list[float] = []
    s = 0.0
    for x in pnls:
        s += x
        out.append(s)
    return out


def max_drawdown_usd(pnls: list[float]) -> tuple[float, float]:
    """
    Max drawdown on cumulative P&L path (USD).
    Returns (max_drawdown, final_equity) — drawdown is nonnegative.
    """
    peak = 0.0
    eq = 0.0
    max_dd = 0.0
    for x in pnls:
        eq += x
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd
    return max_dd, eq


def _sample_std(xs: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    if v < 0:
        return None
    return math.sqrt(v)


def downside_deviation_usd(pnls: list[float], *, target: float = 0.0) -> float | None:
    """Sortino-style downside deviation around target (USD per trade)."""
    if not pnls:
        return None
    downs = [min(0.0, p - target) ** 2 for p in pnls]
    return math.sqrt(sum(downs) / len(pnls))


def sharpe_proxy_per_trade(pnls: list[float], *, rf_per_trade: float = 0.0) -> float | None:
    """
    Mean excess / sample std (per-trade). Not annualized.
    None if undefined (n<2 or zero variance).
    """
    n = len(pnls)
    if n < 2:
        return None
    xs = [p - rf_per_trade for p in pnls]
    std = _sample_std(xs)
    if std is None or std <= 1e-18:
        return None
    m = sum(xs) / n
    return m / std


def sortino_proxy_per_trade(pnls: list[float], *, target: float = 0.0) -> float | None:
    """Mean / downside deviation. None if downside deviation is zero."""
    if not pnls:
        return None
    dd = downside_deviation_usd(pnls, target=target)
    if dd is None or dd <= 1e-18:
        return None
    m = sum(pnls) / len(pnls)
    return m / dd


def calmar_ratio(total_return: float, max_dd: float) -> float | None:
    """Total return / max drawdown when max_dd > 0."""
    if max_dd <= 1e-18:
        return None
    return total_return / max_dd


def historical_var_cvar_usd(
    pnls: list[float],
    *,
    alpha: float = 0.05,
) -> tuple[float | None, float | None]:
    """
    Historical VaR / CVaR on **per-trade P&L** (USD), left-tail alpha.

    VaR: loss magnitude from the alpha empirical quantile (nonnegative).
    CVaR: mean loss in the tail (average of outcomes at or below that quantile).
    """
    if not pnls:
        return None, None
    s = sorted(pnls)
    n = len(s)
    idx = max(0, min(n - 1, int(math.floor(alpha * (n - 1)))))
    q = s[idx]
    var_usd = max(0.0, -q)
    tail = [x for x in s if x <= q]
    if not tail:
        return var_usd, 0.0
    cvar_mean = sum(tail) / len(tail)
    cvar_usd = max(0.0, -cvar_mean)
    return var_usd, cvar_usd


def compute_paper_quant_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Full structured metrics dict for training / math_engine facts.

    Keys are stable for JSON logging; None means undefined.
    """
    pnls = ordered_trade_pnls(trades)
    n = len(pnls)
    total = sum(pnls) if pnls else 0.0
    max_dd, final_eq = max_drawdown_usd(pnls)
    std = _sample_std(pnls) if n >= 2 else None
    sharpe = sharpe_proxy_per_trade(pnls)
    sortino = sortino_proxy_per_trade(pnls)
    calmar = calmar_ratio(total, max_dd)
    var_usd, cvar_usd = historical_var_cvar_usd(pnls, alpha=0.05)

    return {
        "version": QUANT_METRICS_VERSION,
        "trade_count": n,
        "mean_pnl_usd": round(total / n, 8) if n else None,
        "std_pnl_usd": round(std, 8) if std is not None else None,
        "total_pnl_usd": round(total, 8),
        "final_equity_usd": round(final_eq, 8),
        "max_drawdown_usd": round(max_dd, 8),
        "sharpe_proxy_per_trade": round(sharpe, 8) if sharpe is not None else None,
        "sortino_proxy_per_trade": round(sortino, 8) if sortino is not None else None,
        "calmar_proxy": round(calmar, 8) if calmar is not None else None,
        "historical_var_95_usd": round(var_usd, 8) if var_usd is not None else None,
        "historical_cvar_95_usd": round(cvar_usd, 8) if cvar_usd is not None else None,
        "disclaimer": (
            "Per-trade Sharpe/Sortino/VaR proxies on paper USD; not annualized portfolio Sharpe or regulatory VaR."
        ),
    }


def quant_metrics_fact_lines(metrics: dict[str, Any]) -> list[str]:
    """Authoritative FACT lines for the LLM (empty if no trades)."""
    n = metrics.get("trade_count") or 0
    if n == 0:
        return []

    lines: list[str] = []
    lines.append(
        f"FACT (math engine quant): n={n} paper trades; "
        f"total P&L USD={metrics.get('total_pnl_usd')}; "
        f"max drawdown (USD on cumulative path)={metrics.get('max_drawdown_usd')}."
    )
    if metrics.get("sharpe_proxy_per_trade") is not None:
        lines.append(
            f"FACT (math engine quant): Sharpe proxy (per-trade, not annualized)="
            f"{metrics['sharpe_proxy_per_trade']}."
        )
    if metrics.get("sortino_proxy_per_trade") is not None:
        lines.append(
            f"FACT (math engine quant): Sortino proxy (per-trade)={metrics['sortino_proxy_per_trade']}."
        )
    if metrics.get("calmar_proxy") is not None:
        lines.append(f"FACT (math engine quant): Calmar proxy (total P&L / max DD)={metrics['calmar_proxy']}.")
    if metrics.get("historical_var_95_usd") is not None:
        lines.append(
            f"FACT (math engine quant): Historical 95% VaR proxy (USD per-trade tail)≈"
            f"{metrics['historical_var_95_usd']}; CVaR proxy≈{metrics.get('historical_cvar_95_usd')}."
        )
    lines.append(
        "FACT (math engine quant): These are harness descriptive metrics — not live execution or bank VaR."
    )
    return lines
