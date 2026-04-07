"""Hermes SSE parsed price extraction (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.hermes_sse_price import price_from_hermes_parsed_entry  # noqa: E402


def test_sol_like_entry_matches_latest_feeds_shape():
    entry = {
        "id": "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
        "price": {
            "price": "8211160991",
            "conf": "3203828",
            "expo": -8,
            "publish_time": 1775594410,
        },
    }
    px, pub = price_from_hermes_parsed_entry(entry, conf_ratio_max=0.01)
    assert pub == 1775594410
    assert px is not None
    assert 80 < px < 200


def test_low_confidence_skipped():
    entry = {
        "price": {
            "price": "1000000000",
            "conf": "500000000",
            "expo": -8,
            "publish_time": 1,
        },
    }
    px, _ = price_from_hermes_parsed_entry(entry, conf_ratio_max=0.001)
    assert px is None
