"""GT_DIRECTIVE_003 — exam unit state machine (§11.1, §3 ordering)."""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.game_theory.exam_state_machine_v1 import (
    ExamPhase,
    apply_exam_unit_transition_v1,
    create_exam_unit_v1,
    get_exam_unit_v1,
    reset_exam_units_for_tests_v1,
)
from renaissance_v4.game_theory.web_app import create_app


def setup_function() -> None:
    reset_exam_units_for_tests_v1()


def teardown_function() -> None:
    reset_exam_units_for_tests_v1()


def _happy_path_events(*, enter: bool) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = [
        ("open_window_shown", {}),
        ("hypotheses_h1_h3_recorded", {}),
        ("h4_completed", {}),
        ("decision_a_sealed", {"enter": enter}),
    ]
    if enter:
        out.append(("downstream_released", {}))
    out.append(("decision_b_complete", {}))
    out.append(("complete_unit", {}))
    return out


def test_valid_sequence_enter_true() -> None:
    u = create_exam_unit_v1(exam_pack_id="pack_x", exam_pack_version="1.0.0")
    for ev, pl in _happy_path_events(enter=True):
        r = u.apply(ev, pl)
        assert r.get("ok") is True, r
    assert u.phase == ExamPhase.COMPLETE
    assert u.enter is True


def test_valid_sequence_no_trade() -> None:
    u = create_exam_unit_v1()
    for ev, pl in _happy_path_events(enter=False):
        r = u.apply(ev, pl)
        assert r.get("ok") is True, r
    assert u.phase == ExamPhase.COMPLETE
    assert u.enter is False


def test_downstream_before_seal_invalidates() -> None:
    u = create_exam_unit_v1()
    u.apply("open_window_shown", {})
    u.apply("hypotheses_h1_h3_recorded", {})
    u.apply("h4_completed", {})
    r = u.apply("downstream_released", {})
    assert r.get("ok") is False
    assert u.phase == ExamPhase.INVALID


def test_seal_before_h4_invalidates() -> None:
    u = create_exam_unit_v1()
    u.apply("open_window_shown", {})
    u.apply("hypotheses_h1_h3_recorded", {})
    r = u.apply("decision_a_sealed", {"enter": False})
    assert r.get("ok") is False
    assert u.phase == ExamPhase.INVALID


def test_downstream_when_enter_false_invalidates() -> None:
    u = create_exam_unit_v1()
    for ev, pl in [
        ("open_window_shown", {}),
        ("hypotheses_h1_h3_recorded", {}),
        ("h4_completed", {}),
        ("decision_a_sealed", {"enter": False}),
    ]:
        assert u.apply(ev, pl).get("ok") is True
    r = u.apply("downstream_released", {})
    assert r.get("ok") is False
    assert u.phase == ExamPhase.INVALID


def test_golden_fixture_matches_engine() -> None:
    p = (
        Path(__file__).resolve().parents[1]
        / "renaissance_v4"
        / "game_theory"
        / "docs"
        / "proof"
        / "exam_v1"
        / "golden_exam_unit_transition_trace_valid_v1.json"
    )
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc.get("schema") == "golden_exam_unit_transition_trace_v1"
    u = create_exam_unit_v1(exam_unit_id=doc["exam_unit_id"], exam_pack_id="fixture", exam_pack_version="0")
    for step in doc["steps"]:
        r = u.apply(step["event"], step.get("payload") or {})
        assert r.get("ok") is True, (step, r)
    assert u.phase.value == doc["expected_final_phase"]


def test_api_create_get_transition() -> None:
    reset_exam_units_for_tests_v1()
    app = create_app()
    c = app.test_client()
    r = c.post("/api/v1/exam/units", json={"exam_pack_id": "p", "exam_pack_version": "1"})
    assert r.status_code == 201
    data = json.loads(r.data)
    assert data.get("ok") is True
    uid = data["exam_unit_id"]
    r2 = c.get(f"/api/v1/exam/units/{uid}")
    assert r2.status_code == 200
    r3 = c.post(
        f"/api/v1/exam/units/{uid}/transition",
        json={"event": "open_window_shown", "payload": {}},
    )
    assert r3.status_code == 200
    assert json.loads(r3.data).get("phase") == ExamPhase.OPENING_SHOWN.value
