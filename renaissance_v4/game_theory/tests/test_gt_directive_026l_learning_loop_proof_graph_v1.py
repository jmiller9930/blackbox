"""
GT_DIRECTIVE_026L — Learning loop proof graph: verdicts, nodes, materialize, API.

Store rows must pass ``validate_student_learning_record_v1`` (see ``contracts_v1``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.learning_loop_proof_graph_v1 import (
    BP_FINGERPRINT_MISMATCH,
    BP_MEMORY_HAD_NO_EFFECT,
    BP_TIMEFRAME_MISMATCH,
    MATERIALIZE_LEARNING_LOOP_PROOF_V1,
    STATUS_FAIL,
    STATUS_NOT_PROVEN,
    STATUS_PASS,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_LEARNING_CONFIRMED,
    VERDICT_LEARNING_NOT_CONFIRMED,
    _verdict_loop_broken,
    build_learning_loop_proof_graph_v1,
    materialize_learning_loop_proof_graph_v1,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    legal_example_student_learning_record_v1,
)
from renaissance_v4.game_theory.web_app import create_app
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_HOLD,
    GOVERNANCE_PROMOTE,
)

MCI = {
    "schema": "memory_context_impact_audit_v1",
    "memory_impact_yes_no": "YES",
    "run_config_fingerprint_sha256_40": "a" * 40,
    "recall_match_windows_total_sum": 0,
}

DIG64 = "a1" * 32  # 64 hex chars
DIG64_B = "b2" * 32


def _gov(decision: str) -> dict[str, Any]:
    return {
        "schema": "learning_governance_v1",
        "decision": decision,
        "reason_codes": [],
        "source_job_id": "job_a",
        "fingerprint": "ab" * 20,
        "timestamp_utc": "2026-04-20T16:00:00Z",
    }


GOV_PROM = _gov(GOVERNANCE_PROMOTE)
GOV_HOLD = _gov(GOVERNANCE_HOLD)

TRACE_B_RETRIEVAL = [
    {
        "schema": "learning_trace_event_v1",
        "job_id": "job_b",
        "stage": "memory_retrieval_completed",
        "status": "pass",
        "evidence_payload": {
            "student_retrieval_matches": 1,
            "source_run_id": "job_a",
            "source_record_id": "r1",
        },
    },
]


def _batch_payload(dig: str, ohash: str) -> dict[str, Any]:
    return {
        "schema": "batch_parallel_results_v1",
        "results": [
            {
                "ok": True,
                "scenario_id": "s1",
                "student_controlled_replay_v1": {
                    "execution_lane_v1": "student_controlled",
                    "student_execution_intent_digest_v1": dig,
                    "outcomes_hash_v1": ohash,
                },
            }
        ],
        "scenario_order": ["s1"],
    }


def _write_batch(d: Path, dig: str, ohash: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "batch_parallel_results_v1.json").write_text(
        json.dumps(_batch_payload(dig, ohash), ensure_ascii=False),
        encoding="utf-8",
    )


def _base_entry(
    job: str,
    d: Path,
    e: float,
    p: float,
    retr: int,
) -> dict[str, Any]:
    return {
        "job_id": job,
        "status": "done",
        "candle_timeframe_minutes": 5,
        "session_log_batch_dir": str(d),
        "operator_batch_audit": {"context_signature_memory_mode": "read"},
        "memory_context_impact_audit_v1": {**MCI},
        "student_retrieval_matches": retr,
        "exam_e_score_v1": e,
        "exam_p_score_v1": p,
        "execution_authority_v1": "student",
        "student_brain_profile_v1": "memory_context_llm_student",
    }


def _ere(
    action: str,
    *,
    digest: str = DIG64,
    scored: list[dict[str, Any]] | None = None,
    aggregate: str = "aligned",
) -> dict[str, Any]:
    mctx: dict[str, Any] = {
        "schema": "memory_context_eval_v1",
        "aggregate_memory_effect_v1": aggregate,
        "scored_records_v1": scored or [],
    }
    return {
        "schema": "entry_reasoning_eval_v1",
        "entry_reasoning_eval_digest_v1": digest,
        "confidence_01": 0.5,
        "decision_synthesis_v1": {"action": action},
        "memory_context_eval_v1": mctx,
    }


def _learning_row(
    run_id: str,
    rec_id: str,
    *,
    ere: dict[str, Any],
    extra_so: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = legal_example_student_learning_record_v1()
    so = {**base["student_output"], "entry_reasoning_eval_v1": ere}
    if extra_so:
        so.update(extra_so)
    row = {
        **base,
        "run_id": run_id,
        "record_id": rec_id,
        "graded_unit_id": f"gu_{rec_id}_x",
        "student_output": so,
        "context_signature_v1": {"schema": "context_signature_v1", "signature_key": "k"},
    }
    if governance is not None:
        row["learning_governance_v1"] = governance
    return row


def _write_store(path: Path, *lines: dict[str, Any]) -> None:
    path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def scorecard_baseline(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    sc = tmp_path / "sc.jsonl"
    da, db = tmp_path / "ba", tmp_path / "bb"
    _write_batch(da, "diga", "hash_a")
    _write_batch(db, "digb", "hash_b")
    with sc.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_base_entry("job_a", da, 0.1, 0.4, 0)) + "\n")
        fh.write(json.dumps(_base_entry("job_b", db, 0.2, 0.5, 1)) + "\n")
    st = tmp_path / "st.jsonl"
    ere_a = _ere("enter_long", scored=[], aggregate="none")
    # No outcome keys in RSE slices (pre_reveal scan on student_output).
    rse = [{"record_id": "r1", "candle_timeframe_minutes": 5}]
    pkt = {"retrieved_student_experience_v1": rse, "schema": "student_decision_packet_v1"}
    ere_b = _ere(
        "enter_short",
        digest=DIG64_B,
        scored=[
            {
                "record_id": "r1",
                "memory_relevance_score_v1": 0.9,
                "memory_effect_class_v1": "aligned",
            }
        ],
        aggregate="aligned",
    )
    _write_store(
        st,
        _learning_row("job_a", "r1", ere=ere_a, governance=GOV_PROM),
        _learning_row(
            "job_b",
            "r2",
            ere=ere_b,
            extra_so={"student_decision_packet_v1": pkt},
            governance=GOV_PROM,
        ),
    )
    return sc, st, da, db, tmp_path


def _trace_map(**job_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {k: v for k, v in job_rows.items()}


def test_confirmed_learning_chain(
    scorecard_baseline: tuple[Path, Path, Path, Path, Path],
) -> None:
    sc, st, _da, _db, _root = scorecard_baseline
    m = _trace_map(job_b=TRACE_B_RETRIEVAL)
    with patch(
        "renaissance_v4.game_theory.learning_loop_proof_graph_v1.read_learning_trace_events_for_job_v1",
        side_effect=lambda jid, path=None, max_lines=500_000: m.get(str(jid), []),
    ):
        g = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st)
    assert g["final_verdict_v1"] == VERDICT_LEARNING_CONFIRMED
    assert any(
        n["node_id"] == "node_17_learning_feedback_loop_closed_v1" and n["status"] == STATUS_PASS
        for n in g["nodes_v1"]
    )


def test_missing_run_a_line_insufficient() -> None:
    p = Path("/__no_such_dir__/missing_scorecard.jsonl")
    g = build_learning_loop_proof_graph_v1("ja", "jb", scorecard_path=p, store_path=Path("/__bad__/s.jsonl"))
    assert g["final_verdict_v1"] in (
        VERDICT_INSUFFICIENT_DATA,
        _verdict_loop_broken("node_01_run_a_completed_v1"),
    )


def test_run_a_reasoning_missing(tmp_path: Path) -> None:
    sc, da = tmp_path / "s.jsonl", tmp_path / "ba"
    _write_batch(da, "a", "h")
    e = {**_base_entry("ja", da, 0.1, 0.1, 0), "session_log_batch_dir": str(da)}
    sc.write_text(json.dumps(e) + "\n", encoding="utf-8")
    st = tmp_path / "st.jsonl"
    bad_ere = {"schema": "not_entry", "entry_reasoning_eval_digest_v1": DIG64}
    _write_store(st, _learning_row("ja", "r0", ere=bad_ere, governance=GOV_PROM))
    g = build_learning_loop_proof_graph_v1("ja", "ja", scorecard_path=sc, store_path=st)
    n2 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_02_run_a_student_reasoning_exists_v1")
    assert n2["status"] == STATUS_FAIL


def test_run_a_no_student_execution(tmp_path: Path) -> None:
    sc, da = tmp_path / "s.jsonl", tmp_path / "ba"
    _write_batch(da, "a", "h")
    e = {
        **_base_entry("ja", da, 0.1, 0.1, 0),
        "execution_authority_v1": "baseline_control",
        "session_log_batch_dir": str(da),
    }
    e["student_brain_profile_v1"] = "baseline_no_memory_no_llm"
    sc.write_text(json.dumps(e) + "\n", encoding="utf-8")
    st = tmp_path / "st.jsonl"
    _write_store(st, _learning_row("ja", "r0", ere=_ere("enter_long", scored=[]), governance=GOV_PROM))
    g = build_learning_loop_proof_graph_v1("ja", "ja", scorecard_path=sc, store_path=st)
    n3 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_03_run_a_student_execution_exists_v1")
    assert n3["status"] == STATUS_FAIL


def test_empty_store_fails_node_02(tmp_path: Path) -> None:
    sc, da = tmp_path / "s.jsonl", tmp_path / "ba"
    _write_batch(da, "d", "h")
    sc.write_text(json.dumps(_base_entry("ja", da, 0.1, 0.1, 0)) + "\n", encoding="utf-8")
    st = tmp_path / "st.jsonl"
    st.write_text("", encoding="utf-8")
    g = build_learning_loop_proof_graph_v1("ja", "ja", scorecard_path=sc, store_path=st)
    n2 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_02_run_a_student_reasoning_exists_v1")
    assert n2["status"] == STATUS_FAIL


def test_governance_hold_not_confirmed(tmp_path: Path) -> None:
    sc, da, db = tmp_path / "s.jsonl", tmp_path / "b1", tmp_path / "b2"
    _write_batch(da, "a", "h1")
    _write_batch(db, "b", "h2")
    sc.write_text(
        json.dumps(_base_entry("job_a", da, 0.1, 0.1, 0)) + "\n"
        + json.dumps(_base_entry("job_b", db, 0.2, 0.2, 1)) + "\n",
        encoding="utf-8",
    )
    st = tmp_path / "st.jsonl"
    _write_store(st, _learning_row("job_a", "r1", ere=_ere("enter_long", scored=[]), governance=GOV_HOLD))
    g = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st)
    assert g["final_verdict_v1"] == VERDICT_LEARNING_NOT_CONFIRMED


def test_run_b_retrieval_not_proven(
    scorecard_baseline: tuple[Path, Path, Path, Path, Path],
) -> None:
    sc, st, _da, _db, _ = scorecard_baseline
    lines = st.read_text(encoding="utf-8").strip().split("\n")
    b = json.loads(lines[1])
    b["student_output"]["entry_reasoning_eval_v1"]["memory_context_eval_v1"]["scored_records_v1"] = [
        {"record_id": "r_wrong", "memory_relevance_score_v1": 0.1, "memory_effect_class_v1": "ignore"}
    ]
    st.write_text(lines[0] + "\n" + json.dumps(b) + "\n", encoding="utf-8")
    g = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st, baseline_job_id=None)
    n10 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_10_run_b_retrieved_run_a_memory_v1")
    assert n10["status"] in (STATUS_FAIL, STATUS_NOT_PROVEN)
    with patch(
        "renaissance_v4.game_theory.learning_loop_proof_graph_v1.read_learning_trace_events_for_job_v1",
        return_value=[],
    ):
        g2 = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st)
    assert g2["final_verdict_v1"] in (
        VERDICT_LEARNING_NOT_CONFIRMED,
        _verdict_loop_broken("node_10_run_b_retrieved_run_a_memory_v1"),
    )


def test_memory_in_packet_fails(
    scorecard_baseline: tuple[Path, Path, Path, Path, Path],
) -> None:
    sc, st, _da, _db, _ = scorecard_baseline
    lines = st.read_text(encoding="utf-8").strip().split("\n")
    b = json.loads(lines[1])
    b["student_output"]["student_decision_packet_v1"] = {
        "schema": "student_decision_packet_v1",
        "retrieved_student_experience_v1": [{"record_id": "wrong_id", "candle_timeframe_minutes": 5}],
    }
    st.write_text(lines[0] + "\n" + json.dumps(b) + "\n", encoding="utf-8")
    g = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st)
    n11 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_11_memory_reached_student_packet_v1")
    assert n11["status"] == STATUS_FAIL


def test_no_memory_effect_not_confirmed(tmp_path: Path) -> None:
    sc, da, db = tmp_path / "s.jsonl", tmp_path / "b1", tmp_path / "b2"
    _write_batch(da, "a", "h1")
    _write_batch(db, "b", "h2")
    sc.write_text(
        json.dumps(_base_entry("job_a", da, 0.1, 0.1, 0)) + "\n"
        + json.dumps(_base_entry("job_b", db, 0.2, 0.2, 1)) + "\n",
        encoding="utf-8",
    )
    st = tmp_path / "st.jsonl"
    ere_a = _ere("enter_long", scored=[])
    ere_b = _ere(
        "enter_long",
        scored=[
            {
                "record_id": "r1",
                "memory_relevance_score_v1": 0.1,
                "memory_effect_class_v1": "ignore",
            }
        ],
        aggregate="none",
    )
    rse = [{"record_id": "r1", "candle_timeframe_minutes": 5}]
    _write_store(
        st,
        _learning_row("job_a", "r1", ere=ere_a, governance=GOV_PROM),
        _learning_row(
            "job_b",
            "r2",
            ere=ere_b,
            extra_so={
                "student_decision_packet_v1": {
                    "schema": "student_decision_packet_v1",
                    "retrieved_student_experience_v1": rse,
                }
            },
            governance=GOV_PROM,
        ),
    )
    m = _trace_map(job_b=TRACE_B_RETRIEVAL)
    with patch(
        "renaissance_v4.game_theory.learning_loop_proof_graph_v1.read_learning_trace_events_for_job_v1",
        side_effect=lambda jid, path=None, max_lines=500_000: m.get(str(jid), []),
    ):
        g = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st)
    assert g["final_verdict_v1"] == VERDICT_LEARNING_NOT_CONFIRMED
    assert BP_MEMORY_HAD_NO_EFFECT in (g.get("breakpoints_v1") or [])


def test_timeframe_mismatch_fails_n9(tmp_path: Path) -> None:
    sc, da, db = tmp_path / "s.jsonl", tmp_path / "b1", tmp_path / "b2"
    _write_batch(da, "a", "h1")
    _write_batch(db, "b", "h2")
    a = _base_entry("job_a", da, 0.1, 0.1, 0)
    b = {**_base_entry("job_b", db, 0.2, 0.2, 0), "candle_timeframe_minutes": 15}
    sc.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n", encoding="utf-8")
    st = tmp_path / "st.jsonl"
    _write_store(st, _learning_row("job_a", "r1", ere=_ere("enter_long", scored=[]), governance=GOV_PROM))
    g = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st)
    n9 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_09_run_b_completed_v1")
    assert n9["status"] == STATUS_FAIL
    assert BP_TIMEFRAME_MISMATCH in g["breakpoints_v1"]


def test_fingerprint_mismatch_fails_n9(tmp_path: Path) -> None:
    sc, da, db = tmp_path / "s.jsonl", tmp_path / "b1", tmp_path / "b2"
    _write_batch(da, "a", "h1")
    _write_batch(db, "b", "h2")
    a = {**_base_entry("job_a", da, 0.1, 0.1, 0)}
    a["memory_context_impact_audit_v1"] = {**MCI, "run_config_fingerprint_sha256_40": "a" * 40}
    b = {**_base_entry("job_b", db, 0.2, 0.2, 0)}
    b["memory_context_impact_audit_v1"] = {**MCI, "run_config_fingerprint_sha256_40": "b" * 40}
    sc.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n", encoding="utf-8")
    st = tmp_path / "st.jsonl"
    _write_store(st, _learning_row("job_a", "r1", ere=_ere("enter_long", scored=[]), governance=GOV_PROM))
    g = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st)
    n9 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_09_run_b_completed_v1")
    assert n9["status"] == STATUS_FAIL
    assert BP_FINGERPRINT_MISMATCH in g["breakpoints_v1"]


def test_decision_change_execution_unchanged_not_confirmed(
    scorecard_baseline: tuple[Path, Path, Path, Path, Path],
) -> None:
    sc, st, _da, db, _ = scorecard_baseline
    # Same batch digest+outcomes hash and same L1 E/P as Run A → execution+score not changed; decision still differs in store.
    _write_batch(db, "diga", "hash_a")
    lines = sc.read_text(encoding="utf-8").strip().split("\n")
    job_b = json.loads(lines[1])
    job_b["exam_e_score_v1"] = 0.1
    job_b["exam_p_score_v1"] = 0.4
    sc.write_text(lines[0] + "\n" + json.dumps(job_b) + "\n", encoding="utf-8")
    m = _trace_map(job_b=TRACE_B_RETRIEVAL)
    with patch(
        "renaissance_v4.game_theory.learning_loop_proof_graph_v1.read_learning_trace_events_for_job_v1",
        side_effect=lambda jid, path=None, max_lines=500_000: m.get(str(jid), []),
    ):
        g = build_learning_loop_proof_graph_v1("job_a", "job_b", scorecard_path=sc, store_path=st)
    assert g["final_verdict_v1"] == VERDICT_LEARNING_NOT_CONFIRMED
    n15 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_15_execution_comparison_v1")
    assert n15["status"] == STATUS_FAIL
    n16 = next(n for n in g["nodes_v1"] if n["node_id"] == "node_16_score_comparison_v1")
    assert n16["status"] == STATUS_FAIL


def test_materialize_writes_file(tmp_path: Path) -> None:
    sc, da = tmp_path / "s.jsonl", tmp_path / "b"
    _write_batch(da, "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2", "h1")
    sc.write_text(json.dumps(_base_entry("ja", da, 0.1, 0.1, 0)) + "\n", encoding="utf-8")
    st = tmp_path / "st.jsonl"
    _write_store(st, _learning_row("ja", "r0", ere=_ere("enter_long", scored=[]), governance=GOV_PROM))
    outp = tmp_path / "out.json"
    o = materialize_learning_loop_proof_graph_v1(
        run_a="ja",
        run_b="ja",
        scorecard_path=sc,
        store_path=st,
        output_path=outp,
        confirm=MATERIALIZE_LEARNING_LOOP_PROOF_V1,
    )
    assert o.get("ok") is True
    assert outp.is_file()
    body = json.loads(outp.read_text(encoding="utf-8"))
    assert body.get("learning_loop_proof_graph_v1", {}).get("schema") == "learning_loop_proof_graph_v1"


def test_api_get_returns_graph(scorecard_baseline: tuple[Path, Path, Path, Path, Path]) -> None:
    sc, st, _a, _b, _r = scorecard_baseline
    app = create_app()
    m = _trace_map(job_b=TRACE_B_RETRIEVAL)
    with patch("renaissance_v4.game_theory.web_app.student_learning_store_status_v1", return_value={"path": str(st)}), patch(
        "renaissance_v4.game_theory.learning_loop_proof_graph_v1.find_scorecard_entry_by_job_id",
        side_effect=lambda job_id, path=None: _read_sc_line(sc, str(job_id)),
    ), patch(
        "renaissance_v4.game_theory.learning_flow_validator_v1.find_scorecard_entry_by_job_id",
        side_effect=lambda job_id, path=None: _read_sc_line(sc, str(job_id)),
    ), patch(
        "renaissance_v4.game_theory.learning_loop_proof_graph_v1.read_learning_trace_events_for_job_v1",
        side_effect=lambda jid, path=None, max_lines=500_000: m.get(str(jid), []),
    ), patch("renaissance_v4.game_theory.memory_paths.default_batch_scorecard_jsonl", return_value=sc):
        c = app.test_client()
        r = c.get("/api/training/learning-loop-proof?run_a=job_a&run_b=job_b")
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    assert j.get("learning_loop_proof_graph_v1", {}).get("schema") == "learning_loop_proof_graph_v1"


def _read_sc_line(sc: Path, job_id: str) -> dict[str, Any] | None:
    for ln in sc.read_text(encoding="utf-8").splitlines():
        d = json.loads(ln)
        if d.get("job_id") == job_id:
            return d
    return None