"""GT_DIRECTIVE_004 — deliberation capture (§11.2): schema, policy, HTTP, regression."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from renaissance_v4.game_theory.exam_deliberation_capture_v1 import (
    ExamDeliberationPayloadV1,
    PackDeliberationPolicyV1,
    SUPPORTED_DELIBERATION_SCHEMA_VERSIONS,
    assert_non_placeholder_deliberation_v1,
    deliberation_http_route_matrix_v1,
    deliberation_payload_to_export_dict_v1,
    get_frame0_deliberation_v1,
    parse_submit_envelope_v1,
    reset_exam_deliberations_for_tests_v1,
    validate_deliberation_against_policy_v1,
    validate_h4_primary_selection_integrity_v1,
)
from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import reset_exam_timelines_for_tests_v1
from renaissance_v4.game_theory.exam_state_machine_v1 import create_exam_unit_v1, reset_exam_units_for_tests_v1
from renaissance_v4.game_theory.web_app import create_app

_REPO = Path(__file__).resolve().parents[1]
_FIXTURE = (
    _REPO
    / "renaissance_v4"
    / "game_theory"
    / "docs"
    / "proof"
    / "exam_v1"
    / "fixture_exam_deliberation_valid_k3_v1.json"
)
_SCHEMA = (
    _REPO
    / "renaissance_v4"
    / "game_theory"
    / "schemas"
    / "exam_deliberation_payload_v1.schema.json"
)


def setup_function() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    reset_exam_timelines_for_tests_v1()


def teardown_function() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    reset_exam_timelines_for_tests_v1()


def _delib_dict_from_fixture(*, exam_unit_id: str) -> dict:
    doc = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    out = dict(doc)
    out["exam_unit_id"] = exam_unit_id
    return out


def test_fixture_validates_and_meets_k3_h4_contract() -> None:
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    env = parse_submit_envelope_v1({"pack_deliberation_policy": {"k_min": 3}, "deliberation": raw})
    assert len(env.deliberation.hypotheses) >= 3
    assert env.deliberation.h4.primary_selection in {"H1", "H2", "H3", "NO_TRADE"}
    for h in env.deliberation.hypotheses:
        assert len(h.market_interpretation) >= 20
        assert len(h.indicator_support) >= 20
        assert len(h.falsification_condition) >= 20
    assert len(env.deliberation.h4.comparative_evaluation) >= 40
    assert len(env.deliberation.h4.bounded_reasoning) >= 40
    validate_deliberation_against_policy_v1(env.deliberation, env.pack_deliberation_policy)
    assert_non_placeholder_deliberation_v1(env.deliberation)


def test_versioned_schema_artifact_exists_and_matches_model() -> None:
    assert _SCHEMA.is_file()
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    assert schema.get("$id")
    assert schema.get("title") == "exam_deliberation_payload_v1"
    assert "schema" in schema.get("properties", {})
    assert "hypotheses" in schema.get("properties", {})
    assert "schema" in schema.get("required", [])


def test_unsupported_schema_version_rejected() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_one")
    raw["schema_version"] = "0.0.0"
    with pytest.raises(ValidationError):
        ExamDeliberationPayloadV1.model_validate(raw)


def test_malformed_payload_missing_h4_rejected() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_one")
    del raw["h4"]
    with pytest.raises(ValidationError):
        ExamDeliberationPayloadV1.model_validate(raw)


def test_hypothesis_count_below_k_min_rejected() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_one")
    raw["hypotheses"] = raw["hypotheses"][:2]
    raw["h4"]["primary_selection"] = "H2"
    raw["h4"]["comparative_evaluation"] = (
        raw["h4"]["comparative_evaluation"] + " With only H1 and H2 on the tape, the comparison is binary."
    )
    p = ExamDeliberationPayloadV1.model_validate(raw)
    pol = PackDeliberationPolicyV1(k_min=3)
    with pytest.raises(ValueError, match="hypothesis_count_below_k_min"):
        validate_deliberation_against_policy_v1(p, pol)


def test_data_gap_rejected_when_pack_disallows_path() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_one")
    raw["data_gaps"] = [
        {"path": "hypotheses[0].indicator_support", "reason": "Vendor feed dropped one print mid-window."}
    ]
    p = ExamDeliberationPayloadV1.model_validate(raw)
    pol = PackDeliberationPolicyV1(k_min=3, data_gap_allowed_paths=[])
    with pytest.raises(ValueError, match="data_gap_path_not_allowed_by_pack"):
        validate_deliberation_against_policy_v1(p, pol)


def test_duplicate_hypothesis_ids_rejected_for_h4_integrity() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_one")
    raw["hypotheses"] = [dict(raw["hypotheses"][0]), dict(raw["hypotheses"][1]), dict(raw["hypotheses"][2])]
    raw["hypotheses"][1]["hypothesis_id"] = "H1"
    raw["hypotheses"][1]["market_interpretation"] = (
        raw["hypotheses"][1]["market_interpretation"] + " Second row shares H1 id for integrity regression."
    )
    raw["h4"]["primary_selection"] = "H1"
    raw["h4"]["comparative_evaluation"] = (
        raw["h4"]["comparative_evaluation"] + " Primary ties to H1 while duplicate ids remain invalid."
    )
    p = ExamDeliberationPayloadV1.model_validate(raw)
    pol = PackDeliberationPolicyV1(k_min=3)
    with pytest.raises(ValueError, match="duplicate_hypothesis_id"):
        validate_h4_primary_selection_integrity_v1(p, pol)


def test_no_trade_primary_rejected_when_pack_disallows() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_one")
    raw["h4"]["primary_selection"] = "NO_TRADE"
    raw["h4"]["comparative_evaluation"] = (
        raw["h4"]["comparative_evaluation"] + " Pack forbids NO_TRADE primary; this row exercises that gate."
    )
    p = ExamDeliberationPayloadV1.model_validate(raw)
    assert p.h4.primary_selection == "NO_TRADE"
    pol = PackDeliberationPolicyV1(k_min=3, allow_no_trade_primary=False)
    with pytest.raises(ValueError, match="no_trade_primary_not_allowed_by_pack"):
        validate_h4_primary_selection_integrity_v1(p, pol)


def test_data_gap_allowed_only_when_pack_lists_path() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_one")
    raw["data_gaps"] = [
        {"path": "hypotheses[0].indicator_support", "reason": "Vendor feed dropped one print mid-window."}
    ]
    p = ExamDeliberationPayloadV1.model_validate(raw)
    pol = PackDeliberationPolicyV1(
        k_min=3,
        data_gap_allowed_paths=["hypotheses[0].indicator_support"],
    )
    validate_deliberation_against_policy_v1(p, pol)


def test_placeholder_only_export_cannot_pass_non_placeholder_gate() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_one")
    raw["hypotheses"][0]["market_interpretation"] = (
        "This is long enough to pass pydantic min length but still a TODO for the student to replace later."
    )
    p = ExamDeliberationPayloadV1.model_validate(raw)
    with pytest.raises(ValueError, match="placeholder_text_forbidden"):
        assert_non_placeholder_deliberation_v1(p)


def test_exporter_produces_populated_json_dict() -> None:
    raw = _delib_dict_from_fixture(exam_unit_id="unit_export")
    p = ExamDeliberationPayloadV1.model_validate(raw)
    d = deliberation_payload_to_export_dict_v1(p)
    assert d["schema"] == "exam_deliberation"
    assert d["schema_version"] in SUPPORTED_DELIBERATION_SCHEMA_VERSIONS
    assert len(d["hypotheses"]) == 3
    assert "comparative_evaluation" in d["h4"]


def test_http_route_matrix_documented() -> None:
    rows = deliberation_http_route_matrix_v1()
    paths = {r["path"] for r in rows}
    assert "/api/v1/exam/units/{exam_unit_id}/frames/0/deliberation" in paths


def test_http_put_get_frame0_deliberation_200() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={"exam_pack_id": "p", "exam_pack_version": "1"})
    uid = json.loads(cr.data)["exam_unit_id"]
    body = {
        "pack_deliberation_policy": {"k_min": 3, "data_gap_allowed_paths": []},
        "deliberation": _delib_dict_from_fixture(exam_unit_id=uid),
    }
    pr = c.put(f"/api/v1/exam/units/{uid}/frames/0/deliberation", json=body)
    assert pr.status_code == 200, pr.get_data(as_text=True)
    gr = c.get(f"/api/v1/exam/units/{uid}/frames/0/deliberation")
    assert gr.status_code == 200
    data = json.loads(gr.data)
    assert data["decision_frame_index"] == 0
    assert data["deliberation"]["schema"] == "exam_deliberation"
    assert data["deliberation"]["exam_unit_id"] == uid


def test_http_put_404_unknown_unit() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    app = create_app()
    c = app.test_client()
    body = {
        "deliberation": _delib_dict_from_fixture(exam_unit_id="doesnotexist"),
    }
    pr = c.put("/api/v1/exam/units/doesnotexist/frames/0/deliberation", json=body)
    assert pr.status_code == 404


def test_http_put_422_exam_unit_id_mismatch() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={})
    uid = json.loads(cr.data)["exam_unit_id"]
    body = {
        "deliberation": _delib_dict_from_fixture(exam_unit_id="other_id"),
    }
    pr = c.put(f"/api/v1/exam/units/{uid}/frames/0/deliberation", json=body)
    assert pr.status_code == 422


def test_http_put_422_no_trade_primary_disallowed_by_pack() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={})
    uid = json.loads(cr.data)["exam_unit_id"]
    d = _delib_dict_from_fixture(exam_unit_id=uid)
    d["h4"]["primary_selection"] = "NO_TRADE"
    d["h4"]["comparative_evaluation"] = (
        d["h4"]["comparative_evaluation"] + " Exercise NO_TRADE primary with pack flag false."
    )
    pr = c.put(
        f"/api/v1/exam/units/{uid}/frames/0/deliberation",
        json={
            "pack_deliberation_policy": {"k_min": 3, "allow_no_trade_primary": False},
            "deliberation": d,
        },
    )
    assert pr.status_code == 422
    err = json.loads(pr.data).get("error", "")
    assert "no_trade_primary_not_allowed_by_pack" in err


def test_http_put_422_placeholder_body() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={})
    uid = json.loads(cr.data)["exam_unit_id"]
    d = _delib_dict_from_fixture(exam_unit_id=uid)
    d["hypotheses"][0]["market_interpretation"] = "x" * 25 + " PLACEHOLDER " + "y" * 25
    pr = c.put(
        f"/api/v1/exam/units/{uid}/frames/0/deliberation",
        json={"deliberation": d},
    )
    assert pr.status_code == 422


def test_http_put_400_envelope_validation() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={})
    uid = json.loads(cr.data)["exam_unit_id"]
    pr = c.put(f"/api/v1/exam/units/{uid}/frames/0/deliberation", json={"deliberation": "not-an-object"})
    assert pr.status_code == 400


def test_http_get_404_when_missing() -> None:
    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    app = create_app()
    c = app.test_client()
    cr = c.post("/api/v1/exam/units", json={})
    uid = json.loads(cr.data)["exam_unit_id"]
    gr = c.get(f"/api/v1/exam/units/{uid}/frames/0/deliberation")
    assert gr.status_code == 404


def test_pure_functions_store_retrieve() -> None:
    from renaissance_v4.game_theory.exam_deliberation_capture_v1 import put_frame0_deliberation_v1

    reset_exam_units_for_tests_v1()
    reset_exam_deliberations_for_tests_v1()
    u = create_exam_unit_v1()
    p = ExamDeliberationPayloadV1.model_validate(_delib_dict_from_fixture(exam_unit_id=u.exam_unit_id))
    d = deliberation_payload_to_export_dict_v1(p)
    put_frame0_deliberation_v1(u.exam_unit_id, d)
    got = get_frame0_deliberation_v1(u.exam_unit_id)
    assert got is not None
    assert got["h4"]["primary_selection"] == "H3"
