#!/usr/bin/env python3
"""Emit remediation_json_surface_v05.jsonl (80 rows) with instruction lockstep to instruction_contract.

Duplicates the export_exam_remediation_corpus generators but patches INSTRUCTION to
training/exams/instruction_contract.py::TRAINING_INSTRUCTION so new supervision matches proctor.

Usage: python3 training/build_remediation_json_surface_v05.py
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]  # blackbox repo root
_TRAIN = _REPO / "training"
sys.path.insert(0, str(_TRAIN))

_IC = _TRAIN / "exams" / "instruction_contract.py"
_spec = importlib.util.spec_from_file_location("instruction_contract", _IC)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

import export_exam_remediation_corpus as er

er.INSTRUCTION = _mod.TRAINING_INSTRUCTION


def main() -> int:
    out = _TRAIN / "remediation_json_surface_v05.jsonl"
    rng = random.Random(43)
    rows: list = []
    rows += er.generate_atr_hard_rule(rng)
    rows += er.generate_lookahead(rng)
    rows += er.generate_same_bar(rng)
    rows += er.generate_funding_sign(rng)
    rows += er.generate_abstention(rng)
    rows = rows[:80]
    out_rows = []
    for i, row in enumerate(rows):
        row = json.loads(json.dumps(row))
        cid = row.get("case_id", "ROW")
        row["case_id"] = f"{cid}-V05JS-{i:03d}"
        tags = list(row.get("secondary_tags") or [])
        tags.append("json_surface_v05")
        row["secondary_tags"] = list(dict.fromkeys(tags))
        out_rows.append(row)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(out_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
