"""
Orchestrate full math stack: daily series, ARIMA/GARCH, annualized Sharpe, WFO, Monte Carlo, ML, Kalman, coint.
"""
from __future__ import annotations

import os
from typing import Any

from modules.anna_training.math_engine_full.annualized import annualized_sharpe_sortino
from modules.anna_training.math_engine_full.cointegration_kalman import (
    engle_granger_coint,
    kalman_local_level,
)
from modules.anna_training.math_engine_full.daily_series import (
    daily_pnl_series_from_trades,
    daily_returns_from_levels,
)
from modules.anna_training.math_engine_full.ml_baseline import sklearn_direction_baseline
from modules.anna_training.math_engine_full.ts_fit import fit_arima_summary, fit_garch_summary
from modules.anna_training.math_engine_full.walk_forward_monte_carlo import (
    monte_carlo_trade_pnl,
    walk_forward_sharpe_stability,
)
from modules.anna_training.quant_metrics import ordered_trade_pnls

FULL_STACK_VERSION = "1"


def training_full_stack_env_enabled() -> bool:
    """Default off so Anna analyst path stays fast unless operator enables."""
    v = (os.environ.get("ANNA_MATH_ENGINE_FULL") or "0").strip().lower()
    return v not in ("0", "false", "no", "")


def run_full_math_stack(
    trades: list[dict[str, Any]],
    *,
    aux: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run all submodules where data permits. Never raises — errors captured per section.

    ``aux`` optional keys:
      - ``cointegration_series_a``, ``cointegration_series_b``: equal-length float sequences.
    """
    aux = aux or {}
    out: dict[str, Any] = {
        "version": FULL_STACK_VERSION,
        "enabled_by_env": training_full_stack_env_enabled(),
        "sections": {},
    }

    pnls = ordered_trade_pnls(trades)
    out["sections"]["trade_count"] = len(pnls)

    mc_out = monte_carlo_trade_pnl(pnls, n_sims=min(500, max(50, len(pnls) * 20)))
    out["sections"]["monte_carlo_bootstrap"] = mc_out

    daily = daily_pnl_series_from_trades(trades)
    if daily is None or len(daily) < 2:
        out["sections"]["daily"] = {"skipped": True, "reason": "could_not_build_daily_series"}
        return out

    dr = daily_returns_from_levels(daily).dropna()
    out["sections"]["daily_bars"] = int(len(daily))
    out["sections"]["annualized_risk"] = annualized_sharpe_sortino(dr)

    out["sections"]["arima"] = fit_arima_summary(dr)
    out["sections"]["garch"] = fit_garch_summary(dr)

    out["sections"]["walk_forward"] = walk_forward_sharpe_stability(dr)
    out["sections"]["ml_baseline"] = sklearn_direction_baseline(dr)

    kl = kalman_local_level(daily.values.astype(float))
    out["sections"]["kalman_local_level_on_daily_pnl"] = kl

    sa = aux.get("cointegration_series_a")
    sb = aux.get("cointegration_series_b")
    if isinstance(sa, list) and isinstance(sb, list) and len(sa) >= 20:
        out["sections"]["cointegration"] = engle_granger_coint(sa, sb)
    else:
        out["sections"]["cointegration"] = {
            "ok": False,
            "skipped": True,
            "reason": "provide_aux_cointegration_series_a_b_for_engle_granger",
        }

    return out


def full_stack_fact_lines(result: dict[str, Any]) -> list[str]:
    """Short FACT lines for LLM (bounded)."""
    lines: list[str] = []
    sec = result.get("sections") or {}
    ar = sec.get("annualized_risk") or {}
    if ar.get("annualized_sharpe") is not None:
        lines.append(
            f"FACT (math engine full): Annualized Sharpe (daily, rf from ANNA_RISK_FREE_ANNUAL)≈{ar['annualized_sharpe']:.4f}."
        )
    g = sec.get("garch") or {}
    if g.get("ok"):
        lines.append(
            f"FACT (math engine full): GARCH fit AIC≈{g.get('aic')}; last conditional vol scale≈{g.get('conditional_vol_last')}."
        )
    wf = sec.get("walk_forward") or {}
    if wf.get("ok") and wf.get("splits"):
        lines.append(
            f"FACT (math engine full): Walk-forward stability ran {len(wf['splits'])} OOS windows (descriptive)."
        )
    ml = sec.get("ml_baseline") or {}
    if ml.get("ok"):
        lines.append(
            f"FACT (math engine full): ML lag baseline test accuracy≈{ml.get('test_accuracy')} (diagnostic only)."
        )
    mc = sec.get("monte_carlo_bootstrap") or {}
    if mc.get("ok"):
        lines.append(
            f"FACT (math engine full): Bootstrap mean total P&L≈{mc.get('bootstrapped_total_pnl_mean')} "
            f"(std≈{mc.get('bootstrapped_total_pnl_std')})."
        )
    lines.append(
        "FACT (math engine full): ARIMA/GARCH/ML are harness diagnostics — not live edge proof; coint needs two series in aux."
    )
    return lines
