# GT_DIRECTIVE_026C — deterministic lifecycle learning (scoring, store, retrieval)

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.lifecycle_deterministic_learning_026c_v1 import (
    SCHEMA_LIFECYCLE_DETERMINISTIC_LEARNING_RECORD_026C,
    append_lifecycle_deterministic_learning_record_026c_v1,
    build_lifecycle_learning_record_026c_v1,
    compute_attribution_breakdown_026c_v1,
    compute_decision_quality_score_026c_v1,
    merge_026c_deterministic_learning_fault_nodes_v1,
    retrieve_applicable_learning_context_026c_v1,
)


def _outcome(pnl: float, exit_code: str = "target_r_multiple_hit_v1") -> OutcomeRecord:
    return OutcomeRecord(
        trade_id="t1",
        symbol="BTC",
        direction="long",
        entry_time=1_700_000_000_000,
        exit_time=1_700_000_100_000,
        entry_price=100.0,
        exit_price=110.0,
        pnl=pnl,
        mae=0.0,
        mfe=0.1,
        exit_reason=exit_code,
    )


def _target_tape(n_bars: int = 3) -> dict:
    """Minimal closed tape: target exit → high scores."""
    rows: list[dict] = []
    for i in range(n_bars):
        ev = {
            "decision_v1": "hold" if i < n_bars - 1 else "exit",
            "exit_reason_code_v1": "target_r_multiple_hit_v1" if i == n_bars - 1 else "none_v1",
        }
        rows.append(
            {
                "bar_index": 10 + i,
                "lifecycle_reasoning_eval_v1": ev,
            }
        )
    return {
        "schema": "lifecycle_tape_result_v1",
        "closed_v1": True,
        "exit_at_bar_index_v1": 10 + n_bars - 1,
        "exit_reason_code_v1": "target_r_multiple_hit_v1",
        "per_bar_v1": rows,
    }


@pytest.fixture
def store_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "l.jsonl"
    monkeypatch.setenv("PATTERN_GAME_LIFECYCLE_DETERMINISTIC_LEARNING_026C_STORE", str(p))
    return p


def _minimal_ere() -> dict:
    return {
        "entry_thesis_v1": {
            "thesis_text_v1": "continuation",
        },
    }


def test_attribution_sums_including_luck() -> None:
    s = {
        "entry_score_01": 0.6,
        "hold_score_01": 0.6,
        "exit_score_01": 0.6,
    }
    a = compute_attribution_breakdown_026c_v1(s)
    t = (
        a["entry_contribution_01"]
        + a["hold_contribution_01"]
        + a["exit_contribution_01"]
        + a["luck_contribution_01"]
    )
    assert abs(t - 1.0) < 1e-4


def test_losing_trade_rejects(store_path: Path) -> None:
    tape = _target_tape()
    o = _outcome(pnl=-1.0)
    rec = build_lifecycle_learning_record_026c_v1(
        tape=tape,
        entry_reasoning_eval_v1=_minimal_ere(),
        outcome=o,
        trade_id="a",
        symbol="BTC",
        candle_timeframe_minutes=5,
        job_id="j1",
        context_signature_key="k1",
    )
    assert rec is not None
    assert rec["learning_decision_v1"]["outcome_v1"] == "reject_pattern_v1"
    append_lifecycle_deterministic_learning_record_026c_v1(store_path, rec)
    data = store_path.read_text(encoding="utf-8")
    assert SCHEMA_LIFECYCLE_DETERMINISTIC_LEARNING_RECORD_026C in data


def test_mixed_or_insufficient_data(store_path: Path) -> None:
    # scores high but pnl>0, prior_n<2 -> insufficient
    tape = _target_tape()
    o = _outcome(pnl=1.0)
    with patch(
        "renaissance_v4.game_theory.student_proctor."
        "lifecycle_deterministic_learning_026c_v1."
        "count_pattern_key_occurrences_026c_v1",
        return_value=1,
    ):
        rec = build_lifecycle_learning_record_026c_v1(
            tape=tape,
            entry_reasoning_eval_v1=_minimal_ere(),
            outcome=o,
            trade_id="b",
            symbol="BTC",
            candle_timeframe_minutes=5,
            job_id="j1",
            context_signature_key="k1",
        )
    assert rec is not None
    assert rec["learning_decision_v1"]["outcome_v1"] == "insufficient_data_v1"


def _promotable_record(**kwargs) -> dict:
    base = {
        "schema": SCHEMA_LIFECYCLE_DETERMINISTIC_LEARNING_RECORD_026C,
        "contract_version": 1,
        "decision_quality_score_v1": {"overall_score_v1": 0.9},
        "learning_decision_v1": {"outcome_v1": "promote_pattern_v1"},
    }
    base.update(kwargs)
    return base


