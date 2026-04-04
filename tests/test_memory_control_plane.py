"""
Control-plane memory engagement — runtime signals, modes, retrieval params, anna_analysis_v1 visibility.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_RT = _REPO / "scripts" / "runtime"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_RT) not in sys.path:
    sys.path.insert(0, str(_RT))

from _db import connect, ensure_schema  # noqa: E402
from anna_modules.analysis import build_analysis  # noqa: E402
from anna_modules.lesson_memory import STATUS_VALIDATED, insert_lesson  # noqa: E402
from anna_modules.memory_control_plane import (  # noqa: E402
    MODE_BYPASS,
    MODE_INTENSIFIED,
    MODE_OFF,
    detect_problem_signals,
    effective_retrieval_params,
    select_engagement_mode,
)


def _tick():
    return {"symbol": "SOL-PERP", "gate_state": "ok", "price": 100.0}


def test_memory_control_plane_payload_always_present(monkeypatch):
    monkeypatch.delenv("ANNA_LESSON_MEMORY_CONTROL_PLANE", raising=False)
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    a = build_analysis(
        "SOL 5m structure view",
        market=None,
        market_err=None,
        ctx=None,
        ctx_err=None,
        trend=None,
        trend_err=None,
        policy={"mode": "NORMAL", "reasoning": "t"},
        policy_err=None,
        use_snapshot=False,
        use_ctx=False,
        use_trend=False,
        use_policy=True,
        conn=None,
        use_llm=False,
        market_data_tick=_tick(),
        market_data_err=None,
    )
    mcp = a.get("memory_control_plane") or {}
    assert "signals" in mcp
    assert "engagement_mode" in mcp
    assert "retrieval" in mcp
    assert "semantic_ambiguity" in mcp["signals"]
    assert mcp["retrieval"]["top_k"] >= 1
    assert mcp["retrieval"]["min_score"] >= 1


def test_intensified_when_medium_risk(monkeypatch):
    """Medium risk sets low_confidence_derived → intensified mode when control plane on."""
    monkeypatch.delenv("ANNA_LESSON_MEMORY_CONTROL_PLANE", raising=False)
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "1")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "t.sqlite"
        conn = connect(db_path)
        ensure_schema(conn, _REPO)
        insert_lesson(
            conn,
            lesson_text="Lesson for control plane test.",
            validation_status=STATUS_VALIDATED,
            symbol="SOL",
            regime_tag="nominal",
            timeframe="5m",
        )
        a = build_analysis(
            "SOL 5m — risk check",
            market=None,
            market_err=None,
            ctx=None,
            ctx_err=None,
            trend=None,
            trend_err=None,
            policy={"mode": "NORMAL", "reasoning": "t"},
            policy_err=None,
            use_snapshot=False,
            use_ctx=False,
            use_trend=False,
            use_policy=True,
            conn=conn,
            use_llm=False,
            market_data_tick=_tick(),
            market_data_err=None,
        )
        conn.close()
    mcp = a.get("memory_control_plane") or {}
    assert mcp["engagement_mode"] == MODE_INTENSIFIED
    assert mcp["signals"]["low_confidence_derived"] is True
    r = mcp["retrieval"]
    base = effective_retrieval_params("baseline", base_top_k=3, base_min_score=3)
    assert r["min_score"] <= base["min_score"] or r["top_k"] >= base["top_k"]


def test_bypass_frozen_policy_skips_lesson_memory(monkeypatch):
    monkeypatch.delenv("ANNA_LESSON_MEMORY_CONTROL_PLANE", raising=False)
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "1")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "t.sqlite"
        conn = connect(db_path)
        ensure_schema(conn, _REPO)
        insert_lesson(
            conn,
            lesson_text="Should not inject under FROZEN bypass.",
            validation_status=STATUS_VALIDATED,
            symbol="SOL",
            regime_tag="nominal",
            timeframe="5m",
        )
        a = build_analysis(
            "SOL 5m analysis",
            market=None,
            market_err=None,
            ctx=None,
            ctx_err=None,
            trend=None,
            trend_err=None,
            policy={"mode": "FROZEN", "reasoning": "t"},
            policy_err=None,
            use_snapshot=False,
            use_ctx=False,
            use_trend=False,
            use_policy=True,
            conn=conn,
            use_llm=False,
            market_data_tick=_tick(),
            market_data_err=None,
        )
        conn.close()
    mcp = a.get("memory_control_plane") or {}
    assert mcp["engagement_mode"] == MODE_BYPASS
    assert mcp["retrieval"]["bypass"] is True
    lm = a.get("lesson_memory") or {}
    assert lm.get("enabled") is False
    assert (lm.get("facts") or []) == []


def test_control_plane_disabled_matches_baseline_retrieval(monkeypatch):
    monkeypatch.setenv("ANNA_LESSON_MEMORY_CONTROL_PLANE", "0")
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "1")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "t.sqlite"
        conn = connect(db_path)
        ensure_schema(conn, _REPO)
        insert_lesson(
            conn,
            lesson_text="Baseline path.",
            validation_status=STATUS_VALIDATED,
            symbol="SOL",
            regime_tag="nominal",
            timeframe="5m",
        )
        a = build_analysis(
            "SOL 5m — risk keyword for medium risk",
            market=None,
            market_err=None,
            ctx=None,
            ctx_err=None,
            trend=None,
            trend_err=None,
            policy={"mode": "NORMAL", "reasoning": "t"},
            policy_err=None,
            use_snapshot=False,
            use_ctx=False,
            use_trend=False,
            use_policy=True,
            conn=conn,
            use_llm=False,
            market_data_tick=_tick(),
            market_data_err=None,
        )
        conn.close()
    mcp = a.get("memory_control_plane") or {}
    assert mcp["control_plane_enabled"] is False
    # Mode forced baseline for retrieval math; engagement_mode still baseline string
    assert mcp["engagement_mode"] == "baseline"


def test_lesson_memory_env_off_sets_mode_off(monkeypatch):
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "0")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    a = build_analysis(
        "SOL 5m",
        market=None,
        market_err=None,
        ctx=None,
        ctx_err=None,
        trend=None,
        trend_err=None,
        policy={"mode": "NORMAL", "reasoning": "t"},
        policy_err=None,
        use_snapshot=False,
        use_ctx=False,
        use_trend=False,
        use_policy=True,
        conn=None,
        use_llm=False,
        market_data_tick=_tick(),
        market_data_err=None,
    )
    mcp = a.get("memory_control_plane") or {}
    assert mcp["engagement_mode"] == MODE_OFF
    assert mcp["lesson_memory_env_on"] is False


def test_detect_problem_signals_semantic_ambiguity():
    s = detect_problem_signals(
        input_text="Maybe SOL 5m or 1h — unclear",
        guardrail_mode="NORMAL",
        risk_level="low",
        readiness=None,
        playbook_hit=False,
        merged_rule_facts={"structured": {}},
    )
    assert s["semantic_ambiguity"] is True


def test_select_engagement_mode_intensified():
    sig = {
        "semantic_ambiguity": False,
        "low_confidence_derived": True,
        "conflicting_signals": False,
        "elevated_risk": True,
        "bypass_lesson_memory": False,
        "clear_routine": False,
        "playbook_hit": False,
    }
    assert select_engagement_mode(sig, guardrail_mode="NORMAL", risk_level="medium") == MODE_INTENSIFIED
