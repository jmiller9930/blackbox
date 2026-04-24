"""Deterministic ``training_exam_audit_v1`` verdicts from scorecard-shaped dicts."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.training_exam_audit_v1 import build_training_exam_audit_v1


def _base(**overrides: object) -> dict:
    line = {
        "job_id": "j1",
        "status": "done",
        "student_learning_rows_appended": 0,
        "student_retrieval_matches": 0,
        "llm_student_output_rejections_v1": 0,
        "shadow_student_enabled": False,
        "memory_context_impact_audit_v1": {"memory_impact_yes_no": "NO"},
        "student_llm_execution_v1": {"ollama_trades_succeeded": 0, "ollama_trades_attempted": 0},
        "operator_batch_audit": {"context_signature_memory_mode": "off"},
    }
    line.update(overrides)
    return line


def test_verdict_persisted_rows() -> None:
    out = build_training_exam_audit_v1(_base(student_learning_rows_appended=2))
    assert out["schema"] == "training_exam_audit_v1"
    assert out["training_learning_verdict_v1"] == "PERSISTED_LEARNING_ROWS"
    ids = {c["id"]: c["pass"] for c in out["checks_v1"]}
    assert ids["persisted_student_learning_rows"] is True


def test_verdict_engagement_without_store() -> None:
    out = build_training_exam_audit_v1(_base(student_retrieval_matches=1))
    assert out["training_learning_verdict_v1"] == "ENGAGEMENT_WITHOUT_STORE_WRITES"

    out2 = build_training_exam_audit_v1(
        _base(
            student_llm_execution_v1={"ollama_trades_succeeded": 1, "ollama_trades_attempted": 1},
        )
    )
    assert out2["training_learning_verdict_v1"] == "ENGAGEMENT_WITHOUT_STORE_WRITES"


def test_verdict_harness_counters_only() -> None:
    out = build_training_exam_audit_v1(
        _base(
            memory_context_impact_audit_v1={
                "memory_impact_yes_no": "NO",
                "recall_match_windows_total_sum": 3,
                "recall_bias_applied_total_sum": 0,
                "recall_signal_bias_applied_total_sum": 0,
            },
            operator_batch_audit={"context_signature_memory_mode": "read_write"},
        )
    )
    assert out["training_learning_verdict_v1"] == "HARNESS_MEMORY_COUNTERS_ONLY"


def test_verdict_no_scorecard_evidence_student_path() -> None:
    out = build_training_exam_audit_v1(
        _base(operator_batch_audit={"context_signature_memory_mode": "read"})
    )
    assert out["training_learning_verdict_v1"] == "NO_SCORECARD_EVIDENCE_OF_STUDENT_PATH"


def test_verdict_student_lane_off() -> None:
    out = build_training_exam_audit_v1(_base())
    assert out["training_learning_verdict_v1"] == "STUDENT_LANE_NOT_CONFIGURED_OR_OFF"


def test_verdict_insufficient_error() -> None:
    out = build_training_exam_audit_v1(_base(status="error"))
    assert out["training_learning_verdict_v1"] == "INSUFFICIENT_BATCH_STATUS"


def test_verdict_insufficient_cancelled() -> None:
    out = build_training_exam_audit_v1(_base(status="cancelled"))
    assert out["training_learning_verdict_v1"] == "INSUFFICIENT_BATCH_STATUS"


def test_verdict_insufficient_unknown_status() -> None:
    out = build_training_exam_audit_v1(_base(status="running"))
    assert out["training_learning_verdict_v1"] == "INSUFFICIENT_BATCH_STATUS"


def test_api_training_exam_audit_unknown_job() -> None:
    from renaissance_v4.game_theory.web_app import create_app

    app = create_app()
    with app.test_client() as c:
        r = c.get("/api/training-exam-audit/__no_such_job__")
    assert r.status_code == 404
    body = r.get_json()
    assert body is not None
    assert body.get("ok") is False


def test_api_training_exam_audit_rebuilds_when_block_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    import renaissance_v4.game_theory.web_app as wa

    stub = {
        "job_id": "stub-job",
        "status": "done",
        "student_learning_rows_appended": 1,
        "student_retrieval_matches": 0,
        "llm_student_output_rejections_v1": 0,
        "shadow_student_enabled": False,
        "memory_context_impact_audit_v1": {"memory_impact_yes_no": "NO"},
        "student_llm_execution_v1": {"ollama_trades_succeeded": 0, "ollama_trades_attempted": 0},
        "operator_batch_audit": {"context_signature_memory_mode": "read_write"},
    }
    monkeypatch.setattr(wa, "find_scorecard_entry_by_job_id", lambda jid: stub if jid == "stub-job" else None)
    app = wa.create_app()
    with app.test_client() as c:
        r = c.get("/api/training-exam-audit/stub-job")
    assert r.status_code == 200
    body = r.get_json()
    assert body is not None and body.get("ok") is True
    aud = body.get("training_exam_audit_v1")
    assert isinstance(aud, dict)
    assert aud.get("training_learning_verdict_v1") == "PERSISTED_LEARNING_ROWS"
