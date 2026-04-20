"""
Directive 02 — Student context builder: causal packets, multi-timestep, no-leak proof.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
    fetch_bars_causal_up_to,
    validate_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import validate_pre_reveal_bundle_v1


def _mk_synthetic_db(path: Path) -> None:
    """Minimal market_bars_5m with 10 synthetic 5m bars for TESTUSDT."""
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
    sym = "TESTUSDT"
    for i in range(1, 11):
        ts = i * 1_000_000  # distinct open_times
        conn.execute(
            """
            INSERT INTO market_bars_5m (open_time, symbol, open, high, low, close, volume)
            VALUES (?, ?, 100, 101, 99, 100.5, 1000)
            """,
            (ts, sym),
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def synthetic_db(tmp_path: Path) -> Path:
    p = tmp_path / "t.sqlite3"
    _mk_synthetic_db(p)
    return p


def test_fetch_causal_multiple_timesteps(synthetic_db: Path) -> None:
    """Timestep 3M → bars 1M..3M; timestep 7M → bars 1M..7M (causal only)."""
    sym = "TESTUSDT"
    r3, e3 = fetch_bars_causal_up_to(
        db_path=synthetic_db, symbol=sym, decision_open_time_ms=3_000_000, max_bars_in_packet=500
    )
    assert e3 is None
    assert len(r3) == 3
    assert r3[-1]["open_time"] == 3_000_000

    r7, e7 = fetch_bars_causal_up_to(
        db_path=synthetic_db, symbol=sym, decision_open_time_ms=7_000_000, max_bars_in_packet=500
    )
    assert e7 is None
    assert len(r7) == 7
    assert max(row["open_time"] for row in r7) == 7_000_000


def test_no_future_bars_causal_boundary(synthetic_db: Path) -> None:
    """No bar in packet may have open_time > decision_open_time_ms."""
    pkt, err = build_student_decision_packet_v1(
        db_path=synthetic_db,
        symbol="TESTUSDT",
        decision_open_time_ms=5_000_000,
        max_bars_in_packet=500,
    )
    assert err is None and pkt is not None
    t_cut = pkt["decision_open_time_ms"]
    for row in pkt["bars_inclusive_up_to_t"]:
        assert int(row["open_time"]) <= t_cut


def test_build_packet_passes_validate_and_pre_reveal(synthetic_db: Path) -> None:
    pkt, err = build_student_decision_packet_v1(
        db_path=synthetic_db,
        symbol="TESTUSDT",
        decision_open_time_ms=8_000_000,
    )
    assert err is None and pkt is not None
    assert validate_student_decision_packet_v1(pkt) == []
    assert validate_pre_reveal_bundle_v1(pkt) == []


def test_packet_schema_enforced_reject_bad_schema() -> None:
    bad = {
        "schema": "wrong",
        "contract_version": 1,
        "symbol": "X",
        "decision_open_time_ms": 1,
        "bars_inclusive_up_to_t": [],
    }
    errs = validate_student_decision_packet_v1(bad)
    assert errs


def test_manual_injected_flashcard_field_fails_pre_reveal(synthetic_db: Path) -> None:
    pkt, err = build_student_decision_packet_v1(
        db_path=synthetic_db, symbol="TESTUSDT", decision_open_time_ms=4_000_000
    )
    assert err is None and pkt is not None
    poisoned = dict(pkt)
    poisoned["pnl"] = 42.0
    assert validate_pre_reveal_bundle_v1(poisoned), "pre_reveal must reject pnl"
    assert validate_student_decision_packet_v1(poisoned), "packet validator must reject"


def test_builder_never_emits_forbidden_keys(synthetic_db: Path) -> None:
    pkt, err = build_student_decision_packet_v1(
        db_path=synthetic_db, symbol="TESTUSDT", decision_open_time_ms=10_000_000
    )
    assert err is None and pkt is not None
    packet_keys = _all_keys_flat(pkt)
    forbidden = {"pnl", "mfe", "mae", "wins", "losses", "exit_time", "exit_reason"}
    assert not (forbidden & packet_keys)


def _all_keys_flat(obj: object, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                keys.add(k.lower())
            keys |= _all_keys_flat(v, prefix + ".")
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys_flat(item, prefix)
    return keys


def test_empty_db_returns_error_not_crash(tmp_path: Path) -> None:
    empty = tmp_path / "empty.sqlite3"
    empty.write_bytes(b"")
    # invalid sqlite — expect error from fetch
    rows, err = fetch_bars_causal_up_to(
        db_path=empty, symbol="X", decision_open_time_ms=1, max_bars_in_packet=10
    )
    assert err is not None or rows == []
