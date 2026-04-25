"""Debug learning loop trace — extends base trace with compare + breakpoints."""

from __future__ import annotations

from renaissance_v4.game_theory.debug_learning_loop_trace_v1 import (
    SCHEMA_DEBUG,
    build_debug_learning_loop_trace_v1,
)


def test_build_debug_unknown_job_wraps_base_trace() -> None:
    out = build_debug_learning_loop_trace_v1("__no_such_job_xyz__")
    assert out["schema"] == SCHEMA_DEBUG
    assert out.get("ok") is False
    tv = out.get("trace_v1")
    assert isinstance(tv, dict)
    assert tv.get("schema") == "learning_loop_trace_v1"


def test_build_debug_inserts_delta_node(monkeypatch) -> None:
    entry = {
        "job_id": "dbg-trace-min",
        "status": "done",
        "total_processed": 2,
        "student_brain_profile_v1": "memory_context_llm_student",
        "operator_batch_audit": {"context_signature_memory_mode": "read_write"},
        "student_learning_rows_appended": 0,
        "student_retrieval_matches": 0,
        "memory_context_impact_audit_v1": {"memory_impact_yes_no": "YES"},
        "student_llm_execution_v1": {"ollama_trades_succeeded": 0, "ollama_trades_attempted": 0},
        "llm_student_output_rejections_v1": 1,
        "exam_e_score_v1": 0.5,
        "exam_p_score_v1": 0.5,
    }

    def _fake_find(jid: str, path=None):
        return dict(entry) if jid == "dbg-trace-min" else None

    for mod in (
        "renaissance_v4.game_theory.learning_loop_trace_v1",
        "renaissance_v4.game_theory.debug_learning_loop_trace_v1",
    ):
        monkeypatch.setattr(f"{mod}.find_scorecard_entry_by_job_id", _fake_find)
    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_loop_trace_v1.build_scenario_list_for_batch",
        lambda jid, d: (None, [], "no dir"),
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_loop_trace_v1.build_student_panel_run_learning_payload_v1",
        lambda jid: {
            "schema": "student_panel_run_learning_payload_v1",
            "ok": True,
            "job_id": jid,
            "learning_governance_v1": {
                "schema": "learning_governance_v1",
                "decision": "hold",
                "reason_codes": [],
                "source_job_id": jid,
                "fingerprint": None,
            },
            "run_was_stored": False,
            "eligible_for_retrieval": False,
            "per_trade": [],
            "stored_record_count_v1": 0,
        },
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.debug_learning_loop_trace_v1.newest_done_rows_by_brain_profile_for_fingerprint_v1",
        lambda fp, **kw: {str(entry.get("student_brain_profile_v1") or ""): dict(entry)},
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.debug_learning_loop_trace_v1.read_learning_trace_events_for_job_v1",
        lambda jid, path=None: [],
    )

    out = build_debug_learning_loop_trace_v1("dbg-trace-min")
    assert out.get("ok") is True
    assert out.get("schema") == SCHEMA_DEBUG
    ids = [n["id"] for n in out.get("nodes_v1") or []]
    assert "decision_delta_vs_baseline" in ids
    assert "referee_student_output_coupling" in ids
    assert isinstance(out.get("learning_trace_events_v1"), list)
    assert isinstance(out.get("breakpoints_v1"), list)
    cmp = out.get("fingerprint_profile_compare_v1")
    assert isinstance(cmp, dict)
    assert "row_snapshots_v1" in cmp
    assert out.get("learning_trace_integrity_failed_v1") is True
    assert "learning_trace_integrity_failed_v1" in (out.get("breakpoints_v1") or [])
    assert "runtime_learning_trace_events_empty_v1" in (out.get("breakpoints_v1") or [])
    assert out.get("learning_loop_health_banner_v1") == "LEARNING LOOP BROKEN"
    mpc = out.get("model_provenance_chain_v1")
    assert isinstance(mpc, dict) and mpc.get("schema") == "model_provenance_chain_v1"
    cpv = out.get("student_decision_cross_profile_verdict_v1")
    assert isinstance(cpv, dict) and cpv.get("answer_code_v1") == "NOT_PROVEN_INCOMPLETE_ROWS"
    assert isinstance(out.get("same_visible_outcome_candidates_v1"), dict)
    rline = out.get("referee_student_output_operator_line_v1")
    assert isinstance(rline, dict) and "NOT PROVEN" in str(rline.get("headline_v1") or "")
    ff = out.get("fault_focus_v1") or {}
    assert isinstance(ff.get("decisive_operator_questions_v1"), list)


def test_build_debug_done_with_runtime_events_passes_integrity(monkeypatch) -> None:
    entry = {
        "job_id": "dbg-trace-events",
        "status": "done",
        "total_processed": 1,
        "student_brain_profile_v1": "memory_context_llm_student",
        "operator_batch_audit": {"context_signature_memory_mode": "read"},
        "student_learning_rows_appended": 0,
        "student_retrieval_matches": 0,
        "memory_context_impact_audit_v1": {"memory_impact_yes_no": "NO"},
        "student_llm_execution_v1": {"ollama_trades_succeeded": 0, "ollama_trades_attempted": 0},
        "llm_student_output_rejections_v1": 0,
        "exam_e_score_v1": 0.5,
        "exam_p_score_v1": 0.5,
    }
    fake_ev = [
        {
            "schema": "learning_trace_event_v1",
            "job_id": "dbg-trace-events",
            "stage": "referee_execution_started",
            "status": "running",
            "producer": "test",
        }
    ]

    def _fake_find(jid: str, path=None):
        return dict(entry) if jid == "dbg-trace-events" else None

    for mod in (
        "renaissance_v4.game_theory.learning_loop_trace_v1",
        "renaissance_v4.game_theory.debug_learning_loop_trace_v1",
    ):
        monkeypatch.setattr(f"{mod}.find_scorecard_entry_by_job_id", _fake_find)
    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_loop_trace_v1.build_scenario_list_for_batch",
        lambda jid, d: (None, [], "no dir"),
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_loop_trace_v1.build_student_panel_run_learning_payload_v1",
        lambda jid: {
            "schema": "student_panel_run_learning_payload_v1",
            "ok": True,
            "job_id": jid,
            "learning_governance_v1": {
                "schema": "learning_governance_v1",
                "decision": "hold",
                "reason_codes": [],
                "source_job_id": jid,
                "fingerprint": None,
            },
            "run_was_stored": False,
            "eligible_for_retrieval": False,
            "per_trade": [],
            "stored_record_count_v1": 0,
        },
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.debug_learning_loop_trace_v1.newest_done_rows_by_brain_profile_for_fingerprint_v1",
        lambda fp, **kw: {str(entry.get("student_brain_profile_v1") or ""): dict(entry)},
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.debug_learning_loop_trace_v1.read_learning_trace_events_for_job_v1",
        lambda jid, path=None: list(fake_ev) if jid == "dbg-trace-events" else [],
    )

    out = build_debug_learning_loop_trace_v1("dbg-trace-events")
    assert out.get("ok") is True
    assert out.get("learning_trace_integrity_failed_v1") is not True
    assert "runtime_learning_trace_events_empty_v1" not in (out.get("breakpoints_v1") or [])
    assert "learning_trace_integrity_failed_v1" not in (out.get("breakpoints_v1") or [])
    assert (out.get("model_provenance_chain_v1") or {}).get("schema") == "model_provenance_chain_v1"
