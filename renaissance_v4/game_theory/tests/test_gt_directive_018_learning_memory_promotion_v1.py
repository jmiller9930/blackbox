"""GT_DIRECTIVE_018 — memory promotion (promote/hold/reject), retrieval eligibility, run learning API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
    build_student_decision_packet_v1_with_cross_run_retrieval,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_HOLD,
    GOVERNANCE_PROMOTE,
    GOVERNANCE_REJECT,
    aggregate_run_memory_decision_v1,
    build_learning_governance_v1,
    build_student_panel_run_learning_payload_v1,
    classify_trade_memory_promotion_v1,
    memory_retrieval_eligible_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    list_student_learning_records_by_signature_key,
)
from renaissance_v4.game_theory.tests.test_cross_run_retrieval_v1 import _learning_row
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db
from renaissance_v4.game_theory.web_app import create_app


def _row_with_gov(row: dict, *, decision: str) -> dict:
    out = dict(row)
    out["learning_governance_v1"] = build_learning_governance_v1(
        decision=decision,
        reason_codes=[f"test_{decision}_v1"],
        source_job_id=str(out.get("run_id") or "run_x"),
        fingerprint="f" * 40,
    )
    return out


def test_classify_reject_on_critical_gap() -> None:
    l3: dict = {
        "ok": True,
        "job_id": "job_r1",
        "data_gaps": [{"severity": "critical", "reason": "batch_parallel_results_v1_missing"}],
        "decision_record_v1": {},
    }
    d, _, gov = classify_trade_memory_promotion_v1(
        l3_payload=l3, scorecard_entry={"job_id": "job_r1", "expectancy_per_trade": 1.0}
    )
    assert d == GOVERNANCE_REJECT
    assert gov.get("decision") == GOVERNANCE_REJECT


def test_classify_reject_llm_pre_seal_gap() -> None:
    l3: dict = {
        "ok": True,
        "job_id": "job_r2",
        "data_gaps": [{"severity": "warning", "reason": "llm_student_output_rejected_pre_seal_v1"}],
        "decision_record_v1": {},
    }
    d, _, _ = classify_trade_memory_promotion_v1(
        l3_payload=l3, scorecard_entry={"job_id": "job_r2", "expectancy_per_trade": 1.0}
    )
    assert d == GOVERNANCE_REJECT


def test_classify_reject_llm_thesis_gap() -> None:
    l3: dict = {
        "ok": True,
        "job_id": "job_r3",
        "data_gaps": [
            {"severity": "critical", "reason": "student_directional_thesis_store_missing_for_llm_profile_v1"}
        ],
        "decision_record_v1": {},
    }
    d, _, _ = classify_trade_memory_promotion_v1(
        l3_payload=l3, scorecard_entry={"job_id": "job_r3", "expectancy_per_trade": 1.0}
    )
    assert d == GOVERNANCE_REJECT


def test_classify_hold_weak_expectancy() -> None:
    l3: dict = {"ok": True, "job_id": "job_h1", "data_gaps": [], "decision_record_v1": {}}
    d, _, gov = classify_trade_memory_promotion_v1(
        l3_payload=l3, scorecard_entry={"job_id": "job_h1", "expectancy_per_trade": -0.01, "total_processed": 5}
    )
    assert d == GOVERNANCE_HOLD
    assert "hold_weak_expectancy_v1" in (gov.get("reason_codes") or [])


def test_classify_promote_clean_l3_positive_e() -> None:
    l3: dict = {"ok": True, "job_id": "job_p1", "data_gaps": [], "decision_record_v1": {}}
    d, codes, gov = classify_trade_memory_promotion_v1(
        l3_payload=l3,
        scorecard_entry={"job_id": "job_p1", "expectancy_per_trade": 0.25, "total_processed": 3},
    )
    assert d == GOVERNANCE_PROMOTE
    assert "promote_clean_l3_positive_economics_v1" in codes
    assert gov.get("decision") == GOVERNANCE_PROMOTE


def test_aggregate_run_decision_order() -> None:
    assert aggregate_run_memory_decision_v1([]) == GOVERNANCE_HOLD
    assert aggregate_run_memory_decision_v1([GOVERNANCE_PROMOTE, GOVERNANCE_HOLD]) == GOVERNANCE_HOLD
    assert aggregate_run_memory_decision_v1([GOVERNANCE_PROMOTE, GOVERNANCE_REJECT]) == GOVERNANCE_REJECT


def test_memory_retrieval_eligible_v1() -> None:
    assert memory_retrieval_eligible_v1({}) is True
    assert memory_retrieval_eligible_v1({"learning_governance_v1": {"decision": "promote"}}) is True
    assert memory_retrieval_eligible_v1({"learning_governance_v1": {"decision": "hold"}}) is False
    assert memory_retrieval_eligible_v1({"learning_governance_v1": {"decision": "reject"}}) is False


def test_retrieval_skips_hold_rows(tmp_path: Path) -> None:
    store = tmp_path / "r.jsonl"
    sig = "sig_ret_gov"
    a = _learning_row(rid="r_prom", run_id="run_a", sig=sig, trade="t1")
    b = _learning_row(rid="r_hold", run_id="run_b", sig=sig, trade="t2")
    b = _row_with_gov(b, decision=GOVERNANCE_HOLD)
    append_student_learning_record_v1(store, a)
    append_student_learning_record_v1(store, b)
    eligible = list_student_learning_records_by_signature_key(store, sig, retrieval_eligible_only=True)
    assert len(eligible) == 1
    assert eligible[0].get("record_id") == "r_prom"
    all_rows = list_student_learning_records_by_signature_key(store, sig, retrieval_eligible_only=False)
    assert len(all_rows) == 2


def test_cross_run_packet_uses_retrieval_governance(tmp_path: Path) -> None:
    store = tmp_path / "pkt.jsonl"
    sig = "sig_pkt_gov"
    a = _learning_row(rid="r_a", run_id="run_a", sig=sig, trade="ta")
    b = _row_with_gov(_learning_row(rid="r_b", run_id="run_b", sig=sig, trade="tb"), decision=GOVERNANCE_HOLD)
    append_student_learning_record_v1(store, a)
    append_student_learning_record_v1(store, b)
    db = tmp_path / "p.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=5_000_000,
        store_path=store,
        retrieval_signature_key=sig,
        max_retrieval_slices=8,
    )
    assert err is None and pkt is not None
    rx = pkt[FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1]
    assert len(rx) == 1
    assert rx[0].get("source_record_id") == "r_a"


@pytest.fixture
def flask_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_http_run_learning_200(flask_client) -> None:
    with patch(
        "renaissance_v4.game_theory.web_app.build_student_panel_run_learning_payload_v1",
        return_value={
            "schema": "student_panel_run_learning_payload_v1",
            "ok": True,
            "job_id": "jx",
            "learning_governance_v1": build_learning_governance_v1(
                decision=GOVERNANCE_PROMOTE,
                reason_codes=["x"],
                source_job_id="jx",
                fingerprint=None,
            ),
            "run_was_stored": True,
            "eligible_for_retrieval": True,
            "per_trade": [],
            "stored_record_count_v1": 1,
        },
    ):
        r = flask_client.get("/api/student-panel/run/jx/learning")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("learning_governance_v1", {}).get("decision") == GOVERNANCE_PROMOTE
    assert body.get("run_was_stored") is True
    assert body.get("eligible_for_retrieval") is True
