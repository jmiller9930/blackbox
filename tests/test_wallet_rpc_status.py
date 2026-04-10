"""Wallet RPC status merge — avoid spurious disconnect when getHealth flakes but getBalance works."""

from __future__ import annotations

from modules.wallet.solana_wallet import _rpc_status_after_balance_probe


def test_rpc_ok_when_health_ok_without_balance_logic() -> None:
    h = {"ok": True, "detail": {"result": "ok"}}
    assert _rpc_status_after_balance_probe(h, balance_err=None, lamports=1) == h


def test_rpc_ok_when_health_fails_but_balance_succeeds() -> None:
    h = {"ok": False, "detail": "timeout"}
    merged = _rpc_status_after_balance_probe(h, balance_err=None, lamports=0)
    assert merged["ok"] is True
    assert "getBalance succeeded" in str(merged.get("detail"))


def test_rpc_still_bad_when_health_and_balance_fail() -> None:
    h = {"ok": False, "detail": "timeout"}
    merged = _rpc_status_after_balance_probe(h, balance_err="connection refused", lamports=None)
    assert merged["ok"] is False
