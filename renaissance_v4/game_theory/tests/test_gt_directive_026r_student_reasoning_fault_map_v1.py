# GT_DIRECTIVE_026R — student_reasoning_fault_map_v1 (visibility)

from __future__ import annotations

import json

from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import run_entry_reasoning_pipeline_v1
from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
    NODE_IDS_ORDER,
    SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
    STATUS_FAIL,
    STATUS_NOT_PROVEN,
    STATUS_PASS,
    STATUS_SKIPPED,
    build_fault_map_v1,
    make_fault_node_v1,
    merge_runtime_fault_nodes_v1,
    validate_student_reasoning_fault_map_v1,
)


def _packet_minimal(*, bars: list, symbol: str = "BTC") -> dict:
    return {
        "schema": "student_decision_packet_v1",
        "symbol": symbol,
        "candle_timeframe_minutes": 5,
        "bars_inclusive_up_to_t": bars,
    }


def test_missing_market_data_fails_node_market_data_loaded() -> None:
    pkt = _packet_minimal(bars=[])
    out, err, tr, fm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert out is None
    assert "missing_bars" in " ".join(err)
    assert fm.get("schema") == SCHEMA_STUDENT_REASONING_FAULT_MAP_V1
    nodes = fm.get("nodes_v1") or []
    assert nodes[0]["node_id"] == "market_data_loaded"
    assert nodes[0]["status"] == STATUS_FAIL
    assert "price" in (nodes[0].get("operator_message_v1") or "").lower()


def test_insufficient_bars_indicators_fails_at_indicator_node() -> None:
    one_bar = [{"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100.0}]
    pkt = _packet_minimal(bars=one_bar)
    out, err, tr, fm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert out is None
    assert fm["nodes_v1"][0]["status"] == STATUS_PASS
    assert fm["nodes_v1"][1]["node_id"] == "indicator_context_evaluated"
    assert fm["nodes_v1"][1]["status"] == STATUS_FAIL


def test_success_pipeline_has_ten_nodes_and_validates() -> None:
    bars = [
        {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100.0},
        {"open": 1.0, "high": 1.2, "low": 0.95, "close": 1.1, "volume": 110.0},
    ]
    pkt = _packet_minimal(bars=bars)
    out, err, tr, fm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert out is not None
    assert not err
    assert len(fm["nodes_v1"]) == len(NODE_IDS_ORDER)
    for i, n in enumerate(fm["nodes_v1"]):
        if i < 7:
            assert n["status"] in (STATUS_PASS, STATUS_NOT_PROVEN)
        else:
            assert n["status"] == STATUS_SKIPPED
    v = validate_student_reasoning_fault_map_v1(fm)
    assert not v


def test_memory_node_records_retrieval_count() -> None:
    bars = [
        {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100.0},
        {"open": 1.0, "high": 1.2, "low": 0.95, "close": 1.1, "volume": 110.0},
    ]
    rse = [
        {
            "record_id": "r1",
            "candle_timeframe_minutes": 15,
            "referee_outcome_subset": {"pnl": 0.0},
        }
    ]
    pkt = _packet_minimal(bars=bars)
    out, err, tr, fm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=rse,
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert out is not None
    mem = next(n for n in fm["nodes_v1"] if n["node_id"] == "memory_context_evaluated")
    assert int((mem.get("evidence_values_v1") or {}).get("retrieved_count") or 0) == 1
    assert mem["status"] in (STATUS_PASS, STATUS_NOT_PROVEN)
    assert len(mem.get("operator_message_v1") or "") > 5


def test_merge_runtime_skips_llm_node_on_stub_path() -> None:
    base = build_fault_map_v1(
        [make_fault_node_v1("market_data_loaded", STATUS_PASS, input_summary_v1="a", output_summary_v1="b")]
        + [make_fault_node_v1(nid, STATUS_PASS, input_summary_v1="a", output_summary_v1="b") for nid in NODE_IDS_ORDER[1:7]]
    )
    m = merge_runtime_fault_nodes_v1(
        base,
        use_llm_path=False,
        llm_checked_pass=True,
        llm_error_codes=[],
        llm_operator_message="",
        student_sealed_pass=True,
        student_seal_error_codes=[],
        student_seal_message="",
        execution_intent_pass=True,
        execution_intent_error_codes=[],
        execution_intent_message="",
    )
    n8 = next(x for x in m["nodes_v1"] if x["node_id"] == "llm_output_checked")
    assert n8["status"] == STATUS_SKIPPED


def test_real_proof_json_fixture_roundtrip() -> None:
    # Minimal file contract: proof that a known failure shape serializes
    n = make_fault_node_v1(
        "market_data_loaded",
        STATUS_FAIL,
        input_summary_v1="Packet",
        output_summary_v1="Empty",
        operator_message_v1="No price bars were available for this decision.",
    )
    fm = build_fault_map_v1([n] + [make_fault_node_v1(nid, STATUS_SKIPPED, input_summary_v1="x", output_summary_v1="y") for nid in NODE_IDS_ORDER[1:]])
    s = json.dumps(fm, indent=2)
    assert "student_reasoning_fault_map_v1" in s
    assert "market_data_loaded" in s


def test_status_enum_only_allowed() -> None:
    bad = make_fault_node_v1(
        "market_data_loaded",
        "INVALID",
        input_summary_v1="a",
        output_summary_v1="b",
    )
    assert bad["status"] == STATUS_NOT_PROVEN
