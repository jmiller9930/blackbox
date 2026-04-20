"""
Directive 09 closeout — **runtime proof** on real Flask ``/api/run-parallel/start`` + ``/status``:

- Run 1: ``student_learning_rows_appended > 0``
- Run 2 (same request shape): ``retrieval_slice_count > 0`` and Student shadow fields change vs Run 1
- ``POST /api/student-proctor/learning-store/clear`` (typed confirm)
- Run 3: primary-trade shadow snapshot matches Run 1 baseline (no retrieval)

**Note:** The default lab SQLite often yields **zero trades** on full replay. This test therefore
**monkeypatches** ``run_scenarios_parallel`` to return one closed-trade outcome row (Referee-shaped)
while still executing the **real** web_app thread, **real** ``student_loop_seam_after_parallel_batch_v1``,
and **real** learning JSONL under a temp ``BLACKBOX_PML_RUNTIME_ROOT``. That satisfies the
**API path + seam** requirement; a separate manual run on a host with profitable tape proves the
same fields with **unmocked** workers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.student_proctor.student_learning_operator_v1 import (
    RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM,
)


def _manifest_path() -> str:
    root = Path(__file__).resolve().parents[1]
    p = root / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not p.is_file():
        pytest.skip("baseline manifest missing")
    return str(p)


def _minimal_ok_row_for_guard_and_seam(
    *,
    scenario_id: str,
    o: OutcomeRecord,
) -> dict[str, Any]:
    """Enough structure for ``_guard_parallel_batch_not_noop`` + Student seam."""
    return {
        "ok": True,
        "scenario_id": scenario_id,
        "manifest_path": "dummy",
        "replay_outcomes_json": [outcome_record_to_jsonable(o)],
        "summary": {
            "trades": 1,
            "wins": 1,
            "losses": 0,
        },
        "learning_run_audit_v1": {
            "bars_processed": 500,
            "decision_windows_total": 120,
            "learning_engaged_v1": False,
            "operator_learning_status_line_v1": "directive_09_proof_stub",
        },
    }


def _fake_parallel_factory(o: OutcomeRecord):
    def _fake(
        scenarios: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        sid = str(scenarios[0].get("scenario_id") or "d09_proof")
        return [_minimal_ok_row_for_guard_and_seam(scenario_id=sid, o=o)]

    return _fake


def _poll_done(client: object, job_id: str, *, max_wait_s: float = 60.0) -> dict:
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        r = client.get(f"/api/run-parallel/status/{job_id}")
        assert r.status_code == 200
        j = r.get_json()
        if j.get("status") == "done":
            return j
        if j.get("status") == "error":
            pytest.fail(j.get("error") or "job error")
        time.sleep(0.15)
    pytest.fail("job timed out")


def test_directive_09_cross_run_proof_parallel_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db
    import renaissance_v4.game_theory.web_app as web_app
    import renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 as seam_rt

    db_file = tmp_path / "proof.sqlite3"
    _mk_synthetic_db(db_file)
    monkeypatch.setattr(seam_rt, "DB_PATH", db_file)
    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LOOP_SEAM", "1")

    o = OutcomeRecord(
        trade_id="d09_proof_trade",
        symbol="TESTUSDT",
        direction="long",
        entry_time=6_000_000,
        exit_time=6_100_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=3.0,
        mae=0.0,
        mfe=1.0,
        exit_reason="tp",
    )
    monkeypatch.setattr(web_app, "run_scenarios_parallel", _fake_parallel_factory(o))

    app = web_app.create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    mp = _manifest_path()
    body = {
        "scenarios_json": json.dumps(
            [
                {
                    "scenario_id": "d09_proof",
                    "manifest_path": mp,
                    "agent_explanation": {"hypothesis": "Directive 09 API proof"},
                }
            ]
        ),
        "max_workers": 1,
    }

    # --- Run 1 ---
    st1 = client.post("/api/run-parallel/start", data=json.dumps(body), content_type="application/json")
    assert st1.status_code == 200
    done1 = _poll_done(client, st1.get_json()["job_id"])
    res1 = done1.get("result") or {}
    seam1 = res1.get("student_loop_directive_09_v1") or {}
    assert int(seam1.get("student_learning_rows_appended") or 0) > 0
    assert res1.get("shadow_student_enabled") is True
    fp1 = res1.get("student_output_fingerprint")
    assert isinstance(fp1, str) and len(fp1) == 64
    assert int(res1.get("student_retrieval_matches") or 0) == int(seam1.get("student_retrieval_matches") or 0)
    p1 = seam1.get("primary_trade_shadow_student_v1") or {}
    assert p1.get("retrieval_slice_count") == 0
    ref1 = p1.get("student_decision_ref")
    recipes1 = p1.get("pattern_recipe_ids")

    # --- Run 2 ---
    st2 = client.post("/api/run-parallel/start", data=json.dumps(body), content_type="application/json")
    assert st2.status_code == 200
    done2 = _poll_done(client, st2.get_json()["job_id"])
    res2 = done2.get("result") or {}
    seam2 = res2.get("student_loop_directive_09_v1") or {}
    assert int(seam2.get("student_learning_rows_appended") or 0) > 0
    assert res2.get("shadow_student_enabled") is True
    assert int(res2.get("student_retrieval_matches") or 0) > 0
    fp2 = res2.get("student_output_fingerprint")
    assert isinstance(fp2, str) and len(fp2) == 64
    assert fp2 != fp1
    p2 = seam2.get("primary_trade_shadow_student_v1") or {}
    assert int(p2.get("retrieval_slice_count") or 0) > 0
    assert p2.get("student_decision_ref") != ref1
    assert "cross_run_retrieval_informed_v1" in (p2.get("pattern_recipe_ids") or [])

    # --- Reset ---
    clr = client.post(
        "/api/student-proctor/learning-store/clear",
        data=json.dumps({"confirm": RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM}),
        content_type="application/json",
    )
    assert clr.status_code == 200
    assert clr.get_json().get("ok") is True

    # --- Run 3 (baseline) ---
    st3 = client.post("/api/run-parallel/start", data=json.dumps(body), content_type="application/json")
    assert st3.status_code == 200
    done3 = _poll_done(client, st3.get_json()["job_id"])
    res3 = done3.get("result") or {}
    seam3 = res3.get("student_loop_directive_09_v1") or {}
    fp3 = res3.get("student_output_fingerprint")
    assert fp3 == fp1
    p3 = seam3.get("primary_trade_shadow_student_v1") or {}
    assert p3.get("retrieval_slice_count") == 0
    assert p3.get("student_decision_ref") == ref1
    assert p3.get("pattern_recipe_ids") == recipes1
