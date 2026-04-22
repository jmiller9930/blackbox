"""GT_DIRECTIVE_005 — decision frame schema (§11.3): ordering, ids, seal, HTTP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import (
    DecisionFramePayloadV1,
    DecisionFrameV1,
    ExamUnitTimelineDocumentV1,
    OhlcvV1,
    append_local_time_to_decision_frame_dict_v1,
    build_timeline_document_enter_single_frame_v1,
    build_timeline_document_no_trade_single_frame_v1,
    commit_timeline_immutable_v1,
    decision_frame_id_v1,
    find_frame_in_committed_timelines_v1,
    parse_decision_frame_id_v1,
    reset_exam_timelines_for_tests_v1,
    timeline_to_public_response_v1,
    validate_decision_frames_enter_rules_v1,
    validate_decision_frames_structure_v1,
)
from renaissance_v4.game_theory.exam_deliberation_capture_v1 import reset_exam_deliberations_for_tests_v1
from renaissance_v4.game_theory.exam_state_machine_v1 import reset_exam_units_for_tests_v1
from renaissance_v4.game_theory.web_app import create_app

_REPO = Path(__file__).resolve().parents[1]
_GOLDEN = (
    _REPO
    / "renaissance_v4"
    / "game_theory"
    / "docs"
    / "proof"
    / "exam_v1"
    / "golden_exam_unit_timeline_two_frames_enter_v1.json"
)


def setup_function() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    reset_exam_timelines_for_tests_v1()


def teardown_function() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    reset_exam_timelines_for_tests_v1()


def test_golden_fixture_round_trip_and_enter_two_frame_rules() -> None:
    raw = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    doc = ExamUnitTimelineDocumentV1.model_validate(raw)
    validate_decision_frames_enter_rules_v1(doc, enter=True)
    dumped = doc.model_dump(mode="json", by_alias=True)
    doc2 = ExamUnitTimelineDocumentV1.model_validate(dumped)
    assert len(doc2.decision_frames) == 2
    assert doc2.decision_frames[0].frame_index == 0
    assert doc2.decision_frames[1].frame_type == "downstream"


def test_no_trade_exactly_one_frame() -> None:
    d = build_timeline_document_no_trade_single_frame_v1(
        exam_unit_id="unit_no_trade",
        exam_pack_id="p",
        exam_pack_version="1",
        deliberation_export={"schema": "exam_deliberation"},
        bar_close_timestamp_iso="2026-04-21T12:00:00Z",
    )
    validate_decision_frames_enter_rules_v1(d, enter=False)
    assert len(d.decision_frames) == 1


def test_enter_single_frame_current_rule() -> None:
    d = build_timeline_document_enter_single_frame_v1(
        exam_unit_id="unit_enter_one",
        exam_pack_id="p",
        exam_pack_version="1",
        deliberation_export=None,
        bar_close_timestamp_iso="2026-04-21T12:00:00Z",
    )
    validate_decision_frames_enter_rules_v1(d, enter=True)
    assert len(d.decision_frames) == 1


def test_decision_frame_id_unique_and_parseable() -> None:
    uid = "abc123ff"
    assert decision_frame_id_v1(uid, 0) == "abc123ff__df0"
    assert parse_decision_frame_id_v1("abc123ff__df0") == (uid, 0)


def test_commit_immutable_twice_raises() -> None:
    d = build_timeline_document_no_trade_single_frame_v1(
        exam_unit_id="unit_immut",
        exam_pack_id=None,
        exam_pack_version=None,
        deliberation_export=None,
        bar_close_timestamp_iso="2026-04-21T12:00:00Z",
    )
    commit_timeline_immutable_v1(d)
    with pytest.raises(ValueError, match="timeline_already_committed_immutable"):
        commit_timeline_immutable_v1(d)


def test_duplicate_frame_index_rejected() -> None:
    uid = "unit_dup_idx"
    ts = "2026-04-21T12:00:00Z"
    p = DecisionFramePayloadV1(opening_snapshot=None, deliberation=None, decision_a=None)
    frames = [
        DecisionFrameV1(
            decision_frame_id=decision_frame_id_v1(uid, 0),
            exam_unit_id=uid,
            frame_index=0,
            timestamp=ts,
            frame_type="opening",
            payload=p,
        ),
        DecisionFrameV1(
            decision_frame_id=decision_frame_id_v1(uid, 0),
            exam_unit_id=uid,
            frame_index=0,
            timestamp=ts,
            frame_type="opening",
            payload=p,
        ),
    ]
    doc = ExamUnitTimelineDocumentV1(exam_unit_id=uid, decision_frames=frames)
    with pytest.raises(ValueError, match="frame_index_not_dense_or_not_zero_based"):
        validate_decision_frames_structure_v1(doc)


def test_missing_frame_0_rejected() -> None:
    uid = "unit_miss0"
    ts = "2026-04-21T12:00:00Z"
    p = DecisionFramePayloadV1()
    frames = [
        DecisionFrameV1(
            decision_frame_id=decision_frame_id_v1(uid, 1),
            exam_unit_id=uid,
            frame_index=1,
            timestamp=ts,
            frame_type="downstream",
            payload=p,
        ),
    ]
    doc = ExamUnitTimelineDocumentV1(exam_unit_id=uid, decision_frames=frames)
    with pytest.raises(ValueError, match="missing_frame_0"):
        validate_decision_frames_structure_v1(doc)


def test_duplicate_decision_frame_id_rejected() -> None:
    uid = "unit_dup_id"
    ts = "2026-04-21T12:00:00Z"
    p = DecisionFramePayloadV1()
    same_id = decision_frame_id_v1(uid, 0)
    frames = [
        DecisionFrameV1(
            decision_frame_id=same_id,
            exam_unit_id=uid,
            frame_index=0,
            timestamp=ts,
            frame_type="opening",
            payload=p,
        ),
        DecisionFrameV1(
            decision_frame_id=same_id,
            exam_unit_id=uid,
            frame_index=1,
            timestamp=ts,
            frame_type="downstream",
            payload=p,
        ),
    ]
    doc = ExamUnitTimelineDocumentV1(exam_unit_id=uid, decision_frames=frames)
    with pytest.raises(ValueError, match="duplicate_decision_frame_id"):
        validate_decision_frames_structure_v1(doc)


def test_parent_linkage_mismatch_rejected() -> None:
    uid = "unit_parent"
    ts = "2026-04-21T12:00:00Z"
    p = DecisionFramePayloadV1()
    frames = [
        DecisionFrameV1(
            decision_frame_id=decision_frame_id_v1(uid, 0),
            exam_unit_id="other_unit",
            frame_index=0,
            timestamp=ts,
            frame_type="opening",
            payload=p,
        ),
    ]
    doc = ExamUnitTimelineDocumentV1(exam_unit_id=uid, decision_frames=frames)
    with pytest.raises(ValueError, match="decision_frame_parent_mismatch"):
        validate_decision_frames_structure_v1(doc)


def test_no_trade_two_frames_rejected() -> None:
    uid = "unit_nt_two"
    ts = "2026-04-21T12:00:00Z"
    p0 = DecisionFramePayloadV1()
    p1 = DecisionFramePayloadV1(
        price_snapshot=OhlcvV1(open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0),
    )
    doc = ExamUnitTimelineDocumentV1(
        exam_unit_id=uid,
        exam_pack_id="p",
        exam_pack_version="1",
        decision_frames=[
            DecisionFrameV1(
                decision_frame_id=decision_frame_id_v1(uid, 0),
                exam_unit_id=uid,
                frame_index=0,
                timestamp=ts,
                frame_type="opening",
                payload=p0,
            ),
            DecisionFrameV1(
                decision_frame_id=decision_frame_id_v1(uid, 1),
                exam_unit_id=uid,
                frame_index=1,
                timestamp=ts,
                frame_type="downstream",
                payload=p1,
            ),
        ],
    )
    assert len(doc.decision_frames) == 2
    with pytest.raises(ValueError, match="no_trade_requires_exactly_one_frame"):
        validate_decision_frames_enter_rules_v1(doc, enter=False)


def test_enter_second_frame_must_be_downstream() -> None:
    uid = "unit_enter_bad_mid"
    ts = "2026-04-21T12:00:00Z"
    p = DecisionFramePayloadV1()
    doc = ExamUnitTimelineDocumentV1(
        exam_unit_id=uid,
        decision_frames=[
            DecisionFrameV1(
                decision_frame_id=decision_frame_id_v1(uid, 0),
                exam_unit_id=uid,
                frame_index=0,
                timestamp=ts,
                frame_type="opening",
                payload=p,
            ),
            DecisionFrameV1(
                decision_frame_id=decision_frame_id_v1(uid, 1),
                exam_unit_id=uid,
                frame_index=1,
                timestamp=ts,
                frame_type="opening",
                payload=p,
            ),
        ],
    )
    with pytest.raises(ValueError, match="enter_downstream_frames_must_have_type_downstream"):
        validate_decision_frames_enter_rules_v1(doc, enter=True)


def test_http_get_decision_frames_and_frame_after_seal() -> None:
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={"exam_pack_id": "pack_x", "exam_pack_version": "1"})
    uid = json.loads(cr.data)["exam_unit_id"]
    for ev, pl in [
        ("open_window_shown", {}),
        ("hypotheses_h1_h3_recorded", {}),
        ("h4_completed", {}),
    ]:
        r = c.post(f"/api/v1/exam/units/{uid}/transition", json={"event": ev, "payload": pl})
        assert r.status_code == 200
    dbody = _minimal_deliberation_body(uid)
    pr = c.put(f"/api/v1/exam/units/{uid}/frames/0/deliberation", json=dbody)
    assert pr.status_code == 200, pr.get_data(as_text=True)
    rs = c.post(
        f"/api/v1/exam/units/{uid}/transition",
        json={"event": "decision_a_sealed", "payload": {"enter": False}},
    )
    assert rs.status_code == 200
    gf = c.get(f"/api/v1/exam/units/{uid}/decision-frames")
    assert gf.status_code == 200
    gdata = json.loads(gf.data)
    assert gdata["ok"] is True
    assert len(gdata["decision_frames"]) == 1
    fid = gdata["decision_frames"][0]["decision_frame_id"]
    fr = c.get(f"/api/v1/exam/frames/{fid}")
    assert fr.status_code == 200
    assert json.loads(fr.data)["decision_frame_id"] == fid


def test_http_get_decision_frames_404_before_seal() -> None:
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={})
    uid = json.loads(cr.data)["exam_unit_id"]
    gf = c.get(f"/api/v1/exam/units/{uid}/decision-frames")
    assert gf.status_code == 404


def test_timeline_public_response_local_tz_courtesy() -> None:
    doc = build_timeline_document_no_trade_single_frame_v1(
        exam_unit_id="unit_loc",
        exam_pack_id="p",
        exam_pack_version="1",
        deliberation_export=None,
        bar_close_timestamp_iso="2026-04-21T12:00:00Z",
    )
    r = timeline_to_public_response_v1(doc, local_tz="America/New_York")
    assert r["local_time_tz"] == "America/New_York"
    disp = r["decision_frames"][0]["timestamp_local_display"]
    assert isinstance(disp, str)
    assert "2026-04-21 08:00:00" in disp
    assert r["decision_frames"][0]["timestamp"] == "2026-04-21T12:00:00Z"


def test_append_local_time_unknown_timezone() -> None:
    fr = append_local_time_to_decision_frame_dict_v1(
        {"decision_frame_id": "x__df0", "timestamp": "2026-04-21T12:00:00Z"},
        "Not_A_Real_Zone_Xyz",
    )
    assert fr.get("timestamp_local_error") == "unknown_timezone"


def test_http_decision_frames_with_tz_query() -> None:
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={"exam_pack_id": "pack_x", "exam_pack_version": "1"})
    uid = json.loads(cr.data)["exam_unit_id"]
    for ev, pl in [
        ("open_window_shown", {}),
        ("hypotheses_h1_h3_recorded", {}),
        ("h4_completed", {}),
    ]:
        assert c.post(f"/api/v1/exam/units/{uid}/transition", json={"event": ev, "payload": pl}).status_code == 200
    pr = c.put(f"/api/v1/exam/units/{uid}/frames/0/deliberation", json=_minimal_deliberation_body(uid))
    assert pr.status_code == 200
    assert c.post(
        f"/api/v1/exam/units/{uid}/transition",
        json={"event": "decision_a_sealed", "payload": {"enter": False}},
    ).status_code == 200
    gf = c.get(f"/api/v1/exam/units/{uid}/decision-frames?tz=America/New_York")
    assert gf.status_code == 200
    gdata = json.loads(gf.data)
    assert gdata.get("local_time_tz") == "America/New_York"
    assert "timestamp_local_display" in gdata["decision_frames"][0]


def test_http_get_frame_404_unknown() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_timelines_for_tests_v1()
    app = create_app()
    c = app.test_client()
    r = c.get("/api/v1/exam/frames/bogus__df0")
    assert r.status_code == 404


def _minimal_deliberation_body(uid: str) -> dict:
    """Valid deliberation envelope for seal integration (K=3)."""
    from pathlib import Path as P

    fix = P(__file__).resolve().parents[1] / "renaissance_v4/game_theory/docs/proof/exam_v1/fixture_exam_deliberation_valid_k3_v1.json"
    doc = json.loads(fix.read_text(encoding="utf-8"))
    doc["exam_unit_id"] = uid
    return {"pack_deliberation_policy": {"k_min": 3}, "deliberation": doc}
