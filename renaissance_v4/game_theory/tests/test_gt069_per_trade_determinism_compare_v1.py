"""GT069 per-trade determinism compare — synthetic trace exercises."""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.game_theory.learning_trace_events_v1 import build_learning_trace_event_v1
from renaissance_v4.game_theory.tools.gt069_per_trade_determinism_compare_v1 import (
    build_gt069_compare_report_v1,
)


def _emit_line(
    path: Path,
    *,
    job_id: str,
    stage: str,
    scenario_id: str,
    trade_id: str,
    evidence_payload: dict | None = None,
) -> None:
    ev = build_learning_trace_event_v1(
        job_id=job_id,
        fingerprint=None,
        stage=stage,
        status="pass",
        summary="test",
        producer="test",
        scenario_id=scenario_id,
        trade_id=trade_id,
        evidence_payload=evidence_payload or {},
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n")


def _base_trade_trace(path: Path, job_id: str, digest: str, action: str, llm_rounds: int) -> None:
    sid, tid = "scen1", "tr42"
    _emit_line(
        path,
        job_id=job_id,
        stage="entry_reasoning_sealed_v1",
        scenario_id=sid,
        trade_id=tid,
        evidence_payload={
            "entry_reasoning_stage": "entry_reasoning_sealed_v1",
            "outputs": {"sealed": True, "entry_reasoning_eval_digest_v1": digest},
            "inputs": {},
            "evidence": {},
        },
    )
    _emit_line(
        path,
        job_id=job_id,
        stage="memory_retrieval_completed",
        scenario_id=sid,
        trade_id=tid,
        evidence_payload={"student_retrieval_matches": 2},
    )
    _emit_line(
        path,
        job_id=job_id,
        stage="student_llm_contract_resolution_v1",
        scenario_id=sid,
        trade_id=tid,
        evidence_payload={
            "json_repair_attempted_v1": False,
            "validation_repair_attempted_v1": False,
            "json_contract_retry_used_v1": False,
            "ollama_chat_rounds_v1": llm_rounds,
            "student_llm_contract_repair_path_v1": False,
            "final_validation_accepted_v1": True,
        },
    )
    _emit_line(
        path,
        job_id=job_id,
        stage="student_output_sealed",
        scenario_id=sid,
        trade_id=tid,
        evidence_payload={"via": "ollama", "student_action_v1_echo": action},
    )


def test_gt069_digest_mismatch_flags_rm_or_retrieval(tmp_path: Path) -> None:
    p = tmp_path / "trace.jsonl"
    _base_trade_trace(p, "runA", digest="a" * 64, action="enter_long", llm_rounds=1)
    _base_trade_trace(p, "runB", digest="b" * 64, action="enter_long", llm_rounds=1)
    rep = build_gt069_compare_report_v1("runA", "runB", trace_path=p, store_path=None)
    assert rep["intersection_trade_keys_v1"] == 1
    row = rep["per_trade_v1"][0]
    assert row["drift_classification_v1"] == "rm_or_retrieval"
    assert row["entry_reasoning_eval_digest_v1"]["match_v1"] is False


def test_gt069_digest_match_action_mismatch_flags_llm_seam(tmp_path: Path) -> None:
    p = tmp_path / "trace.jsonl"
    d = "c" * 64
    _base_trade_trace(p, "runA", digest=d, action="enter_long", llm_rounds=1)
    _base_trade_trace(p, "runB", digest=d, action="no_trade", llm_rounds=1)
    rep = build_gt069_compare_report_v1("runA", "runB", trace_path=p, store_path=None)
    assert rep["per_trade_v1"][0]["drift_classification_v1"] == "llm_seam"
    assert rep["summary_v1"]["drift_llm_seam_count_v1"] == 1


def test_gt069_identical_runs_none(tmp_path: Path) -> None:
    p = tmp_path / "trace.jsonl"
    d = "d" * 64
    _base_trade_trace(p, "runA", digest=d, action="enter_short", llm_rounds=2)
    _base_trade_trace(p, "runB", digest=d, action="enter_short", llm_rounds=2)
    rep = build_gt069_compare_report_v1("runA", "runB", trace_path=p, store_path=None)
    assert rep["per_trade_v1"][0]["drift_classification_v1"] == "none"
    assert rep["summary_v1"]["drift_none_count_v1"] == 1
