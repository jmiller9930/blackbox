"""GT065 — post-replay seam wall timeout audit + env for max seconds."""

from __future__ import annotations

from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_seam_wall_timeout_audit_v1,
)


def test_student_seam_wall_timeout_audit_shape_v1() -> None:
    results = [
        {
            "ok": True,
            "replay_outcomes_json": [{"trade_id": "t1"}, {"trade_id": "t2"}],
        }
    ]
    a = student_seam_wall_timeout_audit_v1(results=results, run_id="job_x", wall_limit_sec=600.0)
    assert a.get("skipped") is True
    assert a.get("student_seam_stop_reason_v1") == "student_seam_wall_timeout_v1"
    assert a.get("replay_closed_trades_total_v1") == 2
    assert "student_seam_wall_timeout_v1" in (a.get("reason") or "")


def test_student_seam_after_parallel_max_reads_env(monkeypatch) -> None:
    from renaissance_v4.game_theory import web_app as web_app_mod

    monkeypatch.setenv("PATTERN_GAME_STUDENT_SEAM_AFTER_PARALLEL_MAX_SEC", "120")
    assert web_app_mod._student_seam_after_parallel_max_sec_v1() == 120.0
    monkeypatch.delenv("PATTERN_GAME_STUDENT_SEAM_AFTER_PARALLEL_MAX_SEC", raising=False)
    assert web_app_mod._student_seam_after_parallel_max_sec_v1() == 600.0
    monkeypatch.setenv("PATTERN_GAME_STUDENT_SEAM_AFTER_PARALLEL_MAX_SEC", "0")
    assert web_app_mod._student_seam_after_parallel_max_sec_v1() == 0.0
