"""GT_DIRECTIVE_007 — §11.5 grading service (E, P, PASS, pack-driven)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import (
    build_complete_enter_timeline_v1,
    build_timeline_document_no_trade_single_frame_v1,
)
from renaissance_v4.game_theory.exam_deliberation_capture_v1 import reset_exam_deliberations_for_tests_v1
from renaissance_v4.game_theory.exam_grading_service_v1 import (
    ExamPackGradingConfigV1,
    compute_exam_grade_v1,
    get_exam_pack_grading_config_v1,
    register_exam_pack_grading_config_v1,
    reset_exam_pack_grading_configs_for_tests_v1,
)
from renaissance_v4.game_theory.exam_state_machine_v1 import ExamPhase, reset_exam_units_for_tests_v1
from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import reset_exam_timelines_for_tests_v1
from renaissance_v4.game_theory.web_app import create_app

_REPO = Path(__file__).resolve().parents[1]
_FIX_GRADING = (
    _REPO
    / "renaissance_v4"
    / "game_theory"
    / "docs"
    / "proof"
    / "exam_v1"
    / "fixture_exam_grading_pack_and_outcomes_v1.json"
)
_FIX_DELIB = _REPO / "renaissance_v4/game_theory/docs/proof/exam_v1/fixture_exam_deliberation_valid_k3_v1.json"


def setup_function() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    reset_exam_timelines_for_tests_v1()
    reset_exam_pack_grading_configs_for_tests_v1()


def teardown_function() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    reset_exam_timelines_for_tests_v1()
    reset_exam_pack_grading_configs_for_tests_v1()


def _load_grading_fixture() -> dict:
    return json.loads(_FIX_GRADING.read_text(encoding="utf-8"))


def _delib_export(uid: str) -> dict:
    d = json.loads(_FIX_DELIB.read_text(encoding="utf-8"))
    d = deepcopy(d)
    d["exam_unit_id"] = uid
    return d


def _strip_with_expectancy(last_ev: float) -> list[dict]:
    """Two bars: opening + one downstream; last bar carries economic context."""
    return [
        {
            "bar_close": "2026-04-22T10:00:00Z",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000.0,
            "invalidation_triggers_on_close": False,
            "context": {"i": 0},
        },
        {
            "bar_close": "2026-04-22T10:05:00Z",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.0,
            "volume": 1100.0,
            "invalidation_triggers_on_close": False,
            "context": {"realized_expectancy": last_ev},
        },
    ]


def test_pass_no_trade_neutral_high_p() -> None:
    fx = _load_grading_fixture()
    cfg = ExamPackGradingConfigV1.model_validate(fx["pack_grading_no_trade_v1"])
    delib = _delib_export("u_nt")
    doc = build_timeline_document_no_trade_single_frame_v1(
        exam_unit_id="u_nt",
        exam_pack_id="pack_nt",
        exam_pack_version="1",
        deliberation_export=delib,
        bar_close_timestamp_iso="2026-04-22T10:00:00Z",
    )
    raw = doc.model_dump(mode="json", by_alias=True)
    out = compute_exam_grade_v1(
        exam_unit_id="u_nt",
        exam_phase=ExamPhase.DECISION_A_SEALED,
        enter=False,
        exam_pack_id="pack_nt",
        exam_pack_version="1",
        timeline_committed=raw,
        deliberation_export=delib,
        pack_config=cfg,
    )
    assert out["pass"] is True
    assert out["economic_result"]["mode"] == "no_trade_neutral"
    assert out["economic_result"]["passes"] is True
    assert out["process_score"] >= float(cfg.p_min)


def test_fail_e_only_expectancy_below_threshold() -> None:
    fx = _load_grading_fixture()
    cfg = ExamPackGradingConfigV1.model_validate(fx["pack_grading_expectancy_v1"])
    delib = _delib_export("u_fe")
    delib["h4"]["primary_selection"] = "H1"
    strip = _strip_with_expectancy(-0.5)
    doc = build_complete_enter_timeline_v1(
        exam_unit_id="u_fe",
        exam_pack_id="pack_e",
        exam_pack_version="1",
        deliberation_export=delib,
        frame0_bar_close_iso=strip[0]["bar_close"],
        strip=strip,
        policy={"mode": "fixed_bars", "D": 1},
    )
    raw = doc.model_dump(mode="json", by_alias=True)
    out = compute_exam_grade_v1(
        exam_unit_id="u_fe",
        exam_phase=ExamPhase.DECISION_A_SEALED,
        enter=True,
        exam_pack_id="pack_e",
        exam_pack_version="1",
        timeline_committed=raw,
        deliberation_export=delib,
        pack_config=cfg,
    )
    assert out["economic_result"]["passes"] is False
    assert out["pass"] is False
    assert out["process_score"] >= 0.5


def test_fail_p_only_high_e_low_process_weights() -> None:
    """H4 NO_TRADE + enter True → P2=0; p_min above blended P."""
    fx = _load_grading_fixture()
    cfg = ExamPackGradingConfigV1.model_validate(
        {
            **fx["pack_grading_expectancy_v1"],
            "p_min": 0.95,
        }
    )
    delib = _delib_export("u_fp")
    strip = _strip_with_expectancy(0.5)
    doc = build_complete_enter_timeline_v1(
        exam_unit_id="u_fp",
        exam_pack_id="pack_p",
        exam_pack_version="1",
        deliberation_export=delib,
        frame0_bar_close_iso=strip[0]["bar_close"],
        strip=strip,
        policy={"mode": "fixed_bars", "D": 1},
    )
    raw = doc.model_dump(mode="json", by_alias=True)
    out = compute_exam_grade_v1(
        exam_unit_id="u_fp",
        exam_phase=ExamPhase.DECISION_A_SEALED,
        enter=True,
        exam_pack_id="pack_p",
        exam_pack_version="1",
        timeline_committed=raw,
        deliberation_export=delib,
        pack_config=cfg,
    )
    assert out["economic_result"]["passes"] is True
    assert out["process_score"] < float(cfg.p_min)
    assert out["pass"] is False


def test_boundary_p_min_exact_two_thirds() -> None:
    """P1=P3=1, P2=0, equal weights → P=2/3; p_min=2/3 → pass."""
    fx = _load_grading_fixture()
    cfg = ExamPackGradingConfigV1.model_validate(
        {
            **fx["pack_grading_expectancy_v1"],
            "p_min": 2.0 / 3.0,
        }
    )
    delib = _delib_export("u_bndp")
    strip = _strip_with_expectancy(0.2)
    doc = build_complete_enter_timeline_v1(
        exam_unit_id="u_bndp",
        exam_pack_id="pack_b",
        exam_pack_version="1",
        deliberation_export=delib,
        frame0_bar_close_iso=strip[0]["bar_close"],
        strip=strip,
        policy={"mode": "fixed_bars", "D": 1},
    )
    raw = doc.model_dump(mode="json", by_alias=True)
    out = compute_exam_grade_v1(
        exam_unit_id="u_bndp",
        exam_phase=ExamPhase.DECISION_A_SEALED,
        enter=True,
        exam_pack_id="pack_b",
        exam_pack_version="1",
        timeline_committed=raw,
        deliberation_export=delib,
        pack_config=cfg,
    )
    assert out["process_score"] == pytest.approx(2.0 / 3.0)
    assert out["economic_result"]["passes"] is True
    assert out["pass"] is True


def test_boundary_e_threshold_exactly_met() -> None:
    fx = _load_grading_fixture()
    cfg = ExamPackGradingConfigV1.model_validate(fx["pack_grading_expectancy_v1"])
    delib = _delib_export("u_bnde")
    delib["h4"]["primary_selection"] = "H1"
    strip = _strip_with_expectancy(0.05)
    doc = build_complete_enter_timeline_v1(
        exam_unit_id="u_bnde",
        exam_pack_id="pack_be",
        exam_pack_version="1",
        deliberation_export=delib,
        frame0_bar_close_iso=strip[0]["bar_close"],
        strip=strip,
        policy={"mode": "fixed_bars", "D": 1},
    )
    raw = doc.model_dump(mode="json", by_alias=True)
    out = compute_exam_grade_v1(
        exam_unit_id="u_bnde",
        exam_phase=ExamPhase.DECISION_A_SEALED,
        enter=True,
        exam_pack_id="pack_be",
        exam_pack_version="1",
        timeline_committed=raw,
        deliberation_export=delib,
        pack_config=cfg,
    )
    assert out["economic_result"]["value"] == pytest.approx(0.05)
    assert out["economic_result"]["passes"] is True


def test_profit_factor_drawdown_mode() -> None:
    fx = _load_grading_fixture()
    cfg = ExamPackGradingConfigV1.model_validate(fx["pack_grading_pf_dd_v1"])
    delib = _delib_export("u_pf")
    delib["h4"]["primary_selection"] = "H1"
    strip = [
        {
            "bar_close": "2026-04-22T11:00:00Z",
            "open": 1.0,
            "high": 1.1,
            "low": 0.9,
            "close": 1.0,
            "volume": 1.0,
            "invalidation_triggers_on_close": False,
            "context": {},
        },
        {
            "bar_close": "2026-04-22T11:05:00Z",
            "open": 1.0,
            "high": 1.2,
            "low": 0.8,
            "close": 1.05,
            "volume": 2.0,
            "invalidation_triggers_on_close": False,
            "context": {"profit_factor": 1.5, "max_drawdown": 0.1},
        },
    ]
    doc = build_complete_enter_timeline_v1(
        exam_unit_id="u_pf",
        exam_pack_id="pack_pf",
        exam_pack_version="1",
        deliberation_export=delib,
        frame0_bar_close_iso=strip[0]["bar_close"],
        strip=strip,
        policy={"mode": "fixed_bars", "D": 1},
    )
    raw = doc.model_dump(mode="json", by_alias=True)
    out = compute_exam_grade_v1(
        exam_unit_id="u_pf",
        exam_phase=ExamPhase.DECISION_A_SEALED,
        enter=True,
        exam_pack_id="pack_pf",
        exam_pack_version="1",
        timeline_committed=raw,
        deliberation_export=delib,
        pack_config=cfg,
    )
    assert out["economic_result"]["mode"] == "profit_factor_drawdown"
    assert out["economic_result"]["passes"] is True


def test_pack_binding_changes_economic_outcome() -> None:
    """Same realized expectancy; stricter pack fails E."""
    fx = _load_grading_fixture()
    loose = ExamPackGradingConfigV1.model_validate(fx["pack_grading_expectancy_v1"])
    strict = ExamPackGradingConfigV1.model_validate(fx["pack_grading_expectancy_strict_v1"])
    delib = _delib_export("u_bind")
    delib["h4"]["primary_selection"] = "H1"
    strip = _strip_with_expectancy(0.2)
    doc = build_complete_enter_timeline_v1(
        exam_unit_id="u_bind",
        exam_pack_id="pack_x",
        exam_pack_version="1",
        deliberation_export=delib,
        frame0_bar_close_iso=strip[0]["bar_close"],
        strip=strip,
        policy={"mode": "fixed_bars", "D": 1},
    )
    raw = doc.model_dump(mode="json", by_alias=True)
    o_loose = compute_exam_grade_v1(
        exam_unit_id="u_bind",
        exam_phase=ExamPhase.DECISION_A_SEALED,
        enter=True,
        exam_pack_id="pack_x",
        exam_pack_version="1",
        timeline_committed=raw,
        deliberation_export=delib,
        pack_config=loose,
    )
    o_strict = compute_exam_grade_v1(
        exam_unit_id="u_bind",
        exam_phase=ExamPhase.DECISION_A_SEALED,
        enter=True,
        exam_pack_id="pack_x",
        exam_pack_version="1",
        timeline_committed=raw,
        deliberation_export=delib,
        pack_config=strict,
    )
    assert o_loose["economic_result"]["passes"] is True
    assert o_strict["economic_result"]["passes"] is False


def test_missing_pack_config_raises_on_get() -> None:
    register_exam_pack_grading_config_v1("p_only", "1", _load_grading_fixture()["pack_grading_expectancy_v1"])
    assert get_exam_pack_grading_config_v1("p_only", "1") is not None
    assert get_exam_pack_grading_config_v1("p_only", "2") is None


def test_http_grade_200_and_409_incomplete() -> None:
    app = create_app()
    c = app.test_client()
    fx = _load_grading_fixture()
    cr = c.post("/api/v1/exam/units", json={"exam_pack_id": "pack_http_g", "exam_pack_version": "1"})
    uid = json.loads(cr.data)["exam_unit_id"]
    pr = c.post(
        f"/api/v1/exam/packs/pack_http_g/grading-config",
        json={"exam_pack_version": "1", "grading": fx["pack_grading_no_trade_v1"]},
    )
    assert pr.status_code == 200, pr.get_data(as_text=True)
    for ev, pl in [
        ("open_window_shown", {}),
        ("hypotheses_h1_h3_recorded", {}),
        ("h4_completed", {}),
    ]:
        assert c.post(f"/api/v1/exam/units/{uid}/transition", json={"event": ev, "payload": pl}).status_code == 200
    dbody = json.loads(_FIX_DELIB.read_text(encoding="utf-8"))
    dbody["exam_unit_id"] = uid
    assert c.put(
        f"/api/v1/exam/units/{uid}/frames/0/deliberation",
        json={"pack_deliberation_policy": {"k_min": 3}, "deliberation": dbody},
    ).status_code == 200
    g0 = c.get(f"/api/v1/exam/units/{uid}/grade")
    assert g0.status_code == 409
    assert c.post(
        f"/api/v1/exam/units/{uid}/transition",
        json={"event": "decision_a_sealed", "payload": {"enter": False}},
    ).status_code == 200
    g1 = c.get(f"/api/v1/exam/units/{uid}/grade")
    assert g1.status_code == 200, g1.get_data(as_text=True)
    body = json.loads(g1.data)
    assert body["pass"] in (True, False)
    assert "economic_result" in body
    assert body["audit"]["grading_mode"] == "no_trade_neutral"


def test_http_grade_500_missing_pack_grading_config() -> None:
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={"exam_pack_id": "pack_nocfg", "exam_pack_version": "9"})
    uid = json.loads(cr.data)["exam_unit_id"]
    for ev, pl in [
        ("open_window_shown", {}),
        ("hypotheses_h1_h3_recorded", {}),
        ("h4_completed", {}),
    ]:
        c.post(f"/api/v1/exam/units/{uid}/transition", json={"event": ev, "payload": pl})
    dbody = json.loads(_FIX_DELIB.read_text(encoding="utf-8"))
    dbody["exam_unit_id"] = uid
    c.put(
        f"/api/v1/exam/units/{uid}/frames/0/deliberation",
        json={"pack_deliberation_policy": {"k_min": 3}, "deliberation": dbody},
    )
    c.post(f"/api/v1/exam/units/{uid}/transition", json={"event": "decision_a_sealed", "payload": {"enter": False}})
    r = c.get(f"/api/v1/exam/units/{uid}/grade")
    assert r.status_code == 500
    assert b"exam_pack_grading_config_missing" in r.data


def test_missing_economic_context_key_errors() -> None:
    fx = _load_grading_fixture()
    cfg = ExamPackGradingConfigV1.model_validate(fx["pack_grading_expectancy_v1"])
    delib = _delib_export("u_mis")
    delib["h4"]["primary_selection"] = "H1"
    strip = _strip_with_expectancy(0.1)
    strip[1]["context"] = {}  # no realized_expectancy
    doc = build_complete_enter_timeline_v1(
        exam_unit_id="u_mis",
        exam_pack_id="pack_m",
        exam_pack_version="1",
        deliberation_export=delib,
        frame0_bar_close_iso=strip[0]["bar_close"],
        strip=strip,
        policy={"mode": "fixed_bars", "D": 1},
    )
    raw = doc.model_dump(mode="json", by_alias=True)
    with pytest.raises(ValueError, match="missing_economic_context_key"):
        compute_exam_grade_v1(
            exam_unit_id="u_mis",
            exam_phase=ExamPhase.DECISION_A_SEALED,
            enter=True,
            exam_pack_id="pack_m",
            exam_pack_version="1",
            timeline_committed=raw,
            deliberation_export=delib,
            pack_config=cfg,
        )
