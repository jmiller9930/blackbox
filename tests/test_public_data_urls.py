"""Canonical Hermes / Binance URL helpers (``market_data.public_data_urls``)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data import public_data_urls as u  # noqa: E402


def test_defaults_match_blackbox_origins() -> None:
    for k in (
        "PYTH_HERMES_BASE_URL",
        "HERMES_PYTH_BASE_URL",
        "BINANCE_API_BASE_URL",
        "BINANCE_REST_BASE_URL",
    ):
        os.environ.pop(k, None)
    assert u.pyth_hermes_origin() == "https://hermes.pyth.network"
    assert u.binance_api_origin() == "https://api.binance.com"


def test_origins_strip_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTH_HERMES_BASE_URL", "https://hermes.example/")
    monkeypatch.setenv("BINANCE_API_BASE_URL", "https://api.binance.example/")
    assert u.pyth_hermes_origin() == "https://hermes.example"
    assert u.binance_api_origin() == "https://api.binance.example"


def test_hermes_latest_and_stream_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTH_HERMES_BASE_URL", raising=False)
    fid = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
    latest = u.hermes_price_latest_parsed_url(fid)
    assert latest.startswith("https://hermes.pyth.network/v2/updates/price/latest?")
    assert f"ids[]={fid}" in latest
    assert "parsed=true" in latest
    stream = u.hermes_price_stream_url(fid)
    assert stream == (
        "https://hermes.pyth.network/v2/updates/price/stream?"
        f"ids[]={fid}"
    )


def test_binance_ping_klines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_API_BASE_URL", raising=False)
    assert u.binance_ping_url() == "https://api.binance.com/api/v3/ping"
    k = u.binance_klines_url(symbol="SOLUSDT", interval="5m", limit=2)
    assert k == "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=2"
