"""W9a — structured lesson memory: storage, similarity retrieval, FACT lines (no full analysis hook in W9a)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# scripts/runtime on path
import sys

_REPO = Path(__file__).resolve().parents[1]
_RT = _REPO / "scripts" / "runtime"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_RT) not in sys.path:
    sys.path.insert(0, str(_RT))

from _db import connect, ensure_schema  # noqa: E402
from anna_modules.lesson_memory import (  # noqa: E402
    STATUS_CANDIDATE,
    STATUS_VALIDATED,
    build_lesson_memory_fact_lines,
    build_situation,
    insert_lesson,
    retrieve_lessons_for_situation,
    score_lesson,
)


@pytest.fixture()
def lesson_db():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "t.sqlite"
        conn = connect(db_path)
        ensure_schema(conn, _REPO)
        yield conn
        conn.close()


def test_candidate_never_retrieved(lesson_db):
    """Unvalidated lessons must not appear in similarity retrieval."""
    insert_lesson(
        lesson_db,
        lesson_text="Always use stops on SOL",
        validation_status=STATUS_CANDIDATE,
        symbol="SOL",
        regime_tag="volatile",
    )
    sit = build_situation(input_text="SOL 5m long", regime_tag="volatile")
    out = retrieve_lessons_for_situation(lesson_db, sit, min_score=1, top_k=5)
    assert out == []


def test_validated_similarity_retrieval_and_facts(lesson_db):
    """Validated lesson with matching symbol+regime scores high; FACT lines produced."""
    insert_lesson(
        lesson_db,
        lesson_text="In volatile regime, reduce size on SOL perps.",
        validation_status=STATUS_VALIDATED,
        symbol="SOL-PERP",
        regime_tag="volatile",
        timeframe="5m",
        context_tags=["perp", "risk"],
        situation_summary="SOL vol lesson",
    )
    sit = build_situation(
        input_text="SOL 5m",
        regime_tag="volatile",
        context_tags=["perp"],
    )
    rows = retrieve_lessons_for_situation(lesson_db, sit, min_score=3, top_k=3)
    assert len(rows) == 1
    assert rows[0][1] >= 3

    facts, injected = build_lesson_memory_fact_lines(lesson_db, sit)
    assert len(facts) == 1
    assert "FACT (lesson memory):" in facts[0]
    assert "reduce size" in facts[0].lower()
    assert injected[0]["score"] >= 3


def test_near_symbol_match_scores(lesson_db):
    """Near-match: SOL vs SOL-PERP family gets partial symbol score."""
    insert_lesson(
        lesson_db,
        lesson_text="Lesson B",
        validation_status=STATUS_VALIDATED,
        symbol="SOL",
        regime_tag="trend",
    )
    row = {
        "symbol": "SOL-PERP",
        "regime_tag": "trend",
        "timeframe": None,
        "context_tags": "[]",
    }
    sit = build_situation(input_text="SOL-PERP 5m", regime_tag="trend")
    sc = score_lesson(row, sit)
    assert sc >= 3  # 3 exact normalized symbol + 2 regime = 5, or 1+2 if near only - check
    # SOL vs SOL-PERP: normalize both to SOL -> exact +3, regime +2 => 5
    assert sc >= 5


def test_no_memory_empty_facts(lesson_db):
    sit = build_situation(input_text="ETH 1h", regime_tag="calm")
    facts, injected = build_lesson_memory_fact_lines(lesson_db, sit)
    assert facts == [] and injected == []


def test_top_k_bounds(lesson_db):
    for i in range(5):
        insert_lesson(
            lesson_db,
            lesson_text=f"L{i}",
            validation_status=STATUS_VALIDATED,
            symbol="BTC",
            regime_tag="r",
        )
    sit = build_situation(input_text="BTC 5m", regime_tag="r")
    rows = retrieve_lessons_for_situation(lesson_db, sit, min_score=3, top_k=2)
    assert len(rows) <= 2
