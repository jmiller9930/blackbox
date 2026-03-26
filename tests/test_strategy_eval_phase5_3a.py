"""Phase 5.3a — Deterministic strategy evaluation contract tests.

Tests cover:
  - StrategyEvaluationV1 artifact structure (immutability, serialization, defaults)
  - evaluate_strategy() public API against stored market data
  - Tier-aligned threshold selection (tier_1 / tier_2 / tier_3)
  - Determinism: same stored data + same scope = same evaluation
  - Abstain paths: blocked gate, missing data, spread too wide, low confidence
  - Signal paths: long_bias, short_bias, neutral
  - Spread computation edge cases
  - Separation: evaluation only, no execution, no tier escalation
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.participant_scope import ParticipantScope, validate_participant_scope
from market_data.read_contracts import MarketDataReadContractV1
from market_data.store import connect_market_db, ensure_market_schema, insert_tick
from market_data.strategy_eval import (
    EVALUATION_OUTCOMES,
    STRATEGY_VERSION,
    TIER_THRESHOLDS,
    StrategyEvaluationV1,
    _compute_spread_pct,
    _evaluate_from_snapshot,
    evaluate_strategy,
    evaluate_strategy_from_read_contract,
)
from market_data.scoped_reader import ScopedMarketDataSnapshot
from _paths import repo_root


def _make_scope(**overrides) -> ParticipantScope:
    defaults = dict(
        participant_id="sean",
        participant_type="human",
        account_id="acct_001",
        wallet_context="wallet_main",
        risk_tier="tier_2",
        interaction_path="telegram",
    )
    defaults.update(overrides)
    return ParticipantScope(**defaults)


def _seed_tick(
    db_path: Path,
    symbol: str = "SOL-USD",
    primary_price: float = 150.0,
    comparator_price: float | None = None,
    gate_state: str = "ok",
    gate_reason: str = "freshness_ok;freshness_ok;divergence_ok",
) -> int:
    if comparator_price is None:
        comparator_price = primary_price + 0.01
    root = repo_root()
    conn = connect_market_db(db_path)
    ensure_market_schema(conn, root)
    rid = insert_tick(
        conn,
        symbol=symbol,
        inserted_at="2026-03-26T18:00:00+00:00",
        primary_source="pyth_hermes",
        primary_price=primary_price,
        primary_observed_at="2026-03-26T18:00:00+00:00",
        primary_publish_time=1,
        primary_raw={"id": "test"},
        comparator_source="coinbase",
        comparator_price=comparator_price,
        comparator_observed_at="2026-03-26T18:00:00+00:00",
        comparator_raw={"price": str(comparator_price)},
        gate_state=gate_state,
        gate_reason=gate_reason,
    )
    conn.close()
    return rid


def _make_read_contract(**overrides) -> MarketDataReadContractV1:
    base = dict(
        participant_id="sean",
        participant_type="human",
        account_id="acct_001",
        wallet_context="wallet_main",
        risk_tier="tier_2",
        interaction_path="telegram",
        market_symbol="SOL-USD",
    )
    base.update(overrides)
    return MarketDataReadContractV1(**base)


# ---------------------------------------------------------------------------
# Evaluation artifact structure
# ---------------------------------------------------------------------------


class TestReadContractEntryPoint:
    def test_from_read_contract_matches_evaluate_strategy(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        scope = _make_scope()
        c = _make_read_contract()
        r1 = evaluate_strategy(scope, "SOL-USD", db_path=db)
        r2 = evaluate_strategy_from_read_contract(c, db_path=db)
        assert r1.evaluation_outcome == r2.evaluation_outcome
        assert r1.confidence == r2.confidence
        assert r1.spread_pct == r2.spread_pct

    def test_invalid_read_contract_abstains(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        bad = _make_read_contract(risk_tier="tier_99")
        r = evaluate_strategy_from_read_contract(bad, db_path=db)
        assert r.evaluation_outcome == "abstain"
        assert r.abstain_reason == "market_data_read_contract_invalid"
        assert r.error is not None


class TestStrategyEvaluationArtifact:
    def test_evaluation_is_immutable(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        with pytest.raises(AttributeError):
            result.confidence = 0.99  # type: ignore[misc]

    def test_schema_version_default(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.schema_version == "strategy_evaluation_v1"

    def test_to_dict_contains_all_fields(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        d = result.to_dict()
        for field in (
            "participant_scope",
            "symbol",
            "strategy_version",
            "evaluation_outcome",
            "confidence",
            "abstain_reason",
            "gate_state",
            "primary_price",
            "comparator_price",
            "spread_pct",
            "tier_thresholds_used",
            "evaluated_at",
            "schema_version",
        ):
            assert field in d, f"missing field: {field}"

    def test_strategy_version_is_deterministic_spread_v1(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.strategy_version == STRATEGY_VERSION
        assert result.strategy_version == "deterministic_spread_v1"

    def test_participant_scope_preserved_in_artifact(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        scope = _make_scope(participant_id="alice", risk_tier="tier_1")
        result = evaluate_strategy(scope, "SOL-USD", db_path=db)
        assert result.participant_scope.participant_id == "alice"
        assert result.participant_scope.risk_tier == "tier_1"

    def test_symbol_preserved_in_artifact(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db, symbol="SOL-USD")
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.symbol == "SOL-USD"


# ---------------------------------------------------------------------------
# Spread computation
# ---------------------------------------------------------------------------


class TestSpreadComputation:
    def test_valid_prices_computes_spread(self):
        spread = _compute_spread_pct(150.0, 149.9)
        assert spread is not None
        assert isinstance(spread, float)
        expected = (150.0 - 149.9) / ((150.0 + 149.9) / 2.0)
        assert abs(spread - expected) < 1e-10

    def test_none_primary_returns_none(self):
        assert _compute_spread_pct(None, 150.0) is None

    def test_none_comparator_returns_none(self):
        assert _compute_spread_pct(150.0, None) is None

    def test_both_none_returns_none(self):
        assert _compute_spread_pct(None, None) is None

    def test_zero_primary_returns_none(self):
        assert _compute_spread_pct(0.0, 150.0) is None

    def test_negative_price_returns_none(self):
        assert _compute_spread_pct(-1.0, 150.0) is None

    def test_positive_spread_when_primary_higher(self):
        spread = _compute_spread_pct(151.0, 149.0)
        assert spread is not None
        assert spread > 0

    def test_negative_spread_when_primary_lower(self):
        spread = _compute_spread_pct(149.0, 151.0)
        assert spread is not None
        assert spread < 0


# ---------------------------------------------------------------------------
# Signal / evaluation outcomes
# ---------------------------------------------------------------------------


class TestEvaluationOutcomes:
    def test_ok_tick_tight_spread_returns_neutral(self, tmp_path: Path):
        """Tiny spread (< signal_spread_pct) returns neutral."""
        db = tmp_path / "market_data.db"
        _seed_tick(db, primary_price=150.0, comparator_price=150.001)
        result = evaluate_strategy(_make_scope(risk_tier="tier_2"), "SOL-USD", db_path=db)
        assert result.evaluation_outcome == "neutral"
        assert result.abstain_reason is None
        assert result.error is None

    def test_ok_tick_moderate_spread_returns_bias(self, tmp_path: Path):
        """Spread above signal threshold but within max → long_bias or short_bias."""
        db = tmp_path / "market_data.db"
        _seed_tick(db, primary_price=150.0, comparator_price=150.15)
        result = evaluate_strategy(_make_scope(risk_tier="tier_2"), "SOL-USD", db_path=db)
        assert result.evaluation_outcome in ("long_bias", "short_bias")
        assert result.abstain_reason is None
        assert result.confidence > 0

    def test_long_bias_when_primary_lower_than_comparator(self, tmp_path: Path):
        """Primary < comparator → negative spread → long_bias."""
        db = tmp_path / "market_data.db"
        _seed_tick(db, primary_price=149.85, comparator_price=150.0)
        result = evaluate_strategy(_make_scope(risk_tier="tier_3"), "SOL-USD", db_path=db)
        if result.evaluation_outcome != "abstain":
            assert result.evaluation_outcome == "long_bias"

    def test_short_bias_when_primary_higher_than_comparator(self, tmp_path: Path):
        """Primary > comparator → positive spread → short_bias."""
        db = tmp_path / "market_data.db"
        _seed_tick(db, primary_price=150.15, comparator_price=150.0)
        result = evaluate_strategy(_make_scope(risk_tier="tier_3"), "SOL-USD", db_path=db)
        if result.evaluation_outcome != "abstain":
            assert result.evaluation_outcome == "short_bias"

    def test_all_outcomes_in_allowed_set(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.evaluation_outcome in EVALUATION_OUTCOMES


# ---------------------------------------------------------------------------
# Abstain paths
# ---------------------------------------------------------------------------


class TestAbstainPaths:
    def test_invalid_scope_returns_abstain(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        bad_scope = _make_scope(risk_tier="tier_99")
        result = evaluate_strategy(bad_scope, "SOL-USD", db_path=db)
        assert result.evaluation_outcome == "abstain"
        assert result.abstain_reason == "scope_validation_failed"
        assert result.error is not None

    def test_missing_db_returns_abstain(self, tmp_path: Path):
        db = tmp_path / "nonexistent.db"
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.evaluation_outcome == "abstain"
        assert result.error is not None
        assert "market_data" in result.error

    def test_empty_table_returns_abstain(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        conn = connect_market_db(db)
        ensure_market_schema(conn, repo_root())
        conn.close()
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.evaluation_outcome == "abstain"
        assert result.error is not None

    def test_wrong_symbol_returns_abstain(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db, symbol="SOL-USD")
        result = evaluate_strategy(_make_scope(), "BTC-USD", db_path=db)
        assert result.evaluation_outcome == "abstain"
        assert result.error is not None

    def test_blocked_gate_returns_abstain(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(
            db,
            primary_price=150.0,
            comparator_price=150.01,
            gate_state="blocked",
            gate_reason="freshness_stale",
        )
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.evaluation_outcome == "abstain"
        assert result.abstain_reason == "gate_blocked"
        assert result.gate_state == "blocked"

    def test_spread_exceeds_tier_max_returns_abstain(self, tmp_path: Path):
        """Spread > max_spread_pct for the selected tier → abstain."""
        db = tmp_path / "market_data.db"
        _seed_tick(db, primary_price=150.0, comparator_price=152.0)
        result = evaluate_strategy(_make_scope(risk_tier="tier_1"), "SOL-USD", db_path=db)
        assert result.evaluation_outcome == "abstain"
        assert result.abstain_reason == "spread_exceeds_tier_limit"

    def test_missing_comparator_price_returns_abstain(self, tmp_path: Path):
        """NULL comparator price in DB → insufficient_price_data or market_data_error."""
        db = tmp_path / "market_data.db"
        root = repo_root()
        conn = connect_market_db(db)
        ensure_market_schema(conn, root)
        insert_tick(
            conn,
            symbol="SOL-USD",
            inserted_at="2026-03-26T18:00:00+00:00",
            primary_source="pyth_hermes",
            primary_price=150.0,
            primary_observed_at="2026-03-26T18:00:00+00:00",
            primary_publish_time=1,
            primary_raw=None,
            comparator_source="coinbase",
            comparator_price=None,
            comparator_observed_at=None,
            comparator_raw=None,
            gate_state="ok",
            gate_reason="ok",
        )
        conn.close()
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.evaluation_outcome == "abstain"


# ---------------------------------------------------------------------------
# Tier alignment
# ---------------------------------------------------------------------------


class TestTierAlignment:
    def test_all_three_tiers_produce_evaluations(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        for tier in ("tier_1", "tier_2", "tier_3"):
            result = evaluate_strategy(_make_scope(risk_tier=tier), "SOL-USD", db_path=db)
            assert isinstance(result, StrategyEvaluationV1)
            assert result.participant_scope.risk_tier == tier

    def test_tier_thresholds_used_matches_input_tier(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        for tier in ("tier_1", "tier_2", "tier_3"):
            result = evaluate_strategy(_make_scope(risk_tier=tier), "SOL-USD", db_path=db)
            if result.tier_thresholds_used is not None:
                assert result.tier_thresholds_used == TIER_THRESHOLDS[tier]

    def test_risk_tier_not_escalated(self, tmp_path: Path):
        """risk_tier in output must match risk_tier in input — no escalation."""
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        scope = _make_scope(risk_tier="tier_1")
        result = evaluate_strategy(scope, "SOL-USD", db_path=db)
        assert result.participant_scope.risk_tier == "tier_1"

    def test_tier_1_stricter_than_tier_3(self):
        """Tier 1 has higher min_confidence and lower max_spread_pct (stricter)."""
        t1 = TIER_THRESHOLDS["tier_1"]
        t3 = TIER_THRESHOLDS["tier_3"]
        assert t1["min_confidence"] > t3["min_confidence"]
        assert t1["max_spread_pct"] < t3["max_spread_pct"]

    def test_evaluation_stays_within_selected_tier(self, tmp_path: Path):
        """The artifact reflects the tier the participant selected, never another."""
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        scope_t1 = _make_scope(risk_tier="tier_1")
        scope_t3 = _make_scope(risk_tier="tier_3")
        r1 = evaluate_strategy(scope_t1, "SOL-USD", db_path=db)
        r3 = evaluate_strategy(scope_t3, "SOL-USD", db_path=db)
        assert r1.participant_scope.risk_tier == "tier_1"
        assert r3.participant_scope.risk_tier == "tier_3"
        if r1.tier_thresholds_used and r3.tier_thresholds_used:
            assert r1.tier_thresholds_used != r3.tier_thresholds_used


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self, tmp_path: Path):
        """Given the same stored tick + same scope, the evaluation is identical."""
        db = tmp_path / "market_data.db"
        _seed_tick(db, primary_price=150.0, comparator_price=150.05)
        scope = _make_scope(risk_tier="tier_2")
        r1 = evaluate_strategy(scope, "SOL-USD", db_path=db)
        r2 = evaluate_strategy(scope, "SOL-USD", db_path=db)
        assert r1.evaluation_outcome == r2.evaluation_outcome
        assert r1.confidence == r2.confidence
        assert r1.spread_pct == r2.spread_pct
        assert r1.abstain_reason == r2.abstain_reason

    def test_different_participants_same_data_same_signal(self, tmp_path: Path):
        """Two participants with the same tier see the same evaluation outcome on the same tick."""
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        scope_a = _make_scope(participant_id="alice", risk_tier="tier_2")
        scope_b = _make_scope(participant_id="bob", risk_tier="tier_2")
        ra = evaluate_strategy(scope_a, "SOL-USD", db_path=db)
        rb = evaluate_strategy(scope_b, "SOL-USD", db_path=db)
        assert ra.evaluation_outcome == rb.evaluation_outcome
        assert ra.confidence == rb.confidence

    def test_human_and_bot_same_tier_same_outcome(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        human = _make_scope(participant_type="human", risk_tier="tier_2")
        bot = _make_scope(participant_id="bot_1", participant_type="bot", risk_tier="tier_2")
        rh = evaluate_strategy(human, "SOL-USD", db_path=db)
        rb = evaluate_strategy(bot, "SOL-USD", db_path=db)
        assert rh.evaluation_outcome == rb.evaluation_outcome
        assert rh.confidence == rb.confidence


# ---------------------------------------------------------------------------
# Degraded gate — confidence penalty
# ---------------------------------------------------------------------------


class TestDegradedGate:
    def test_degraded_gate_reduces_confidence(self, tmp_path: Path):
        db_ok = tmp_path / "ok.db"
        db_deg = tmp_path / "degraded.db"
        _seed_tick(db_ok, primary_price=150.0, comparator_price=150.05, gate_state="ok")
        _seed_tick(db_deg, primary_price=150.0, comparator_price=150.05, gate_state="degraded")

        r_ok = evaluate_strategy(_make_scope(risk_tier="tier_3"), "SOL-USD", db_path=db_ok)
        r_deg = evaluate_strategy(_make_scope(risk_tier="tier_3"), "SOL-USD", db_path=db_deg)

        if r_ok.evaluation_outcome != "abstain" and r_deg.evaluation_outcome != "abstain":
            assert r_deg.confidence < r_ok.confidence

    def test_degraded_gate_state_reflected_in_artifact(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db, gate_state="degraded", gate_reason="freshness_near_limit")
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert result.gate_state == "degraded"


# ---------------------------------------------------------------------------
# Separation: no execution, no writes
# ---------------------------------------------------------------------------


class TestSeparation:
    def test_evaluation_does_not_write_to_db(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        count_before = conn.execute("SELECT COUNT(*) FROM market_ticks").fetchone()[0]
        conn.close()

        for _ in range(5):
            evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        count_after = conn.execute("SELECT COUNT(*) FROM market_ticks").fetchone()[0]
        conn.close()

        assert count_before == count_after

    def test_no_execution_fields_in_artifact(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        d = result.to_dict()
        for forbidden in ("order_id", "execution_id", "venue", "trade_size", "layer_4"):
            assert forbidden not in d

    def test_evaluated_at_is_iso_timestamp(self, tmp_path: Path):
        db = tmp_path / "market_data.db"
        _seed_tick(db)
        result = evaluate_strategy(_make_scope(), "SOL-USD", db_path=db)
        assert "T" in result.evaluated_at
