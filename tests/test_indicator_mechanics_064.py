"""DV-ARCH-INDICATOR-MECHANICS-064 — mechanical registry, intake failure modes, harness context."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from renaissance_v4.policy_intake.pipeline import run_intake_pipeline
from renaissance_v4.policy_spec.indicator_mechanics import (
    MECHANICAL_CLASS_BY_KIND,
    MechanicalClass,
    assert_registry_covers_vocabulary,
)
from renaissance_v4.policy_spec.indicators_v1 import INDICATOR_KIND_VOCABULARY


def test_mechanical_registry_covers_full_vocabulary() -> None:
    assert_registry_covers_vocabulary()
    for k in INDICATOR_KIND_VOCABULARY:
        assert k in MECHANICAL_CLASS_BY_KIND
        assert MECHANICAL_CLASS_BY_KIND[k] in {
            MechanicalClass.MECHANICALLY_SUPPORTED,
            MechanicalClass.DECLARATION_ONLY,
            MechanicalClass.UNSUPPORTED,
        }


def test_declaration_only_divergence_fails_intake_json() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = {
        "policy_id": "kitchen_decl_test_v1",
        "timeframe": "5m",
        "indicators": {
            "declarations": [
                {
                    "id": "div1",
                    "kind": "divergence",
                    "params": {"lookback": 5, "indicator_ref": "rsi_main"},
                }
            ],
            "gates": [],
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    rep = run_intake_pipeline(root, raw, "policy.json", test_window_bars=120)
    assert rep.get("pass") is not True
    errs = rep.get("errors") or []
    assert any("indicator_declared_but_not_mechanically_supported: divergence" in e for e in errs)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_ts_fixture_with_supported_indicators_passes_e2e() -> None:
    root = Path(__file__).resolve().parents[1]
    fix = root / "tests" / "fixtures" / "policy_intake" / "minimal_direction_policy.ts"
    if not fix.is_file():
        pytest.skip("fixture missing")
    raw = fix.read_bytes()
    rep = run_intake_pipeline(root, raw, "minimal_direction_policy.ts", test_window_bars=400)
    assert rep.get("pass") is True, rep.get("errors")
    det = (rep.get("stages") or {}).get("stage_5_deterministic") or {}
    assert det.get("harness_revision") == "int_ohlc_v4"
    ctx = det.get("indicator_evaluation_context") or {}
    last = ctx.get("last_bar_indicators") or {}
    assert "rsi_main" in last
    assert isinstance(last.get("rsi_main"), (int, float))


def test_ts_embedded_block_parsed_into_canonical() -> None:
    from renaissance_v4.policy_intake.pipeline import _extract_rv4_policy_indicators_json_from_ts

    src = """
/* RV4_POLICY_INDICATORS
{"schema_version":"policy_indicators_v1","declarations":[{"id":"x","kind":"ema","params":{"period":9}}],"gates":[]}
*/
export const policy_id = 't';
"""
    got = _extract_rv4_policy_indicators_json_from_ts(src)
    assert got is not None
    assert got["declarations"][0]["kind"] == "ema"
