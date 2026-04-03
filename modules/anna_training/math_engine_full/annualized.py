"""Annualized Sharpe / Sortino on daily returns with risk-free rate."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd


def _daily_rf(rf_annual: float) -> float:
    return (1.0 + rf_annual) ** (1.0 / 252.0) - 1.0


def annualized_sharpe_sortino(
    daily_returns: pd.Series,
    *,
    rf_annual: float | None = None,
) -> dict[str, float | None]:
    """
    Trading-day convention: 252 days/year.
    ``rf_annual`` from env ``ANNA_RISK_FREE_ANNUAL`` if not passed (default 0.04).
    """
    if rf_annual is None:
        raw = (os.environ.get("ANNA_RISK_FREE_ANNUAL") or "").strip()
        rf_annual = float(raw) if raw else 0.04
    drf = _daily_rf(rf_annual)
    x = daily_returns.astype(float) - drf
    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    n = len(x)
    if n < 2:
        return {
            "annualized_sharpe": None,
            "annualized_sortino": None,
            "daily_obs": float(n),
            "rf_annual_used": rf_annual,
        }
    m = float(x.mean())
    s = float(x.std(ddof=1))
    downside = x[x < 0]
    ds = float(downside.std(ddof=1)) if len(downside) >= 2 else None
    sharpe = (m / s) * np.sqrt(252.0) if s and s > 1e-18 else None
    sortino = (m / ds) * np.sqrt(252.0) if ds and ds > 1e-18 else None
    return {
        "annualized_sharpe": float(sharpe) if sharpe is not None else None,
        "annualized_sortino": float(sortino) if sortino is not None else None,
        "daily_obs": float(n),
        "rf_annual_used": rf_annual,
    }
