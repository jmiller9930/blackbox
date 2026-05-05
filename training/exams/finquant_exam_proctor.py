#!/usr/bin/env python3
"""
FinQuant Adversarial Exam — Proctor Harness

Reads finquant_adversarial_exam_v1_cases.jsonl, sends each case to Ollama,
grades the response, and emits a full report + certification string.

Usage:
  # Against fine-tuned model on trx40 local Ollama:
  python3 training/exams/finquant_exam_proctor.py \\
    --cases training/exams/finquant_adversarial_exam_v1_cases.jsonl \\
    --model finquant-1-qwen7b-v0.1 \\
    --ollama-url http://localhost:11434 \\
    --out /data/NDE/finquant/agentic_v05/reports/exam_results/

  # Baseline comparison against vanilla qwen on .230:
  python3 training/exams/finquant_exam_proctor.py \\
    --cases training/exams/finquant_adversarial_exam_v1_cases.jsonl \\
    --model qwen2.5:7b \\
    --ollama-url http://172.20.2.230:11434 \\
    --out /data/NDE/finquant/agentic_v05/reports/exam_results/ \\
    --run-label baseline_qwen2.5_7b

Stdlib + urllib only (no requests). Runs on trx40 without extra deps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Output contract required fields ──────────────────────────────────────────
REQUIRED_FIELDS = [
    "Final_status",
    "Claim_reviewed",
    "Math_verdict",
    "Numeric_answer",
    "Leakage_check",
    "Policy_alignment",
    "DATA_or_assumption_gaps",
    "rule_checks",
]

FINAL_STATUS_ENUM = {
    "ENTER_LONG", "ENTER_SHORT", "NO_TRADE",
    "INSUFFICIENT_DATA", "FAIL",
}

HARD_FAIL_CASES = {
    "FQ-Q-0103",  # ATR hard limit
    "FQ-Q-0401",  # Lookahead leakage
    "FQ-Q-0502",  # Same-bar rule
    "FQ-Q-0602",  # Funding sign
    "FQ-Q-0505",  # SHORT ATR mirror
}

# System prompt — minimal, deferring to the user prompt instruction (matches training pattern)
SYSTEM_PROMPT = (
    "You are FinQuant, a disciplined quantitative crypto-perps reasoning agent.\n"
    "P-1 NEVER LIE. Only use data in this prompt. Never invent values.\n"
    "P-2 REASON WITH TOOLS. Cite specific indicator values (RSI, ATR, EMA) in your thesis.\n"
    "P-3 SELECTIVE ENTRY. Enter only when multiple signals align and all hard rules pass.\n"
    "P-4 PATTERN SIMILARITY. Weight governed memory records over fuzzy similarity.\n"
    "P-5 CONTEXT FIRST. Read regime before applying rules.\n"
    "P-6 LONG-RUN MATH. Aim for R >= 1.5 when entering."
)

# Exact instruction used during training (model was fine-tuned on this exact string)
TRAINING_INSTRUCTION = (
    "You are FinQuant. Use ONLY reference_facts_v1, case_assumptions_v1, "
    "context_inventory_v1, and retrieved_memory_v1. "
    "Decision applies to the LAST bar (decision_bar_index_in_window). "
    "Produce strict JSON per gold contract.\n\n"
    "The JSON must include ALL of these fields: Final_status "
    "(one of: ENTER_LONG, ENTER_SHORT, NO_TRADE, INSUFFICIENT_DATA, FAIL), "
    "Claim_reviewed, Math_verdict, Numeric_answer, Leakage_check, "
    "Policy_alignment, DATA_or_assumption_gaps, rule_checks.\n\n"
    "Output only valid JSON. No markdown, no commentary outside the JSON."
)


def build_prompt(case: dict[str, Any]) -> str:
    """Build student-facing prompt in exact training format — grading metadata stripped."""
    has_structured = "reference_facts_v1" in case or "case_assumptions_v1" in case

    if has_structured:
        # Use exact training instruction format for structured cases
        input_packet: dict[str, Any] = {}
        for k in ("case_assumptions_v1", "reference_facts_v1",
                  "context_inventory_v1", "retrieved_memory_v1"):
            if k in case:
                input_packet[k] = case[k]
        return (
            f"{TRAINING_INSTRUCTION}\n\n"
            f"Input:\n{json.dumps(input_packet, indent=2, ensure_ascii=False)}"
        )
    else:
        # Math / policy / learning cases — include all non-grader fields
        input_packet = {
            k: v for k, v in case.items()
            if k not in ("grading_v1", "human_review_required", "difficulty",
                         "exam_schema", "exam_version", "secondary_tags", "required")
        }
        return (
            "You are FinQuant. Analyze the following case and respond with a single "
            "valid JSON object containing these exact fields: Final_status "
            "(one of: ENTER_LONG, ENTER_SHORT, NO_TRADE, INSUFFICIENT_DATA, FAIL), "
            "Claim_reviewed, Math_verdict, Numeric_answer (null or number), "
            "Leakage_check (PASS or FAIL), Policy_alignment, "
            "DATA_or_assumption_gaps, rule_checks (object).\n\n"
            "Output only valid JSON. No text outside the JSON.\n\n"
            f"Case:\n{json.dumps(input_packet, indent=2, ensure_ascii=False)}"
        )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def strip_think_blocks(text: str) -> str:
    """Remove DeepSeek <think>…</think> reasoning traces before extracting JSON.
    Also handles orphaned </think> closing tags and everything before them."""
    # Full think block
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Orphaned closing tag — strip everything up to and including </think>
    text = re.sub(r"^.*?</think>", "", text, flags=re.DOTALL)
    # Bare unclosed <think> (truncated output)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    return text.strip()


def ollama_generate(
    prompt: str,
    model: str,
    ollama_url: str,
    timeout: int = 90,
) -> str:
    """Use /api/chat so Ollama applies the model's chat template correctly."""
    url = ollama_url.rstrip("/") + "/api/chat"
    payload = json.dumps({
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0.05,
            "top_p": 0.9,
            "num_ctx": 12288,
            "num_predict": 2048,
        },
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            # /api/chat returns message.content
            raw = data.get("message", {}).get("content", "")
            return strip_think_blocks(raw)
    except urllib.error.URLError as e:
        raise SystemExit(f"Ollama error at {url}: {e}") from e


def _find_json_objects(text: str) -> list[str]:
    """Find all top-level JSON objects using bracket counting (handles nesting)."""
    results = []
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                results.append(text[start:i + 1])
                start = -1
    return results


def extract_json(raw: str) -> dict[str, Any] | None:
    """Extract best JSON object from model output using proper bracket counting.
    Prefers the LAST valid top-level object (model often drafts, then produces final)."""
    raw = raw.strip()

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try markdown fences (last wins)
    for m in reversed(list(re.finditer(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL))):
        candidate = m.group(1).strip()
        objs = _find_json_objects(candidate)
        for obj in reversed(objs):
            try:
                return json.loads(obj)
            except json.JSONDecodeError:
                continue

    # Find all top-level JSON objects in raw text (last wins)
    objs = _find_json_objects(raw)
    for obj in reversed(objs):
        try:
            return json.loads(obj)
        except json.JSONDecodeError:
            continue

    return None


def normalize_numeric(val: Any) -> float | None:
    """Strip $, commas; return float or None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


_FIELD_ALIASES: dict[str, str] = {
    "final_status": "Final_status",
    "claim_reviewed": "Claim_reviewed",
    "math_verdict": "Math_verdict",
    "numeric_answer": "Numeric_answer",
    "numeric_answer_v1": "Numeric_answer",
    "leakage_check": "Leakage_check",
    "policy_alignment": "Policy_alignment",
    "data_or_assumption_gaps": "DATA_or_assumption_gaps",
    "rule_checks": "rule_checks",
    "math_verdict_v1": "Math_verdict",
}


def _normalize_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Remap lowercase / variant field names to the contract's expected keys."""
    out = dict(resp)
    for src, dst in _FIELD_ALIASES.items():
        if src in out and dst not in out:
            out[dst] = out[src]
    return out


def grade_case(
    case: dict[str, Any],
    response: dict[str, Any] | None,
    raw_output: str,
) -> dict[str, Any]:
    """Grade one case. Returns result dict."""
    case_id = case["case_id"]
    grading = case.get("grading_v1", {})
    rules = grading.get("rules") or grading.get("automated_rules") or []
    failure_codes: list[str] = []
    passes: list[bool] = []

    if response is not None:
        response = _normalize_response(response)

    if response is None:
        return {
            "case_id": case_id,
            "pass": False,
            "primary_category": case.get("primary_category"),
            "failure_codes": ["schema_violation"],
            "remediation": {"schema_violation": "data_hygiene"},
            "raw_output_sha256": sha256_text(raw_output),
            "notes": "Could not parse JSON from model output",
        }

    # Schema check: required fields
    for field in REQUIRED_FIELDS:
        if field not in response:
            failure_codes.append("schema_violation")
            passes.append(False)
            break

    # Final_status enum check
    fs = response.get("Final_status", "")
    if fs not in FINAL_STATUS_ENUM:
        failure_codes.append("schema_violation")
        passes.append(False)

    # Apply grading rules
    for rule in rules:
        rule_id = rule.get("id", "unnamed")
        path = rule.get("path", "")
        required = rule.get("required", True)

        # Resolve JSON path (simple: $.field or $.field.subfield)
        val = response
        try:
            for part in path.lstrip("$.").split("."):
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    val = None
                    break
        except Exception:
            val = None

        # Check rules
        passed = True

        if "expect_equals" in rule:
            expected = rule["expect_equals"]
            if isinstance(expected, str):
                actual = str(val).strip() if val is not None else ""
                passed = actual == expected
            elif isinstance(expected, bool):
                passed = bool(val) == expected
            else:
                passed = val == expected

        elif "expect_not_equals" in rule:
            passed = val != rule["expect_not_equals"]

        elif "expect_one_of" in rule:
            passed = val in rule["expect_one_of"]

        elif "expect_less_than" in rule:
            n = normalize_numeric(val)
            passed = n is not None and n < rule["expect_less_than"]

        elif "expect_value" in rule:
            n = normalize_numeric(val)
            expected_n = float(rule["expect_value"])
            tol = float(rule.get("max_abs_error", 0.01))
            passed = n is not None and abs(n - expected_n) <= tol

        elif "expect_contains_any" in rule:
            text = str(val or "").lower()
            passed = any(s.lower() in text for s in rule["expect_contains_any"])

        elif "expect_not_contains" in rule:
            text = str(val or "").lower()
            passed = rule["expect_not_contains"].lower() not in text

        if not passed and required:
            failure_codes.append(rule_id)
        passes.append(passed or not required)

    overall = len(failure_codes) == 0

    # Hard fail override
    if case_id in HARD_FAIL_CASES and not overall:
        failure_codes = list(set(failure_codes + ["hard_rule_violation"]))

    rem = grading.get("remediation_map", {})

    return {
        "case_id": case_id,
        "pass": overall,
        "primary_category": case.get("primary_category"),
        "failure_codes": failure_codes,
        "remediation": {code: rem.get(code, "policy_adherence") for code in failure_codes},
        "raw_output_sha256": sha256_text(raw_output),
        "Final_status_returned": response.get("Final_status"),
        "human_review_required": case.get("human_review_required", False),
        "notes": "" if overall else f"Failed rules: {failure_codes}",
    }


def score_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute E/P scores and overall verdict."""
    required = [r for r in results if not r.get("human_review_required", False)]
    total = len(required)
    passed = sum(1 for r in required if r["pass"])

    hard_violations = [
        r for r in required
        if r["case_id"] in HARD_FAIL_CASES and not r["pass"]
    ]

    all_failure_codes: list[str] = []
    remediation_buckets: dict[str, int] = {}
    for r in results:
        for code in r.get("failure_codes", []):
            all_failure_codes.append(code)
            bucket = (r.get("remediation") or {}).get(code, "policy_adherence")
            remediation_buckets[bucket] = remediation_buckets.get(bucket, 0) + 1

    # Economic score: correct Final_status on auto-gradable cases
    e_score = round((passed / total * 100) if total else 0, 1)
    # Process score: no schema violations + required fields + rule_checks present
    schema_violations = sum(1 for r in required if "schema_violation" in (r.get("failure_codes") or []))
    p_score = round(((total - schema_violations) / total * 100) if total else 0, 1)

    e_pass = e_score >= 75.0
    p_pass = p_score >= 80.0
    hard_pass = len(hard_violations) == 0
    overall = "PASS" if (e_pass and p_pass and hard_pass) else "FAIL"

    return {
        "total_cases": len(results),
        "auto_gradable": total,
        "human_review_pending": len(results) - total,
        "passed": passed,
        "failed": total - passed,
        "economic_score": e_score,
        "process_score": p_score,
        "hard_rule_violations": [r["case_id"] for r in hard_violations],
        "overall": overall,
        "remediation_buckets": remediation_buckets,
        "unique_failure_codes": sorted(set(all_failure_codes)),
    }


def print_report(model: str, exam_sha: str, results: list[dict], scores: dict) -> None:
    print(f"\n{'='*62}", flush=True)
    print("  FINQUANT ADVERSARIAL EXAM — PROCTOR REPORT", flush=True)
    print(f"{'='*62}", flush=True)
    print(f"  Model:       {model}", flush=True)
    print(f"  Exam SHA256: {exam_sha}", flush=True)
    print(f"  Date:        {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}", flush=True)
    print(f"\n  Cases:    {scores['total_cases']} total / {scores['auto_gradable']} auto-graded", flush=True)
    print(f"  Passed:   {scores['passed']} / {scores['auto_gradable']}", flush=True)
    print(f"\n  ── Scores ──────────────────────────────────────", flush=True)
    e_icon = "✓" if scores["economic_score"] >= 75 else "✗"
    p_icon = "✓" if scores["process_score"] >= 80 else "✗"
    print(f"  {e_icon} Economic  {scores['economic_score']:5.1f}%  (need ≥ 75%)", flush=True)
    print(f"  {p_icon} Process   {scores['process_score']:5.1f}%  (need ≥ 80%)", flush=True)

    if scores["hard_rule_violations"]:
        print(f"\n  ✗ Hard rule violations: {scores['hard_rule_violations']}", flush=True)
    else:
        print(f"\n  ✓ No hard rule violations", flush=True)

    print(f"\n  ── Per-Case Results ─────────────────────────────", flush=True)
    for r in results:
        icon = "✓" if r["pass"] else "✗"
        hr = " [human-review]" if r.get("human_review_required") else ""
        fs = str(r.get("Final_status_returned") or "?")
        fc = ", ".join(r.get("failure_codes") or [])
        print(f"  {icon} {r['case_id']:16s}  {fs:20s}{hr}", flush=True)
        if fc:
            print(f"      ↳ {fc}", flush=True)

    print(f"\n  ── Remediation Buckets ──────────────────────────", flush=True)
    for bucket, count in sorted(scores["remediation_buckets"].items()):
        print(f"  {bucket:20s} {count} failure(s)", flush=True)

    print(f"\n{'='*62}", flush=True)
    verdict_icon = "✓✓ PASS" if scores["overall"] == "PASS" else "✗✗ FAIL"
    print(f"  VERDICT: {verdict_icon}", flush=True)
    if scores["overall"] == "PASS":
        print(f"  CERTIFICATION: FinQuant quant exam v3 PASS — {model}", flush=True)
    else:
        print(f"  NOT CERTIFIED. Fix: {scores['unique_failure_codes']}", flush=True)
    print(f"{'='*62}\n", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="FinQuant adversarial exam proctor")
    ap.add_argument("--cases", type=Path,
                    default=Path(__file__).parent / "finquant_adversarial_exam_v1_cases.jsonl")
    ap.add_argument("--model", type=str, default="finquant-1-qwen7b-v0.1")
    ap.add_argument("--ollama-url", type=str, default="http://localhost:11434")
    ap.add_argument("--out", type=Path, default=None, help="Output directory for results JSON")
    ap.add_argument("--run-label", type=str, default=None, help="Optional label for report filename")
    ap.add_argument("--timeout", type=int, default=120, help="Per-case Ollama timeout (seconds)")
    ap.add_argument("--skip-human", action="store_true",
                    help="Skip human-review cases (grade only auto cases)")
    args = ap.parse_args()

    if not args.cases.is_file():
        raise SystemExit(f"Cases file not found: {args.cases}")

    cases = []
    with args.cases.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    # Pin exam SHA256
    exam_sha = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    print(f"[proctor] Exam file: {args.cases}", flush=True)
    print(f"[proctor] SHA256:    {exam_sha}", flush=True)
    print(f"[proctor] Cases:     {len(cases)}", flush=True)
    print(f"[proctor] Model:     {args.model} @ {args.ollama_url}", flush=True)

    results: list[dict[str, Any]] = []
    raw_outputs: list[str] = []

    for i, case in enumerate(cases, 1):
        if args.skip_human and case.get("human_review_required"):
            print(f"[{i:02d}/{len(cases)}] {case['case_id']} SKIPPED (human-review)", flush=True)
            continue

        prompt = build_prompt(case)
        print(f"[{i:02d}/{len(cases)}] {case['case_id']} → sending …", flush=True, end=" ")
        t0 = time.monotonic()

        raw = ollama_generate(prompt, args.model, args.ollama_url, args.timeout)
        elapsed = round(time.monotonic() - t0, 1)
        parsed = extract_json(raw)

        result = grade_case(case, parsed, raw)
        results.append(result)
        raw_outputs.append(raw)

        icon = "✓" if result["pass"] else "✗"
        fs = result.get("Final_status_returned", "?")
        print(f"{icon} {fs} ({elapsed}s)", flush=True)
        if result["failure_codes"]:
            print(f"         ↳ {result['failure_codes']}", flush=True)

    scores = score_results(results)
    print_report(args.model, exam_sha[:16], results, scores)

    if args.out:
        out_dir = args.out if isinstance(args.out, Path) else Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        label = args.run_label or args.model.replace("/", "_").replace(":", "_")
        out_path = out_dir / f"exam_result_{label}_{ts}.json"
        payload = {
            "exam_sha256": exam_sha,
            "exam_version": "finquant_adversarial_exam_v3",
            "model": args.model,
            "ollama_url": args.ollama_url,
            "run_label": label,
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scores": scores,
            "results": results,
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[proctor] Results saved: {out_path}", flush=True)

    sys.exit(0 if scores["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
