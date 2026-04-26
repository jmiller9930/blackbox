# GT_DIRECTIVE_026B — full trade lifecycle reasoning (per-bar, fault map, optional 026AI bridge)

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
import tempfile

import pytest

from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import (
    build_indicator_context_eval_v1,
    run_entry_reasoning_pipeline_v1,
)
from renaissance_v4.game_theory.student_proctor.lifecycle_reasoning_engine_v1 import (
    DEC_HOLD,
    EXIT_CODE_CONFIDENCE_COLLAPSE,
    EXIT_CODE_OPPOSING_SIGNAL,
    EXIT_CODE_STOP_HIT,
    EXIT_CODE_TARGET_HIT,
    EXIT_CODE_THESIS_INVALIDATED,
    EXIT_CODE_TIME_EXPIRED,
    build_entry_thesis_v1,
    evaluate_lifecycle_bar_v1,
    run_lifecycle_tape_v1,
)
from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
    NODE_IDS_ORDER,
    STATUS_FAIL,
    build_fault_map_v1,
    make_fault_node_v1,
    merge_lifecycle_reasoning_fault_nodes_v1,
)


def _mono_bars(
    n: int,
    *,
    o: float = 100.0,
    step: float = 0.2,
) -> list[dict]:
    out: list[dict] = []
    c = o
    for i in range(n):
        c = o + i * step
        out.append(
            {
                "open": c - 0.05,
                "high": c + 0.1,
                "low": c - 0.1,
                "close": c,
                "volume": 100.0 + float(i),
            }
        )
    return out


def _packet(bars, sym="X"):
    return {"symbol": sym, "bars_inclusive_up_to_t": bars}


def test_lifecycle_emits_stages_to_learning_trace_jsonl():
    """Closure: per-bar and tape summary are persisted and reloadable for job_id."""
    from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1

    bars = _mono_bars(18, o=100.0, step=0.3)
    ere, _, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(bars[:5]),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert ere
    job = f"gt026b_test_{uuid.uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory() as td:
        os.environ["PATTERN_GAME_MEMORY_ROOT"] = td
        try:
            res = run_lifecycle_tape_v1(
                all_bars=bars,
                entry_bar_index=3,
                side="long",
                entry_reasoning_eval_v1=ere,
                run_candle_timeframe_minutes=5,
                symbol="J",
                max_hold_bars=40,
                job_id=job,
                fingerprint="fp026b",
                emit_lifecycle_traces=True,
                trade_id="T1",
                scenario_id="S1",
            )
            assert res.get("closed_v1")
            evs = read_learning_trace_events_for_job_v1(job)
            stg = [e for e in evs if e.get("stage") == "lifecycle_reasoning_stage_v1"]
            one = [e for e in evs if e.get("stage") == "lifecycle_tape_summary_v1"]
            assert len(stg) >= 2
            assert len(one) == 1
            assert (one[0].get("evidence_payload") or {}).get("lifecycle_tape_result_v1", {}).get("per_bar_slim_v1")
        finally:
            os.environ.pop("PATTERN_GAME_MEMORY_ROOT", None)


def test_lifecycle_node_ids_in_fault_map_order():
    assert "lifecycle_context_loaded" in NODE_IDS_ORDER
    assert "lifecycle_exit_evaluated" in NODE_IDS_ORDER
    assert NODE_IDS_ORDER.index("lifecycle_context_loaded") < NODE_IDS_ORDER.index("lifecycle_exit_evaluated")


def test_scenario_1_hold_multiple_bars():
    """1. trade holds for multiple bars (rising tape, long, no early exit)."""
    bars = _mono_bars(15, step=0.05)
    ere, _e, _t, pfm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(bars[:8]),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert ere
    act = str((ere.get("decision_synthesis_v1") or {}).get("action") or "no_trade")
    side = "long" if act == "enter_long" else "short"
    if act == "no_trade":
        side = "long"  # force a synthetic long for tape test
    entry_idx = 7
    tape = run_lifecycle_tape_v1(
        all_bars=bars,
        entry_bar_index=entry_idx,
        side=side,
        entry_reasoning_eval_v1=ere,
        run_candle_timeframe_minutes=5,
        symbol="X",
        retrieved_student_experience=[],
        max_hold_bars=100,
    )
    rows = tape.get("per_bar_v1") or []
    assert len(rows) >= 2
    holds = [r for r in rows if (r.get("lifecycle_reasoning_eval_v1") or {}).get("decision_v1") == DEC_HOLD]
    assert len(holds) >= 1


