"""ARIMA and GARCH fits on a univariate return series."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def fit_arima_summary(series: pd.Series, *, order: tuple[int, int, int] = (1, 1, 1)) -> dict[str, Any]:
    """ARIMA via statsmodels; returns AIC and params or error."""
    try:
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError as e:
        return {"ok": False, "error": str(e)}
    y = series.astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if len(y) < order[0] + order[2] + 5:
        return {"ok": False, "skipped": True, "reason": "insufficient_obs"}
    try:
        res = ARIMA(y, order=order).fit(maxiter=75)
        params = {str(k): float(v) for k, v in res.params.items()}
        return {
            "ok": True,
            "order": order,
            "aic": float(res.aic),
            "params": params,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def fit_garch_summary(returns: pd.Series, *, p: int = 1, q: int = 1) -> dict[str, Any]:
    """GARCH(p,q) on demeaned returns via ``arch``."""
    try:
        from arch import arch_model
    except ImportError as e:
        return {"ok": False, "error": str(e)}
    y = returns.astype(float).replace([np.inf, -np.inf], np.nan).dropna() * 100.0
    if len(y) < max(10, p + q + 5):
        return {"ok": False, "skipped": True, "reason": "insufficient_obs"}
    try:
        am = arch_model(y, vol="Garch", p=p, q=q, rescale=False)
        res = am.fit(disp="off", options={"maxiter": 100})
        return {
            "ok": True,
            "p": p,
            "q": q,
            "aic": float(res.aic),
            "conditional_vol_last": float(np.sqrt(res.conditional_volatility.values[-1] / 100.0)),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
