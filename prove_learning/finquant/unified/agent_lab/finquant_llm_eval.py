"""
FinQuant LLM Evaluation Harness

Tests a fine-tuned FinQuant model against the standard criteria.
Run this after QLoRA completes on trx40 to determine if the dedicated
model is ready to replace general Qwen 7B in the live forward loop.

PASS gates (all must clear):
  1. Schema validity >= 98%       — model produces valid structured JSON
  2. ENTER rate 15-40%            — model is willing to enter when signal is clear
  3. risk_context_v1 present >= 95% — model outputs risk sizing with every decision
  4. R-002 compliance >= 90%      — entries have confidence_spread >= 0.20
  5. Divergence citation >= 80%   — thesis cites divergence when signal is present
  6. Decision quality >= 65%      — wins + correct stand-downs / total

Comparison baseline (general Qwen 7B, 200-case run):
  Schema validity:    ~80% (many truncations before stop-token fix)
  ENTER rate:         ~23%
  risk_context:       now 100% (wired this session)
  R-002 compliance:   ~85%
  Divergence citation: ~96%
  Decision quality:   70.5% (cycle 1)

Usage:
  python3 prove_learning/finquant/unified/agent_lab/finquant_llm_eval.py \\
    --db data/sqlite/market_data.db \\
    --model finquant-1-qwen7b-v0.1 \\
    --ollama-url http://172.20.2.230:11434 \\
    --cases 50 \\
    --output-dir prove_learning/finquant/unified/agent_lab/outputs/llm_eval

  Or against general Qwen (baseline comparison):
  python3 ... --model qwen2.5:7b
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

_LAB_ROOT = Path(__file__).parent
sys.path.insert(0, str(_LAB_ROOT))

# ── Pass gate thresholds ──────────────────────────────────────────────────────
GATE_SCHEMA_VALIDITY    = 0.98   # 98% of responses parse as valid JSON
GATE_ENTER_RATE_MIN     = 0.10   # at least 10% entries (model must be willing)
GATE_ENTER_RATE_MAX     = 0.50   # at most 50% entries (model must be selective)
GATE_RISK_CONTEXT       = 0.95   # 95% of responses include risk_context_v1
GATE_R002_COMPLIANCE    = 0.90   # 90% of entries have spread >= 0.20
GATE_DIVERGENCE_CITE    = 0.75   # 75% of theses mention divergence
GATE_DECISION_QUALITY   = 0.65   # 65% good decisions (wins + no_trade_correct)


# ── Data loading (same as live forward test) ──────────────────────────────────

def load_eval_cases(db_path: str, n_cases: int, symbol: str = "SOL-PERP") -> list[dict[str, Any]]:
    """Load N 15m cases from the live DB for evaluation."""
    from market_data_bridge import fetch_5m_bars, rollup_bars, compute_indicators, generate_cases_from_bars

    now = datetime.datetime.now(timezone.utc)
    from_utc = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    bars_5m = fetch_5m_bars(db_path, symbol, from_utc, to_utc)
    bars_15m = rollup_bars(bars_5m, 15)
    bars_15m = compute_indicators(bars_15m)

    cases = generate_cases_from_bars(
        bars_15m,
        symbol=symbol,
        timeframe_minutes=15,
        case_prefix=f"eval_{symbol.lower().replace('-','')}_15m",
        context_candles=20,
        decision_steps=1,
        outcome_candles=7,
        stride=5,
        expected_learning_focus=["entry_quality"],
    )

    return cases[:n_cases]


# ── Single case evaluation ─────────────────────────────────────────────────────

def eval_single_case(
    case: dict[str, Any],
    model: str,
    ollama_url: str,
    timeout: int = 45,
) -> dict[str, Any]:
    """Run one case through the model and score the output."""
    from execution_flow import execute_case
    import tempfile

    config = {
        "schema": "finquant_agent_lab_config_v1",
        "agent_id": "finquant_eval",
        "mode": "llm_v1",
        "use_llm_v1": True,
        "llm_model_v1": model,
        "ollama_base_url_v1": ollama_url,
        "llm_timeout_seconds_v1": timeout,
        "llm_max_tokens_v1": 700,
        "memory_store_path": "",
        "retrieval_enabled_default_v1": False,
        "write_outputs_v1": False,
        "auto_promote_learning_v1": False,
    }

    # Write case to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(case, f)
        case_path = f.name

    try:
        result = execute_case(case_path=case_path, config=config, output_dir="/tmp/eval_runs")
    except Exception as e:
        return {"error": str(e), "case_id": case.get("case_id")}
    finally:
        Path(case_path).unlink(missing_ok=True)

    decisions = result.get("decisions") or []
    if not decisions:
        return {"error": "no_decisions", "case_id": case.get("case_id")}

    d = decisions[0]
    raw = str(d.get("raw_model_output_v1") or "")
    action = str(d.get("action") or "NO_TRADE")
    thesis = str(d.get("thesis_v1") or "")
    llm_used = bool(d.get("llm_used_v1"))
    h1 = d.get("hypothesis_1_v1") or {}
    h2 = d.get("hypothesis_2_v1") or {}
    spread = d.get("confidence_spread_v1")
    risk_ctx = d.get("risk_context_v1") or {}

    # Score this decision
    schema_valid = llm_used and bool(raw) and action in ("ENTER_LONG", "ENTER_SHORT", "NO_TRADE", "INSUFFICIENT_DATA")
    is_entry = action in ("ENTER_LONG", "ENTER_SHORT")
    has_risk_ctx = bool(risk_ctx) and "final_risk_pct" in risk_ctx
    r002_compliant = not is_entry or (spread is not None and float(spread) >= 0.20)
    divergence_cited = any(w in thesis.lower() for w in ("divergence", "bullish div", "bearish div", "rsi lower", "rsi higher"))

    # Outcome from evaluation
    evaluation = result.get("evaluation") or {}
    entry_quality = evaluation.get("entry_quality_v1") or ""
    final_status = evaluation.get("final_status_v1") or "INFO"
    no_trade_correctness = evaluation.get("no_trade_correctness_v1") or ""

    if is_entry:
        good = (entry_quality == "entered_as_expected" and final_status == "PASS")
    else:
        good = no_trade_correctness in ("correctly_stood_down",) or entry_quality == "correctly_abstained"

    return {
        "case_id": case.get("case_id"),
        "action": action,
        "llm_used": llm_used,
        "schema_valid": schema_valid,
        "is_entry": is_entry,
        "has_risk_context": has_risk_ctx,
        "r002_compliant": r002_compliant,
        "divergence_cited": divergence_cited,
        "confidence_spread": spread,
        "is_good_decision": good,
        "final_status": final_status,
        "thesis_excerpt": thesis[:120],
        "raw_excerpt": raw[:100],
        "risk_pct": risk_ctx.get("final_risk_pct") if risk_ctx else None,
    }


# ── Aggregate scoring ──────────────────────────────────────────────────────────

def score_results(results: list[dict[str, Any]], model: str) -> dict[str, Any]:
    valid = [r for r in results if "error" not in r]
    n = len(valid)
    if n == 0:
        return {"error": "no valid results", "model": model}

    llm_used_count    = sum(1 for r in valid if r.get("llm_used"))
    schema_valid_rate = sum(1 for r in valid if r.get("schema_valid")) / n
    entries           = [r for r in valid if r.get("is_entry")]
    enter_rate        = len(entries) / n
    risk_ctx_rate     = sum(1 for r in valid if r.get("has_risk_context")) / n
    r002_rate         = sum(1 for r in entries if r.get("r002_compliant")) / max(len(entries), 1)
    div_cite_rate     = sum(1 for r in valid if r.get("divergence_cited")) / n
    good_rate         = sum(1 for r in valid if r.get("is_good_decision")) / n

    # Pass/fail each gate
    gates = {
        "schema_validity":    (schema_valid_rate,  GATE_SCHEMA_VALIDITY,  schema_valid_rate >= GATE_SCHEMA_VALIDITY),
        "enter_rate_min":     (enter_rate,          GATE_ENTER_RATE_MIN,   enter_rate >= GATE_ENTER_RATE_MIN),
        "enter_rate_max":     (enter_rate,          GATE_ENTER_RATE_MAX,   enter_rate <= GATE_ENTER_RATE_MAX),
        "risk_context":       (risk_ctx_rate,       GATE_RISK_CONTEXT,     risk_ctx_rate >= GATE_RISK_CONTEXT),
        "r002_compliance":    (r002_rate,           GATE_R002_COMPLIANCE,  r002_rate >= GATE_R002_COMPLIANCE),
        "divergence_citation":(div_cite_rate,       GATE_DIVERGENCE_CITE,  div_cite_rate >= GATE_DIVERGENCE_CITE),
        "decision_quality":   (good_rate,           GATE_DECISION_QUALITY, good_rate >= GATE_DECISION_QUALITY),
    }

    all_pass = all(v[2] for v in gates.values())
    errors = [r.get("error") for r in results if "error" in r]

    return {
        "model": model,
        "cases_total": len(results),
        "cases_valid": n,
        "cases_errored": len(errors),
        "llm_used_count": llm_used_count,
        "llm_used_rate": round(llm_used_count / n, 4),
        "metrics": {
            "schema_validity_rate":    round(schema_valid_rate, 4),
            "enter_rate":              round(enter_rate, 4),
            "risk_context_rate":       round(risk_ctx_rate, 4),
            "r002_compliance_rate":    round(r002_rate, 4),
            "divergence_citation_rate":round(div_cite_rate, 4),
            "decision_quality_rate":   round(good_rate, 4),
        },
        "gates": {k: {"value": round(v[0], 4), "threshold": v[1], "pass": v[2]} for k, v in gates.items()},
        "overall": "PASS" if all_pass else "FAIL",
        "errors_sample": errors[:5],
    }


def print_report(score: dict[str, Any]) -> None:
    model = score.get("model", "?")
    overall = score.get("overall", "FAIL")
    metrics = score.get("metrics") or {}
    gates   = score.get("gates") or {}

    print(f"\n{'='*60}")
    print(f"  FinQuant LLM Evaluation — {model}")
    print(f"  Overall: {'✓ PASS' if overall == 'PASS' else '✗ FAIL'}")
    print(f"{'='*60}")
    print(f"  Cases: {score.get('cases_valid')}/{score.get('cases_total')} valid | {score.get('cases_errored')} errors")
    print(f"  LLM called: {score.get('llm_used_count')}/{score.get('cases_valid')} ({score.get('llm_used_rate',0):.0%})")
    print()
    print("  ── Gate Results ────────────────────────────────")
    for gate_name, gate in gates.items():
        icon = "✓" if gate["pass"] else "✗"
        print(f"  {icon} {gate_name:26s} {gate['value']:.1%} (need {gate['threshold']:.0%})")
    print()
    print("  ── vs General Qwen 7B Baseline ─────────────────")
    baseline = {
        "schema_validity_rate":     0.80,
        "enter_rate":               0.23,
        "risk_context_rate":        1.00,
        "r002_compliance_rate":     0.85,
        "divergence_citation_rate": 0.96,
        "decision_quality_rate":    0.705,
    }
    for k, v in metrics.items():
        b = baseline.get(k, 0)
        diff = v - b
        arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        print(f"  {k:30s} {v:.1%}  {arrow} {abs(diff):.1%} vs baseline {b:.1%}")
    print()
    if overall == "PASS":
        print("  VERDICT: Dedicated model ready to replace general Qwen in live loop.")
    else:
        failed = [k for k, g in gates.items() if not g["pass"]]
        print(f"  VERDICT: Not ready. Failed gates: {', '.join(failed)}")
        print("  → Fix these before wiring to live forward test.")
    print(f"{'='*60}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant LLM evaluation harness")
    parser.add_argument("--db", required=True, help="Path to market_data.db")
    parser.add_argument("--model", default="qwen2.5:7b", help="Ollama model name (e.g. finquant-1-qwen7b-v0.1)")
    parser.add_argument("--ollama-url", default="http://172.20.2.230:11434", help="Ollama base URL")
    parser.add_argument("--cases", type=int, default=50, help="Number of cases to evaluate")
    parser.add_argument("--symbol", default="SOL-PERP")
    parser.add_argument("--output-dir", default=None, help="Save results JSON here")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    print(f"[eval] Loading {args.cases} cases from {args.db}...")
    cases = load_eval_cases(args.db, args.cases, args.symbol)
    print(f"[eval] Got {len(cases)} cases. Running against model: {args.model}")

    results = []
    for i, case in enumerate(cases):
        if i % 10 == 0:
            print(f"[eval]   {i}/{len(cases)}...")
        r = eval_single_case(case, args.model, args.ollama_url, args.timeout)
        results.append(r)

    score = score_results(results, args.model)
    print_report(score)

    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = out / f"llm_eval_{args.model.replace('/', '_')}_{ts}.json"
        out_path.write_text(json.dumps({"score": score, "results": results}, indent=2))
        print(f"[eval] Results saved: {out_path}")

    sys.exit(0 if score.get("overall") == "PASS" else 1)


if __name__ == "__main__":
    main()
