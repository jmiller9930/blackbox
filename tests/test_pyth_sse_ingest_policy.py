"""pyth_sse_ingest tick policy — full-tape default, no silent price_change fallback."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _load_ingest():
    root = Path(__file__).resolve().parents[1]
    trading = root / "scripts" / "trading"
    if str(trading) not in sys.path:
        sys.path.insert(0, str(trading))
    import pyth_sse_ingest as m  # noqa: PLC0415

    return importlib.reload(m)


def test_tick_policy_invalid_env_defaults_to_every_message(monkeypatch) -> None:
    monkeypatch.setenv("PYTH_SSE_TICK_POLICY", "not_a_real_policy")
    m = _load_ingest()
    assert m._tick_policy() == "every_message"


def test_tick_policy_explicit_price_change(monkeypatch) -> None:
    monkeypatch.setenv("PYTH_SSE_TICK_POLICY", "price_change")
    m = _load_ingest()
    assert m._tick_policy() == "price_change"