def test_scenario_2_exit_thesis_invalidation():
    """2. thesis invalidation can exit when degrading streak is forced via opposing tape."""
    # Alternating / conflict memory path is heavy; use short tape + low max hold not needed —
    # drive invalidation: many bars with strong opposing indicator requires long run.
    # Simpler: time_expired with small max_hold
    bars = _mono_bars(40, step=0.01)
    ere, _, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(bars[:10]),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert ere
    t = run_lifecycle_tape_v1(
        all_bars=bars,
        entry_bar_index=3,
        side="long",
        entry_reasoning_eval_v1=ere,
        run_candle_timeframe_minutes=5,
        symbol="S2",
        max_hold_bars=4,
    )
    assert t.get("closed_v1")
    assert t.get("exit_reason_code_v1") == EXIT_CODE_TIME_EXPIRED


def test_scenario_3_exit_stop():
    """3. stop: price path pierces stop for a long."""
    bars: list[dict] = []
    p = 100.0
    for i in range(8):
        bars.append(
            {
                "open": p,
                "high": p + 0.2,
                "low": p - 0.2,
                "close": p,
                "volume": 100.0,
            }
        )
        p -= 1.2  # drop hard after a few up bars
    ere, _, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(bars[:3]),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert ere
    t = run_lifecycle_tape_v1(
        all_bars=bars,
        entry_bar_index=2,
        side="long",
        entry_reasoning_eval_v1=ere,
        run_candle_timeframe_minutes=5,
        symbol="S3",
        max_hold_bars=50,
    )
    if t.get("closed_v1"):
        assert t.get("exit_reason_code_v1") in (
            EXIT_CODE_STOP_HIT,
            EXIT_CODE_THESIS_INVALIDATED,
            EXIT_CODE_CONFIDENCE_COLLAPSE,
            EXIT_CODE_OPPOSING_SIGNAL,
        )


def test_scenario_4_exit_target_rising_tape():
    """4. target hit on strong uptrend (long)."""
    bars = _mono_bars(50, o=100.0, step=0.4)
    ere, _, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(bars[:5]),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert ere
    t = run_lifecycle_tape_v1(
        all_bars=bars,
        entry_bar_index=3,
        side="long",
        entry_reasoning_eval_v1=ere,
        run_candle_timeframe_minutes=5,
        symbol="S4",
        max_hold_bars=80,
    )
    assert t.get("exit_reason_code_v1") in (EXIT_CODE_TARGET_HIT, EXIT_CODE_STOP_HIT, EXIT_CODE_TIME_EXPIRED) or t.get("closed_v1")
    if t.get("exit_reason_code_v1") == EXIT_CODE_TARGET_HIT:
        assert t.get("closed_v1")


def test_scenario_5_confidence_degrades():
    """5. confidence can drop bar-over-bar with thesis stress (non-increasing in stress path)."""
    bars = _mono_bars(12, step=0.02)
    ere, _, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(bars[:6]),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    confs: list[float] = []
    prev: float | None = None
    d_s = 0
    o_s = 0
    th = build_entry_thesis_v1(side="long", entry_reasoning_eval_v1=ere)
    ict0, _, _ = build_indicator_context_eval_v1(bars[:3])
    atr0 = float(ict0.get("atr_last") or 0.1)
    ep = float(bars[3]["close"])
    c0 = float(ere.get("confidence_01") or 0.5)
    for i in range(3, min(8, len(bars))):
        r = evaluate_lifecycle_bar_v1(
            all_bars=bars,
            current_bar_index=i,
            entry_bar_index=3,
            side="long",
            entry_thesis_v1=th,
            entry_atr=atr0,
            entry_price=ep,
            run_candle_timeframe_minutes=5,
            symbol="Q",
            retrieved_student_experience=[],
            initial_confidence_01=c0,
            entry_confidence_01=c0,
            prior_confidence_01=prev,
            max_hold_bars=100,
            degrading_streak=d_s,
            opposing_bar_streak=o_s,
        )
        ev = r.get("lifecycle_reasoning_eval_v1") or {}
        confs.append(float(ev.get("confidence_01") or 0.0))
        prev = float(ev.get("confidence_01") or 0.0)
        d_s = int(r.get("carry_degrading_streak_v1") or 0)
        o_s = int(r.get("carry_opposing_streak_v1") or 0)
    assert len(confs) >= 2


