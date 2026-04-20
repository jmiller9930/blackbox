"""
Directive 03 — Context plurality (minimum vs target).

* MUST: causal ``bars_inclusive_up_to_t`` on every built packet (non-empty for real fixtures).
* SHOULD: ``retrieved_student_experience_v1`` non-empty when learning store matches signature.
* Target: versioned ``student_context_annex_v1`` (``TRADING_CONTEXT_REFERENCE_V1`` buckets) only
  when attached as a legal annex passing pre-reveal + packet validation.
"""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1,
    FIELD_STUDENT_CONTEXT_ANNEX_V1,
    SCHEMA_STUDENT_CONTEXT_ANNEX_V1,
    TRADING_CONTEXT_BUCKET_KEYS_V1,
    legal_example_student_context_annex_v1,
    validate_student_context_annex_v1,
)
from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
    build_student_decision_packet_v1_with_cross_run_retrieval,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    attach_student_context_annex_v1,
    build_student_decision_packet_v1,
    validate_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
)
from renaissance_v4.game_theory.tests.test_cross_run_retrieval_v1 import _learning_row


def _mk_synthetic_db(db_path: Path) -> None:
    """Minimal OHLCV rows for TESTUSDT (same spirit as student_context_builder tests)."""
    import sqlite3

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_bars_5m (
                open_time INTEGER, symbol TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL
            )
            """
        )
        conn.execute("DELETE FROM market_bars_5m WHERE symbol = ?", ("TESTUSDT",))
        for t in (4_999_000, 5_000_000):
            conn.execute(
                """
                INSERT INTO market_bars_5m (open_time, symbol, open, high, low, close, volume)
                VALUES (?, 'TESTUSDT', 100, 101, 99, 100.5, 1000)
                """,
                (t,),
            )
        conn.commit()


def test_d3_must_have_causal_bars(tmp_path: Path) -> None:
    db = tmp_path / "d3.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1(
        db_path=db, symbol="TESTUSDT", decision_open_time_ms=5_000_000
    )
    assert err is None and pkt is not None
    bars = pkt["bars_inclusive_up_to_t"]
    assert isinstance(bars, list) and len(bars) >= 1
    assert all(int(r["open_time"]) <= 5_000_000 for r in bars)


def test_d3_retrieval_nonempty_when_store_matches(tmp_path: Path) -> None:
    store = tmp_path / "sl.jsonl"
    append_student_learning_record_v1(
        store, _learning_row(rid="lr_d3", run_id="r_d3", sig="sig_d3", trade="tr_d3")
    )
    db = tmp_path / "m.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=5_000_000,
        store_path=store,
        retrieval_signature_key="sig_d3",
        max_retrieval_slices=8,
    )
    assert err is None and pkt is not None
    raw = pkt.get(FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1)
    assert isinstance(raw, list) and len(raw) == 1
    assert validate_student_decision_packet_v1(pkt) == []


def test_d3_versioned_annex_passes_and_merge(tmp_path: Path) -> None:
    db = tmp_path / "annex.sqlite3"
    _mk_synthetic_db(db)
    base, err = build_student_decision_packet_v1(
        db_path=db, symbol="TESTUSDT", decision_open_time_ms=5_000_000
    )
    assert err is None and base is not None
    annex = legal_example_student_context_annex_v1()
    assert validate_student_context_annex_v1(annex) == []
    merged, merr = attach_student_context_annex_v1(base, annex)
    assert merr is None and merged is not None
    assert merged.get(FIELD_STUDENT_CONTEXT_ANNEX_V1) is annex
    assert validate_student_decision_packet_v1(merged) == []


def test_d3_annex_unknown_top_level_key_rejected() -> None:
    a = legal_example_student_context_annex_v1()
    a["extra_noise"] = {}
    assert validate_student_context_annex_v1(a)


def test_d3_annex_nested_forbidden_key_rejected() -> None:
    a = legal_example_student_context_annex_v1()
    a["price_context"] = {"pnl": 1.0}
    assert validate_student_context_annex_v1(a)


def test_d3_trading_context_bucket_keys_aligned_with_contract() -> None:
    assert TRADING_CONTEXT_BUCKET_KEYS_V1 == frozenset(
        {"price_context", "structure_context", "indicator_context", "time_context"}
    )
    assert SCHEMA_STUDENT_CONTEXT_ANNEX_V1 == "student_context_annex_v1"


def test_d3_pattern_recipe_ids_on_shadow_output_strings(tmp_path: Path) -> None:
    """MAY: pattern/cookbook tags on ``student_output_v1`` (shadow stub uses str ids)."""
    from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import emit_shadow_stub_student_output_v1

    db = tmp_path / "shadow.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1(
        db_path=db, symbol="TESTUSDT", decision_open_time_ms=5_000_000
    )
    assert err is None and pkt
    out, e2 = emit_shadow_stub_student_output_v1(pkt, graded_unit_id="gx")
    assert not e2 and out
    pr = out.get("pattern_recipe_ids")
    assert isinstance(pr, list) and all(isinstance(x, str) for x in pr)


def test_d3_shadow_stub_accepts_packet_with_context_annex(tmp_path: Path) -> None:
    """Shadow Student ignores annex for heuristics but packet must stay valid."""
    from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import emit_shadow_stub_student_output_v1

    db = tmp_path / "shadow2.sqlite3"
    _mk_synthetic_db(db)
    base, err = build_student_decision_packet_v1(
        db_path=db, symbol="TESTUSDT", decision_open_time_ms=5_000_000
    )
    assert err is None and base
    merged, merr = attach_student_context_annex_v1(base, legal_example_student_context_annex_v1())
    assert merr is None and merged
    out, e2 = emit_shadow_stub_student_output_v1(merged, graded_unit_id="gy")
    assert not e2 and out
