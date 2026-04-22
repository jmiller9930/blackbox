"""§11.7 / §12 — exam timeline UI splice markers on Pattern Machine page HTML."""

from __future__ import annotations

from renaissance_v4.game_theory.web_app import create_app


def test_index_html_contains_exam_timeline_splice_shell() -> None:
    app = create_app()
    r = app.test_client().get("/")
    assert r.status_code == 200
    body = r.data
    assert b"pgExamUiSplice" in body
    assert b"pgExamDrillHost" in body
    assert b"wireExamUiSpliceV1" in body
    assert b"/api/v1/exam/units/" in body
    assert b"decision-frames" in body


def test_exam_timeline_http_flow_after_seal() -> None:
    """Smoke: same fetches the UI uses return 200 after a sealed NO_TRADE unit."""
    import json
    from pathlib import Path

    fix = Path(__file__).resolve().parents[1] / "renaissance_v4/game_theory/docs/proof/exam_v1/fixture_exam_deliberation_valid_k3_v1.json"
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={"exam_pack_id": "pack_ui", "exam_pack_version": "1"})
    uid = json.loads(cr.data)["exam_unit_id"]
    for ev, pl in [
        ("open_window_shown", {}),
        ("hypotheses_h1_h3_recorded", {}),
        ("h4_completed", {}),
    ]:
        assert c.post(f"/api/v1/exam/units/{uid}/transition", json={"event": ev, "payload": pl}).status_code == 200
    dbody = json.loads(fix.read_text(encoding="utf-8"))
    dbody["exam_unit_id"] = uid
    assert (
        c.put(
            f"/api/v1/exam/units/{uid}/frames/0/deliberation",
            json={"pack_deliberation_policy": {"k_min": 3}, "deliberation": dbody},
        ).status_code
        == 200
    )
    assert (
        c.post(
            f"/api/v1/exam/units/{uid}/transition",
            json={"event": "decision_a_sealed", "payload": {"enter": False}},
        ).status_code
        == 200
    )
    g1 = c.get(f"/api/v1/exam/units/{uid}/decision-frames")
    assert g1.status_code == 200
    frames = json.loads(g1.data)["decision_frames"]
    assert len(frames) == 1
    fid = frames[0]["decision_frame_id"]
    g2 = c.get(f"/api/v1/exam/frames/{fid}")
    assert g2.status_code == 200
    assert json.loads(g2.data)["decision_frame_id"] == fid
