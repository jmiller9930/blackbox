"""Binance kline quote volume enrichment for canonical 5m bars."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.binance_kline_volume import (  # noqa: E402
    enrich_canonical_bar_volume_from_binance,
    fetch_binance_quote_volume_5m,
)
from market_data.canonical_bar import CanonicalBarV1  # noqa: E402
from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP, TIMEFRAME_5M  # noqa: E402
from market_data.canonical_time import candle_close_utc_exclusive  # noqa: E402


def test_fetch_quote_volume_parses_kline_row(monkeypatch: pytest.MonkeyPatch) -> None:
    op = datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)
    start_ms = int(op.timestamp() * 1000)
    payload = [
        [
            start_ms,
            "1",
            "2",
            "0.5",
            "1.5",
            "100",
            1999999999999,
            "12345.67",
            10,
            "50",
            "75",
            "0",
        ]
    ]

    class _Resp:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *a: object) -> None:
            return None

    def _urlopen(req: object, timeout: float = 0, **_kw: object) -> _Resp:  # noqa: ARG001
        return _Resp()

    monkeypatch.setenv("BLACKBOX_BINANCE_KLINE_ENABLED", "1")
    with patch("urllib.request.urlopen", _urlopen):
        v = fetch_binance_quote_volume_5m(binance_symbol="SOLUSDT", candle_open_utc=op)
    assert v == pytest.approx(12345.67)


def test_fetch_returns_none_on_open_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    op = datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)
    wrong_ms = int(op.timestamp() * 1000) + 300_000
    payload = [[wrong_ms, "1", "2", "0.5", "1.5", "100", 0, "99.0", 1, "1", "1", "0"]]

    class _Resp:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *a: object) -> None:
            return None

    with patch("urllib.request.urlopen", lambda *a, **k: _Resp()):
        v = fetch_binance_quote_volume_5m(binance_symbol="SOLUSDT", candle_open_utc=op)
    assert v is None


def test_enrich_sets_volume_base(monkeypatch: pytest.MonkeyPatch) -> None:
    op = datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)
    meid = "SOL-PERP_5m_2026-04-01T19:55:00Z"
    bar = CanonicalBarV1(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        tick_symbol="SOL-USD",
        timeframe=TIMEFRAME_5M,
        candle_open_utc=op,
        candle_close_utc=candle_close_utc_exclusive(op),
        market_event_id=meid,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        tick_count=3,
        volume_base=None,
        price_source="pyth_primary",
    )
    monkeypatch.setenv("BLACKBOX_BINANCE_KLINE_ENABLED", "1")
    start_ms = int(op.timestamp() * 1000)
    payload = [[start_ms, "1", "2", "0.5", "1.5", "100", 0, "999.5", 1, "1", "1", "0"]]

    class _Resp:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *a: object) -> None:
            return None

    with patch("urllib.request.urlopen", lambda *a, **k: _Resp()):
        out, meta = enrich_canonical_bar_volume_from_binance(bar)
    assert out.volume_base == pytest.approx(999.5)
    assert meta.get("quote_volume_usdt") == pytest.approx(999.5)


def test_enrich_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    op = datetime(2026, 4, 1, 19, 55, 0, tzinfo=timezone.utc)
    bar = CanonicalBarV1(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        tick_symbol="SOL-USD",
        timeframe=TIMEFRAME_5M,
        candle_open_utc=op,
        candle_close_utc=candle_close_utc_exclusive(op),
        market_event_id="SOL-PERP_5m_2026-04-01T19:55:00Z",
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        tick_count=3,
        volume_base=None,
        price_source="pyth_primary",
    )
    monkeypatch.setenv("BLACKBOX_BINANCE_KLINE_ENABLED", "0")
    out, meta = enrich_canonical_bar_volume_from_binance(bar)
    assert out.volume_base is None
    assert meta.get("skipped") == "disabled"
