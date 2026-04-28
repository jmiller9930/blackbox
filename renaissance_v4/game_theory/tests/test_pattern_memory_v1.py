"""GT_DIRECTIVE_030 — pattern_memory_v1 unit tests."""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.game_theory.reasoning_model.pattern_memory_v1 import (
    SCHEMA_PERPS_PATTERN_SIGNATURE_V1,
    build_perps_pattern_signature_v1,
    evaluate_pattern_memory_v1,
    pattern_similarity_score_v1,
)
from renaissance_v4.game_theory.reasoning_model.perps_state_model_v1 import compute_perps_state_model_v1
from renaissance_v4.game_theory.student_proctor.contracts_v1 import legal_example_student_learning_record_v1
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import build_indicator_context_eval_v1


def _bars_uptrend(n: int = 80) -> list[dict]:
    t0, step = 1_000_000, 300_000
    out = []
    for i in range(n):
        p = 100.0 + i * 0.15
        out.append(
            {
                "open_time": t0 + i * step,
                "symbol": "PMTEST",
                "open": p,
                "high": p + 0.2,
                "low": p - 0.1,
                "close": p + 0.05,
                "volume": 1000.0 + i * 2,
            }
        )
    return out


def test_signature_deterministic_hash() -> None:
    ictx, errs, _ = build_indicator_context_eval_v1(_bars_uptrend(90))
    assert not errs
    ps = compute_perps_state_model_v1(ictx)
    a = build_perps_pattern_signature_v1(
        indicator_context_eval_v1=ictx,
        perps_state_model_v1=ps,
        symbol="PMTEST",
        candle_timeframe_minutes=5,
    )
    b = build_perps_pattern_signature_v1(
        indicator_context_eval_v1=ictx,
        perps_state_model_v1=ps,
        symbol="PMTEST",
        candle_timeframe_minutes=5,
    )
    assert a["signature_hash_v1"] == b["signature_hash_v1"]
    assert a["schema"] == SCHEMA_PERPS_PATTERN_SIGNATURE_V1


def test_similarity_identical_one() -> None:
    ictx, errs, _ = build_indicator_context_eval_v1(_bars_uptrend(90))
    assert not errs
    ps = compute_perps_state_model_v1(ictx)
    sig = build_perps_pattern_signature_v1(
        indicator_context_eval_v1=ictx,
        perps_state_model_v1=ps,
        symbol="PMTEST",
        candle_timeframe_minutes=5,
    )
    assert pattern_similarity_score_v1(sig, dict(sig)) == 1.0


def test_similarity_symbol_mismatch_zero() -> None:
    ictx, errs, _ = build_indicator_context_eval_v1(_bars_uptrend(90))
    assert not errs
    ps = compute_perps_state_model_v1(ictx)
    a = build_perps_pattern_signature_v1(
        indicator_context_eval_v1=ictx,
        perps_state_model_v1=ps,
        symbol="A",
        candle_timeframe_minutes=5,
    )
    b = build_perps_pattern_signature_v1(
        indicator_context_eval_v1=ictx,
        perps_state_model_v1=ps,
        symbol="B",
        candle_timeframe_minutes=5,
    )
    assert pattern_similarity_score_v1(a, b) == 0.0


def test_evaluate_loads_store_matches_and_effect(tmp_path: Path, monkeypatch) -> None:
    ictx, errs, _ = build_indicator_context_eval_v1(_bars_uptrend(90))
    assert not errs
    ps = compute_perps_state_model_v1(ictx)
    sig = build_perps_pattern_signature_v1(
        indicator_context_eval_v1=ictx,
        perps_state_model_v1=ps,
        symbol="PMTEST",
        candle_timeframe_minutes=5,
    )
    store = tmp_path / "student_learning_records_v1.jsonl"
    rows: list[str] = []
    for i in range(3):
        base = legal_example_student_learning_record_v1()
        base["record_id"] = f"660e8400-e29b-41d4-a716-44665544000{i}"
        base["run_id"] = "run_hist_pmtest"
        base["graded_unit_id"] = f"trade_pm_{i}"
        base["candle_timeframe_minutes"] = 5
        base["referee_outcome_subset"] = {"pnl": 10.0, "trade_id": f"t{i}", "symbol": "PMTEST"}
        base["perps_pattern_signature_v1"] = dict(sig)
        rows.append(json.dumps(base, ensure_ascii=False))
    store.write_text("\n".join(rows) + "\n", encoding="utf-8")

    monkeypatch.setenv("PATTERN_GAME_PATTERN_MEMORY_MIN_SAMPLE", "3")
    monkeypatch.setenv("PATTERN_GAME_PATTERN_MEMORY_SIMILARITY_FLOOR", "0.01")

    out = evaluate_pattern_memory_v1(
        indicator_context_eval_v1=ictx,
        perps_state_model_v1=ps,
        symbol="PMTEST",
        candle_timeframe_minutes=5,
        store_path=store,
        current_run_id="run_current_pmtest",
    )
    assert len(out.get("top_matches_v1") or []) >= 1
    stats = out.get("pattern_outcome_stats_v1") or {}
    assert int(stats.get("count") or 0) >= 3
    assert float(out.get("pattern_effect_to_score_v1") or 0.0) > 0.0
