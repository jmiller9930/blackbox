"""Hermes SSE parsed price extraction (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from market_data.hermes_sse_price import (  # noqa: E402
    hermes_price_identity_from_entry,
    human_price_float_from_identity,
    price_from_hermes_parsed_entry,
    tape_price_and_publish_from_entry,
)


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


def test_hermes_identity_exact_no_rounding_merge():
    a = {"price": {"price": "8192304846", "conf": "1", "expo": -8, "publish_time": 1}}
    b = {"price": {"price": "8192200001", "conf": "1", "expo": -8, "publish_time": 2}}
    ia = hermes_price_identity_from_entry(a)
    ib = hermes_price_identity_from_entry(b)
    assert ia is not None and ib is not None
    assert ia != ib
    assert human_price_float_from_identity(ia[0], ia[1]) != human_price_float_from_identity(ib[0], ib[1])


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


def test_tape_path_includes_low_confidence_parse():
    """Full tape: same entry still yields price + publish when conf gate is not applied."""
    entry = {
        "price": {
            "price": "1000000000",
            "conf": "500000000",
            "expo": -8,
            "publish_time": 1,
        },
    }
    px, pub = tape_price_and_publish_from_entry(entry)
    assert px is not None
    assert pub == 1
