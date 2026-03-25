from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "runtime"))

from data_clients import market_data
from messaging_interface.live_data import extract_symbol, requires_live_data, wants_spread
from telegram_interface.agent_dispatcher import dispatch
from telegram_interface.message_router import RoutedMessage
from telegram_interface.response_formatter import format_response


@pytest.mark.parametrize(
    "q, expected",
    [
        ("Anna, what is the current price of SOL?", True),
        ("what is SOL trading at", True),
        ("current spread on BTC", True),
        ("what is a spread?", False),
        ("explain liquidity", False),
    ],
)
def test_requires_live_data_v1(q: str, expected: bool) -> None:
    assert requires_live_data(q) is expected


def test_extract_symbol_v1() -> None:
    assert extract_symbol("current price of SOL") == "SOL"
    assert extract_symbol("live price of ethereum") == "ETH"
    assert extract_symbol("spread on BTCUSDT?") == "BTC"


def test_wants_spread_v1() -> None:
    assert wants_spread("current spread on SOL") is True
    assert wants_spread("current price of SOL") is False


def test_market_data_price_success_with_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"bidPrice": "123.40", "askPrice": "123.50"}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(market_data.urllib.request, "urlopen", lambda *a, **k: _Resp())
    out = market_data.get_price("SOL")
    assert out["ok"] is True
    assert out["symbol"] == "SOL"
    assert out["source"] == "binance"
    assert out["price"] == pytest.approx(123.45)


def test_dispatch_live_data_success_uses_source(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = {
        "ok": True,
        "symbol": "SOL",
        "price": 123.45,
        "bid": 123.40,
        "ask": 123.50,
        "spread": 0.10,
        "source": "binance",
        "as_of": "2026-03-25T00:00:00Z",
        "note": "",
    }
    monkeypatch.setattr("data_clients.market_data.get_price", lambda symbol: fake)
    payload = dispatch(RoutedMessage("anna", "Anna, what is the current price of SOL?"))
    aa = payload["data"]["anna_analysis"]
    assert payload["kind"] == "anna"
    assert aa["pipeline"]["answer_source"] == "live_market_data"
    assert "Source: binance" in aa["interpretation"]["summary"]


def test_dispatch_live_data_failure_uses_exact_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = {
        "ok": False,
        "symbol": "SOL",
        "source": "binance",
        "as_of": "",
        "note": "network_error",
    }
    monkeypatch.setattr("data_clients.market_data.get_price", lambda symbol: fake)
    payload = dispatch(RoutedMessage("anna", "Anna, what is the current price of SOL?"))
    out = format_response(payload)
    assert "I don’t have access to live market data for that request right now." in out
    assert "re-evaluate" not in out.lower()