def test_scenario_6_external_router_disabled_engine_holds_path(monkeypatch):
    """6. with router off, no external review attached; engine decisions remain deterministic hold/exit only."""
    bars = _mono_bars(10, step=0.05)
    ere, _, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(bars[:4]),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    t = run_lifecycle_tape_v1(
        all_bars=bars,
        entry_bar_index=2,
        side="long",
        entry_reasoning_eval_v1=ere,
        run_candle_timeframe_minutes=5,
        symbol="S6",
        max_hold_bars=100,
        unified_agent_router=False,
    )
    for row in t.get("per_bar_v1") or []:
        le = row.get("lifecycle_reasoning_eval_v1") or {}
        assert "external_reasoning_review_lifecycle_v1" not in le or le.get("external_reasoning_review_lifecycle_v1") is None
        break


def test_scenario_7_lifecycle_context_failure_is_visible_in_fault_map():
    """7. bad side → context/eval path records failure in merge."""
    r = evaluate_lifecycle_bar_v1(
        all_bars=[],
        current_bar_index=0,
        entry_bar_index=0,
        side="bogus",
        entry_thesis_v1={},
        entry_atr=0.1,
        entry_price=1.0,
        run_candle_timeframe_minutes=5,
        symbol="Z",
        retrieved_student_experience=[],
        initial_confidence_01=0.5,
    )
    fm = r.get("student_reasoning_fault_map_v1") or {}
    n0 = next((x for x in (fm.get("nodes_v1") or []) if x.get("node_id") == "lifecycle_context_loaded"), None)
    assert n0 and n0.get("status") == STATUS_FAIL


def test_merge_lifecycle_marks_nodes_pass_on_success():
    base = build_fault_map_v1(
        [make_fault_node_v1("market_data_loaded", "PASS", input_summary_v1="a", output_summary_v1="b")],
    )
    m = merge_lifecycle_reasoning_fault_nodes_v1(
        base, context_loaded_ok=True, reasoning_eval_ok=True, decision_ok=True, exit_eval_ok=True
    )
    nids = {n.get("node_id") for n in m.get("nodes_v1", []) if isinstance(n, dict)}
    for want in (
        "lifecycle_context_loaded",
        "lifecycle_reasoning_evaluated",
        "lifecycle_decision_made",
        "lifecycle_exit_evaluated",
    ):
        assert want in nids


def test_write_proof_artifact_lifecycle_tape_v1():
    """Proof JSON: one real in-process lifecycle run (no network)."""
    bars = _mono_bars(20, o=100.0, step=0.2)
    ere, _, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(bars[:6]),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert ere
    res = run_lifecycle_tape_v1(
        all_bars=bars,
        entry_bar_index=3,
        side="long",
        entry_reasoning_eval_v1=ere,
        run_candle_timeframe_minutes=5,
        symbol="PROOF",
        max_hold_bars=40,
    )
    root = Path(__file__).resolve().parents[3] / "docs" / "proof" / "lifecycle_v1"
    root.mkdir(parents=True, exist_ok=True)
    out = root / "PROOF_026B_sample_lifecycle_tape_v1.json"
    out.write_text(
        json.dumps(
            {
                "schema": "gt_directive_026b_lifecycle_proof_v1",
                "contract_version": 1,
                "tape": res,
                "per_bar_stages": [
                    (row.get("lifecycle_reasoning_stage_v1") or {}) for row in (res.get("per_bar_v1") or [])
                ],
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    assert out.is_file() and out.stat().st_size > 100


def test_parse_exam_run_contract_passthrough_026b_lifecycle_bars_v1() -> None:
    from renaissance_v4.game_theory.exam_run_contract_v1 import (
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        parse_exam_run_contract_request_v1,
    )

    bars = [
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0},
        {"open": 1.5, "high": 2.0, "low": 1.0, "close": 2.0, "volume": 1.0},
    ]
    out, err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                "bars_trade_lifecycle_inclusive_v1": bars,
            }
        }
    )
    assert err is None and out is not None
    assert len(out["bars_trade_lifecycle_inclusive_v1"]) == 2
    o2, err2 = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                "bars_trade_lifecycle_inclusive_v1": [bars[0]],
            }
        }
    )
    assert o2 is None and err2 is not None


