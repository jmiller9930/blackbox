"""Tests for CANONICAL #137 Chris Coinbase paper adapter + 12th-grade score surfaces."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

from modules.execution_adapter.chris_coinbase_paper import (
    CHRIS_COINBASE_PAPER_LANE,
    CoinbasePaperStatusV1,
    fetch_coinbase_paper_status,
    submit_chris_coinbase_paper_adapter,
)
from modules.execution_adapter.paper import PaperVenueScenario
from modules.execution_adapter.validation import EXA_SCOPE_003, EXA_VENUE_006, adapter_request_from_dict
from modules.execution_artifacts.validation import execution_intent_from_dict
from modules.paper_loop.chris_scoring import (
    ChrisPaperArtifactBundleV1,
    ChrisPaperDecisionRecordV1,
    ChrisPaperOutcomeRecordV1,
    ChrisPaperRcsReflectionLinkV1,
    compute_chris_score_surfaces,
    ensure_chris_paper_artifact_schema,
    read_chris_paper_bundles,
    write_chris_paper_artifact_bundle,
)
from modules.paper_loop.orchestration import run_first_approved_paper_loop
from modules.paper_loop.validation import LOOP_PAPER_005


def _scope() -> dict[str, str]:
    return {
        "participant_id": "p-chris",
        "participant_type": "human",
        "account_id": "acct-chris",
        "wallet_context": "wallet-chris",
        "risk_tier": "Tier 1",
        "interaction_path": CHRIS_COINBASE_PAPER_LANE,
    }


def _intent_dict() -> dict[str, str]:
    s = _scope()
    return {
        "intent_id": "int-chris-1",
        "approval_id": "appr-chris-1",
        "candidate_id": "cand-chris-1",
        "signal_id": "sig-chris-1",
        **s,
        "execution_idempotency_key": "idem-exec-chris",
        "context_hash": "ab" * 32,
        "order_side": "buy",
        "order_type": "limit",
        "quantity": "1.0",
        "submitted_at_utc": "2026-01-01T10:05:00+00:00",
        "expires_at_utc": "2026-01-01T11:00:00+00:00",
        "trace_id": "trace-chris",
    }


def _adapter_req_dict() -> dict[str, str]:
    s = _scope()
    return {
        "intent_id": "int-chris-1",
        "approval_id": "appr-chris-1",
        "candidate_id": "cand-chris-1",
        "signal_id": "sig-chris-1",
        "trace_id": "trace-chris",
        **s,
        "order_side": "buy",
        "order_type": "limit",
        "quantity": "1.0",
        "limit_price": "100.0",
        "time_in_force": "GTC",
        "venue_order_idempotency_key": "idem-venue-chris",
        "submit_by_utc": "2026-01-01T10:30:00+00:00",
        "intent_expires_at_utc": "2026-01-01T11:00:00+00:00",
        "context_hash": "ab" * 32,
    }


def _approval_dict() -> dict[str, str]:
    s = _scope()
    return {
        "signal_id": "sig-chris-1",
        "candidate_id": "cand-chris-1",
        "approval_id": "appr-chris-1",
        **s,
        "symbol": "SOL-PERP",
        "approved_at_utc": "2026-01-01T09:00:00+00:00",
        "approval_expires_at_utc": "2026-01-01T12:00:00+00:00",
        "trace_id": "trace-chris",
    }


def _intent_link_dict() -> dict[str, str]:
    s = _scope()
    return {
        "intent_id": "int-chris-1",
        "approval_id": "appr-chris-1",
        "candidate_id": "cand-chris-1",
        "signal_id": "sig-chris-1",
        "participant_id": s["participant_id"],
        "account_id": s["account_id"],
        "wallet_context": s["wallet_context"],
        "risk_tier": s["risk_tier"],
        "interaction_path": s["interaction_path"],
        "context_hash": "ab" * 32,
        "market_snapshot_id": "mks-1",
        "venue_order_idempotency_key": "idem-venue-chris",
        "submit_by_utc": "2026-01-01T10:30:00+00:00",
        "intent_expires_at_utc": "2026-01-01T11:00:00+00:00",
        "trace_id": "trace-chris",
    }


def _load_intent():
    it, r = execution_intent_from_dict(_intent_dict())
    assert r.ok and it is not None
    return it


def _load_req():
    req, r = adapter_request_from_dict(_adapter_req_dict())
    assert r.ok and req is not None
    return req


def _now() -> datetime:
    return datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_chris_submit_success_deterministic_status():
    req = _load_req()
    intent = _load_intent()
    st = CoinbasePaperStatusV1(
        candles_state="healthy",
        lob_state="healthy",
        last_checked_at="2026-01-01T10:00:00+00:00",
        reason_code=None,
    )
    r = submit_chris_coinbase_paper_adapter(
        req,
        intent,
        now_utc=_now(),
        idempotency_registry={},
        scenario=PaperVenueScenario.ACCEPT,
        outcome_id="out-1",
        venue_order_id="vo-1",
        submitted_at_utc="2026-01-01T10:10:00+00:00",
        coinbase_status=st,
    )
    assert r.result.ok and r.outcome is not None
    assert r.outcome.venue_name == CHRIS_COINBASE_PAPER_LANE
    assert r.outcome.venue_status == "paper_submitted"


def test_chris_submit_fail_closed_wrong_lane():
    req = _load_req()
    intent = _load_intent()
    d = _adapter_req_dict()
    d["interaction_path"] = "operator_console"
    bad, br = adapter_request_from_dict(d)
    assert br.ok and bad is not None
    st = CoinbasePaperStatusV1("healthy", "unavailable", "2026-01-01T10:00:00+00:00", None)
    r = submit_chris_coinbase_paper_adapter(
        bad,
        intent,
        now_utc=_now(),
        idempotency_registry={},
        scenario=PaperVenueScenario.ACCEPT,
        outcome_id="out-1",
        venue_order_id="vo-1",
        submitted_at_utc="2026-01-01T10:10:00+00:00",
        coinbase_status=st,
    )
    assert not r.result.ok and r.result.reason_code == EXA_SCOPE_003


def test_chris_submit_forces_unavailable_when_candles_down():
    req = _load_req()
    intent = _load_intent()
    st = CoinbasePaperStatusV1(
        candles_state="down",
        lob_state="unavailable",
        last_checked_at="2026-01-01T10:00:00+00:00",
        reason_code="COIN-PAPER-CANDLES-DOWN",
    )
    r = submit_chris_coinbase_paper_adapter(
        req,
        intent,
        now_utc=_now(),
        idempotency_registry={},
        scenario=PaperVenueScenario.ACCEPT,
        outcome_id="out-1",
        venue_order_id="vo-1",
        submitted_at_utc="2026-01-01T10:10:00+00:00",
        coinbase_status=st,
    )
    assert r.result.ok and r.outcome is not None
    assert r.outcome.failure_code == EXA_VENUE_006
    assert r.outcome.venue_status == "venue_unavailable"


def test_fetch_coinbase_status_required_candles_optional_l2():
    now_epoch = 1_704_067_200  # fixed epoch
    candles_payload = [[now_epoch, 100.0, 101.0, 99.0, 100.5, 150.0]]
    lob_payload = {"bids": [["100.0", "1.2", 2]], "asks": [["100.2", "1.0", 1]]}

    class _Resp:
        def __init__(self, obj):
            self._obj = obj

        def read(self):
            return json.dumps(self._obj).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout):  # noqa: ARG001
        url = req.full_url
        if "candles" in url:
            return _Resp(candles_payload)
        return _Resp(lob_payload)

    with patch("modules.execution_adapter.chris_coinbase_paper.urlopen", _fake_urlopen):
        st = fetch_coinbase_paper_status(product_id="SOL-USD", max_candle_age_sec=1e12)
    assert st.candles_state == "healthy"
    assert st.lob_state == "healthy"


def test_orchestration_lane_chris_coinbase_paper_v1_success():
    from modules.paper_loop.validation import execution_intent_link_from_dict, signal_approval_link_from_dict

    approval, ar = signal_approval_link_from_dict(_approval_dict())
    intent_link, ilr = execution_intent_link_from_dict(_intent_link_dict())
    assert ar.ok and approval is not None and ilr.ok and intent_link is not None
    intent = _load_intent()
    req = _load_req()
    r = run_first_approved_paper_loop(
        approval,
        intent_link,
        intent,
        req,
        market_snapshot_id="mks-1",
        signal=None,
        now_utc=_now(),
        venue_name="paper",
        idempotency_registry={},
        execution_id="exec-1",
        paper_scenario=PaperVenueScenario.ACCEPT,
        outcome_id="out-1",
        venue_order_id="vo-1",
        submitted_at_utc="2026-01-01T10:20:00+00:00",
        metric_event_id="met-1",
        failure_event_id=None,
        audit_event_id="aud-1",
        adapter_lane=CHRIS_COINBASE_PAPER_LANE,
        chris_coinbase_status=CoinbasePaperStatusV1(
            candles_state="healthy",
            lob_state="unavailable",
            last_checked_at="2026-01-01T10:00:00+00:00",
            reason_code=None,
        ),
    )
    assert r.ok and r.adapter_outcome is not None
    assert r.adapter_outcome.venue_name == CHRIS_COINBASE_PAPER_LANE


def test_orchestration_lane_chris_coinbase_paper_v1_reject():
    from modules.paper_loop.validation import execution_intent_link_from_dict, signal_approval_link_from_dict

    approval, ar = signal_approval_link_from_dict(_approval_dict())
    intent_link, ilr = execution_intent_link_from_dict(_intent_link_dict())
    assert ar.ok and approval is not None and ilr.ok and intent_link is not None
    intent = _load_intent()
    req = _load_req()
    r = run_first_approved_paper_loop(
        approval,
        intent_link,
        intent,
        req,
        market_snapshot_id="mks-1",
        signal=None,
        now_utc=_now(),
        venue_name="paper",
        idempotency_registry={},
        execution_id="exec-1",
        paper_scenario=PaperVenueScenario.REJECT,
        outcome_id="out-1",
        venue_order_id="vo-1",
        submitted_at_utc="2026-01-01T10:20:00+00:00",
        metric_event_id="met-1",
        failure_event_id="fail-1",
        audit_event_id="aud-1",
        adapter_lane=CHRIS_COINBASE_PAPER_LANE,
        chris_coinbase_status=CoinbasePaperStatusV1(
            candles_state="healthy",
            lob_state="unavailable",
            last_checked_at="2026-01-01T10:00:00+00:00",
            reason_code=None,
        ),
    )
    assert not r.ok and r.loop_reason_code == LOOP_PAPER_005


def test_chris_12th_grade_score_surfaces():
    b1 = ChrisPaperArtifactBundleV1(
        decision=ChrisPaperDecisionRecordV1(
            decision_id="d1",
            intent_id="i1",
            candidate_id="c1",
            signal_id="s1",
            participant_id="p1",
            account_id="a1",
            risk_tier="Tier 1",
            decision_at_utc="2026-01-01T10:00:00+00:00",
            decision_summary="long continuation",
        ),
        outcome=ChrisPaperOutcomeRecordV1(
            outcome_id="o1",
            intent_id="i1",
            decision_id="d1",
            venue_status="paper_submitted",
            recorded_at_utc="2026-01-01T10:05:00+00:00",
            filled_quantity="1",
            avg_fill_price="100",
            fees_total="0.1",
            realized_pnl="10",
            baseline_pnl="6",
        ),
        rcs_link=ChrisPaperRcsReflectionLinkV1(
            reflection_id="r1",
            decision_id="d1",
            outcome_id="o1",
            linked_at_utc="2026-01-01T10:06:00+00:00",
        ),
    )
    b2 = ChrisPaperArtifactBundleV1(
        decision=ChrisPaperDecisionRecordV1(
            decision_id="d2",
            intent_id="i2",
            candidate_id="c2",
            signal_id="s2",
            participant_id="p1",
            account_id="a1",
            risk_tier="Tier 1",
            decision_at_utc="2026-01-01T11:00:00+00:00",
            decision_summary="failed break",
        ),
        outcome=ChrisPaperOutcomeRecordV1(
            outcome_id="o2",
            intent_id="i2",
            decision_id="d2",
            venue_status="paper_submitted",
            recorded_at_utc="2026-01-01T11:08:00+00:00",
            filled_quantity="1",
            avg_fill_price="100",
            fees_total="0.1",
            realized_pnl="-4",
            baseline_pnl="-1",
        ),
        rcs_link=ChrisPaperRcsReflectionLinkV1(
            reflection_id="r2",
            decision_id="d2",
            outcome_id="o2",
            linked_at_utc="2026-01-01T11:09:00+00:00",
        ),
    )
    s = compute_chris_score_surfaces([b1, b2])
    assert s.win_rate == 0.5
    assert s.expectancy == 3.0
    assert s.profit_factor == 2.5
    assert s.max_drawdown == 4.0
    assert s.baseline_delta == 1.0


def test_chris_artifact_persistence_and_scoring_from_store():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    ensure_chris_paper_artifact_schema(conn)
    b = ChrisPaperArtifactBundleV1(
        decision=ChrisPaperDecisionRecordV1(
            decision_id="d1",
            intent_id="i1",
            candidate_id="c1",
            signal_id="s1",
            participant_id="p1",
            account_id="a1",
            risk_tier="Tier 1",
            decision_at_utc="2026-01-01T10:00:00+00:00",
            decision_summary="long continuation",
        ),
        outcome=ChrisPaperOutcomeRecordV1(
            outcome_id="o1",
            intent_id="i1",
            decision_id="d1",
            venue_status="paper_submitted",
            recorded_at_utc="2026-01-01T10:05:00+00:00",
            filled_quantity="1",
            avg_fill_price="100",
            fees_total="0.1",
            realized_pnl="2",
            baseline_pnl="1",
        ),
        rcs_link=ChrisPaperRcsReflectionLinkV1(
            reflection_id="r1",
            decision_id="d1",
            outcome_id="o1",
            linked_at_utc="2026-01-01T10:06:00+00:00",
        ),
    )
    ok, reason = write_chris_paper_artifact_bundle(conn, b)
    assert ok and reason == ""
    # idempotent repeat should pass with same key/payload
    ok2, reason2 = write_chris_paper_artifact_bundle(conn, b)
    assert ok2 and reason2 == ""
    rows = read_chris_paper_bundles(conn, participant_id="p1", account_id="a1")
    assert len(rows) == 1
    s = compute_chris_score_surfaces(rows)
    assert s.win_rate == 1.0
    assert s.expectancy == 2.0
    assert s.baseline_delta == 1.0
    conn.close()

