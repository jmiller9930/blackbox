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
        "renaissance_v4.game_theory.debug_learning_loop_trace_v1.read_batch_scorecard_file_order_v1",
        lambda max_lines=25000: [dict(entry)],
    )

    out = build_debug_learning_loop_trace_v1("dbg-trace-min")
    assert out.get("ok") is True
    assert out.get("schema") == SCHEMA_DEBUG
    ids = [n["id"] for n in out.get("nodes_v1") or []]
    assert "decision_delta_vs_baseline" in ids
    assert isinstance(out.get("breakpoints_v1"), list)
    cmp = out.get("fingerprint_profile_compare_v1")
    assert isinstance(cmp, dict)
    assert "row_snapshots_v1" in cmp
