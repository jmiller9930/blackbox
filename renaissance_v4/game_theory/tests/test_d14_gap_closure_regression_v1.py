"""
D14.GC.1 / GC.7 — regression: operator Student fold architecture, trade_id grain, delete scope, data_gap honesty.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.web_app import create_app

_WEB_APP = Path(__file__).resolve().parents[1] / "web_app.py"


def test_operator_student_triangle_body_has_only_l1_l2_l3_shell() -> None:
    """GC.1 — #studentTriangleBody contains a single shell div; seam/learning strip IDs not inside it."""
    text = _WEB_APP.read_text(encoding="utf-8")
    start = text.find('id="studentTriangleBody"')
    assert start != -1
    dev = text.find('id="pgDevStudentBatchPlumbing"')
    assert dev != -1
    assert start < dev
    segment = text[start:dev]
    assert 'id="pgStudentPanelD11"' in segment
    assert "pgDevStudentSeamInner" not in segment
    assert "pgLearningEventsStrip" not in segment
    assert "pgStudentHandoffStrip" not in segment


def test_level1_render_fn_contains_run_table_only_no_handoff_dom() -> None:
    """GC.7 — Level-1 refresh must not inject seam / handoff HTML (developer surface is separate)."""
    text = _WEB_APP.read_text(encoding="utf-8")
    m = re.search(
        r"async function refreshStudentPanelD11\(\) \{[\s\S]*?^    \}",
        text,
        re.MULTILINE,
    )
    assert m, "refreshStudentPanelD11 not found"
    body = m.group(0)
    assert "Run table" in body or "pg-student-d11-table" in body
    assert "pgDevStudentSeamInner" not in body
    assert "student_loop_directive_09" not in body


def test_selected_run_api_missing_job_is_explicit() -> None:
    """Missing job_id does not fabricate carousel grain."""
    from renaissance_v4.game_theory.student_panel_d13 import build_d13_selected_run_payload_v1

    p = build_d13_selected_run_payload_v1("__missing_job__")
    assert p.get("ok") is False
    assert "error" in p


def test_d13_selected_run_slices_keyed_by_trade_id_from_batch() -> None:
    """GC.7 — L2 carousel cards carry ``trade_id`` / ``graded_unit_id`` from replay outcomes."""
    from renaissance_v4.game_theory.student_panel_d13 import (
        SCHEMA_CAROUSEL_SLICE,
        build_d13_selected_run_payload_v1,
    )

    fake_oj = {
        "trade_id": "tr_carouse_proof",
        "symbol": "SOLUSDT",
        "direction": "long",
        "pnl": 1.0,
    }
    payload = {
        "schema": "batch_parallel_results_v1",
        "scenario_order": ["s1"],
        "results": [
            {
                "ok": True,
                "scenario_id": "s1",
                "replay_outcomes_json": [fake_oj],
            }
        ],
    }
    entry = {
        "job_id": "d13_k_test_job",
        "session_log_batch_dir": "/tmp",
    }
    scenarios = [{"scenario_id": "s1", "folder": "f1"}]
    with (
        patch(
            "renaissance_v4.game_theory.student_panel_d13.find_scorecard_entry_by_job_id",
            return_value=entry,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d13.build_scenario_list_for_batch",
            return_value=(Path("/tmp"), scenarios, None),
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d13.load_batch_parallel_results_v1",
            return_value=payload,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d13._panel_run_row_for_job",
            return_value=None,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d13.load_student_learning_records_v1",
            return_value=[],
        ),
    ):
        out = build_d13_selected_run_payload_v1("d13_k_test_job")
    assert out.get("grain") == "trade_id"
    assert len(out.get("slices") or []) == 1
    sl0 = out["slices"][0]
    assert sl0.get("schema") == SCHEMA_CAROUSEL_SLICE
    assert sl0.get("trade_id") == "tr_carouse_proof"
    assert sl0.get("graded_unit_id") == "tr_carouse_proof"


def test_d13_selected_run_slices_sorted_by_entry_time_asc() -> None:
    """Carousel housekeeping: slices follow entry_time ascending (earliest left), not batch row order."""
    from renaissance_v4.game_theory.student_panel_d13 import build_d13_selected_run_payload_v1

    later = {
        "trade_id": "tr_later",
        "pnl": -1.0,
        "entry_time": 2_000,
    }
    earlier = {
        "trade_id": "tr_earlier",
        "pnl": 1.0,
        "entry_time": 1_000,
    }
    payload = {
        "schema": "batch_parallel_results_v1",
        "scenario_order": ["s1"],
        "results": [
            {
                "ok": True,
                "scenario_id": "s1",
                "replay_outcomes_json": [later, earlier],
            }
        ],
    }
    entry = {"job_id": "d13_sort_job", "session_log_batch_dir": "/tmp"}
    scenarios = [{"scenario_id": "s1", "folder": "f1"}]
    with (
        patch(
            "renaissance_v4.game_theory.student_panel_d13.find_scorecard_entry_by_job_id",
            return_value=entry,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d13.build_scenario_list_for_batch",
            return_value=(Path("/tmp"), scenarios, None),
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d13.load_batch_parallel_results_v1",
            return_value=payload,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d13._panel_run_row_for_job",
            return_value=None,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d13.load_student_learning_records_v1",
            return_value=[],
        ),
    ):
        out = build_d13_selected_run_payload_v1("d13_sort_job")
    assert out.get("slice_ordering") == "trade_opportunities_entry_time_asc"
    slices = out.get("slices") or []
    assert len(slices) == 2
    assert slices[0].get("trade_id") == "tr_earlier"
    assert slices[0].get("order_index") == 0
    assert slices[1].get("trade_id") == "tr_later"
    assert slices[1].get("order_index") == 1


