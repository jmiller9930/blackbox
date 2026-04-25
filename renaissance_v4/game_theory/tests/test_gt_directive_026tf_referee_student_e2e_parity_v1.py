"""
GT_DIRECTIVE_026TF — **Final e2e parity** (unblocks formal closeout).

Proves the **Referee** pre-loop tape (``load_replay_pre_loop_bars_v1``, the exact dataset
``run_manifest_replay`` uses after rollup) matches ``build_student_decision_packet_v1`` for the same
``decision_open_time_ms`` and ``candle_timeframe_minutes`` on a **single-symbol** database.

**Condition:** The Referee path loads the full table in global time order; the Student path loads
all rows for one symbol. When the DB contains only one symbol, the two sequences are identical —
this test encodes that contract.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from renaissance_v4.research.replay_runner import load_replay_pre_loop_bars_v1
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
)

SYMBOL = "GT026TF_PARITY"


def _mk_single_symbol_bars(path: Path, n: int) -> None:
    """n synthetic 5m rows for :data:`SYMBOL` only (Referee and Student are aligned)."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE market_bars_5m (
            open_time INTEGER, symbol TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL
        )
        """
    )
    t0 = 1_000_000
    step = 300_000
    for i in range(n):
        base = 100.0 + (i % 11) * 0.1 + (i % 3) * 0.04
        c = base + 0.03 * (i % 5)
        conn.execute(
            "INSERT INTO market_bars_5m VALUES (?,?,?,?,?,?,?)",
            (t0 + i * step, SYMBOL, base, base + 0.25, base - 0.12, c, 500.0 + i),
        )
    conn.commit()
    conn.close()


@pytest.mark.parametrize("candle_timeframe_minutes", [5, 15, 60])
def test_referee_replay_rolled_bars_match_student_decision_packet_e2e(
    tmp_path: Path,
    candle_timeframe_minutes: int,
) -> None:
    """
    MANDATORY closeout: bar count, timestamp list, OHLCV, and ``candle_timeframe_minutes`` in the
    Student packet match the Referee's ``load_replay_pre_loop_bars_v1`` output at the same cut.
    """
    db = tmp_path / "e2e_single_symbol.sqlite3"
    _mk_single_symbol_bars(db, 64)
    # Causal at bar index 50 (51 bars 5m through cut); sufficient rolled bars for 15m/60m.
    t_cut = 1_000_000 + 50 * 300_000
    max_bars = 10_000

    with sqlite3.connect(str(db)) as conn:
        ref_rows, _audit, ctf = load_replay_pre_loop_bars_v1(
            conn,
            bar_window_calendar_months=None,
            candle_timeframe_minutes=candle_timeframe_minutes,
            verbose=False,
        )
    # Referee tape up to t (inclusive) — same causal rule as Student / closeout tests.
    referee_causal = [r for r in ref_rows if int(r.get("open_time") or 0) <= t_cut]
    if len(referee_causal) > max_bars:
        referee_causal = referee_causal[-max_bars:]

    pkt, err = build_student_decision_packet_v1(
        db_path=db,
        symbol=SYMBOL,
        decision_open_time_ms=t_cut,
        candle_timeframe_minutes=candle_timeframe_minutes,
        max_bars_in_packet=max_bars,
    )
    assert not err and pkt
    stu = pkt["bars_inclusive_up_to_t"]

    assert pkt.get("candle_timeframe_minutes") == int(candle_timeframe_minutes)
    # Parsed TF from the same kwargs as run_manifest_replay (5 = base bars, no rollup branch).
    assert ctf == int(candle_timeframe_minutes)

    r_ts = [int(x["open_time"]) for x in referee_causal]
    s_ts = [int(x["open_time"]) for x in stu]
    assert r_ts == s_ts, f"timestamp list mismatch for TF {candle_timeframe_minutes}m"
    assert len(stu) == len(referee_causal)

    for br, bs in zip(referee_causal, stu, strict=True):
        for k in ("open", "high", "low", "close", "volume"):
            assert abs(float(br[k]) - float(bs[k])) < 1e-9, f"{k} mismatch at open_time={br.get('open_time')}"
        assert str(br.get("symbol", "")) == str(bs.get("symbol", "")) == SYMBOL
