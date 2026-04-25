"""
Directive 04 — Memory must matter.

When cross-run retrieval returns **non-empty** slices, policy output (shadow ``student_output_v1``)
**must** differ from the **same** causal bar tape with **no** memory — otherwise retrieval is
inert for observability.

Proof targets (stub implementation):

* ``confidence_01`` is strictly higher with at least one slice vs none (same ``act``).
* ``pattern_recipe_ids`` gains ``cross_run_retrieval_informed_v1``.
* ``student_decision_ref`` and ``reasoning_text`` include retrieval (deterministic deltas).

Retrieval **enabled** but **zero** matches must match **bars-only** shadow output (control).
"""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.student_proctor.contracts_v1 import FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1
from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
    build_student_decision_packet_v1_with_cross_run_retrieval,
)
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import emit_shadow_stub_student_output_v1
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
)
from renaissance_v4.game_theory.tests.test_cross_run_retrieval_v1 import _learning_row
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db

_GRADED = "d4_mem_trade"
_T_OPEN = 5_000_000
_SIG = "student_entry_v1:TESTUSDT:5000000"


def test_d4_shadow_confidence_and_tags_delta_vs_bars_only(tmp_path: Path) -> None:
    db = tmp_path / "d4.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "mem.jsonl"
    append_student_learning_record_v1(
        store,
        _learning_row(rid="lr_d4a", run_id="run_pre", sig=_SIG, trade="prior_t"),
    )

    base, err = build_student_decision_packet_v1(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=_T_OPEN,
        candle_timeframe_minutes=5,
        max_bars_in_packet=500,
    )
    assert err is None and base is not None
    assert FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1 not in base

    rx_pkt, rerr = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=_T_OPEN, 
        candle_timeframe_minutes=5,
        store_path=store,
        retrieval_signature_key=_SIG,
        max_bars_in_packet=500,
    )
    assert rerr is None and rx_pkt is not None
    sl = rx_pkt.get(FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1)
    assert isinstance(sl, list) and len(sl) >= 1

    so0, e0 = emit_shadow_stub_student_output_v1(
        base, graded_unit_id=_GRADED, decision_at_ms=_T_OPEN
    )
    so1, e1 = emit_shadow_stub_student_output_v1(
        rx_pkt, graded_unit_id=_GRADED, decision_at_ms=_T_OPEN
    )
    assert not e0 and not e1 and so0 and so1

    assert so0["confidence_01"] < so1["confidence_01"]
    assert so0["pattern_recipe_ids"] == ["shadow_stub_v1"]
    assert "cross_run_retrieval_informed_v1" in so1["pattern_recipe_ids"]
    assert so0["student_decision_ref"] != so1["student_decision_ref"]
    assert "retrieval_slices=" not in (so0.get("reasoning_text") or "")
    assert "retrieval_slices=" in (so1.get("reasoning_text") or "")


def test_d4_zero_matches_matches_bars_only_shadow_output(tmp_path: Path) -> None:
    """Wrong signature → empty retrieval; shadow must match bars-only packet."""
    db = tmp_path / "d4b.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "empty_sig.jsonl"
    append_student_learning_record_v1(
        store,
        _learning_row(rid="lr_d4b", run_id="run_x", sig="other_sig", trade="tx"),
    )

    base, err = build_student_decision_packet_v1(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=_T_OPEN,
        candle_timeframe_minutes=5,
        max_bars_in_packet=500,
    )
    miss, rerr = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=_T_OPEN, 
        candle_timeframe_minutes=5,
        store_path=store,
        retrieval_signature_key=_SIG,
        max_bars_in_packet=500,
    )
    assert err is None and rerr is None and base and miss
    assert miss[FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1] == []

    a, ea = emit_shadow_stub_student_output_v1(base, graded_unit_id="z", decision_at_ms=_T_OPEN)
    b, eb = emit_shadow_stub_student_output_v1(miss, graded_unit_id="z", decision_at_ms=_T_OPEN)
    assert not ea and not eb and a and b
    keys_obs = ("confidence_01", "direction", "act", "pattern_recipe_ids", "student_decision_ref")
    for k in keys_obs:
        assert a[k] == b[k], k


def test_d4_confidence_monotone_in_retrieval_count(tmp_path: Path) -> None:
    db = tmp_path / "d4c.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "multi.jsonl"
    for i in range(3):
        append_student_learning_record_v1(
            store,
            _learning_row(
                rid=f"lr_{i}", run_id=f"r{i}", sig=_SIG, trade=f"t{i}",
            ),
        )
    pkt, err = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=_T_OPEN, 
        candle_timeframe_minutes=5,
        store_path=store,
        retrieval_signature_key=_SIG,
        max_retrieval_slices=8,
        max_bars_in_packet=500,
    )
    assert err is None and pkt is not None
    n = len(pkt[FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1])
    assert n >= 2
    s_hi, _ = emit_shadow_stub_student_output_v1(pkt, graded_unit_id="g", decision_at_ms=_T_OPEN)

    pkt_one, err2 = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=_T_OPEN, 
        candle_timeframe_minutes=5,
        store_path=store,
        retrieval_signature_key=_SIG,
        max_retrieval_slices=1,
        max_bars_in_packet=500,
    )
    assert err2 is None and pkt_one is not None
    assert len(pkt_one[FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1]) == 1
    s_lo, _ = emit_shadow_stub_student_output_v1(pkt_one, graded_unit_id="g", decision_at_ms=_T_OPEN)
    assert s_hi["confidence_01"] > s_lo["confidence_01"]


def test_d4_operator_audit_nonzero_retrieval_when_store_seeded(tmp_path: Path) -> None:
    db = tmp_path / "d4op.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "op.jsonl"
    append_student_learning_record_v1(
        store,
        _learning_row(rid="lr_op", run_id="seed", sig=_SIG, trade="old"),
    )
    o = OutcomeRecord(
        trade_id="live_trade",
        symbol="TESTUSDT",
        direction="long",
        entry_time=_T_OPEN,
        exit_time=_T_OPEN + 100_000,
        entry_price=100.0,
        exit_price=100.5,
        pnl=0.5,
        mae=0.0,
        mfe=0.2,
        exit_reason="tp",
    )
    audit = student_loop_seam_after_parallel_batch_v1(
        results=[
            {
                "ok": True,
                "scenario_id": "sc_d4",
                "replay_outcomes_json": [outcome_record_to_jsonable(o)],
            }
        ],
        run_id="run_d4_audit",
        db_path=db,
        store_path=store,
    )
    assert int(audit.get("student_retrieval_matches") or 0) >= 1
    pt = audit.get("primary_trade_shadow_student_v1")
    assert isinstance(pt, dict)
    assert int(pt.get("retrieval_slice_count") or 0) >= 1
    assert "cross_run_retrieval_informed_v1" in (pt.get("pattern_recipe_ids") or [])
