#!/usr/bin/env python3
"""Summarize a shadow_bot log: Pyth, signals, errors (grep-based, no deps)."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: summarize_log.py <logfile>")
        return 2
    p = Path(sys.argv[1])
    if not p.is_file():
        print(f"missing: {p}")
        return 1
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    def count(pat: str) -> int:
        r = re.compile(pat, re.I)
        return sum(1 for ln in lines if r.search(ln))

    summary = {
        "lines": len(lines),
        "pyth_sse_connected": count(r"Pyth SSE connected"),
        "pyth_price": count(r"Pyth price:"),
        "signal_detected": count(r"Signal detected"),
        "signals_line": count(r"Signals:\s+short="),
        "long_signal_true": count(r"longSignal.*true|Long=\s*true"),
        "short_signal_true": count(r"shortSignal.*true|Short=\s*true"),
        "error": count(r"\berror\b|\bERROR\b|Error:"),
        "drift": count(r"Drift|driftClient|initDrift"),
    }
    print("--- shadow_bot log summary ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
