"""JUPv3 freshness contract + timeline proof helpers."""

from __future__ import annotations

from modules.anna_training.jup_v3_freshness_contract import (
    build_jup_v3_timeline_proof,
    enrich_jup_v3_five_m_freshness,
    freshness_severity,
    within_freshness_contract,
)


def test_freshness_severity_contract_buckets() -> None:
    assert freshness_severity(0, allowed_max=1) == "ok"
    assert freshness_severity(1, allowed_max=1) == "warning"
    assert freshness_severity(2, allowed_max=1) == "fault"


def test_within_freshness_contract() -> None:
    assert within_freshness_contract(0, allowed_max=1) is True
    assert within_freshness_contract(1, allowed_max=1) is True
    assert within_freshness_contract(2, allowed_max=1) is False


def test_enrich_jup_v3_five_m_freshness_sets_contract() -> None:
    out = {
        "schema": "five_m_ingest_freshness_v2",
        "freshness_source": "binance_strategy_bars_5m",
        "closed_bucket_lag": 1,
    }
    enrich_jup_v3_five_m_freshness(out)
    assert out.get("freshness_contract_applies") is True
    assert out.get("freshness_severity") == "warning"
    assert out.get("within_freshness_contract") is True


def test_build_jup_v3_timeline_proof_pass() -> None:
    proof = build_jup_v3_timeline_proof(
        trade_chain={
            "baseline_jupiter_policy": {"active_id": "jup_v3"},
            "five_m_ingest_freshness": {
                "freshness_source": "binance_strategy_bars_5m",
                "expected_last_closed_candle_open_utc": "2026-01-01T12:00:00Z",
                "db_newest_closed_candle_open_utc": "2026-01-01T12:00:00Z",
                "closed_bucket_lag": 0,
            },
        },
        jupiter_policy_snapshot={
            "tile_bar_selection_proof": {
                "selected_candle_open_utc": "2026-01-01T12:00:00Z",
                "db_max_candle_open_utc": "2026-01-01T12:00:00Z",
                "selection_matches_db_max": True,
            }
        },
        market_db_path=None,
    )
    assert proof is not None
    assert proof.get("timeline_invariant_pass") is True
    assert proof.get("diagnostic") is None


def test_build_jup_v3_timeline_proof_none_for_v2() -> None:
    assert (
        build_jup_v3_timeline_proof(
            trade_chain={"baseline_jupiter_policy": {"active_id": "jup_v2"}},
            jupiter_policy_snapshot={},
            market_db_path=None,
        )
        is None
    )
