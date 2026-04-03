"""Training quant metrics (paper P&L — Sharpe/Sortino proxies, DD, VaR/CVaR)."""
from __future__ import annotations

from modules.anna_training.quant_metrics import (
    compute_paper_quant_metrics,
    historical_var_cvar_usd,
    max_drawdown_usd,
    sharpe_proxy_per_trade,
    sortino_proxy_per_trade,
)


def test_max_drawdown_simple() -> None:
    dd, eq = max_drawdown_usd([10.0, -30.0, 20.0])
    assert eq == 0.0
    assert dd == 30.0


def test_sharpe_proxy_undefined_small_n() -> None:
    assert sharpe_proxy_per_trade([1.0]) is None
    assert sharpe_proxy_per_trade([1.0, 3.0]) is not None


def test_sortino_with_downside() -> None:
    """Sortino needs nonzero downside deviation vs target 0."""
    s = sortino_proxy_per_trade([2.0, -1.0, 3.0])
    assert s is not None


def test_var_left_tail_losses() -> None:
    pnls = [-20.0, -10.0, -5.0, 1.0, 2.0]
    v, c = historical_var_cvar_usd(pnls, alpha=0.2)
    assert v is not None and c is not None
    assert v >= 0 and c >= 0


def test_compute_paper_quant_metrics_schema() -> None:
    trades = [
        {
            "schema": "anna_paper_trade_v1",
            "ts_utc": "2026-01-01T00:00:00Z",
            "pnl_usd": -5.0,
            "result": "lost",
        },
        {
            "schema": "anna_paper_trade_v1",
            "ts_utc": "2026-01-02T00:00:00Z",
            "pnl_usd": 10.0,
            "result": "won",
        },
    ]
    m = compute_paper_quant_metrics(trades)
    assert m["trade_count"] == 2
    assert m["total_pnl_usd"] == 5.0
    assert m["max_drawdown_usd"] is not None
    assert m["version"] == "1"
