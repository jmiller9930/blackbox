"""GT_DIRECTIVE_006 — §11.4 downstream frame generator (termination, ordering, no-lookahead)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import (
    DecisionFramePayloadV1,
    DecisionFrameV1,
    ExamUnitTimelineDocumentV1,
    build_complete_enter_timeline_v1,
    decision_frame_id_v1,
    validate_decision_frames_enter_rules_v1,
)
from renaissance_v4.game_theory.exam_downstream_frame_generator_v1 import (
    DownstreamTerminationPolicyV1,
    generate_downstream_frames_after_seal_v1,
    reset_exam_downstream_dev_stores_for_tests_v1,
)
from renaissance_v4.game_theory.exam_deliberation_capture_v1 import reset_exam_deliberations_for_tests_v1
from renaissance_v4.game_theory.exam_state_machine_v1 import reset_exam_units_for_tests_v1
from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import reset_exam_timelines_for_tests_v1
from renaissance_v4.game_theory.web_app import create_app

_REPO = Path(__file__).resolve().parents[1]
_FIXTURE = (
    _REPO
    / "renaissance_v4"
    / "game_theory"
    / "docs"
    / "proof"
    / "exam_v1"
    / "fixture_exam_downstream_ohlc_strip_v1.json"
)


def setup_function() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    reset_exam_timelines_for_tests_v1()
    reset_exam_downstream_dev_stores_for_tests_v1()


def teardown_function() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    reset_exam_timelines_for_tests_v1()
    reset_exam_downstream_dev_stores_for_tests_v1()


def _strip() -> list[dict[str, object]]:
    doc = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return list(doc["bars"])


def _minimal_deliberation_body(uid: str) -> dict:
    fix = _REPO / "renaissance_v4/game_theory/docs/proof/exam_v1/fixture_exam_deliberation_valid_k3_v1.json"
    d = json.loads(fix.read_text(encoding="utf-8"))
    d["exam_unit_id"] = uid
    return {"pack_deliberation_policy": {"k_min": 3}, "deliberation": d}


def test_fixed_bar_count_default_and_explicit() -> None:
    s = _strip()
    pol = DownstreamTerminationPolicyV1(mode="fixed_bars", D=3)
    frames = generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_fix",
        strip=s,
        policy=pol,
        decision_a_sealed=True,
        enter=True,
    )
    assert len(frames) == 3
    assert [f.frame_index for f in frames] == [1, 2, 3]
    assert frames[-1].payload.price_snapshot is not None
    assert frames[-1].payload.price_snapshot.close == pytest.approx(102.0)


def test_until_invalidation_stops_on_correct_bar() -> None:
    s = _strip()
    pol = DownstreamTerminationPolicyV1(mode="until_invalidation")
    frames = generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_inv",
        strip=s,
        policy=pol,
        decision_a_sealed=True,
        enter=True,
    )
    assert len(frames) == 4
    assert frames[-1].timestamp == "2026-04-21T12:20:00Z"
    assert frames[-1].payload.price_snapshot is not None


def test_volatility_stops_at_threshold_or_cap() -> None:
    s = _strip()
    pol = DownstreamTerminationPolicyV1(
        mode="volatility_regime_cap",
        range_threshold=0.5,
        max_bars=20,
    )
    frames = generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_vol",
        strip=s,
        policy=pol,
        decision_a_sealed=True,
        enter=True,
    )
    assert len(frames) == 5
    assert frames[-1].timestamp == "2026-04-21T12:25:00Z"


def test_no_trade_zero_downstream() -> None:
    s = _strip()
    pol = DownstreamTerminationPolicyV1(mode="fixed_bars", D=5)
    assert (
        generate_downstream_frames_after_seal_v1(
            exam_unit_id="u_nt",
            strip=s,
            policy=pol,
            decision_a_sealed=True,
            enter=False,
        )
        == []
    )


def test_downstream_requires_seal() -> None:
    with pytest.raises(ValueError, match="downstream_requires_decision_a_sealed"):
        generate_downstream_frames_after_seal_v1(
            exam_unit_id="u",
            strip=_strip(),
            policy=DownstreamTerminationPolicyV1(),
            decision_a_sealed=False,
            enter=True,
        )


def test_frame_index_strictly_increasing_matches_strip_index() -> None:
    s = _strip()
    frames = generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_ord",
        strip=s,
        policy=DownstreamTerminationPolicyV1(mode="fixed_bars", D=4),
        decision_a_sealed=True,
        enter=True,
    )
    prev = 0
    for f in frames:
        assert f.frame_index > prev
        prev = f.frame_index
        assert f.frame_index < len(s)
        assert f.timestamp == s[f.frame_index]["bar_close"]


def test_no_lookahead_payload_uses_only_current_bar_close() -> None:
    strip: list[dict[str, object]] = [
        {
            "bar_close": "2026-04-21T10:00:00Z",
            "open": 1.0,
            "high": 1.1,
            "low": 0.9,
            "close": 1.0,
            "volume": 1.0,
            "invalidation_triggers_on_close": False,
            "context": {},
        },
        {
            "bar_close": "2026-04-21T10:05:00Z",
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 2.0,
            "invalidation_triggers_on_close": False,
            "context": {},
        },
        {
            "bar_close": "2026-04-21T10:10:00Z",
            "open": 2.0,
            "high": 2.2,
            "low": 1.8,
            "close": 77.0,
            "volume": 3.0,
            "invalidation_triggers_on_close": False,
            "context": {"note": "target_bar"},
        },
        {
            "bar_close": "2026-04-21T10:15:00Z",
            "open": 500.0,
            "high": 510.0,
            "low": 490.0,
            "close": 999.0,
            "volume": 4.0,
            "invalidation_triggers_on_close": False,
            "context": {"trap": True},
        },
    ]
    frames = generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_nl",
        strip=strip,
        policy=DownstreamTerminationPolicyV1(mode="fixed_bars", D=2),
        decision_a_sealed=True,
        enter=True,
    )
    assert len(frames) == 2
    assert frames[1].frame_index == 2
    assert frames[1].payload.price_snapshot is not None
    assert frames[1].payload.price_snapshot.close == pytest.approx(77.0)


def test_strip_bar_read_order_no_ahead_of_emit_cursor() -> None:
    class TrackingStrip(list):
        def __init__(self, seq: list[dict[str, object]]) -> None:
            super().__init__(seq)
            self.accessed: list[int] = []

        def __getitem__(self, i: int) -> dict[str, object]:  # type: ignore[override]
            self.accessed.append(i)
            return super().__getitem__(i)

    inner = _strip()
    tr = TrackingStrip(inner)
    generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_trk",
        strip=tr,
        policy=DownstreamTerminationPolicyV1(mode="fixed_bars", D=3),
        decision_a_sealed=True,
        enter=True,
    )
    assert tr.accessed == [1, 2, 3]


def test_fixed_bars_respects_D_not_full_strip() -> None:
    s = _strip()
    frames = generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_cap",
        strip=s,
        policy=DownstreamTerminationPolicyV1(mode="fixed_bars", D=1),
        decision_a_sealed=True,
        enter=True,
    )
    assert len(frames) == 1
    assert frames[0].frame_index == 1


def test_volatility_max_bars_cap() -> None:
    s = _strip()
    pol = DownstreamTerminationPolicyV1(
        mode="volatility_regime_cap",
        range_threshold=10.0,
        max_bars=2,
    )
    frames = generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_mxc",
        strip=s,
        policy=pol,
        decision_a_sealed=True,
        enter=True,
    )
    assert len(frames) == 2


def test_enter_downstream_without_price_snapshot_rejected() -> None:
    uid = "u_bad_ds"
    ts = "2026-04-21T12:00:00Z"
    p0 = DecisionFramePayloadV1(
        opening_snapshot=None,
        deliberation=None,
        decision_a={"enter": True},
    )
    p1 = DecisionFramePayloadV1(
        opening_snapshot=None,
        deliberation=None,
        decision_a=None,
        price_snapshot=None,
    )
    doc = ExamUnitTimelineDocumentV1(
        exam_unit_id=uid,
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
    with pytest.raises(ValueError, match="enter_downstream_requires_price_snapshot"):
        validate_decision_frames_enter_rules_v1(doc, enter=True)


def test_fixture_expectations_document_matches_generator() -> None:
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    exp = raw["expectations"]
    s = list(raw["bars"])
    f = generate_downstream_frames_after_seal_v1(
        exam_unit_id="u_doc",
        strip=s,
        policy=DownstreamTerminationPolicyV1(mode="fixed_bars", D=3),
        decision_a_sealed=True,
        enter=True,
    )
    assert len(f) == exp["fixed_bars_D3"]["downstream_frame_count"]
    assert f[-1].payload.price_snapshot is not None
    assert f[-1].payload.price_snapshot.close == pytest.approx(exp["fixed_bars_D3"]["last_downstream_close"])


def test_build_complete_enter_timeline_round_trip_validate() -> None:
    s = _strip()
    doc = build_complete_enter_timeline_v1(
        exam_unit_id="u_comp",
        exam_pack_id="p",
        exam_pack_version="1",
        deliberation_export={"schema": "exam_deliberation"},
        frame0_bar_close_iso=str(s[0]["bar_close"]),
        strip=s,
        policy=DownstreamTerminationPolicyV1(mode="fixed_bars", D=2),
    )
    validate_decision_frames_enter_rules_v1(doc, enter=True)
    assert len(doc.decision_frames) == 3
    assert doc.decision_frames[0].frame_type == "opening"
    assert all(x.frame_type == "downstream" for x in doc.decision_frames[1:])


def test_http_enter_seal_without_ohlc_post_uses_synthetic_strip_default_D5() -> None:
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
    assert (
        c.post(
            f"/api/v1/exam/units/{uid}/transition",
            json={"event": "decision_a_sealed", "payload": {"enter": True}},
        ).status_code
        == 200
    )
    gf = c.get(f"/api/v1/exam/units/{uid}/decision-frames")
    assert gf.status_code == 200
    gdata = json.loads(gf.data)
    assert len(gdata["decision_frames"]) == 6


def test_http_get_decision_frames_includes_downstream_after_enter_seal() -> None:
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={"exam_pack_id": "pack_x", "exam_pack_version": "1"})
    uid = json.loads(cr.data)["exam_unit_id"]
    sr = c.post(
        f"/api/v1/exam/units/{uid}/ohlc-strip",
        json={"bars": _strip(), "downstream_termination": {"mode": "fixed_bars", "D": 2}},
    )
    assert sr.status_code == 200, sr.get_data(as_text=True)
    for ev, pl in [
        ("open_window_shown", {}),
        ("hypotheses_h1_h3_recorded", {}),
        ("h4_completed", {}),
    ]:
        r = c.post(f"/api/v1/exam/units/{uid}/transition", json={"event": ev, "payload": pl})
        assert r.status_code == 200
    pr = c.put(f"/api/v1/exam/units/{uid}/frames/0/deliberation", json=_minimal_deliberation_body(uid))
    assert pr.status_code == 200, pr.get_data(as_text=True)
    rs = c.post(
        f"/api/v1/exam/units/{uid}/transition",
        json={"event": "decision_a_sealed", "payload": {"enter": True}},
    )
    assert rs.status_code == 200
    gf = c.get(f"/api/v1/exam/units/{uid}/decision-frames")
    assert gf.status_code == 200
    gdata = json.loads(gf.data)
    assert gdata["ok"] is True
    frames = gdata["decision_frames"]
    assert len(frames) == 3
    assert frames[0]["frame_index"] == 0
    assert frames[1]["frame_index"] == 1
    assert frames[2]["frame_index"] == 2
    assert frames[1]["frame_type"] == "downstream"
    assert frames[1]["payload"]["price_snapshot"]["close"] == pytest.approx(100.5)
