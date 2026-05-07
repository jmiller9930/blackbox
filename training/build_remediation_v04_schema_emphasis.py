#!/usr/bin/env python3
"""Double remediation v0.3 with schema-emphasis instruction clones (repo-local).

Reads training/remediation_corpus_v0.3.jsonl; writes training/remediation_corpus_v0.4.jsonl
(original rows + rows with case_id '-SCH' suffix and EXAM_OUTPUT_TOP_KEYS instruction block).

Usage: python3 training/build_remediation_v04_schema_emphasis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCHEMA_BLOCK = (
    "\n\nEXAM_OUTPUT_TOP_KEYS: The JSON you output must include these keys at the top level "
    "with exact spelling: Final_status, Claim_reviewed, Math_verdict, Numeric_answer, "
    "Leakage_check, Policy_alignment, DATA_or_assumption_gaps, rule_checks. "
    "The rule_checks value must be an object with boolean fields: atr_filter_passed, "
    "spread_liquidity_ok, data_quality_passed, confidence_gap_passed. "
    "Keep all other required finquant_agentic_qa_v1 fields in the same single JSON object."
)


def main() -> int:
    root = Path(__file__).resolve().parent
    src = root / "remediation_corpus_v0.3.jsonl"
    dst = root / "remediation_corpus_v0.4.jsonl"
    if not src.is_file():
        print(f"Missing {src}", file=sys.stderr)
        return 1
    base: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        base.append(json.loads(line))
    out: list[dict] = []
    out.extend(base)
    for r in base:
        r2 = json.loads(json.dumps(r))
        cid = r2.get("case_id", "row")
        r2["case_id"] = f"{cid}-SCH"
        r2["instruction"] = str(r2.get("instruction", "")) + _SCHEMA_BLOCK
        out.append(r2)
    dst.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in out) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {dst} ({len(out)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
