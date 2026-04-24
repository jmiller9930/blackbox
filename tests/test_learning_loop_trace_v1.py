"""Learning Loop Trace — graph payload + standalone page asset."""

from __future__ import annotations

from renaissance_v4.game_theory.learning_loop_trace_v1 import (
    build_learning_loop_trace_v1,
    read_learning_loop_trace_page_html_v1,
)
from renaissance_v4.game_theory.web_app import create_app


def test_build_trace_unknown_job() -> None:
    out = build_learning_loop_trace_v1("__no_such_job_xyz__")
    assert out["schema"] == "learning_loop_trace_v1"
    assert out.get("ok") is False
    assert out.get("nodes_v1") == []


def test_build_trace_empty_job_id() -> None:
    out = build_learning_loop_trace_v1("  ")
    assert out.get("ok") is False
    assert out.get("error") == "job_id required"


def test_page_html_loads() -> None:
    html = read_learning_loop_trace_page_html_v1()
    assert "Learning Loop Trace" in html
    assert "learning-loop-trace" in html or "learning_loop_trace" in html


def test_api_learning_loop_trace_route() -> None:
    app = create_app()
    with app.test_client() as c:
        r = c.get("/api/student-panel/run/__bad__/learning-loop-trace")
    assert r.status_code == 200
    body = r.get_json()
    assert body is not None
    assert body.get("schema") == "learning_loop_trace_v1"


def test_page_learning_loop_trace_legacy_redirects_to_debug() -> None:
    app = create_app()
    with app.test_client() as c:
        r = c.get("/learning-loop-trace?job_id=j1&trade_id=t1", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers.get("Location") or ""
    assert loc == "/debug/learning-loop?job_id=j1&trade_id=t1"


def test_page_debug_learning_loop_route() -> None:
    app = create_app()
    with app.test_client() as c:
        r = c.get("/debug/learning-loop")
    assert r.status_code == 200
    assert b"Learning Loop (Debug)" in r.data


def test_api_debug_learning_loop_trace_unknown_job() -> None:
    app = create_app()
    with app.test_client() as c:
        r = c.get("/api/debug/learning-loop/trace/__no_such_job_xyz__")
    assert r.status_code == 200
    body = r.get_json()
    assert body is not None
    assert body.get("schema") == "debug_learning_loop_trace_v1"
    assert body.get("ok") is False
    assert isinstance(body.get("trace_v1"), dict)


def test_trace_minimal_scorecard(monkeypatch) -> None:
    entry = {
        "job_id": "trace-min",
        "status": "done",
        "total_processed": 2,
        "student_brain_profile_v1": "baseline_no_memory_no_llm",
        "operator_batch_audit": {"context_signature_memory_mode": "off"},
        "student_learning_rows_appended": 0,
        "student_retrieval_matches": 0,
        "memory_context_impact_audit_v1": {"memory_impact_yes_no": "NO"},
        "student_llm_execution_v1": {"ollama_trades_succeeded": 0, "ollama_trades_attempted": 0},
    }

    def _fake_find(jid: str, path=None):
        return dict(entry) if jid == "trace-min" else None

    monkeypatch.setattr(
        "renaissance_v4.game_theory.learning_loop_trace_v1.find_scorecard_entry_by_job_id",
        _fake_find,
    )
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

    out = build_learning_loop_trace_v1("trace-min")
    assert out.get("ok") is True
    assert len(out.get("nodes_v1") or []) >= 10
    assert out.get("learning_loop_health_banner_v1")
    ff = out.get("fault_focus_v1")
    assert isinstance(ff, dict)
    assert ff.get("schema") == "fault_focus_v1"
    assert "headline_one_liner_v1" in ff
    ids = [n["id"] for n in out["nodes_v1"]]
    assert "run_started" in ids and "learning_store" in ids
