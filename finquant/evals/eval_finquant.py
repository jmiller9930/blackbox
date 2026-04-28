#!/usr/bin/env python3
"""
FinQuant-1 — evaluation harness for verifier-shaped outputs (Phase 4–5).

Scores generations on:
  pass/fail rubric (structured headings present, trap detection cues)
  reasoning quality (heuristic: length, section coverage)
  DATA validation presence (DATA evidence required block substantive)

Does not modify Blackbox.

Usage:
  export FINQUANT_BASE=/data/finquant-1
  python3 finquant/evals/eval_finquant.py \\
    --adapter adapters/finquant-1-qwen7b-v0.1-smoke \\
    --write-report

Requires GPU + training deps (same as train_qlora.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def finquant_base() -> Path:
    env = (os.environ.get("FINQUANT_BASE") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


VERIFIER_HEADINGS = (
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


GENERIC_PATTERNS = (
    re.compile(r"(?i)^\s*as an ai\b"),
    re.compile(r"(?i)\bi cannot give financial advice\b"),
    re.compile(r"(?i)^\s*here are (some )?tips\b"),
)


@dataclass
class EvalCase:
    case_id: str
    theme: str
    user_content: str
    expect_detect_issue: bool  # model should flag math/logic/policy issue in verdict areas


EVAL_SUITE: list[EvalCase] = [
    EvalCase(
        "pnl_math_error",
        "PnL math errors",
        "[VERIFY] Strategy claims daily Sharpe 3.1 using 9 trading days and ignores risk-free rate.\n"
        "Show whether Sharpe is miscomputed and what DATA would fix it.",
        True,
    ),
    EvalCase(
        "funding_liquidation",
        "Funding / liquidation risk",
        "[VERIFY] Claim: 'Long perps always earn positive funding on Binance.'\n"
        "Assess funding sign mechanics and liquidation proximity vs leverage.",
        True,
    ),
    EvalCase(
        "indicator_misuse",
        "Indicator misuse",
        "[VERIFY] RSI(14) on 1m candles is offered as proof of weekly macro trend.\n"
        "Evaluate timeframe mismatch and indicator validity.",
        True,
    ),
    EvalCase(
        "lookahead_bias",
        "Lookahead bias",
        "[VERIFY] Backtest claims no lookahead but universe membership uses earnings dates filed next quarter.\n"
        "Flag leakage paths.",
        True,
    ),
    EvalCase(
        "policy_mismatch",
        "Policy mismatch",
        "[VERIFY] Live bot reports TP from strategy YAML but execution logs show hard-coded ATR multiple not in YAML.\n"
        "Policy vs implementation.",
        True,
    ),
    EvalCase(
        "crypto_perp_scenario",
        "Crypto-perp scenarios",
        "[VERIFY] Market card: BTC perp open interest spikes while funding neutral; claim 'liquidations must follow soon.'\n"
        "Challenge causal certainty.",
        True,
    ),
]


def heuristic_reasoning_score(text: str) -> float:
    """Rough 0–1 score: headings + length + non-generic."""
    if not text or len(text.strip()) < 120:
        return 0.1
    score = 0.0
    for h in VERIFIER_HEADINGS:
        if h in text:
            score += 0.07
    low = text.lower()
    if any(p.search(text) for p in GENERIC_PATTERNS):
        score *= 0.4
    if "data evidence required:" in low and len(low.split("data evidence required:", 1)[-1].strip()) > 40:
        score += 0.15
    return min(1.0, score)


def data_validation_present(text: str) -> bool:
    if "DATA evidence required:" not in text:
        return False
    tail = text.split("DATA evidence required:", 1)[-1]
    tail = tail.split("Final verifier status:", 1)[0]
    return len(tail.strip()) >= 25


def structural_pass(text: str) -> bool:
    return all(h in text for h in VERIFIER_HEADINGS)


def detect_issue_signals(text: str) -> bool:
    low = text.lower()
    cues = (
        "fail",
        "incorrect",
        "cannot determine",
        "miscomputed",
        "invalid",
        "lookahead",
        "leak",
        "mismatch",
        "trap",
        "unstable",
        "insufficient",
    )
    return any(c in low for c in cues)


def run_generation(model: Any, tokenizer: Any, user_content: str, max_new_tokens: int = 768) -> str:
    import torch

    messages = [{"role": "user", "content": user_content.strip()}]
    tmpl = getattr(tokenizer, "chat_template", None)
    if tmpl:
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    else:
        prompt = (
            "<|im_start|>user\n"
            + user_content.strip()
            + "<|im_end|>\n<|im_start|>assistant\n"
        )
    dev = next(model.parameters()).device
    inputs = tokenizer(prompt, return_tensors="pt").to(dev)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(gen, skip_special_tokens=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="FinQuant-1 eval harness")
    ap.add_argument("--base", type=Path, default=None)
    ap.add_argument(
        "--model",
        default="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        help="Base model id",
    )
    ap.add_argument(
        "--adapter",
        type=str,
        required=True,
        help="Adapter dir relative to FINQUANT_BASE or absolute",
    )
    ap.add_argument("--max-new-tokens", type=int, default=768)
    ap.add_argument("--write-report", action="store_true", help="Write eval report markdown under FINQUANT_BASE/reports/")
    ap.add_argument(
        "--report-path",
        type=str,
        default=None,
        help="Report filename relative to FINQUANT_BASE/reports/ (default: smoke_eval_report.md or v0.1_eval_report.md with --adapter full)",
    )
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    base = (args.base or finquant_base()).resolve()
    adapter_path = Path(args.adapter)
    if not adapter_path.is_absolute():
        adapter_path = (base / adapter_path).resolve()

    if not adapter_path.is_dir():
        raise SystemExit(f"Adapter dir not found: {adapter_path}")

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as e:
        raise SystemExit("Install training deps: pip install -r finquant/requirements-finquant-training.txt\n" + str(e)) from e

    if not torch.cuda.is_available():
        raise SystemExit("CUDA required for 4-bit eval load (run on trx40).")

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    base_model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base_model, str(adapter_path))
    model.eval()

    torch.manual_seed(args.seed)

    results: list[dict[str, Any]] = []
    for case in EVAL_SUITE:
        text = run_generation(model, tokenizer, case.user_content, max_new_tokens=args.max_new_tokens)
        struct_ok = structural_pass(text)
        data_ok = data_validation_present(text)
        rq = heuristic_reasoning_score(text)
        generic = any(p.search(text) for p in GENERIC_PATTERNS)
        issue_hint = detect_issue_signals(text)
        passed = struct_ok and data_ok and rq >= 0.45 and not generic
        if case.expect_detect_issue:
            passed = passed and issue_hint
        results.append(
            {
                "case_id": case.case_id,
                "theme": case.theme,
                "structural_pass": struct_ok,
                "data_validation_present": data_ok,
                "reasoning_score": round(rq, 4),
                "generic_smell": generic,
                "issue_signals": issue_hint,
                "pass": passed,
                "output_preview": text[:1200],
            }
        )

    summary = {
        "adapter": str(adapter_path),
        "base_model": args.model,
        "cases_total": len(results),
        "cases_pass": sum(1 for r in results if r["pass"]),
    }
    print(json.dumps({"summary": summary, "results": results}, indent=2))

    if args.write_report:
        report_name = args.report_path
        if not report_name:
            report_name = "v0.1_eval_report.md" if "v0.1" in str(adapter_path) and "smoke" not in str(adapter_path) else "smoke_eval_report.md"
        title = "FinQuant-1 — v0.1 full eval report" if "v0.1_eval" in report_name else "FinQuant-1 — smoke eval report"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        host = socket.gethostname()
        lines = [
            f"# {title}",
            "",
            f"**Generated:** `{ts}` UTC",
            f"**Host:** `{host}`",
            f"**Base model:** `{args.model}`",
            f"**Adapter:** `{adapter_path}`",
            "",
            "## Summary",
            "",
            json.dumps(summary, indent=2),
            "",
            "## Criteria",
            "",
            "- **Structural pass:** all mandatory verifier headings present.",
            "- **DATA validation:** substantive `DATA evidence required:` block.",
            "- **Reasoning quality:** heuristic score (headings, length, non-generic).",
            "- **Issue detection:** verdict text hints at fail/incorrect/mismatch/leakage where applicable.",
            "",
            "## Per-case results",
            "",
        ]
        for r in results:
            lines.append(f"### `{r['case_id']}` — {r['theme']}")
            lines.append("")
            lines.append(f"- **pass:** {r['pass']}")
            lines.append(f"- **structural_pass:** {r['structural_pass']}")
            lines.append(f"- **data_validation_present:** {r['data_validation_present']}")
            lines.append(f"- **reasoning_score:** {r['reasoning_score']}")
            lines.append(f"- **generic_smell:** {r['generic_smell']}")
            lines.append("")
            lines.append("```")
            lines.append(r["output_preview"])
            lines.append("```")
            lines.append("")
        lines.extend(
            [
                "## Phase gate",
                "",
                "Review outputs above: model should **detect errors**, **request DATA**, and avoid **generic refusals**.",
                "",
            ]
        )
        outp = Path(report_name) if Path(report_name).is_absolute() else base / "reports" / report_name
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {outp}")


if __name__ == "__main__":
    main()