def test_winning_trade_high_score_promotion_after_warmup(store_path: Path) -> None:
    # Same pattern two prior lines (any outcome); third close with good scores → promote
    sk = "sigA"
    sym = "BTC"
    tf = 5
    ex = "target_r_multiple_hit_v1"
    pk = f"{sym}:{tf}:long:{ex}"[:256]
    for i in range(2):
        append_lifecycle_deterministic_learning_record_026c_v1(
            store_path,
            _promotable_record(
                record_id_026c=f"w{i}",
                created_utc_026c="2020-01-01T00:00:00Z",
                job_id_v1="old",
                trade_id_v1=f"t{i}",
                symbol_v1=sym,
                timeframe_v1=tf,
                context_signature_key_v1=sk,
                pattern_key_026c_v1=pk,
            ),
        )
    tape = _target_tape()
    o = _outcome(1.0)
    with patch.dict(os.environ, {"PATTERN_GAME_LIFECYCLE_DETERMINISTIC_LEARNING_026C_STORE": str(store_path)}):
        rec = build_lifecycle_learning_record_026c_v1(
            tape=tape,
            entry_reasoning_eval_v1=_minimal_ere(),
            outcome=o,
            trade_id="t_final",
            symbol=sym,
            candle_timeframe_minutes=tf,
            job_id="jnew",
            context_signature_key=sk,
        )
    assert rec is not None
    sc = rec["decision_quality_score_v1"]
    assert float(sc["overall_score_v1"]) >= 0.72
    d = rec["learning_decision_v1"]
    assert d["outcome_v1"] == "promote_pattern_v1", d


def test_retrieve_only_past_and_promoted(store_path: Path) -> None:
    sk = "s1"
    # Decision "now" in 2020: include 2020 line, exclude 2030 line (strictly prior to decision).
    now_ms = 1_600_000_000_000
    future = (datetime(2030, 1, 1, tzinfo=timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    past = (datetime(2020, 1, 1, tzinfo=timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for rid, tsc, out in [("a", past, "promote_pattern_v1"), ("b", future, "promote_pattern_v1")]:
        r = _promotable_record(
            record_id_026c=rid,
            created_utc_026c=tsc,
            job_id_v1=rid,
            symbol_v1="ETH",
            timeframe_v1=5,
            context_signature_key_v1=sk,
        )
        r["pattern_key_026c_v1"] = "ETH:5:long:x"
        r["learning_decision_v1"] = {"outcome_v1": out}
        append_lifecycle_deterministic_learning_record_026c_v1(store_path, r)
    with patch.dict(os.environ, {"PATTERN_GAME_LIFECYCLE_DETERMINISTIC_LEARNING_026C_STORE": str(store_path)}):
        out = retrieve_applicable_learning_context_026c_v1(
            symbol="ETH",
            candle_timeframe_minutes=5,
            context_signature_key=sk,
            decision_open_time_ms=now_ms,
        )
    ids = {x.get("record_id_026c") for x in out}
    assert "a" in ids
    assert "b" not in ids


def test_conflict_resolution_prefers_better_pattern(store_path: Path) -> None:
    sk = "c1"
    sym = "SOL"
    tf = 5
    p_low = f"{sym}:{tf}:long:low_v1"
    p_high = f"{sym}:{tf}:long:target_r_multiple_hit_v1"
    for i in range(3):
        r = _promotable_record(
            record_id_026c=f"low_{i}",
            created_utc_026c="2019-01-01T00:00:00Z",
            symbol_v1=sym,
            timeframe_v1=tf,
            context_signature_key_v1=sk,
            pattern_key_026c_v1=p_low,
        )
        r["decision_quality_score_v1"] = {"overall_score_v1": 0.4}
        append_lifecycle_deterministic_learning_record_026c_v1(store_path, r)
    h = _promotable_record(
        record_id_026c="hi1",
        created_utc_026c="2019-06-01T00:00:00Z",
        symbol_v1=sym,
        timeframe_v1=tf,
        context_signature_key_v1=sk,
        pattern_key_026c_v1=p_high,
    )
    h["decision_quality_score_v1"] = {"overall_score_v1": 0.99}
    append_lifecycle_deterministic_learning_record_026c_v1(store_path, h)
    with patch.dict(os.environ, {"PATTERN_GAME_LIFECYCLE_DETERMINISTIC_LEARNING_026C_STORE": str(store_path)}):
        res = retrieve_applicable_learning_context_026c_v1(
            symbol=sym,
            candle_timeframe_minutes=tf,
            context_signature_key=sk,
            decision_open_time_ms=2_000_000_000_000,
        )
    assert res
    assert res[0].get("conflict_resolved_v1")


def test_decay_reduces_weight() -> None:
    from renaissance_v4.game_theory.student_proctor import lifecycle_deterministic_learning_026c_v1 as m

    w_fresh = m._decay_weight_01_v1(
        (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    w_old = m._decay_weight_01_v1("2000-01-01T00:00:00Z")
    assert w_old < w_fresh


def test_merge_026c_fault_map_nodes() -> None:
    base = merge_026c_deterministic_learning_fault_nodes_v1(
        {"schema": "student_reasoning_fault_map_v1", "contract_version": 1, "nodes_v1": []},
        record_ok=True,
        scoring_ok=True,
        decision_ok=True,
        retrieval_in_path=False,
    )
    by = {n["node_id"]: n["status"] for n in (base.get("nodes_v1") or [])}
    assert by.get("learning_record_created") == "PASS"
    assert by.get("learning_scoring_evaluated") == "PASS"
    assert by.get("learning_promotion_decision") == "PASS"


def test_scoring_is_deterministic() -> None:
    t = _target_tape()
    s1 = compute_decision_quality_score_026c_v1(
        tape=t, entry_reasoning_eval_v1=_minimal_ere()
    )
    s2 = compute_decision_quality_score_026c_v1(
        tape=deepcopy(t), entry_reasoning_eval_v1=_minimal_ere()
    )
    assert s1 == s2
