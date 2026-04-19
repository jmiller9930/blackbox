"""Context Signature Memory v1 — deterministic signature, store, match, optimizer v3 bias."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from renaissance_v4.game_theory.bundle_optimizer import optimize_bundle_v3
from renaissance_v4.game_theory.context_signature_memory import (
    ContextSignatureMemoryError,
    SignatureMatchParamsV1,
    append_context_memory_record,
    apply_context_memory_bias_v1,
    canonical_signature_key,
    derive_context_signature_v1,
    eligible_bias_records,
    find_matching_records_v1,
    read_context_memory_records,
    signatures_match_v1,
)


def _sample_pc() -> dict:
    return {
        "schema": "pattern_context_v1",
        "bars_processed": 100,
        "dominant_regime": "range",
        "dominant_volatility_bucket": "neutral",
        "structure_tag_shares": {
            "range_like": 0.5,
            "trend_like": 0.1,
            "breakout_like": 0.05,
            "vol_compressed": 0.2,
            "vol_expanding": 0.15,
        },
        "high_conflict_bars": 10,
        "aligned_directional_bars": 5,
        "countertrend_directional_bars": 3,
    }


def test_derive_signature_and_key_stable() -> None:
    pc = _sample_pc()
    s1 = derive_context_signature_v1(pc)
    s2 = derive_context_signature_v1(pc)
    assert s1 == s2
    assert s1["schema"] == "context_signature_v1"
    k1 = canonical_signature_key(s1)
    k2 = canonical_signature_key(s2)
    assert k1 == k2
    assert len(k1) == 64


def test_signatures_match_tolerance() -> None:
    pc = _sample_pc()
    a = derive_context_signature_v1(pc)
    b = derive_context_signature_v1(pc)
    assert signatures_match_v1(a, b)
    b2 = dict(b)
    b2["range_like_share"] = round(float(b["range_like_share"]) + 0.05, 6)
    assert signatures_match_v1(a, b2)
    b3 = dict(b)
    b3["range_like_share"] = round(float(b["range_like_share"]) + 0.2, 6)
    assert not signatures_match_v1(a, b3)


def test_append_read_roundtrip() -> None:
    pc = _sample_pc()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.jsonl"
        rec = append_context_memory_record(
            pattern_context_v1=pc,
            source_run_id="run_a",
            source_artifact_paths=["/x/manifest.json"],
            effective_apply={"fusion_min_score": 0.30},
            outcome_summary={
                "expectancy": 0.5,
                "max_drawdown": 5.0,
                "win_rate": 0.55,
                "total_trades": 10,
                "cumulative_pnl": 1.0,
            },
            optimizer_reason_codes=["V1_X"],
            memory_path=p,
        )
        rows = read_context_memory_records(p)
        assert len(rows) == 1
        assert rows[0]["record_id"] == rec["record_id"]
        assert rows[0]["signature_key"] == rec["signature_key"]


def test_read_rejects_bad_jsonl() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.jsonl"
        p.write_text("not json\n", encoding="utf-8")
        with pytest.raises(ContextSignatureMemoryError):
            read_context_memory_records(p)


def test_eligible_bias_records_filters_by_outcome() -> None:
    matches = [
        {
            "record_id": "r1",
            "outcome_summary": {
                "expectancy": 0.2,
                "max_drawdown": 10.0,
                "win_rate": 0.5,
                "total_trades": 5,
                "cumulative_pnl": 0.0,
            },
        }
    ]
    current = {
        "expectancy": -0.1,
        "max_drawdown": 25.0,
        "win_rate": 0.4,
        "total_trades": 5,
        "cumulative_pnl": -1.0,
    }
    el = eligible_bias_records(matches, current)
    assert len(el) == 1


def test_optimizer_v3_bias_from_memory(tmp_path: Path) -> None:
    pc = _sample_pc()
    rec = append_context_memory_record(
        pattern_context_v1=pc,
        source_run_id="prior_good",
        source_artifact_paths=["m.json"],
        effective_apply={
            "fusion_min_score": 0.22,
            "fusion_max_conflict_score": 0.35,
        },
        outcome_summary={
            "expectancy": 0.4,
            "max_drawdown": 8.0,
            "win_rate": 0.5,
            "total_trades": 8,
            "cumulative_pnl": 2.0,
        },
        optimizer_reason_codes=["V1_NO_TRADES_RELAX_FUSION"],
        memory_path=tmp_path / "mem.jsonl",
        record_id="rec001",
    )

    metrics = {
        "source_run_id": "current_worse",
        "total_trades": 2,
        "max_drawdown": 50.0,
        "win_rate": 0.3,
        "expectancy": -0.2,
        "cumulative_pnl": -3.0,
        "fusion_no_trade_bars": 20,
        "fusion_directional_bars": 30,
        "entries_attempted": 2,
        "closes_recorded": 2,
        "risk_blocked_bars": 0,
        "dataset_bars": 100,
        "scorecards": {},
        "pattern_context_v1": pc,
    }
    bundle, proof = optimize_bundle_v3(
        metrics,
        manifest_signal_modules=["mean_reversion_fade", "trend_continuation", "breakout_expansion"],
        context_memory_path=tmp_path / "mem.jsonl",
        signature_match_params=SignatureMatchParamsV1(structure_share_abs_tol=0.2),
    )
    assert proof["schema"] == "bundle_optimizer_proof_v3"
    assert proof["context_memory_match_count"] >= 1
    assert proof["context_signature_key_current"] == rec["signature_key"]
    assert proof["context_memory_bias_applied"] is True
    assert "fusion_min_score" in bundle["apply"]


def test_optimizer_v3_empty_store_explicit(tmp_path: Path) -> None:
    pc = _sample_pc()
    metrics = {
        "source_run_id": "x",
        "total_trades": 0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "cumulative_pnl": 0.0,
        "fusion_no_trade_bars": 50,
        "fusion_directional_bars": 5,
        "entries_attempted": 0,
        "closes_recorded": 0,
        "risk_blocked_bars": 0,
        "dataset_bars": 100,
        "scorecards": {},
        "pattern_context_v1": pc,
    }
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    _b, proof = optimize_bundle_v3(
        metrics,
        manifest_signal_modules=["mean_reversion_fade"],
        context_memory_path=p,
    )
    assert proof["context_memory_match_count"] == 0
    assert "CM3_NO_MATCHING_SIGNATURES_IN_STORE" in proof["context_memory_reason_codes"]


def test_apply_bias_v1_moves_toward_prior() -> None:
    v2 = {"fusion_min_score": 0.35}
    eligible = [
        {
            "record_id": "z",
            "effective_apply": {"fusion_min_score": 0.20},
            "outcome_summary": {
                "expectancy": 1.0,
                "max_drawdown": 1.0,
                "win_rate": 0.5,
                "total_trades": 3,
                "cumulative_pnl": 0.0,
            },
        }
    ]
    d, diff, codes = apply_context_memory_bias_v1(
        v2,
        eligible_records=eligible,
        manifest_signal_modules=["mean_reversion_fade"],
    )
    assert "fusion_min_score" in d
    assert d["fusion_min_score"] < 0.35
    assert "CM3_BIAS_NUMERIC_TOWARD_PRIOR" in codes
