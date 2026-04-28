#!/usr/bin/env python3
"""Validate FinQuant v0.1 JSONL structure and verifier contract strings."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

REQUIRED_HEADINGS = (
    "Claim reviewed:",
    "Math verdict:",
    "Risk/PnL verdict:",
    "Indicator validity:",
    "Regime considerations:",
    "Failure modes / edge cases:",
    "Leakage / overfit concerns:",
    "Policy-vs-implementation concerns:",
    "DATA evidence required:",
    "Final verifier status:",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True)
    args = ap.parse_args()
    path = Path(args.jsonl)
    cat_counts: Counter[int] = Counter()
    polar: Counter[str] = Counter()
    heading_miss_records = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        out = o.get("output", "")
        bad = any(h not in out for h in REQUIRED_HEADINGS)
        if bad:
            heading_miss_records += 1
        m = o.get("meta", {})
        cat_counts[int(m.get("category_id", -1))] += 1
        polar[str(m.get("polarity", "?"))] += 1

    n = sum(cat_counts.values())
    adv_frac = polar.get("adversarial", 0) / n if n else 0
    print("total", n)
    print("adversarial_frac", round(adv_frac, 4))
    print("polarity", dict(polar))
    print("categories", dict(sorted(cat_counts.items())))
    print("records_missing_any_heading", heading_miss_records)


if __name__ == "__main__":
    main()
