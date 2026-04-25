"""
GT_DIRECTIVE_025 — Learning flow step validator: PASS/FAIL/NOT_PROVEN cases + HTTP wiring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.learning_flow_validator_v1 import (
    MATERIALIZE_LEARNING_FLOW_VALIDATION_V1,
    VERDICT_INSUFFICIENT,
    VERDICT_LEARNING_CONFIRMED,
    VERDICT_LEARNING_NOT_CONFIRMED,
    build_learning_flow_validation_v1,
    materialize_learning_flow_validation_v1,
    verdict_loop_broken_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_HOLD,
    GOVERNANCE_PROMOTE,
)
from renaissance_v4.game_theory.web_app import create_app

GOV_PROM = {
    "schema": "learning_governance_v1",
    "decision": GOVERNANCE_PROMOTE,
    "reason_codes": [],
    "source_job_id": "x",
    "fingerprint": "ab" * 20,
}
GOV_HOLD = {**GOV_PROM, "decision": GOVERNANCE_HOLD}

TRACE_FULL_A = [
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_a",
        "stage": "memory_retrieval_completed",
        "status": "pass",
        "evidence_payload": {"student_retrieval_matches": 1},
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_a",
        "stage": "student_output_sealed",
        "status": "pass",
        "evidence_payload": {"via": "test"},
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_a",
        "stage": "student_execution_intent_consumed",
        "status": "pass",
        "evidence_payload": {
            "student_execution_intent_digest_v1": "diga",
        },
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_a",
        "stage": "student_controlled_replay_completed",
        "status": "pass",
        "evidence_payload": {"student_outcomes_hash_v1": "hha"},
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_a",
        "stage": "grading_completed",
        "status": "pass",
        "evidence_payload": {"exam_e_score_v1": 0.1},
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_a",
        "stage": "governance_decided",
        "status": "promote",
        "evidence_payload": {"decision": "promote"},
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_a",
        "stage": "learning_record_appended",
        "status": "pass",
        "evidence_payload": {"record_id": "r_a1"},
    },
]

TRACE_B_LINK = [
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_b",
        "stage": "memory_retrieval_completed",
        "status": "pass",
        "evidence_payload": {
            "student_retrieval_matches": 1,
            "source_run_id": "job_a",
        },
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_b",
        "stage": "student_output_sealed",
        "status": "pass",
        "evidence_payload": {},
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_b",
        "stage": "student_execution_intent_consumed",
        "status": "pass",
        "evidence_payload": {
            "student_execution_intent_digest_v1": "digb",
        },
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_b",
        "stage": "student_controlled_replay_completed",
        "status": "pass",
        "evidence_payload": {"student_outcomes_hash_v1": "hhb"},
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_b",
        "stage": "grading_completed",
        "status": "pass",
        "evidence_payload": {"exam_e_score_v1": 0.3},
    },
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_b",
        "stage": "governance_decided",
        "status": "hold",
        "evidence_payload": {"decision": "hold"},
    },
]

MCI = {
    "schema": "memory_context_impact_audit_v1",
    "memory_impact_yes_no": "YES",
    "run_config_fingerprint_sha256_40": "a" * 40,
    "recall_match_windows_total_sum": 0,
}


def _result_row(
    dig: str,
    outcome_hash: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "scenario_id": "s1",
        "student_controlled_replay_v1": {
            "student_execution_intent_digest_v1": dig,
            "outcomes_hash_v1": outcome_hash,
            "student_outcomes_hash_v1": outcome_hash,
        },
    }


def _write_batch(d: Path, dig: str, ohash: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    p = {
        "schema": "batch_parallel_results_v1",
        "results": [_result_row(dig, ohash)],
        "scenario_order": ["s1"],
    }
    (d / "batch_parallel_results_v1.json").write_text(
        json.dumps(p, ensure_ascii=False), encoding="utf-8"
    )


def _base_entry(
    job: str,
    d: Path,
    fp: str,
    e: float,
    retr: int,
) -> dict[str, Any]:
    return {
        "job_id": job,
        "status": "done",
        "session_log_batch_dir": str(d),
        "operator_batch_audit": {
            "context_signature_memory_mode": "read",
        },
        "memory_context_impact_audit_v1": {**MCI, "run_config_fingerprint_sha256_40": "a" * 40},
        "student_retrieval_matches": retr,
        "student_output_fingerprint": fp,
        "exam_e_score_v1": e,
        "exam_p_score_v1": 0.5,
        "student_controlled_replay_ran_v1": 1,
        "student_learning_rows_appended": 1,
    }


@pytest.fixture
def scorecard_and_batches(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    sc = tmp_path / "batch_scorecard.jsonl"
    da = tmp_path / "batch_a"
    db = tmp_path / "batch_b"
    with sc.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                _base_entry("job_a", da, "fp_a", 0.1, 1),
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                _base_entry("job_b", db, "fp_b", 0.2, 1),
            )
            + "\n"
        )
    _write_batch(da, "diga", "hex_a")
    _write_batch(db, "digb", "hex_b")
    return sc, da, db, sc


def _trace_merged(**job_id_to_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {str(k): v for k, v in job_id_to_rows.items()}


def test_pass_a_influences_b(
    scorecard_and_batches: tuple[Path, Path, Path, Path],
    tmp_path: Path,
) -> None:
    sc, _da, _db, _ = scorecard_and_batches
    st = tmp_path / "empty_store.jsonl"
    st.write_text("", encoding="utf-8")
    m = _trace_merged(job_a=TRACE_FULL_A, job_b=TRACE_B_LINK)
    with (
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.read_learning_trace_events_for_job_v1",
            side_effect=lambda jid, path=None, max_lines=500_000: m.get(
                str(jid), []
            ),
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.build_student_panel_run_learning_payload_v1",
            side_effect=lambda jid: {**GOV_PROM, "ok": True, "job_id": jid}
            if str(jid) == "job_a"
            else {**GOV_HOLD, "ok": True, "job_id": jid},
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.list_student_learning_records_by_run_id",
            side_effect=lambda sp, run_id: (
                [
                    {
                        "record_id": "r_a1",
                        "run_id": "job_a",
                        "context_signature_v1": {"signature_key": "k"},
                    }
                ]
                if str(run_id) == "job_a"
                else []
            ),
        ),
    ):
        r = build_learning_flow_validation_v1(
            "job_a",
            "job_b",
            scorecard_path=sc,
            store_path=st,
        )
    assert r.get("verdict_v1") == VERDICT_LEARNING_CONFIRMED


def test_insufficient_data_missing_exam(
    tmp_path: Path,
) -> None:
    sc = tmp_path / "sc.jsonl"
    d = tmp_path / "bdir"
    _write_batch(d, "d1", "h1")
    with sc.open("w", encoding="utf-8") as fh:
        ent = {
            "job_id": "ja",
            "status": "done",
            "session_log_batch_dir": str(d),
            "operator_batch_audit": {"context_signature_memory_mode": "read"},
            "memory_context_impact_audit_v1": MCI,
            "student_retrieval_matches": 1,
            "student_output_fingerprint": "f",
        }
        fh.write(json.dumps(ent) + "\n")
    st = tmp_path / "s.jsonl"
    st.write_text("", encoding="utf-8")
    with (
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.read_learning_trace_events_for_job_v1",
            return_value=[],
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.build_student_panel_run_learning_payload_v1",
            return_value={**GOV_PROM, "ok": True, "job_id": "ja"},
        ),
    ):
        r = build_learning_flow_validation_v1(
            "ja",
            "ja",
            scorecard_path=sc,
            store_path=st,
        )
    # Same job id: still, step 7 NOT_PROVEN without E/P/grading — insufficient for early chain
    assert r.get("verdict_v1") == VERDICT_INSUFFICIENT


def test_not_confirmed_fingerprint_unchanged(
    scorecard_and_batches: tuple[Path, Path, Path, Path],
    tmp_path: Path,
) -> None:
    sc, _da, _db, _ = scorecard_and_batches
    st = tmp_path / "s.jsonl"
    st.write_text("", encoding="utf-8")
    with sc.open("w", encoding="utf-8") as fh:
        ent_b = _base_entry("job_b", _db, "fp_a", 0.2, 1)
        ent_b["student_output_fingerprint"] = "fp_a"  # same as A: no decision change
        fh.write(json.dumps(_base_entry("job_a", _da, "fp_a", 0.1, 1)) + "\n")
        fh.write(json.dumps(ent_b) + "\n")
    m = _trace_merged(job_a=TRACE_FULL_A, job_b=TRACE_B_LINK)
    with (
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.read_learning_trace_events_for_job_v1",
            side_effect=lambda jid, path=None, max_lines=500_000: m.get(
                str(jid), []
            ),
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.build_student_panel_run_learning_payload_v1",
            side_effect=lambda jid: {**GOV_PROM, "ok": True, "job_id": jid}
            if str(jid) == "job_a"
            else {**GOV_HOLD, "ok": True, "job_id": jid},
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.list_student_learning_records_by_run_id",
            side_effect=lambda sp, run_id: (
                [{"record_id": "r1", "run_id": "job_a", "context_signature_v1": {"signature_key": "k"}}]
                if str(run_id) == "job_a"
                else []
            ),
        ),
    ):
        r = build_learning_flow_validation_v1(
            "job_a", "job_b", scorecard_path=sc, store_path=st
        )
    assert r.get("verdict_v1") == VERDICT_LEARNING_NOT_CONFIRMED
    s11 = next(
        x
        for x in (r.get("steps_v1") or [])
        if str(x.get("step_id_v1", "")) == "11_student_decision_changed_v1"
    )
    assert s11.get("status_v1") == "FAIL"


def test_not_confirmed_execution_unchanged(
    scorecard_and_batches: tuple[Path, Path, Path, Path],
    tmp_path: Path,
) -> None:
    sc, _da, _db, _ = scorecard_and_batches
    st = tmp_path / "s.jsonl"
    st.write_text("", encoding="utf-8")
    _write_batch(_db, "diga", "hex_c")
    m = _trace_merged(job_a=TRACE_FULL_A, job_b=TRACE_B_LINK)
    with (
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.read_learning_trace_events_for_job_v1",
            side_effect=lambda jid, path=None, max_lines=500_000: m.get(
                str(jid), []
            ),
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.build_student_panel_run_learning_payload_v1",
            side_effect=lambda jid: {**GOV_PROM, "ok": True, "job_id": jid}
            if str(jid) == "job_a"
            else {**GOV_HOLD, "ok": True, "job_id": jid},
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.list_student_learning_records_by_run_id",
            side_effect=lambda sp, run_id: (
                [{"record_id": "r1", "run_id": "job_a", "context_signature_v1": {"signature_key": "k"}}]
                if str(run_id) == "job_a"
                else []
            ),
        ),
    ):
        r = build_learning_flow_validation_v1(
            "job_a", "job_b", scorecard_path=sc, store_path=st
        )
    assert r.get("verdict_v1") == VERDICT_LEARNING_NOT_CONFIRMED
    s12 = next(
        x
        for x in (r.get("steps_v1") or [])
        if str(x.get("step_id_v1", "")) == "12_execution_changed_v1"
    )
    assert s12.get("status_v1") == "FAIL"


def test_not_confirmed_score_unchanged(
    scorecard_and_batches: tuple[Path, Path, Path, Path],
    tmp_path: Path,
) -> None:
    sc, _da, _db, _ = scorecard_and_batches
    st = tmp_path / "s.jsonl"
    st.write_text("", encoding="utf-8")
    with sc.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_base_entry("job_a", _da, "fp_a", 0.2, 1)) + "\n")
        fh.write(json.dumps(_base_entry("job_b", _db, "fp_b", 0.2, 1)) + "\n")
    m = _trace_merged(job_a=TRACE_FULL_A, job_b=TRACE_B_LINK)
    with (
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.read_learning_trace_events_for_job_v1",
            side_effect=lambda jid, path=None, max_lines=500_000: m.get(
                str(jid), []
            ),
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.build_student_panel_run_learning_payload_v1",
            side_effect=lambda jid: {**GOV_PROM, "ok": True, "job_id": jid}
            if str(jid) == "job_a"
            else {**GOV_HOLD, "ok": True, "job_id": jid},
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.list_student_learning_records_by_run_id",
            side_effect=lambda sp, run_id: (
                [{"record_id": "r1", "run_id": "job_a", "context_signature_v1": {"signature_key": "k"}}]
                if str(run_id) == "job_a"
                else []
            ),
        ),
    ):
        r = build_learning_flow_validation_v1(
            "job_a", "job_b", scorecard_path=sc, store_path=st
        )
    assert r.get("verdict_v1") == VERDICT_LEARNING_NOT_CONFIRMED
    s13 = next(
        x
        for x in (r.get("steps_v1") or [])
        if str(x.get("step_id_v1", "")) == "13_score_changed_v1"
    )
    assert s13.get("status_v1") == "FAIL"


def test_step10_fail_no_memory_on_b(
    scorecard_and_batches: tuple[Path, Path, Path, Path],
    tmp_path: Path,
) -> None:
    sc, _da, _db, _ = scorecard_and_batches
    st = tmp_path / "s.jsonl"
    st.write_text("", encoding="utf-8")
    with sc.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_base_entry("job_a", _da, "fp_a", 0.1, 1)) + "\n")
        eb = _base_entry("job_b", _db, "fp_b", 0.2, 0)
        fh.write(json.dumps(eb) + "\n")
    b_trace = [x for x in TRACE_B_LINK if "memory" not in str(x.get("stage", ""))]
    m = _trace_merged(job_a=TRACE_FULL_A, job_b=b_trace)
    with (
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.read_learning_trace_events_for_job_v1",
            side_effect=lambda jid, path=None, max_lines=500_000: m.get(
                str(jid), []
            ),
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.build_student_panel_run_learning_payload_v1",
            side_effect=lambda jid: {**GOV_PROM, "ok": True, "job_id": jid}
            if str(jid) == "job_a"
            else {**GOV_HOLD, "ok": True, "job_id": jid},
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.list_student_learning_records_by_run_id",
            side_effect=lambda sp, run_id: (
                [{"record_id": "r1", "run_id": "job_a", "context_signature_v1": {"signature_key": "k"}}]
                if str(run_id) == "job_a"
                else []
            ),
        ),
    ):
        r = build_learning_flow_validation_v1(
            "job_a", "job_b", scorecard_path=sc, store_path=st
        )
    assert r.get("verdict_v1") == VERDICT_LEARNING_NOT_CONFIRMED
    s10 = next(
        x
        for x in (r.get("steps_v1") or [])
        if str(x.get("step_id_v1", "")) == "10_memory_retrieved_from_run_A_v1"
    )
    assert s10.get("status_v1") == "FAIL"


def test_run_a_loop_broken_at_step1(
    tmp_path: Path,
) -> None:
    sc = tmp_path / "sc.jsonl"
    d = tmp_path / "bdir"
    d.mkdir()
    p = {
        "schema": "batch_parallel_results_v1",
        "results": [
            {
                "ok": True,
                "scenario_id": "s1",
            }
        ],
    }
    (d / "batch_parallel_results_v1.json").write_text(
        json.dumps(p), encoding="utf-8"
    )
    mci_dry = {
        **MCI,
        "memory_impact_yes_no": "NO",
        "recall_match_windows_total_sum": 0,
    }
    with sc.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "job_id": "jx",
                    "status": "done",
                    "session_log_batch_dir": str(d),
                    "operator_batch_audit": {
                        "context_signature_memory_mode": "read",
                    },
                    "memory_context_impact_audit_v1": mci_dry,
                    "student_retrieval_matches": 0,
                }
            )
            + "\n"
        )
    st = tmp_path / "s.jsonl"
    st.write_text("", encoding="utf-8")
    with (
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.read_learning_trace_events_for_job_v1",
            return_value=[],
        ),
        patch(
            "renaissance_v4.game_theory.learning_flow_validator_v1.build_student_panel_run_learning_payload_v1",
            return_value={**GOV_PROM, "ok": True, "job_id": "jx"},
        ),
    ):
        r = build_learning_flow_validation_v1(
            "jx",
            "jx",
            scorecard_path=sc,
            store_path=st,
        )
    s1 = next(
        x
        for x in (r.get("steps_v1") or [])
        if str(x.get("step_id_v1", "")) == "1_memory_retrieved_v1"
    )
    assert s1.get("status_v1") == "FAIL"
    assert r.get("verdict_v1") == verdict_loop_broken_v1(1)


def test_materialize_confirm(tmp_path: Path) -> None:
    sc = tmp_path / "sc.jsonl"
    d = tmp_path / "b"
    d.mkdir()
    (d / "batch_parallel_results_v1.json").write_text(
        json.dumps(
            {
                "schema": "batch_parallel_results_v1",
                "results": [
                    {
                        "ok": True,
                        "scenario_id": "s1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with sc.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "job_id": "a1",
                    "status": "done",
                    "session_log_batch_dir": str(d),
                    "operator_batch_audit": {
                        "context_signature_memory_mode": "read"
                    },
                    "memory_context_impact_audit_v1": MCI,
                    "student_retrieval_matches": 0,
                }
            )
            + "\n"
        )
    st = tmp_path / "st.jsonl"
    st.write_text("", encoding="utf-8")
    out = materialize_learning_flow_validation_v1(
        run_a="a1",
        run_b="a1",
        scorecard_path=sc,
        store_path=st,
        output_path=tmp_path / "v.json",
        confirm="wrong",
    )
    assert out.get("ok") is False
    out2 = materialize_learning_flow_validation_v1(
        run_a="a1",
        run_b="a1",
        scorecard_path=sc,
        store_path=st,
        output_path=tmp_path / "v.json",
        confirm=MATERIALIZE_LEARNING_FLOW_VALIDATION_V1,
    )
    assert out2.get("ok") is True
    assert (tmp_path / "v.json").is_file()


def test_api_get() -> None:
    app = create_app()
    with patch(
        "renaissance_v4.game_theory.web_app.build_learning_flow_validation_v1"
    ) as m:
        m.return_value = {
            "schema": "learning_flow_validation_v1",
            "verdict_v1": VERDICT_INSUFFICIENT,
            "steps_v1": [],
        }
        c = app.test_client()
        r = c.get("/api/training/learning-flow-validate?run_a=x&run_b=y")
        assert r.status_code == 200
        b = r.get_json()
        assert b.get("ok") is True
        m.assert_called_once()
    c2 = app.test_client()
    r2 = c2.get("/api/training/learning-flow-validate?run_a=")
    assert r2.status_code == 400
