"""Anna deterministic math engine (Wilson intervals, cohort facts, merge)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from anna_modules.analysis_math import (  # noqa: E402
    compute_math_engine_facts,
    merge_authoritative_fact_layers,
    relative_mid_spread_pct,
    spread_bps_of_mid,
    wilson_score_interval_95,
)


def test_wilson_interval_monotone_in_n() -> None:
    lo5, hi5 = wilson_score_interval_95(3, 5)
    lo30, hi30 = wilson_score_interval_95(18, 30)
    assert hi5 - lo5 > hi30 - lo30


def test_spread_bps() -> None:
    assert spread_bps_of_mid(100.0, 0.05) == pytest.approx(5.0)
    assert spread_bps_of_mid(0.0, 1.0) is None


def test_relative_mid_spread_pct() -> None:
    # (primary - comparator) / mid, mid = (a+b)/2
    assert relative_mid_spread_pct(100.0, 100.02) == pytest.approx((100.0 - 100.02) / 100.01)


def test_merge_layers() -> None:
    m = merge_authoritative_fact_layers(
        {"facts_for_prompt": ["A"], "structured": {"x": 1}},
        {"facts_for_prompt": ["B"], "structured": {"y": 2}},
    )
    assert m["facts_for_prompt"] == ["A", "B"]
    assert m["structured"] == {"x": 1, "y": 2}


def test_compute_math_engine_facts_empty_trades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "anna_modules.analysis_math._load_paper_trades_safe",
        lambda: [],
    )
    out = compute_math_engine_facts("hello", {}, market=None, market_data_tick=None)
    assert "math_engine" in out["structured"]
    assert "no decisive" in " ".join(out["facts_for_prompt"]).lower()


def test_build_analysis_includes_math_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    sys.path.insert(0, str(ROOT / "scripts" / "runtime"))
    from anna_modules.analysis import build_analysis

    monkeypatch.setattr(
        "anna_modules.analysis_math._load_paper_trades_safe",
        lambda: [],
    )
    a = build_analysis(
        "If a setup scores 61 confidence after adjustments and our threshold is 65, what should happen?",
        market=None,
        market_err=None,
        ctx=None,
        ctx_err=None,
        trend=None,
        trend_err=None,
        policy=None,
        policy_err=None,
        use_snapshot=False,
        use_ctx=False,
        use_trend=False,
        use_policy=False,
        conn=None,
    )
    assert a.get("math_engine") is not None
    assert a["math_engine"]["version"] == "3"
