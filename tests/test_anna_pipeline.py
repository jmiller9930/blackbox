"""Anna pipeline: context stop, memory, pipeline metadata."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from _db import ensure_schema, seed_agents
from _paths import repo_root
from anna_modules.analysis import build_analysis
from learning_core.store import get_learning_record_by_source, transition_learning_record


def _ctx(conn=None):
    return dict(
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
        conn=conn,
    )


def test_clarification_stops_pipeline():
    a = build_analysis("Should we take it?", **_ctx())
    assert a["pipeline"]["answer_source"] == "clarification_requested"
    assert "Need a bit more context" in (a.get("interpretation") or {}).get("headline", "")


def test_memory_reuse_after_store():
    root = repo_root()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn, root)
    seed_agents(conn)

    q = "If a setup scores 61 confidence after adjustments and our threshold is 65, what should happen?"
    os.environ["ANNA_USE_LLM"] = "0"
    first = build_analysis(q, **_ctx(conn=conn))
    assert first["pipeline"]["answer_source"] == "rules_only"
    mem_id = first.get("pipeline", {}).get("stored_memory_id")
    assert mem_id

    # 4.6.3.2 Part A: candidate memory is not reusable.
    second = build_analysis(q, **_ctx(conn=conn))
    assert second["pipeline"]["answer_source"] == "rules_only"

    rec = get_learning_record_by_source(
        conn,
        source="anna_context_memory",
        source_record_id=str(mem_id),
    )
    assert rec is not None
    assert rec.state == "candidate"
    transition_learning_record(conn, record_id=rec.id, to_state="under_test", notes="test promotion")
    transition_learning_record(conn, record_id=rec.id, to_state="validated", notes="validated for reuse")

    third = build_analysis(q, **_ctx(conn=conn))
    assert third["pipeline"]["answer_source"] == "memory_only"
    assert "61" in str(third["interpretation"].get("summary", ""))


def test_playbook_rules_without_llm():
    os.environ["ANNA_USE_LLM"] = "0"
    a = build_analysis(
        "What conditions would make you refuse a signal even if RSI divergence appears valid?",
        **_ctx(),
    )
    assert a["pipeline"]["answer_source"] == "rules_only"
    assert a.get("strategy_playbook_applied") is True


def test_what_is_spread_uses_registry_without_llm():
    os.environ["ANNA_USE_LLM"] = "0"
    a = build_analysis("What is a spread?", **_ctx())
    assert a["pipeline"]["answer_source"] == "registry_definition"
    summ = str((a.get("interpretation") or {}).get("summary") or "")
    assert "bid" in summ.lower() and "ask" in summ.lower()
    assert "difference" in summ.lower() or "ask minus bid" in summ.lower()
