"""DV-ARCH-CANONICAL-POLICY-VOCABULARY-063 — indicator vocabulary + selective declarations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from renaissance_v4.policy_spec.indicators_v1 import (
    INDICATOR_KIND_VOCABULARY,
    validate_indicators_section,
)
from renaissance_v4.policy_spec.normalize import normalize_policy


def test_empty_indicators_valid() -> None:
    assert validate_indicators_section(None) == []
    assert validate_indicators_section({}) == []
    assert validate_indicators_section({"declarations": [], "gates": []}) == []


def test_declared_ema_rsi_validates_params() -> None:
    sec = {
        "schema_version": "policy_indicators_v1",
        "declarations": [
            {"id": "fast", "kind": "ema", "params": {"period": 9}},
            {"id": "slow", "kind": "ema", "params": {"period": 21}},
            {"id": "r", "kind": "rsi", "params": {"period": 14}},
        ],
        "gates": [{"indicator_id": "r", "operator": "lte", "value": 30}],
    }
    assert validate_indicators_section(sec) == []


def test_unknown_kind_fails() -> None:
    sec = {
        "declarations": [{"id": "x", "kind": "made_up_indicator", "params": {}}],
        "gates": [],
    }
    errs = validate_indicators_section(sec)
    assert any("unknown kind" in e for e in errs)


def test_macd_missing_param_fails() -> None:
    sec = {
        "declarations": [{"id": "m", "kind": "macd", "params": {"fast_period": 12}}],
        "gates": [],
    }
    errs = validate_indicators_section(sec)
    assert any("slow_period" in e or "signal_period" in e for e in errs)


def test_undeclared_macd_not_validated() -> None:
    """Policy only declares RSI — MACD params are not checked."""
    sec = {
        "declarations": [{"id": "r", "kind": "rsi", "params": {"period": 14}}],
        "gates": [],
    }
    assert validate_indicators_section(sec) == []


def test_gate_unknown_indicator_id_fails() -> None:
    sec = {
        "declarations": [{"id": "r", "kind": "rsi", "params": {"period": 14}}],
        "gates": [{"indicator_id": "nosuch", "operator": "lt", "value": 50}],
    }
    errs = validate_indicators_section(sec)
    assert any("must match" in e for e in errs)


def test_unknown_top_level_key_fails() -> None:
    errs = validate_indicators_section({"declarations": [], "gates": [], "junk_field": 1})
    assert any("unknown keys" in e for e in errs)


def test_normalize_merges_indicators() -> None:
    out = normalize_policy(
        {
            "policy_id": "kitchen_test_v1",
            "timeframe": "5m",
            "indicators": {
                "declarations": [{"id": "r", "kind": "rsi", "params": {"period": 14}}],
                "gates": [],
            },
        }
    )
    assert out["indicators"]["schema_version"] == "policy_indicators_v1"
    assert len(out["indicators"]["declarations"]) == 1
    assert out["indicators"]["declarations"][0]["kind"] == "rsi"


def test_vocabulary_includes_minimal_directive_list() -> None:
    required = {
        "ema",
        "sma",
        "rsi",
        "atr",
        "macd",
        "bollinger_bands",
        "vwap",
        "supertrend",
        "stochastic",
        "adx",
        "volume_filter",
        "divergence",
        "body_measurement",
        "fixed_threshold",
        "threshold_group",
    }
    assert required <= INDICATOR_KIND_VOCABULARY


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_harness_echoes_policy_indicators_json() -> None:
    root = Path(__file__).resolve().parents[1]
    fix = root / "tests" / "fixtures" / "policy_intake" / "minimal_direction_policy.ts"
    if not fix.is_file():
        pytest.skip("fixture missing")
    harness = root / "renaissance_v4" / "policy_intake" / "run_ts_intake_eval.mjs"
    env = dict(os.environ)
    env["RV4_POLICY_INDICATORS_JSON"] = json.dumps(
        {
            "schema_version": "policy_indicators_v1",
            "declarations": [
                {"id": "a", "kind": "ema", "params": {"period": 9}},
                {"id": "b", "kind": "rsi", "params": {"period": 14}},
            ],
            "gates": [],
        }
    )
    r = subprocess.run(
        ["node", str(harness), str(fix.resolve()), "120"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    obj = json.loads(lines[-1])
    assert obj.get("ok") is True
    pi = obj.get("policy_indicators") or {}
    assert pi.get("validated") is True
    assert pi.get("declaration_count") == 2
    assert set(pi.get("kinds") or []) == {"ema", "rsi"}
