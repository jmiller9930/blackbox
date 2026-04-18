"""Width+depth 15-scenario batch example — catalog-safe ATR grid + one memory-bundle row."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.scenario_contract import validate_scenarios


def _example_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "renaissance_v4" / "game_theory" / "examples" / "width_depth_15.example.json"


def test_width_depth_15_loads_and_validates() -> None:
    p = _example_path()
    if not p.is_file():
        pytest.skip("width_depth_15.example.json missing")
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert len(raw) == 15
    ok, msgs = validate_scenarios(raw, require_hypothesis=True)
    assert ok is True, msgs
    ids = [x.get("scenario_id") for x in raw]
    assert ids[-1] == "width_depth_15_memory"
    assert raw[-1].get("memory_bundle_path")


def test_width_depth_atr_pairs_in_catalog_band() -> None:
    """Manifest validator allows atr in [0.5, 6.0]; scenario overrides must match."""
    p = _example_path()
    if not p.is_file():
        pytest.skip("width_depth_15.example.json missing")
    raw = json.loads(p.read_text(encoding="utf-8"))
    for s in raw[:-1]:
        for k in ("atr_stop_mult", "atr_target_mult"):
            v = s.get(k)
            if v is not None:
                assert 0.5 <= float(v) <= 6.0