def test_build_student_decision_record_structured_reasoning_fields_are_data_gap() -> None:
    """GC.4 — structured_reasoning_v1 placeholders remain explicit data_gap until exporters exist."""
    from renaissance_v4.game_theory.student_panel_d14 import build_student_decision_record_v1

    fake_oj = {
        "trade_id": "tr_proof_1",
        "symbol": "SOLUSDT",
        "direction": "long",
        "entry_time": 1_700_000_000_000,
        "exit_time": 1_700_000_300_000,
        "entry_price": 100.0,
        "exit_price": 101.0,
        "pnl": 1.0,
        "mae": 0.1,
        "mfe": 0.5,
        "exit_reason": "test",
        "metadata": {},
    }
    payload = {
        "schema": "batch_parallel_results_v1",
        "results": [
            {
                "ok": True,
                "scenario_id": "baseline_default",
                "replay_outcomes_json": [fake_oj],
            }
        ],
    }
    entry = {"job_id": "x", "session_log_batch_dir": "/tmp"}
    with (
        patch(
            "renaissance_v4.game_theory.student_panel_d14.find_scorecard_entry_by_job_id",
            return_value=entry,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d14.build_scenario_list_for_batch",
            return_value=(Path("/tmp"), [{"scenario_id": "baseline_default", "folder": "baseline_default"}], None),
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d14.load_batch_parallel_results_v1",
            return_value=payload,
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d14.load_run_record",
            return_value={},
        ),
        patch(
            "renaissance_v4.game_theory.student_panel_d14.list_student_learning_records_by_graded_unit_id",
            return_value=[],
        ),
    ):
        rec = build_student_decision_record_v1("x", "tr_proof_1")
    assert rec and isinstance(rec, dict)
    sr = rec.get("structured_reasoning_v1") or {}
    for k in (
        "context_factors_considered",
        "pattern_candidates",
        "pattern_selected",
        "groundhog_influence",
        "decision_basis_summary",
        "baseline_difference_summary",
    ):
        assert sr.get(k) == "data_gap"
    gaps = rec.get("data_gaps") or []
    assert "structured_reasoning_export_not_wired" in gaps


@pytest.fixture
def flask_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_pattern_game_index_http_200(flask_client) -> None:
    """§F — Flask app serves shell (operator verifies live port separately)."""
    client = flask_client
    r = client.get("/")
    assert r.status_code == 200


def test_batch_scorecard_delete_returns_groundhog_unchanged(flask_client) -> None:
    """GC.3/GC.7 — row delete is scorecard-only; response promises Groundhog unchanged."""
    client = flask_client
    with patch(
        "renaissance_v4.game_theory.web_app.remove_batch_scorecard_line_by_job_id",
        return_value={"ok": True, "removed": 1},
    ) as rm:
        r = client.delete(
            "/api/batch-scorecard/run/test-job",
            json={"confirm": True},
        )
    rm.assert_called_once_with("test-job")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("groundhog_unchanged") is True
    assert body.get("student_proctor_learning_store_unchanged") is True


def test_student_panel_runs_route_returns_d14_schema(flask_client) -> None:
    with patch(
        "renaissance_v4.game_theory.web_app.default_batch_scorecard_jsonl",
        return_value=Path("/nonexistent_scorecard.jsonl"),
    ):
        r = flask_client.get("/api/student-panel/runs?limit=5")
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("schema") == "student_panel_d14_runs_v1"


def test_fixture_export_script_outputs_exist() -> None:
    """Proof artifacts tracked beside tests (regenerate via scripts/d14_gc_export_proof_payloads.py)."""
    proof = Path(__file__).resolve().parents[1] / "docs" / "proof" / "d14_gc"
    for name in (
        "sample_get_student_panel_runs_row.json",
        "sample_get_student_panel_selected_run.json",
        "sample_student_decision_record_v1.json",
        "fixture_batch/batch_parallel_results_v1.json",
    ):
        assert (proof / name).is_file(), f"missing {name}"

