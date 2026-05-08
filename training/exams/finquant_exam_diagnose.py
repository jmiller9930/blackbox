#!/usr/bin/env python3
"""
Turn an exam_result_*.json + finquant_adversarial_exam_v1_cases.jsonl into an
operator-facing engineering triage report: failure histogram, hard-case status,
remediation buckets per case, and optional raw-output snippets.

Usage (repo root or anywhere):
  python3 training/exams/finquant_exam_diagnose.py \\
    --exam-json /path/to/exam_result_*.json \\
    --cases training/exams/finquant_adversarial_exam_v1_cases.jsonl \\
    --preview-chars 600

With raw dumps from proctor --raw-dir:
  same, plus --raw-dir pointing at that folder to print first N chars per failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Must match finquant_exam_proctor.HARD_FAIL_CASES
HARD_FAIL_CASES = frozenset({
    "FQ-Q-0103",
    "FQ-Q-0401",
    "FQ-Q-0502",
    "FQ-Q-0602",
    "FQ-Q-0505",
})


def _load_jsonl_cases(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        cid = o.get("case_id")
        if isinstance(cid, str):
            out[cid] = o
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="FinQuant adversarial exam — failure triage")
    ap.add_argument("--exam-json", type=Path, required=True, help="exam_result_*.json from proctor")
    ap.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).parent / "finquant_adversarial_exam_v1_cases.jsonl",
        help="Frozen case pack (for remediation_map + categories)",
    )
    ap.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help="Directory of <case_id>.txt from proctor --raw-dir (optional)",
    )
    ap.add_argument("--preview-chars", type=int, default=500, help="Chars of raw preview per failed case")
    args = ap.parse_args()

    if not args.exam_json.is_file():
        print(f"Not found: {args.exam_json}", file=sys.stderr)
        return 1
    if not args.cases.is_file():
        print(f"Not found: {args.cases}", file=sys.stderr)
        return 1

    doc = json.loads(args.exam_json.read_text(encoding="utf-8"))
    scores = doc.get("scores") or {}
    results: list[dict[str, Any]] = list(doc.get("results") or [])
    by_case = _load_jsonl_cases(args.cases)

    print("\n=== FINQUANT EXAM — ENGINEERING TRIAGE ===\n")
    print(f"Exam JSON:     {args.exam_json}")
    print(f"Cases pack:    {args.cases}")
    print(f"Model:         {doc.get('model', '?')}")
    print(f"SHA256:        {(doc.get('exam_sha256') or '')[:16]}…")
    print(f"Verdict:       {scores.get('overall', '?')}")
    print(
        f"Economic:      {scores.get('economic_score')}%  "
        f"Process: {scores.get('process_score')}%  "
        f"Passed (auto): {scores.get('passed')}/{scores.get('auto_gradable')}"
    )
    print(f"Hard fails:    {scores.get('hard_rule_violations', [])}")
    print()

    # Failure code histogram (all cases)
    fc_counter: Counter[str] = Counter()
    for r in results:
        for c in r.get("failure_codes") or []:
            fc_counter[str(c)] += 1

    print("── Failure-code histogram (counts across cases) ──")
    for code, n in fc_counter.most_common():
        print(f"  {n:3d}  {code}")
    print()

    print("── Per-case (failed auto-graded first) ──")
    failed = [r for r in results if not r.get("pass")]
    for r in sorted(failed, key=lambda x: (x.get("case_id") or "")):
        cid = r.get("case_id", "?")
        case_pack = by_case.get(cid, {})
        grading = (case_pack.get("grading_v1") or {})
        rmap = grading.get("remediation_map") or {}
        cat = case_pack.get("primary_category", "?")
        fs = r.get("Final_status_returned", "?")
        codes = r.get("failure_codes") or []
        print(f"\n  {cid}  [{cat}]  model_Final_status={fs!r}  pass=False")
        if cid in HARD_FAIL_CASES:
            print("    ** HARD-GATE CASE **")
        for code in codes:
            bucket = rmap.get(code, (r.get("remediation") or {}).get(code, "?"))
            print(f"    - {code}  → remediation_bucket={bucket}")
        notes = (r.get("notes") or "").strip()
        if notes:
            print(f"    notes: {notes}")
        # Raw preview
        raw_path = r.get("raw_artifact_path")
        rd = args.raw_dir
        if raw_path and Path(raw_path).is_file():
            blob = Path(raw_path).read_text(encoding="utf-8")[: args.preview_chars]
            print(f"    raw ({args.preview_chars} chars): {blob!r}")
        elif rd:
            safe = cid.replace("/", "_").replace(" ", "_")
            p = rd / f"{safe}.txt"
            if p.is_file():
                blob = p.read_text(encoding="utf-8")[: args.preview_chars]
                print(f"    raw ({args.preview_chars} chars): {blob!r}")

    print("\n── Suggested next actions (honest, not soft-passes) ──")
    top = [c for c, _ in fc_counter.most_common(5)]
    if "schema_violation" in top:
        print(
            "  • schema_violation is high: tighten training so assistant outputs a single "
            "valid JSON object with REQUIRED_FIELDS; inspect raw/*.txt for prose or truncated JSON."
        )
    if "hard_rule_violation" in top or scores.get("hard_rule_violations"):
        print(
            "  • hard_rule_violation: add gold rows that match grader paths for the five hard IDs "
            "(ATR >1.35, leakage, same-bar, funding, short mirror) — labels must match rules, not vibes."
        )
    if any("final_status" in t for t in top):
        print(
            "  • Wrong Final_status: add contrastive rows (same packet, different allowed verdict) "
            "or widen signal in corpus for that regime."
        )

    print("\nRe-run exam with traceability:")
    print("  python3 training/exams/finquant_exam_proctor.py ... \\")
    print("    --out \"$FINQUANT_BASE/reports/exam_results/\" \\")
    print("    --raw-dir \"$FINQUANT_BASE/reports/exam_results/raw_RUN/\"")
    print("  python3 training/exams/finquant_exam_diagnose.py \\")
    print("    --exam-json \"$FINQUANT_BASE/reports/exam_results/exam_result_....json\" \\")
    print(f"    --cases {args.cases} \\")
    print("    --raw-dir \"$FINQUANT_BASE/reports/exam_results/raw_RUN/\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
