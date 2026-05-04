#!/usr/bin/env python3
"""
Validate finquant_agentic_qa_v1 JSONL rows against PROJECT_REQUISITES rules.

  python3 training/validate_agentic_corpus_v1.py [path.jsonl]
  python3 training/validate_agentic_corpus_v1.py --corpus /data/.../corpus.jsonl --store /data/.../exemplar_store.jsonl

Defaults to training/corpus_v05_agentic_seed.jsonl and repo memory store.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_store(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        mid = obj.get("memory_id")
        if isinstance(mid, str):
            out[mid] = obj
    return out


def _fail(msg: str) -> None:
    print(f"VALIDATION_FAIL: {msg}", file=sys.stderr)


def validate_row(row: dict, memory_ids: set[str], path: str, line_no: int) -> list[str]:
    errs: list[str] = []
    prefix = f"{path}:{line_no}"
    ts = row.get("training_schema")
    if ts != "finquant_agentic_qa_v1":
        errs.append(f"{prefix} training_schema expected finquant_agentic_qa_v1 got {ts!r}")

    out = row.get("output")
    if not isinstance(out, dict):
        errs.append(f"{prefix} missing output object")
        return errs

    hy = out.get("hypotheses_v1")
    if not isinstance(hy, list) or len(hy) < 2:
        errs.append(f"{prefix} hypotheses_v1 must have length >= 2")

    if isinstance(hy, list):
        for i, h in enumerate(hy):
            if not isinstance(h, dict):
                errs.append(f"{prefix} hypothesis[{i}] not an object")
                continue
            for k in ("supporting_evidence", "counter_evidence", "confidence"):
                if k not in h:
                    errs.append(f"{prefix} hypothesis[{i}] missing {k}")

    c1 = out.get("confidence_gap_v1")
    idk = out.get("i_dont_know_triggered")
    if isinstance(c1, (int, float)) and idk is False:
        if c1 < 0.20:
            errs.append(f"{prefix} confidence_gap_v1 {c1} < 0.20 requires i_dont_know_triggered true")

    adj = out.get("threshold_adjustment_proposal_v1")
    if isinstance(adj, dict):
        direction = adj.get("direction")
        if direction == "less_conservative":
            errs.append(f"{prefix} forbidden threshold direction less_conservative")
        evid = adj.get("evidence_memory_ids")
        prop = adj.get("proposed_change", "")
        if prop and str(prop).lower() != "no_change" and direction != "no_change":
            if not isinstance(evid, list) or len(evid) < 1:
                errs.append(f"{prefix} threshold proposal requires evidence_memory_ids")
            elif isinstance(evid, list):
                for mid in evid:
                    if mid not in memory_ids:
                        errs.append(f"{prefix} unknown evidence_memory_id {mid!r}")

    inp = row.get("input")
    if isinstance(inp, dict):
        rm = inp.get("retrieved_memory_v1")
        if isinstance(rm, list):
            for item in rm:
                if isinstance(item, dict):
                    mid = item.get("memory_id")
                    if isinstance(mid, str) and mid not in memory_ids:
                        errs.append(f"{prefix} retrieved_memory_v1 cites unknown {mid!r}")

    exp = out.get("expectancy_check_v1")
    if exp is not None:
        if not isinstance(exp, dict):
            errs.append(f"{prefix} expectancy_check_v1 must be object or omitted")
        else:
            for k in ("planned_r_multiple", "breakeven_win_rate_required", "contributes_to_long_run_math"):
                if k not in exp:
                    errs.append(f"{prefix} expectancy_check_v1 missing {k}")

    lr = out.get("learning_record_candidate_v1")
    if isinstance(lr, dict):
        sig = lr.get("setup_signature")
        if not sig or not str(sig).strip():
            errs.append(f"{prefix} learning_record_candidate_v1.setup_signature required")

    rc = out.get("risk_context_v1")
    rec = out.get("recommended_risk_pct")
    if not isinstance(rc, dict):
        errs.append(f"{prefix} output.risk_context_v1 required object")
    else:
        for k in (
            "baseline_risk_pct",
            "volatility_factor",
            "structure_factor",
            "signal_factor",
            "session_factor",
            "health_factor",
            "final_risk_pct",
            "risk_bounds",
            "factor_notes",
        ):
            if k not in rc:
                errs.append(f"{prefix} risk_context_v1 missing {k}")
        rb = rc.get("risk_bounds")
        if not isinstance(rb, dict) or "min" not in rb or "max" not in rb:
            errs.append(f"{prefix} risk_context_v1.risk_bounds must be object with min,max")
        fn = rc.get("factor_notes")
        if not isinstance(fn, dict) or not fn:
            errs.append(f"{prefix} risk_context_v1.factor_notes must be non-empty object")
    if not isinstance(rec, (int, float)):
        errs.append(f"{prefix} output.recommended_risk_pct must be number")
    elif isinstance(rc, dict) and "final_risk_pct" in rc:
        if abs(float(rec) - float(rc["final_risk_pct"])) > 1e-9:
            errs.append(
                f"{prefix} recommended_risk_pct must equal risk_context_v1.final_risk_pct "
                f"(got {rec} vs {rc.get('final_risk_pct')})"
            )

    return errs


def main() -> int:
    repo_training = Path(__file__).resolve().parent
    default_jsonl = repo_training / "corpus_v05_agentic_seed.jsonl"
    default_store = repo_training / "finquant_memory" / "exemplar_store.jsonl"

    ap = argparse.ArgumentParser(description="Validate finquant_agentic_qa_v1 JSONL")
    ap.add_argument(
        "corpus",
        nargs="?",
        type=Path,
        default=default_jsonl,
        help="JSONL corpus path",
    )
    ap.add_argument("--store", type=Path, default=None, help="exemplar_store.jsonl path")
    args = ap.parse_args()
    target = args.corpus
    target = target.expanduser().resolve()
    if not target.is_file():
        _fail(f"file not found: {target}")
        return 2

    store_path = (args.store or default_store).expanduser().resolve()
    if not store_path.is_file():
        _fail(f"memory store not found: {store_path}")
        return 2
    memory_ids = set(load_store(store_path).keys())

    all_errs: list[str] = []
    with target.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            all_errs.extend(validate_row(row, memory_ids, str(target), n))

    if all_errs:
        for e in all_errs:
            print(e, file=sys.stderr)
        _fail(f"{len(all_errs)} issue(s)")
        return 1

    print(f"OK — {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
