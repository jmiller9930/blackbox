#!/usr/bin/env python3
"""
GT_DIRECTIVE_026C — **harness-only** closure capture (not production, not clawbot learning proof).

Builds the same ``debug_learning_loop_trace_v1`` shape using ``closure_proof_026c_sandbox`` as
``PATTERN_GAME_MEMORY_ROOT``. Production 026C closure: live Run A / B / Control job_ids, real
``batch_scorecard.jsonl`` + ``learning_trace_events_v1.jsonl`` + 026C store on the server, same
GET on the live API. See ``docs/architect/global_clawbot_proof_standard.md``.

Re-run after editing sandbox files to refresh the harness artifact.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SANDBOX = _REPO_ROOT / "docs" / "proof" / "lifecycle_v1" / "closure_proof_026c_sandbox"

# Canonical proof job ids (commit-stable; also embedded in sandbox JSONL).
JOB_RUN_A = "PROOF_026C_RUN_A"
JOB_RUN_B = "PROOF_026C_RUN_B"
JOB_CONTROL = "PROOF_026C_CONTROL"
RECORD_026C = "proof_rec_026c_001"
SIG = "closure_proof_ctx_sig_v1"

OUT_PATH = _REPO_ROOT / "docs" / "proof" / "lifecycle_v1" / "LIVE_026C_closure_proof_artifact_v1.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_sandbox_artifacts() -> None:
    """Idempotent: ensure sandbox dirs and committed proof inputs exist."""
    mem = _SANDBOX / "memory"
    mem.mkdir(parents=True, exist_ok=True)

    sc_path = mem / "batch_scorecard.jsonl"
    if not sc_path.is_file():
        sc_path.write_text("", encoding="utf-8")
    # Three scorecard lines: control (baseline), run A (producer), run B (treatment) — last line per job_id wins; order so each job has one line.
    lines: list[dict] = [
        {
            "schema": "pattern_game_batch_scorecard_v1",
            "job_id": JOB_CONTROL,
            "status": "done",
            "total_processed": 1,
            "operator_batch_audit": {"context_signature_memory_mode": "on"},
            "session_log_batch_dir": str(_SANDBOX / "batch_ctrl"),
            "student_brain_profile_v1": "memory_context_llm_student",
            "student_action_v1": "no_trade",
            "student_confidence_01": 0.44,
            "exam_e_score_v1": 0.5,
            "exam_p_score_v1": 0.48,
            "expectancy_per_trade": -0.01,
        },
        {
            "schema": "pattern_game_batch_scorecard_v1",
            "job_id": JOB_RUN_A,
            "status": "done",
            "total_processed": 1,
            "operator_batch_audit": {"context_signature_memory_mode": "on"},
            "session_log_batch_dir": str(_SANDBOX / "batch_a"),
        },
        {
            "schema": "pattern_game_batch_scorecard_v1",
            "job_id": JOB_RUN_B,
            "status": "done",
            "total_processed": 1,
            "operator_batch_audit": {"context_signature_memory_mode": "on"},
            "session_log_batch_dir": str(_SANDBOX / "batch_b"),
            "student_brain_profile_v1": "memory_context_llm_student",
            "student_action_v1": "enter_long",
            "student_confidence_01": 0.82,
            "exam_e_score_v1": 0.72,
            "exam_p_score_v1": 0.68,
            "expectancy_per_trade": 0.14,
        },
    ]
    with sc_path.open("w", encoding="utf-8") as fh:
        for row in lines:
            fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")

    # Learning trace: Run A 026C emits; Run B router + lifecycle + 026C injection; Control lifecycle only
    lpath = mem / "learning_trace_events_v1.jsonl"
    ev_lines: list[dict] = []

    def add_ev(
        job_id: str,
        stage: str,
        evidence: dict,
        producer: str = "proof_sandbox",
    ) -> None:
        ev_lines.append(
            {
                "schema": "learning_trace_event_v1",
                "schema_version": 1,
                "job_id": job_id,
                "fingerprint": "proof_fp_026c",
                "stage": stage,
                "timestamp_utc": _now_iso(),
                "status": "pass",
                "summary": stage,
                "evidence_payload": evidence,
                "producer": producer,
            }
        )

    # --- Run A: closed 026C learning (producer job) ---
    add_ev(
        JOB_RUN_A,
        "learning_record_created_v1",
        {"record_id_026c": RECORD_026C, "event": "learning_record_created_v1"},
    )
    add_ev(
        JOB_RUN_A,
        "learning_scoring_completed_v1",
        {
            "event": "learning_scoring_completed_v1",
            "decision_quality_score_v1": {
                "schema": "decision_quality_score_v1",
                "overall_score_v1": 0.88,
            },
        },
    )
    add_ev(
        JOB_RUN_A,
        "learning_decision_made_v1",
        {
            "event": "learning_decision_made_v1",
            "learning_decision_v1": {"outcome_v1": "promote_pattern_v1"},
        },
    )

    # --- Run B: router, lifecycle with 026C retrieval + deterministic context; external not called (local) ---
    add_ev(
        JOB_RUN_B,
        "reasoning_router_decision_v1",
        {
            "reasoning_router_decision_v1": {
                "schema": "reasoning_router_decision_v1",
                "final_route_v1": "local_only",
                "escalation_reason_codes_v1": [],
                "escalation_blockers_v1": ["no_escalation_reason_v1"],
                "external_api_enabled_v1": True,
            },
            "call_ledger_sanitized_v1": {
                "api_call_attempted_v1": False,
                "provider_v1": "openai",
                "model_requested_v1": "gpt-4.1",
                "model_resolved_v1": None,
                "input_tokens_v1": 0,
                "output_tokens_v1": 0,
                "total_tokens_v1": 0,
                "latency_ms_v1": 0.0,
                "estimated_cost_usd_v1": 0.0,
                "response_status_v1": "not_called",
                "validator_status_v1": "not_applicable",
            },
        },
        producer="unified_agent_v1",
    )
    add_ev(
        JOB_RUN_B,
        "lifecycle_tape_summary_v1",
        {
            "lifecycle_tape_result_v1": {
                "closed_v1": True,
                "exit_at_bar_index_v1": 15,
                "exit_reason_code_v1": "target_r_multiple_hit_v1",
                "per_bar_slim_v1": [
                    {"decision_v1": "hold"},
                    {"decision_v1": "hold"},
                    {"decision_v1": "hold"},
                    {"decision_v1": "exit"},
                ],
                "retrieved_lifecycle_deterministic_learning_026c_v1": [
                    {
                        "schema": "retrieved_lifecycle_deterministic_learning_slice_026c_v1",
                        "record_id_026c": RECORD_026C,
                        "pattern_key_026c_v1": "X",
                        "overall_score_01": 0.88,
                        "decay_weight_01": 0.95,
                    }
                ],
                "deterministic_learning_context_026c_v1": {
                    "slice_count_v1": 1,
                    "max_decay_weight_01": 0.95,
                },
            }
        },
        producer="lifecycle_reasoning_engine_v1",
    )

    # Control: different lifecycle (exit reason + hold path) to show measurable delta
    add_ev(
        JOB_CONTROL,
        "lifecycle_tape_summary_v1",
        {
            "lifecycle_tape_result_v1": {
                "closed_v1": True,
                "exit_at_bar_index_v1": 11,
                "exit_reason_code_v1": "stop_hit_v1",
                "per_bar_slim_v1": [
                    {"decision_v1": "hold"},
                    {"decision_v1": "exit"},
                ],
            }
        },
        producer="lifecycle_reasoning_engine_v1",
    )

    with lpath.open("w", encoding="utf-8") as fh:
        for e in ev_lines:
            fh.write(json.dumps(e, separators=(",", ":"), ensure_ascii=False) + "\n")

    # 026C append-only store: exact record from Run A (Run B retrieval links here)
    store = _SANDBOX / "026c_lifecycle_store.jsonl"
    rec = {
        "schema": "student_lifecycle_deterministic_learning_record_026c_v1",
        "contract_version": 1,
        "record_id_026c": RECORD_026C,
        "created_utc_026c": "2020-01-15T12:00:00Z",
        "job_id_v1": JOB_RUN_A,
        "trade_id_v1": "t_proof_a",
        "symbol_v1": "BTC",
        "timeframe_v1": 5,
        "context_signature_key_v1": SIG,
        "pattern_key_026c_v1": "BTC:5:long:target_r_multiple_hit_v1",
        "learning_decision_v1": {"outcome_v1": "promote_pattern_v1"},
        "decision_quality_score_v1": {"overall_score_v1": 0.88},
    }
    with store.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n")


def main() -> int:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    _write_sandbox_artifacts()
    mem_root = str((_SANDBOX / "memory").resolve())
    store_path = str((_SANDBOX / "026c_lifecycle_store.jsonl").resolve())
    os.environ["PATTERN_GAME_MEMORY_ROOT"] = mem_root
    os.environ["PATTERN_GAME_LIFECYCLE_DETERMINISTIC_LEARNING_026C_STORE"] = store_path

    from renaissance_v4.game_theory.debug_learning_loop_trace_v1 import build_debug_learning_loop_trace_v1

    out = build_debug_learning_loop_trace_v1(
        JOB_RUN_B,
        run_a_job_id=JOB_RUN_A,
        control_job_id=JOB_CONTROL,
    )
    lec = out.get("learning_effect_closure_026c_v1")
    if not isinstance(lec, dict) or lec.get("ok") is False:
        print("learning_effect_closure_026c_v1 missing or error:", lec, file=sys.stderr)
        return 2
    res = lec.get("closure_result_v1")
    if res not in (
        "LEARNING_CHANGED_BEHAVIOR",
        "LEARNING_RETRIEVED_BUT_NO_BEHAVIOR_CHANGE",
    ):
        print("Closure result not in accepted set for proof:", res, file=sys.stderr)
        print(json.dumps(lec, indent=2)[:4000], file=sys.stderr)
        return 3

    proof = {
        "schema": "live_026c_closure_proof_wrap_v1",
        "proof_generated_utc": _now_iso(),
        "closure_proof_tier_v1": "harness_sandbox_v1",
        "production_closure_satisfied_v1": False,
        "production_closure_note_v1": (
            "This JSON was generated with PATTERN_GAME_MEMORY_ROOT pointing at closure_proof_026c_sandbox; "
            "it validates the closure query shape and code paths only. GT 026C production closure requires "
            "the same GET against live clawbot job_ids with real scorecard, learning_trace, lifecycle emits, "
            "router, LLM provenance, and 026C store under production paths — not this sandbox."
        ),
        "query_v1": {
            "url_pattern_v1": "GET /api/debug/learning-loop/trace/<run_b_job_id>",
            "run_b_job_id": JOB_RUN_B,
            "run_a_job_id": JOB_RUN_A,
            "control_job_id": JOB_CONTROL,
            "query_string_v1": f"?run_a_job_id={JOB_RUN_A}&control_job_id={JOB_CONTROL}",
        },
        "sandbox_v1": {
            "PATTERN_GAME_MEMORY_ROOT": mem_root,
            "PATTERN_GAME_LIFECYCLE_DETERMINISTIC_LEARNING_026C_STORE": store_path,
            "harness_sandbox_relpath_v1": "docs/proof/lifecycle_v1/closure_proof_026c_sandbox",
        },
        "debug_learning_loop_trace_v1": out,
    }
    OUT_PATH.write_text(
        json.dumps(proof, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(OUT_PATH)
    print("closure_result_v1:", res)
    return 0 if res == "LEARNING_CHANGED_BEHAVIOR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
