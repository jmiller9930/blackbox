"""Minimal sklearn baseline: predict sign of next-day return from lags."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def sklearn_direction_baseline(
    daily_returns: pd.Series,
    *,
    lags: int = 5,
    min_train: int = 20,
) -> dict[str, Any]:
    """
    RandomForest on lagged returns -> y = sign(next return).
    For harness diagnostics only; expect weak OOS.
    """
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score
    except ImportError as e:
        return {"ok": False, "error": str(e)}
    r = daily_returns.astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < min_train + lags + 10:
        return {"ok": False, "skipped": True, "reason": "insufficient_history"}
    vals = r.values
    X_list: list[list[float]] = []
    y_list: list[int] = []
    for i in range(lags, len(vals) - 1):
        X_list.append([vals[i - j] for j in range(1, lags + 1)])
        y_list.append(1 if vals[i + 1] > 0 else 0)
    X = np.array(X_list)
    y = np.array(y_list)
    if len(y) < 20:
        return {"ok": False, "skipped": True, "reason": "too_few_rows"}
    try:
        split = max(1, int(len(X) * 0.75))
        X_tr, X_te = X[:split], X[split:]
        y_tr, y_te = y[:split], y[split:]
        clf = RandomForestClassifier(n_estimators=15, max_depth=4, random_state=42, n_jobs=1)
        clf.fit(X_tr, y_tr)
        pred = clf.predict(X_te)
        acc = float(accuracy_score(y_te, pred))
        return {
            "ok": True,
            "model": "RandomForestClassifier",
            "lags": lags,
            "test_accuracy": acc,
            "train_rows": int(len(y_tr)),
            "test_rows": int(len(y_te)),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
