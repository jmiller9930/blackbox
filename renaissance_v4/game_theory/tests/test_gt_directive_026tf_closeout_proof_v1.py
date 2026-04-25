"""
GT_DIRECTIVE_026TF — **Closeout proof** (foreclosure / acceptance gate).

These tests assert what the directive requires: bar parity, indicator deltas across TF,
memory isolation, mismatch detection, and trace handoff fields — not narrative explanations.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from renaissance_v4.game_theory.candle_timeframe_runtime import rollup_5m_rows_to_candle_timeframe
from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
    emit_candle_timeframe_nexus_v1,
    emit_learning_record_appended_v1,
    emit_memory_retrieval_completed_v1,
    emit_timeframe_mismatch_detected_v1,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import legal_example_student_learning_record_v1
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
    fetch_bars_causal_up_to,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    list_student_learning_records_by_signature_key_v1,
)
from renaissance_v4.utils.math_utils import ema as ema_last


def _mk_db_many_5m(path: Path, n: int) -> None:
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
        base = 100.0 + (i % 7) * 0.1 + (i % 3) * 0.05
        c = base + 0.02 * (i % 5)
        conn.execute(
            "INSERT INTO market_bars_5m VALUES (?,?,?,?,?,?,?)",
            (t0 + i * step, "TESTUSDT", base, base + 0.2, base - 0.1, c, 1000.0 + i),
        )
    conn.commit()
    conn.close()


def _replay_style_rolled_bars(
    *, db: Path, symbol: str, decision_open_time_ms: int, candle_timeframe_minutes: int, max_5m: int
) -> list[dict[str, Any]]:
    """
    Match replay: load full ascending 5m for symbol, then rollup — same as ``run_manifest_replay``
    (no calendar window). Filter to ``open_time <= decision`` like the Student packet.
    """
    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT open_time, symbol, open, high, low, close, volume FROM market_bars_5m "
            "WHERE symbol = ? ORDER BY open_time ASC",
            (symbol,),
        )
        all_rows = list(cur.fetchall())
    if candle_timeframe_minutes == 5:
        out, _ = rollup_5m_rows_to_candle_timeframe(list(all_rows), target_minutes=5)
    else:
        out, _ = rollup_5m_rows_to_candle_timeframe(list(all_rows), target_minutes=candle_timeframe_minutes)
    cut = int(decision_open_time_ms)
    causal = [dict(r) for r in out if int(r.get("open_time") or 0) <= cut]
    if len(causal) > max_5m and candle_timeframe_minutes == 5:
        causal = causal[-max_5m:]
    elif len(causal) > 10_000:
        causal = causal[-10_000:]
    return causal


def _wilder_rsi_last(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


@pytest.mark.parametrize("tf", [5, 60])
def test_026tf_replay_vs_student_bar_parity_by_open_time(tmp_path: Path, tf: int) -> None:
    """MANDATORY: replay-style rollup (full DB) vs Student packet — identical timestamps & count (per TF)."""
    db = tmp_path / f"p_{tf}.sqlite3"
    _mk_db_many_5m(db, 48)
    t_cut = 1_000_000 + 30 * 300_000
    max_5m = 10_000
    replay_bars = _replay_style_rolled_bars(
        db=db,
        symbol="TESTUSDT",
        decision_open_time_ms=t_cut,
        candle_timeframe_minutes=tf,
        max_5m=max_5m,
    )
    stu, err = build_student_decision_packet_v1(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=t_cut,
        candle_timeframe_minutes=tf,
        max_bars_in_packet=max_5m,
    )
    assert not err and stu
    s_bars = stu["bars_inclusive_up_to_t"]
    r_ts = [int(x["open_time"]) for x in replay_bars]
    s_ts = [int(x["open_time"]) for x in s_bars]
    assert r_ts == s_ts, f"TF={tf}m: replay_ts != student_ts (len {len(r_ts)} vs {len(s_ts)})"
    assert len(s_bars) == len(replay_bars)
    for br, bs in zip(replay_bars, s_bars, strict=True):
        for k in ("open_time", "open", "high", "low", "close", "volume"):
            assert abs(float(br[k]) - float(bs[k])) < 1e-9, f"TF={tf} {k} mismatch"


def test_026tf_indicators_differ_5m_vs_60m_same_cut(tmp_path: Path) -> None:
    """MANDATORY: same scenario, 5m vs 1h — RSI / EMA last values differ (series differ)."""
    db = tmp_path / "ind.sqlite3"
    _mk_db_many_5m(db, 220)
    t_cut = 1_000_000 + 200 * 300_000
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
    c5 = [float(b["close"]) for b in p5["bars_inclusive_up_to_t"]]
    c60 = [float(b["close"]) for b in p60["bars_inclusive_up_to_t"]]
    assert len(c5) != len(c60)
    assert len(c5) >= 20 and len(c60) >= 16
    r5 = _wilder_rsi_last(c5, 14)
    r60 = _wilder_rsi_last(c60, 14)
    e5v = ema_last(c5, 14)
    e60v = ema_last(c60, 14)
    assert math.isfinite(r5) and math.isfinite(r60)
    assert abs(r5 - r60) > 1.0, "RSI should differ meaningfully between 5m and 1h on same cut"
    assert abs(e5v - e60v) > 0.01, "EMA should differ between 5m and 1h on same cut"


def test_026tf_memory_isolation_5m_vs_60m_and_legacy_rule(tmp_path: Path) -> None:
    """
    5m run does not retrieve 1h rows; 1h run does not retrieve 3-part-only / 5m-tagged rows.
    Legacy 3-part key matches only 5m runs.
    """
    store = tmp_path / "iso.jsonl"
    rec_1h = legal_example_student_learning_record_v1()
    rec_1h["record_id"] = "a60"
    rec_1h["candle_timeframe_minutes"] = 60
    rec_1h["context_signature_v1"] = {
        "schema": "context_signature_v1",
        "signature_key": "student_entry_v1:TESTUSDT:9:60",
    }
    rec_1h["graded_unit_id"] = "g60"
    append_student_learning_record_v1(store, rec_1h)

    m_bad = list_student_learning_records_by_signature_key_v1(
        store,
        "student_entry_v1:TESTUSDT:9:60",
        run_candle_timeframe_minutes=5,
    )
    assert m_bad == []

    m_ok = list_student_learning_records_by_signature_key_v1(
        store,
        "student_entry_v1:TESTUSDT:9:60",
        run_candle_timeframe_minutes=60,
    )
    assert len(m_ok) == 1

    rec_legacy = legal_example_student_learning_record_v1()
    rec_legacy["record_id"] = "leg"
    rec_legacy["context_signature_v1"] = {
        "schema": "context_signature_v1",
        "signature_key": "student_entry_v1:TESTUSDT:9",
    }
    if "candle_timeframe_minutes" in rec_legacy:
        del rec_legacy["candle_timeframe_minutes"]
    append_student_learning_record_v1(store, rec_legacy)
    m_leg_5 = list_student_learning_records_by_signature_key_v1(
        store,
        "student_entry_v1:TESTUSDT:9:5",
        run_candle_timeframe_minutes=5,
    )
    assert len(m_leg_5) == 1
    m_leg_60 = list_student_learning_records_by_signature_key_v1(
        store,
        "student_entry_v1:TESTUSDT:9:60",
        run_candle_timeframe_minutes=60,
    )
    assert len(m_leg_60) == 1 and m_leg_60[0]["record_id"] == "a60"


def test_026tf_timeframe_mismatch_emitted_to_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, Any]] = []

    def _cap(**kwargs: Any) -> None:
        captured.append(dict(kwargs))

    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_trace_instrumentation_v1._emit",
        _cap,
    )
    emit_timeframe_mismatch_detected_v1(
        job_id="job_proof",
        fingerprint="fp1",
        left_role="run_contract",
        left_minutes=5,
        right_role="replay_worker_row",
        right_minutes=60,
        scenario_id="s1",
    )
    assert any(x.get("stage") == "timeframe_mismatch_detected_v1" for x in captured)
    ev = [x for x in captured if x.get("stage") == "timeframe_mismatch_detected_v1"][-1]
    assert ev.get("status") == "fail"
    ep = ev.get("evidence_payload") or {}
    assert int(ep.get("left_minutes") or 0) == 5
    assert int(ep.get("right_minutes") or 0) == 60


def test_026tf_trace_nexus_stages_contain_candle_timeframe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidence at run contract / replay / student_packet + memory + learning append — TF present."""
    rows: list[dict[str, Any]] = []

    def _cap(**kwargs: Any) -> None:
        rows.append(dict(kwargs))

    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_trace_instrumentation_v1._emit",
        _cap,
    )
    emit_candle_timeframe_nexus_v1(
        job_id="j", fingerprint=None, nexus="run_contract", candle_timeframe_minutes=60
    )
    emit_candle_timeframe_nexus_v1(
        job_id="j", fingerprint=None, nexus="replay", candle_timeframe_minutes=60, scenario_id="s"
    )
    emit_candle_timeframe_nexus_v1(
        job_id="j", fingerprint=None, nexus="student_packet", candle_timeframe_minutes=60, trade_id="t"
    )
    emit_memory_retrieval_completed_v1(
        job_id="j",
        fingerprint=None,
        scenario_id="s",
        trade_id="t",
        retrieval_matches=0,
        candle_timeframe_minutes=60,
        retrieval_signature_key="student_entry_v1:X:1:60",
    )
    emit_learning_record_appended_v1(
        job_id="j",
        fingerprint=None,
        scenario_id="s",
        trade_id="t",
        record_id="r1",
        candle_timeframe_minutes=60,
    )

    for want in ("run_contract", "replay", "student_packet"):
        hit = [x for x in rows if (x.get("evidence_payload") or {}).get("candle_timeframe_nexus") == want]
        assert hit, f"missing nexus {want}"
        assert hit[0].get("evidence_payload", {}).get("candle_timeframe_minutes") == 60
    mem = [x for x in rows if x.get("stage") == "memory_retrieval_completed"][-1]
    assert (mem.get("evidence_payload") or {}).get("candle_timeframe_minutes") == 60
    lr = [x for x in rows if x.get("stage") == "learning_record_appended"][-1]
    assert (lr.get("evidence_payload") or {}).get("candle_timeframe_minutes") == 60
