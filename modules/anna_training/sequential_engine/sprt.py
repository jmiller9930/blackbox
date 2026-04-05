"""Wald SPRT on binary outcomes (Bernoulli likelihood ratios)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SprtThresholds:
    """Wald thresholds on the likelihood ratio scale (not log)."""

    upper: float  # accept H1 (improvement) when Lambda >= upper
    lower: float  # accept H0 when Lambda <= lower


def sprt_thresholds(*, alpha: float, beta: float) -> SprtThresholds:
    """Classic Wald boundaries: A = (1-beta)/alpha, B = beta/(1-alpha)."""
    if alpha <= 0 or alpha >= 1 or beta <= 0 or beta >= 1:
        raise ValueError("alpha and beta must be in (0,1)")
    upper = (1.0 - beta) / alpha
    lower = beta / (1.0 - alpha)
    return SprtThresholds(upper=upper, lower=lower)


def sprt_log_contribution(*, win: bool, p0: float, p1: float) -> float:
    """Log likelihood ratio contribution for one Bernoulli observation."""
    if not (0.0 < p0 < 1.0 and 0.0 < p1 < 1.0):
        raise ValueError("p0 and p1 must be strictly in (0,1)")
    if win:
        return math.log(p1) - math.log(p0)
    return math.log(1.0 - p1) - math.log(1.0 - p0)


def sprt_likelihood_ratio_from_log(log_sum: float) -> float:
    return math.exp(log_sum)


def classify_sprt_decision(
    *,
    log_likelihood_ratio: float,
    alpha: float,
    beta: float,
) -> str:
    """
    Returns PROMOTE | KILL | CONTINUE based on cumulative likelihood ratio.

    PROMOTE: Lambda >= upper
    KILL: Lambda <= lower
    CONTINUE: strictly between
    """
    th = sprt_thresholds(alpha=alpha, beta=beta)
    lam = sprt_likelihood_ratio_from_log(log_likelihood_ratio)
    if lam >= th.upper:
        return "PROMOTE"
    if lam <= th.lower:
        return "KILL"
    return "CONTINUE"
