"""
W9b/W9c — lesson memory wired into build_analysis; side-by-side proof (memory on vs off).

Uses temp SQLite + ensure_schema; no Ollama required for structural proof.
Material change to reasoning when LLM is on is environment-dependent; we prove:
  - FACT injection into merged_rule_facts path (pipeline.lesson_memory.facts)
  - With memory disabled or empty, no lesson facts
  - With memory enabled + validated lesson, lesson facts present and differ from disabled run
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
import sys

import pytest

_REPO = Path(__file__).resolve().parents[1]
_RT = _REPO / "scripts" / "runtime"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_RT) not in sys.path:
    sys.path.insert(0, str(_RT))

from _db import connect, ensure_schema  # noqa: E402
from anna_modules.analysis import build_analysis  # noqa: E402
from anna_modules.lesson_memory import (  # noqa: E402
    STATUS_VALIDATED,
    insert_lesson,
)


def _tick_nominal():
    return {"symbol": "SOL-PERP", "gate_state": "ok", "price": 100.0}


@pytest.fixture()
def lesson_conn():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "e2e.sqlite"
        conn = connect(db_path)
        ensure_schema(conn, _REPO)
        insert_lesson(
            conn,
            lesson_text="W9 proof lesson: when gate is nominal on SOL perps, cite liquidity before sizing.",
            validation_status=STATUS_VALIDATED,
            symbol="SOL",
            regime_tag="nominal",
            timeframe="5m",
            situation_summary="e2e",
        )
        yield conn
        conn.close()


def test_build_analysis_injects_lesson_facts_when_enabled(lesson_conn, monkeypatch):
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "1")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    a = build_analysis(
        "SOL 5m — should match lesson symbol and nominal regime",
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
        conn=lesson_conn,
        use_llm=False,
        market_data_tick=_tick_nominal(),
        market_data_err=None,
    )
    lm = a.get("lesson_memory") or {}
    assert lm.get("enabled") is True
    assert len(lm.get("facts") or []) >= 1
    assert "W9 proof lesson" in (lm.get("facts") or [""])[0]
    pipe = a.get("pipeline") or {}
    assert "lesson_memory" in pipe
    assert len(pipe["lesson_memory"].get("facts") or []) >= 1


def test_build_analysis_no_lesson_when_disabled(lesson_conn, monkeypatch):
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "0")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    a = build_analysis(
        "SOL 5m — same input",
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
        conn=lesson_conn,
        use_llm=False,
        market_data_tick=_tick_nominal(),
        market_data_err=None,
    )
    lm = a.get("lesson_memory") or {}
    assert lm.get("enabled") is False
    assert (lm.get("facts") or []) == []


def test_side_by_side_fact_count_differs(lesson_conn, monkeypatch):
    """Memory on: non-empty lesson facts. Memory off: empty lesson facts."""
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    monkeypatch.setenv("ANNA_LESSON_MEMORY_DEBUG", "1")

    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "1")
    on = build_analysis(
        "SOL 5m analysis request for e2e",
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
        conn=lesson_conn,
        use_llm=False,
        market_data_tick=_tick_nominal(),
        market_data_err=None,
    )
    n_on = len((on.get("lesson_memory") or {}).get("facts") or [])
    auth_on = len((on.get("lesson_memory") or {}).get("authoritative_facts_all") or [])

    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "0")
    off = build_analysis(
        "SOL 5m analysis request for e2e",
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
        conn=lesson_conn,
        use_llm=False,
        market_data_tick=_tick_nominal(),
        market_data_err=None,
    )
    n_off = len((off.get("lesson_memory") or {}).get("facts") or [])

    assert n_on >= 1
    assert n_off == 0
    assert auth_on >= n_on  # debug snapshot includes all authoritative facts


def test_candidate_lesson_not_injected(lesson_conn, monkeypatch):
    insert_lesson(
        lesson_conn,
        lesson_text="SHOULD NOT APPEAR",
        validation_status="candidate",
        symbol="SOL",
        regime_tag="nominal",
    )
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "1")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    a = build_analysis(
        "SOL 5m",
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
        conn=lesson_conn,
        use_llm=False,
        market_data_tick=_tick_nominal(),
        market_data_err=None,
    )
    facts = (a.get("lesson_memory") or {}).get("facts") or []
    assert not any("SHOULD NOT APPEAR" in f for f in facts)
