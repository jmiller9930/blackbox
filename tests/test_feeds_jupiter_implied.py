"""Jupiter quote parsing (mocked HTTP)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.feeds_jupiter import fetch_jupiter_implied_sol_usd  # noqa: E402


def test_implied_usd_per_sol_from_quote():
    # 150 USDC atomic (6 dp) for 1 SOL → 150 USD/SOL
    payload = {"outAmount": "150000000"}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def read(self):
            return json.dumps(payload).encode("utf-8")

    with patch("market_data.feeds_jupiter.urlopen", return_value=FakeResp()):
        q = fetch_jupiter_implied_sol_usd(in_lamports=1_000_000_000, quote_url="https://x/v6/quote")
    assert q.price is not None
    assert abs(q.price - 150.0) < 1e-6
