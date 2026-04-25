"""
GT_DIRECTIVE_026TF — Student packet + memory + replay row agree on candle timeframe.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from renaissance_v4.game_theory.candle_timeframe_runtime import (
    CANONICAL_CANDLE_TIMEFRAME_MINUTES_V1,
    effective_replay_timeframe_from_worker_replay_row_v1,
    rollup_5m_rows_to_candle_timeframe,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    list_student_learning_records_by_signature_key_v1,
)
def _mk_empty_5m_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE market_bars_5m (
            open_time INTEGER,
            symbol TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_n_5m_bars(db: Path, n: int) -> None:
    with sqlite3.connect(str(db)) as conn:
        t0 = 1_000_000
        step = 300_000
        for i in range(n):
            conn.execute(
                """
                INSERT OR REPLACE INTO market_bars_5m
                (open_time, symbol, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (t0 + i * step, "TESTUSDT", 1.0, 1.1, 0.9, 1.05, 100.0 + i),
            )


def test_5m_vs_60m_bar_counts_differ(tmp_path: Path) -> None:
    db = tmp_path / "tf.sqlite3"
    _mk_empty_5m_db(db)
    _insert_n_5m_bars(db, 24)
    t_cut = 1_000_000 + 23 * 300_000
    p5, e5 = build_student_decision_packet_v1(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=t_cut,
        candle_timeframe_minutes=5,
        max_bars_in_packet=10_000,
    )
    p60, e60 = build_student_decision_packet_v1(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=t_cut,
        candle_timeframe_minutes=60,
        max_bars_in_packet=10_000,
    )
    assert not e5 and not e60 and p5 and p60
    assert p5["bar_count"] != p60["bar_count"]
    assert p60["bar_count"] < p5["bar_count"]


def test_student_rolled_bars_match_prefix_of_full_rollup(tmp_path: Path) -> None:
    """Prefix causal 5m → roll 60m must match first K rows of full-dataset 60m rollup."""
    db = tmp_path / "align.sqlite3"
    _mk_empty_5m_db(db)
    _insert_n_5m_bars(db, 36)
    t_cut = 1_000_000 + 20 * 300_000
    full_5m: list[sqlite3.Row] = []
    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT open_time, symbol, open, high, low, close, volume FROM market_bars_5m "
            "WHERE symbol = ? ORDER BY open_time ASC",
            ("TESTUSDT",),
        )
        full_5m = list(cur.fetchall())
    full_60, _a = rollup_5m_rows_to_candle_timeframe(list(full_5m), target_minutes=60)
    pkt, err = build_student_decision_packet_v1(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=t_cut,
        candle_timeframe_minutes=60,
        max_bars_in_packet=10_000,
    )
    assert not err and pkt
    stu = pkt["bars_inclusive_up_to_t"]
    # find how many full_60 bars are fully <= t_cut
    head = [r for r in full_60 if int(r["open_time"]) <= t_cut]
    assert len(stu) == len(head)
    for a, b in zip(stu, head, strict=True):
        assert int(a["open_time"]) == int(b["open_time"])


def test_memory_retrieval_isolates_timeframe(tmp_path: Path) -> None:
    store = tmp_path / "mem.jsonl"
    rec_5 = {
        "schema": "student_learning_record_v1",
        "contract_version": 1,
        "record_id": "r5",
        "created_utc": "2026-04-24T00:00:00Z",
        "run_id": "x",
        "graded_unit_id": "g1",
        "candle_timeframe_minutes": 5,
        "context_signature_v1": {"schema": "context_signature_v1", "signature_key": "student_entry_v1:TESTUSDT:1:5"},
        "student_output": {
            "schema": "student_output_v1",
            "contract_version": 1,
            "graded_unit_type": "closed_trade",
            "graded_unit_id": "g1",
            "decision_at_ms": 1,
            "act": True,
            "direction": "long",
            "pattern_recipe_ids": ["x"],
            "confidence_01": 0.5,
            "reasoning_text": None,
            "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
        },
        "referee_outcome_subset": {"pnl": 1.0},
        "alignment_flags_v1": {},
    }
    rec_60 = dict(rec_5)
    rec_60["record_id"] = "r60"
    rec_60["candle_timeframe_minutes"] = 60
    rec_60["context_signature_v1"] = {
        "schema": "context_signature_v1",
        "signature_key": "student_entry_v1:TESTUSDT:1:60",
    }
    append_student_learning_record_v1(store, rec_5)
    append_student_learning_record_v1(store, rec_60)
    m5 = list_student_learning_records_by_signature_key_v1(
        store,
        "student_entry_v1:TESTUSDT:1:5",
        run_candle_timeframe_minutes=5,
    )
    m60 = list_student_learning_records_by_signature_key_v1(
        store,
        "student_entry_v1:TESTUSDT:1:60",
        run_candle_timeframe_minutes=60,
    )
    assert len(m5) == 1 and m5[0]["record_id"] == "r5"
    assert len(m60) == 1 and m60[0]["record_id"] == "r60"


def test_effective_replay_row_prefers_top_level_minutes() -> None:
    row = {
        "ok": True,
        "replay_timeframe_minutes": 60,
        "replay_data_audit": {},
    }
    assert effective_replay_timeframe_from_worker_replay_row_v1(row) == 60


@pytest.mark.parametrize("m", sorted(CANONICAL_CANDLE_TIMEFRAME_MINUTES_V1))
def test_canonical_minutes_are_expected(m: int) -> None:
    assert m in (5, 15, 60, 240)
