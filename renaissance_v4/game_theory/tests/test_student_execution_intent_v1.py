"""GT_DIRECTIVE_024B — ``student_execution_intent_v1`` builder, validation, digests (no replay wiring)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.exam_run_contract_v1 import STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
from renaissance_v4.game_theory.student_proctor.contracts_v1 import legal_example_student_output_with_thesis_v1
from renaissance_v4.game_theory.student_proctor.student_execution_intent_v1 import (
    SCHEMA_STUDENT_EXECUTION_INTENT_V1,
    build_student_execution_intent_from_sealed_output_v1,
    compute_student_execution_intent_digest_v1,
    digest_sealed_student_output_v1,
    student_execution_intent_trace_created_fields_v1,
    validate_student_execution_intent_v1,
)
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_json(name: str) -> dict:
    p = _FIXTURES_DIR / name
    return json.loads(p.read_text(encoding="utf-8"))


def _llm_sealed_valid() -> dict:
    d = _load_json("student_output_thesis_llm_valid_v1.json")
    assert d["schema"] == "student_output_v1"
    return d


def _llm_sealed_incomplete() -> dict:
    return _load_json("student_output_thesis_llm_incomplete_v1.json")


def test_valid_enter_long_from_llm_sealed() -> None:
    so = _llm_sealed_valid()
    created = "2026-04-24T12:00:00.000000Z"
    out, err = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="job_gt024b_001",
        fingerprint="a" * 40,
        scenario_id="scen_1",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        llm_model="qwen2.5:7b",
        created_at_utc=created,
    )
    assert not err
    assert out is not None
    assert out["action"] == "enter_long"
    assert out["direction"] == "long"
    assert out["source_student_output_digest_v1"] == digest_sealed_student_output_v1(so)
    assert validate_student_execution_intent_v1(out) == []


def test_valid_enter_short_sealed() -> None:
    so = _llm_sealed_valid()
    so = copy.deepcopy(so)
    so["direction"] = "short"
    so["act"] = True
    so["student_action_v1"] = "enter_short"
    created = "2026-04-24T12:00:00.000000Z"
    out, err = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="job_gt024b_002",
        fingerprint="b" * 40,
        scenario_id="scen_1",
        trade_id=so["graded_unit_id"],
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        llm_model="deepseek-r1:14b",
        created_at_utc=created,
    )
    assert not err
    assert out and out["action"] == "enter_short" and out["direction"] == "short"


def test_valid_no_trade_sealed() -> None:
    so = _llm_sealed_valid()
    so = copy.deepcopy(so)
    so["act"] = False
    so["direction"] = "flat"
    so["student_action_v1"] = "no_trade"
    created = "2026-04-24T12:00:00.000000Z"
    out, err = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="job_gt024b_003",
        fingerprint="c" * 40,
        scenario_id="scen_2",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        created_at_utc=created,
    )
    assert not err
    assert out and out["action"] == "no_trade" and out["direction"] == "flat"


def test_invalid_action_direction_pair_rejected() -> None:
    bad = {
        "schema": SCHEMA_STUDENT_EXECUTION_INTENT_V1,
        "schema_version": 1,
        "job_id": "j",
        "fingerprint": "f" * 40,
        "student_brain_profile_v1": "memory_context_llm_student",
        "llm_model": "qwen2.5:7b",
        "source_student_output_digest_v1": "0" * 64,
        "student_execution_intent_digest_v1": "0" * 64,
        "action": "enter_long",
        "direction": "short",
        "confidence_01": 0.5,
        "confidence_band": "medium",
        "supporting_indicators": [],
        "conflicting_indicators": [],
        "context_fit": "trend",
        "invalidation_text": "n/a",
        "created_at_utc": "2026-04-24T12:00:00.000000Z",
        "scenario_id": "s1",
    }
    bad["student_execution_intent_digest_v1"] = compute_student_execution_intent_digest_v1(
        {k: v for k, v in bad.items() if k != "student_execution_intent_digest_v1"}
    )
    e = validate_student_execution_intent_v1(bad)
    assert e and any("mismatch" in x or "action" in x.lower() for x in e)


def test_missing_thesis_rejected_for_llm_profile() -> None:
    so = _llm_sealed_incomplete()
    out, err = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="job",
        fingerprint="a" * 40,
        scenario_id="s",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    )
    assert out is None
    assert err
    assert any("llm" in x.lower() or "thesis" in x.lower() or "missing" in x.lower() for x in err)


def test_intent_digest_stable_excludes_timestamp() -> None:
    so = _llm_sealed_valid()
    t1 = "2026-04-24T10:00:00.000000Z"
    t2 = "2026-04-30T00:00:00.000000Z"
    a, _ = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="same",
        fingerprint="a" * 40,
        scenario_id="s",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        created_at_utc=t1,
    )
    b, _ = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="same",
        fingerprint="a" * 40,
        scenario_id="s",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        created_at_utc=t2,
    )
    assert a and b
    assert a["student_execution_intent_digest_v1"] == b["student_execution_intent_digest_v1"]
    assert t1 != t2
    assert a["source_student_output_digest_v1"] == b["source_student_output_digest_v1"]


def test_intent_deterministic_digest_same_inputs() -> None:
    so = _llm_sealed_valid()
    t = "2026-01-01T00:00:00.000000Z"
    a, e1 = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="j",
        fingerprint="d" * 40,
        scenario_id="sx",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        created_at_utc=t,
    )
    b, e2 = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="j",
        fingerprint="d" * 40,
        scenario_id="sx",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        created_at_utc=t,
    )
    assert not e1 and not e2
    assert a and b
    assert a["student_execution_intent_digest_v1"] == b["student_execution_intent_digest_v1"]


def test_source_digest_matches_sealed_object() -> None:
    so = _llm_sealed_valid()
    out, _ = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="j",
        fingerprint="e" * 40,
        scenario_id="s",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        created_at_utc="2026-04-24T00:00:00.000000Z",
    )
    assert out
    assert out["source_student_output_digest_v1"] == digest_sealed_student_output_v1(so)
    if out["source_student_output_digest_v1"] != digest_sealed_student_output_v1(copy.deepcopy(so)):
        pytest.fail("copy should produce same digest")


def test_schema_validation_malformed() -> None:
    assert validate_student_execution_intent_v1("not a dict")
    assert validate_student_execution_intent_v1({"schema": "wrong"})


def test_trace_created_fields_shape() -> None:
    so = _llm_sealed_valid()
    out, _ = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="trace_j",
        fingerprint="f" * 40,
        scenario_id="s",
        student_brain_profile_v1=STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        llm_model="m",
        created_at_utc="2026-04-24T00:00:00.000000Z",
    )
    assert out
    t = student_execution_intent_trace_created_fields_v1(out)
    for k in (
        "job_id",
        "fingerprint",
        "student_execution_intent_digest_v1",
        "source_student_output_digest_v1",
        "action",
        "direction",
        "confidence_01",
        "student_brain_profile_v1",
        "llm_model",
    ):
        assert k in t


def test_non_llm_thesis_basics_legal_path() -> None:
    """``memory_context_student`` with full thesis on sealed output (from legal helper)."""
    so = legal_example_student_output_with_thesis_v1()
    out, err = build_student_execution_intent_from_sealed_output_v1(
        student_output_v1=so,
        job_id="j_nc",
        fingerprint="0" * 40,
        scenario_id="s_nc",
        student_brain_profile_v1="memory_context_student",
        created_at_utc="2026-04-24T12:00:00.000000Z",
    )
    assert not err
    assert out and out["action"] == "enter_long"


def test_valid_fixture_json_file_passes() -> None:
    v = _load_json("valid_student_execution_intent_enter_long_v1.json")
    assert validate_student_execution_intent_v1(v) == []


def test_invalid_fixture_json_file_fails_adr() -> None:
    v = _load_json("invalid_student_execution_intent_action_direction_v1.json")
    e = validate_student_execution_intent_v1(v)
    assert e and any("mismatch" in x for x in e)