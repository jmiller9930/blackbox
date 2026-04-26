"""One-off: emit real_shape closure JSON (same code paths as seam). Not imported by tests."""
from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import run_entry_reasoning_pipeline_v1
from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
    SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
    attach_fault_map_v1,
    merge_runtime_fault_nodes_v1,
)


def main() -> None:
    bars = [
        {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100.0},
        {"open": 1.0, "high": 1.2, "low": 0.95, "close": 1.1, "volume": 110.0},
    ]
    pkt = {
        "schema": "student_decision_packet_v1",
        "symbol": "BTC",
        "candle_timeframe_minutes": 5,
        "bars_inclusive_up_to_t": bars,
    }
    ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=pkt,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    if err or ere is None:
        raise SystemExit(f"pipeline failed: {err}")
    full = merge_runtime_fault_nodes_v1(
        pfm,
        use_llm_path=False,
        llm_checked_pass=True,
        llm_error_codes=[],
        llm_operator_message="",
        student_sealed_pass=True,
        student_seal_error_codes=[],
        student_seal_message="The student line was merged with the engine and is ready to store.",
        execution_intent_pass=True,
        execution_intent_error_codes=[],
        execution_intent_message="A formal execution handoff was built from the sealed student line.",
    )
    so: dict = {
        "schema": "student_output_v1",
        "contract_version": 1,
        "graded_unit_id": "closure_proof_trade_01",
        "act": False,
        "direction": "flat",
        "student_action_v1": "no_trade",
        "confidence_01": 0.5,
        "confidence_band": "medium",
        "pattern_recipe_ids": ["p1"],
        "reasoning_text": "closure sample",
        "context_fit": "trend",
        "invalidation_text": "x",
        "supporting_indicators": ["a"],
        "conflicting_indicators": [],
    }
    attach_fault_map_v1(so, full)
    out = {
        "comment": (
            "GT_DIRECTIVE_026R closure: in-process sample using run_entry_reasoning_pipeline_v1 + "
            "merge_runtime_fault_nodes_v1 (non-LLM / stub-equivalent path). "
            "student_output attachment: field student_reasoning_fault_map_v1 is duplicated as "
            "student_output_student_reasoning_fault_map_v1 for review. "
            "Debug API: see test_debug_learning_loop_trace_includes_fault_map_from_runtime_event_v1. "
            "Optional live lab: GET /api/debug/learning-loop/trace/<job_id> on a reachable host; "
            "save redacted JSON beside this file if you need a network-captured artifact."
        ),
        "schema_fault_map": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
        "node_count": len(full.get("nodes_v1") or []),
        "statuses_in_order": [n.get("status") for n in (full.get("nodes_v1") or [])],
        "student_reasoning_fault_map_v1": full,
        "student_output_student_reasoning_fault_map_v1": so.get("student_reasoning_fault_map_v1"),
    }
    p = Path(__file__).resolve().parent / "real_run_closure_inprocess_sample_v1.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", p)


if __name__ == "__main__":
    main()
