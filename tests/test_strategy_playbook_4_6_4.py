"""Directive 4.6.4 — strategy playbook covers all benchmark prompts."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))
sys.path.insert(0, str(ROOT / "scripts" / "runtime" / "tools"))

from anna_modules.analysis import build_analysis
from run_anna_benchmark_4_6_4 import BENCHMARKS, _ctx


def test_all_benchmarks_apply_playbook() -> None:
    for _title, prompt in BENCHMARKS:
        a = build_analysis(prompt, **_ctx())
        assert a.get("strategy_playbook_applied") is True, f"no playbook: {prompt[:60]}"


def test_confidence_threshold_mentions_gate() -> None:
    a = build_analysis(
        "If a setup scores 61 confidence after adjustments and our threshold is 65, what should happen?",
        **_ctx(),
    )
    s = str((a.get("interpretation") or {}).get("summary") or "").lower()
    assert "61" in s and "65" in s
    assert "not" in s or "no-go" in s or "fail" in s


def test_no_guardrail_unknown_in_suggested_rationale() -> None:
    a = build_analysis("If RSI divergence is present but SOL-PERP volume is weak, should we still take the trade?", **_ctx())
    r = str((a.get("suggested_action") or {}).get("rationale") or "").lower()
    assert "guardrail mode unknown" not in r