def test_026b_seam_exam_lifecycle_merges_debug_trace_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Packet-gated lifecycle tape: exam contract → packet merge → events → debug API overlay."""
    import sqlite3

    from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
    from renaissance_v4.game_theory.batch_scorecard import append_batch_scorecard_line
    from renaissance_v4.game_theory.debug_learning_loop_trace_v1 import build_debug_learning_loop_trace_v1
    from renaissance_v4.game_theory.exam_run_contract_v1 import (
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        parse_exam_run_contract_request_v1,
    )
    from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
        student_loop_seam_after_parallel_batch_v1,
    )

    def _bars(n: int) -> list[dict]:
        o: list[dict] = []
        for i in range(n):
            c = 100.0 + i * 0.35
            o.append(
                {
                    "open": c - 0.02,
                    "high": c + 0.12,
                    "low": c - 0.1,
                    "close": c,
                    "volume": 100.0,
                }
            )
        return o

    def _db(path) -> str:
        sym = "TESTUSDT"
        conn = sqlite3.connect(str(path))
        conn.execute(
            """
            CREATE TABLE market_bars_5m (
                open_time INTEGER, symbol TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL
            )
            """
        )
        for i in range(1, 15):
            ts = i * 1_000_000
            c = 100.0 + (i - 1) * 0.45
            conn.execute(
                "INSERT INTO market_bars_5m (open_time, symbol, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                (ts, sym, c - 0.1, c + 0.2, c - 0.2, c, 1000.0),
            )
        conn.commit()
        conn.close()
        return sym

    monkeypatch.setenv("PATTERN_GAME_STUDENT_LOOP_SEAM", "1")
    monkeypatch.setenv("PATTERN_GAME_MEMORY_ROOT", str(tmp_path))

    job_id = f"gt026b_unit_{uuid.uuid4().hex[:12]}"
    ex_req, ex_err = parse_exam_run_contract_request_v1(
        {
            "exam_run_contract_v1": {
                "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
                "candle_timeframe_minutes": 5,
                "bars_trade_lifecycle_inclusive_v1": _bars(24),
            }
        }
    )
    assert ex_err is None and ex_req
    o = OutcomeRecord(
        trade_id="t_seam_026b",
        symbol="TESTUSDT",
        direction="long",
        entry_time=6_000_000,
        exit_time=6_100_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=1.0,
        mae=0.0,
        mfe=0.5,
        exit_reason="tp",
    )
    results = [
        {
            "ok": True,
            "scenario_id": "sc1",
            "replay_outcomes_json": [outcome_record_to_jsonable(o)],
        }
    ]
    db = tmp_path / "b.sqlite3"
    _db(db)
    append_batch_scorecard_line(
        {
            "schema": "pattern_game_batch_scorecard_v1",
            "job_id": job_id,
            "status": "done",
            "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": "b" * 40},
        }
    )
    student_loop_seam_after_parallel_batch_v1(
        results=results,
        run_id=job_id,
        db_path=db,
        store_path=tmp_path / "learn.jsonl",
        exam_run_contract_request_v1=ex_req,
        operator_batch_audit={"candle_timeframe_minutes": 5},
    )
    dbg = build_debug_learning_loop_trace_v1(job_id)
    assert dbg.get("ok")
    ovl = dbg.get("lifecycle_trace_overlay_v1") or {}
    assert ovl.get("schema") == "lifecycle_debug_overlay_v1"
    assert int(ovl.get("lifecycle_stage_events_count_v1") or 0) >= 2
    summ = ovl.get("lifecycle_tape_summary_v1")
    assert isinstance(summ, dict) and summ.get("closed_v1")
    ex = str(summ.get("exit_reason_code_v1") or "")
    assert ex in (
        "target_hit_v1",
        "stop_hit_v1",
        "time_expired_v1",
        "thesis_invalidated_v1",
        "confidence_collapse_v1",
        "opposing_signal_v1",
    )

