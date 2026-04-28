"""Disk persistence for terminal parallel jobs — survives Flask ``_JOBS`` eviction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.parallel_job_terminal_persistence_v1 import (
    SCHEMA_PARALLEL_JOB_TERMINAL_RECORD_V1,
    load_parallel_job_terminal_record_v1,
    terminal_student_runtime_result_path_v1,
    write_parallel_job_terminal_record_v1,
)


def test_write_and_load_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from renaissance_v4.game_theory import parallel_job_terminal_persistence_v1 as mod

    monkeypatch.setattr(mod, "pml_runtime_batches_dir", lambda: tmp_path)

    jid = "abc123"
    payload = {
        "ok": True,
        "job_id": jid,
        "results": [{"ok": True, "replay_outcomes_json": [{"trade_id": "t1"}]}],
        "student_loop_directive_09_v1": {
            "schema": "student_loop_seam_audit_v1",
            "student_seam_stop_reason_v1": "completed_all_trades_v1",
            "trades_considered": 1,
            "replay_closed_trades_total_v1": 1,
        },
    }
    out = write_parallel_job_terminal_record_v1(
        job_id=jid,
        terminal_status="done",
        api_result_payload=payload,
        session_log_batch_dir=str(tmp_path / "sess"),
        telemetry_dir=str(tmp_path / "tel"),
        learning_trace_path=tmp_path / "trace.jsonl",
    )
    assert out is not None
    assert out.is_file()
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw.get("schema") == SCHEMA_PARALLEL_JOB_TERMINAL_RECORD_V1
    assert raw.get("terminal_status") == "done"
    assert raw.get("student_seam_stop_reason_v1") == "completed_all_trades_v1"

    loaded = load_parallel_job_terminal_record_v1(jid)
    assert isinstance(loaded, dict)
    assert loaded.get("full_parallel_result_v1", {}).get("ok") is True


def test_terminal_path_matches_expected_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from renaissance_v4.game_theory import parallel_job_terminal_persistence_v1 as mod

    monkeypatch.setattr(mod, "pml_runtime_batches_dir", lambda: tmp_path)
    jid = "deadbeef"
    p = terminal_student_runtime_result_path_v1(jid)
    assert p.parent.name == jid
    assert p.name == f"student_runtime_result_{jid}.json"
