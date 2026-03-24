#!/usr/bin/env python3
"""Score Directive 4.6.4 benchmarks: keyword hints + red-flag detection (heuristic)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from anna_modules.analysis import build_analysis
from telegram_interface.response_formatter import format_response

from run_anna_benchmark_4_6_4 import BENCHMARKS, _ctx

# Minimum "strategy" terms we expect somewhere in user-visible text for a pass-ish signal.
GOOD_HINTS: list[tuple[int, list[str]]] = [
    (1, ["momentum", "wick", "volume", "structure", "stop", "profit", "partial", "reversal", "stall"]),
    (2, ["follow", "reject", "wick", "hold", "breakout", "range", "volume", "trap", "false"]),
    (3, ["volume", "divergence", "rsi", "confidence", "skip", "reduce", "weak"]),
    (4, ["spread", "slippage", "fill", "wide", "confidence", "delay", "skip"]),
    (5, ["61", "65", "threshold", "forward", "not", "below", "pass", "execute"]),
    (6, ["pause", "loss", "cool", "low", "volume", "stop", "halt"]),
    (7, ["partial", "target", "momentum", "resistance", "trail", "structure", "profit"]),
    (8, ["spread", "volume", "divergence", "confidence", "veto", "refuse", "filter"]),
    (9, ["spread", "fill", "environment", "signal", "learn", "execution", "slippage"]),
    (10, ["log", "feedback", "validate", "clarif", "correct", "evidence", "rule"]),
]

RED_FLAGS = (
    "guardrail mode unknown",
    "i'll walk through risk and what i'd watch",
    "without tight keyword tags",
)


def _full_text(prompt: str) -> str:
    a = build_analysis(prompt, **_ctx())
    interp = a.get("interpretation") or {}
    summary = str(interp.get("summary") or "")
    payload = {"kind": "anna", "data": {"anna_analysis": a, "stored_task_id": None}}
    telegram = format_response(payload, user_display_name="Sean")
    return (summary + "\n" + telegram).lower()


def main() -> None:
    print("Directive 4.6.4 — heuristic score (keyword coverage + red flags)\n")
    print("Pass* = at least 2 good-hint terms AND no red-flag phrase in combined summary+Telegram.\n")
    passed = 0
    for i, (_title, prompt) in enumerate(BENCHMARKS, 1):
        blob = _full_text(prompt)
        hints = next(h for n, h in GOOD_HINTS if n == i)
        hit = sum(1 for t in hints if t in blob)
        bad = [r for r in RED_FLAGS if r in blob]
        ok = hit >= 2 and not bad
        if ok:
            passed += 1
        status = "PASS*" if ok else "FAIL"
        print(f"Benchmark {i}: {status}  (good-hint hits: {hit}/{len(hints)}, red_flags: {bad or 'none'})")
        print(f"  prompt: {prompt[:72]}...")
        print()
    print(f"Total PASS*: {passed}/10")
    print("\n*Heuristic only; directive also requires analytical depth and strategy alignment.")


if __name__ == "__main__":
    main()
