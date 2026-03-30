"""Phase 5.4 (continued) — Layer 3 trade candidate approval routing."""
from __future__ import annotations

import json
import sqlite3
import sys
from io import BytesIO
from pathlib import Path

import pytest
from wsgiref.util import setup_testing_defaults

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from approval_interface.app import make_app
from market_data.candidate_trade import build_candidate_trade_v1
from market_data.participant_scope import ParticipantScope
from market_data.pre_trade_fast_gate import run_pre_trade_fast_gate
from market_data.strategy_eval import STRATEGY_VERSION, StrategyEvaluationV1
from market_data.strategy_selection import select_tier_aligned_strategy
from market_data.trade_approval_routing import (
    assert_trade_execution_eligible,
    approve_trade_pending,
    execution_intent_would_emit,
    reject_trade_pending,
    submit_candidate_trade_for_approval,
)


def _scope(**overrides) -> ParticipantScope:
    d = dict(
        participant_id="sean",
        participant_type="human",
        account_id="acct_001",
        wallet_context="wallet_main",
        risk_tier="tier_2",
        interaction_path="telegram",
    )
    d.update(overrides)
    return ParticipantScope(**d)


def _candidate() -> object:
    scope = _scope()
    ev = StrategyEvaluationV1(
        participant_scope=scope,
        symbol="SOL-USD",
        strategy_version=STRATEGY_VERSION,
        evaluation_outcome="long_bias",
        confidence=0.85,
        abstain_reason=None,
        gate_state="ok",
        primary_price=150.0,
        comparator_price=151.0,
        spread_pct=0.0066,
        tier_thresholds_used={"min_confidence": 0.4, "max_spread_pct": 0.004, "signal_spread_pct": 0.0003},
        evaluated_at="2026-03-30T12:00:00+00:00",
        error=None,
    )
    gate = run_pre_trade_fast_gate(ev, simulation=None, gated_at="2026-03-30T12:01:00+00:00")
    sel = select_tier_aligned_strategy(ev, gate=gate, selected_at="2026-03-30T12:02:00+00:00")
    return build_candidate_trade_v1(
        ev,
        sel,
        gate=gate,
        expires_at_iso="2099-12-31T23:59:59+00:00",
        candidate_built_at="2026-03-30T12:03:00+00:00",
    )


def _call(
    app,
    path: str,
    method: str = "GET",
    body: bytes = b"",
    *,
    token: str | None = None,
) -> tuple[str, bytes]:
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "SCRIPT_NAME": "",
        "QUERY_STRING": "",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": BytesIO(body),
        "wsgi.errors": BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": True,
        "CONTENT_LENGTH": str(len(body)),
    }
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    setup_testing_defaults(environ)
    status_holder: list[str] = []

    def start_response(status: str, _headers: list) -> None:
        status_holder.append(status)

    out = b"".join(app(environ, start_response))
    return status_holder[0], out


@pytest.fixture()
def trade_db_path(tmp_path: Path) -> Path:
    p = tmp_path / "trade_l3.db"
    conn = sqlite3.connect(p)
    conn.close()
    return p


def test_submit_approve_execution_eligible(trade_db_path: Path) -> None:
    conn = sqlite3.connect(trade_db_path)
    try:
        c = _candidate()
        row = submit_candidate_trade_for_approval(conn, c, requested_by="system:test")
        aid = row["approval_id"]
        assert row["status"] == "PENDING"
        approve_trade_pending(conn, approval_id=aid, approved_by="operator", ttl_hours=24)
        assert_trade_execution_eligible(conn, aid)
        assert execution_intent_would_emit(conn=conn, approval_id=aid) is True
    finally:
        conn.close()


def test_reject_blocks_execution(trade_db_path: Path) -> None:
    conn = sqlite3.connect(trade_db_path)
    try:
        c = _candidate()
        row = submit_candidate_trade_for_approval(conn, c, requested_by="system:test")
        aid = row["approval_id"]
        reject_trade_pending(conn, approval_id=aid, approved_by="operator", decision_note="no")
        with pytest.raises(ValueError, match="status=REJECTED"):
            assert_trade_execution_eligible(conn, aid)
        assert execution_intent_would_emit(conn=conn, approval_id=aid) is False
    finally:
        conn.close()


def test_pending_blocks_execution(trade_db_path: Path) -> None:
    conn = sqlite3.connect(trade_db_path)
    try:
        c = _candidate()
        row = submit_candidate_trade_for_approval(conn, c, requested_by="system:test")
        aid = row["approval_id"]
        with pytest.raises(ValueError, match="status=PENDING"):
            assert_trade_execution_eligible(conn, aid)
    finally:
        conn.close()


def test_fingerprint_stable(trade_db_path: Path) -> None:
    conn = sqlite3.connect(trade_db_path)
    try:
        c = _candidate()
        r1 = submit_candidate_trade_for_approval(conn, c, requested_by="a")
        r2 = submit_candidate_trade_for_approval(conn, c, requested_by="b")
        assert r1["candidate_fingerprint"] == r2["candidate_fingerprint"]
        assert r1["approval_id"] != r2["approval_id"]
    finally:
        conn.close()


def test_trade_api_get_routes(trade_db_path: Path) -> None:
    conn = sqlite3.connect(trade_db_path)
    try:
        c = _candidate()
        submit_candidate_trade_for_approval(conn, c, requested_by="http")
    finally:
        conn.close()

    tok = "pytest-trade-token"
    app = make_app(trade_db_path, decision_token=tok)
    status, resp = _call(app, "/api/trade-approvals", method="GET")
    assert status.startswith("200")
    data = json.loads(resp.decode())
    assert data["ok"] is True
    assert len(data["trade_approvals"]) >= 1
    aid = data["trade_approvals"][0]["approval_id"]
    status2, resp2 = _call(app, f"/api/trade-approvals/{aid}", method="GET")
    assert status2.startswith("200")
    detail = json.loads(resp2.decode())
    assert detail["candidate"]["symbol"] == "SOL-USD"


def test_trade_api_post_decision(trade_db_path: Path) -> None:
    conn = sqlite3.connect(trade_db_path)
    try:
        c = _candidate()
        row = submit_candidate_trade_for_approval(conn, c, requested_by="http")
        aid = row["approval_id"]
    finally:
        conn.close()

    tok = "pytest-trade-token-2"
    app = make_app(trade_db_path, decision_token=tok)
    body = json.dumps({"action": "reject", "actor": "op", "reason": "risk"}).encode()
    status, resp = _call(app, f"/api/trade-approvals/{aid}/decision", method="POST", body=body, token=tok)
    assert status.startswith("200")
    data = json.loads(resp.decode())
    assert data["ok"] is True
    assert data["trade_approval"]["status"] == "REJECTED"
