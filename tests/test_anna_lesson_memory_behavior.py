"""
W9 behavioral acceptance — same input, memory on vs off: structured outcomes differ (not wording-only).

Uses validated lesson with context_tags JSON ``behavior_effect: tighten_suggested_action`` so that when
baseline policy would yield ``PAPER_TRADE_READY``, injected memory deterministically tightens to ``WATCH``,
which changes ``classify_proposal_type`` (NO_CHANGE → OBSERVATION_ONLY) for NORMAL/low-risk sessions.
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
from anna_modules.policy import LESSON_BEHAVIOR_TIGHTEN_SUGGESTED  # noqa: E402
from anna_modules.proposal import classify_proposal_type  # noqa: E402


def _tick_nominal():
    return {"symbol": "SOL-PERP", "gate_state": "ok", "price": 100.0}


def _normal_policy():
    return {"mode": "NORMAL", "reasoning": "behavioral proof fixture"}


# Avoid input tokens that bump risk to medium ("risk", "risky") or negate PAPER_TRADE_READY.
_INPUT = "SOL 5m structure view"


@pytest.fixture()
def behavior_conn():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "behavior.sqlite"
        conn = connect(db_path)
        ensure_schema(conn, _REPO)
        insert_lesson(
            conn,
            lesson_text="Behavioral proof: validated lesson prefers observation over paper rehearsal here.",
            validation_status=STATUS_VALIDATED,
            symbol="SOL",
            regime_tag="nominal",
            timeframe="5m",
            situation_summary="w9 behavior",
            context_tags={
                "tags": ["structure"],
                "behavior_effect": LESSON_BEHAVIOR_TIGHTEN_SUGGESTED,
            },
        )
        yield conn
        conn.close()


def test_same_input_memory_off_paper_ready_no_change_proposal(behavior_conn, monkeypatch):
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "0")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    a = build_analysis(
        _INPUT,
        market=None,
        market_err=None,
        ctx=None,
        ctx_err=None,
        trend=None,
        trend_err=None,
        policy=_normal_policy(),
        policy_err=None,
        use_snapshot=False,
        use_ctx=False,
        use_trend=False,
        use_policy=True,
        conn=behavior_conn,
        use_llm=False,
        market_data_tick=_tick_nominal(),
        market_data_err=None,
    )
    assert (a.get("suggested_action") or {}).get("intent") == "PAPER_TRADE_READY"
    assert classify_proposal_type(a) == "NO_CHANGE"
    assert not (a.get("lesson_memory") or {}).get("behavior_applied")


def test_same_input_memory_on_tightens_intent_and_proposal_type(behavior_conn, monkeypatch):
    monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "1")
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    a = build_analysis(
        _INPUT,
        market=None,
        market_err=None,
        ctx=None,
        ctx_err=None,
        trend=None,
        trend_err=None,
        policy=_normal_policy(),
        policy_err=None,
        use_snapshot=False,
        use_ctx=False,
        use_trend=False,
        use_policy=True,
        conn=behavior_conn,
        use_llm=False,
        market_data_tick=_tick_nominal(),
        market_data_err=None,
    )
    assert (a.get("suggested_action") or {}).get("intent") == "WATCH"
    assert classify_proposal_type(a) == "OBSERVATION_ONLY"
    assert (a.get("lesson_memory") or {}).get("behavior_applied") == [LESSON_BEHAVIOR_TIGHTEN_SUGGESTED]


def test_behavior_effect_requires_validated_injection(monkeypatch):
    """Candidate-only lesson does not inject → baseline PAPER_TRADE_READY unchanged."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "cand.sqlite"
        conn = connect(db_path)
        ensure_schema(conn, _REPO)
        insert_lesson(
            conn,
            lesson_text="Candidate should not tighten.",
            validation_status="candidate",
            symbol="SOL",
            regime_tag="nominal",
            timeframe="5m",
            context_tags={"tags": [], "behavior_effect": LESSON_BEHAVIOR_TIGHTEN_SUGGESTED},
        )
        monkeypatch.setenv("ANNA_LESSON_MEMORY_ENABLED", "1")
        monkeypatch.setenv("ANNA_USE_LLM", "0")
        a = build_analysis(
            _INPUT,
            market=None,
            market_err=None,
            ctx=None,
            ctx_err=None,
            trend=None,
            trend_err=None,
            policy=_normal_policy(),
            policy_err=None,
            use_snapshot=False,
            use_ctx=False,
            use_trend=False,
            use_policy=True,
            conn=conn,
            use_llm=False,
            market_data_tick=_tick_nominal(),
            market_data_err=None,
        )
        assert (a.get("suggested_action") or {}).get("intent") == "PAPER_TRADE_READY"
        conn.close()
