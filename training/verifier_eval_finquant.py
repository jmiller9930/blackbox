#!/usr/bin/env python3
"""
FinQuant-1 — verifier-shaped eval (training-local copy).

**Isolation:** Lives under `training/` only. Sync periodically from
`prove_learning/finquant/evals/eval_finquant.py` if that upstream changes — do not
route FinQuant training work through other workstreams.

Scores generations on:
  pass/fail rubric (structured headings present, trap detection cues)
  reasoning quality (heuristic: length, section coverage)
  DATA validation presence (DATA evidence required block substantive)

Does not modify Blackbox.

Usage:
  export FINQUANT_BASE=/data/NDE/finquant/agentic_v05
  python3 training/verifier_eval_finquant.py \\
    --adapter adapters/finquant-agentic-v05-smoke \\
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
    return Path.cwd().resolve()


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

# Eval default: strict 4-section schema (prompt-aligned; matches harness structural check).
STRICT_PROMPT_HEADINGS = (
    "Claim reviewed:",
    "Math verdict:",
    "DATA evidence required:",
    "Final verifier status:",
)

STRICT_VERIFIER_PROMPT_PREFIX = """You are a verifier. Your assistant reply must be ONLY the four labeled sections below—no preamble, no chain-of-thought, no markdown fences.

The visible answer MUST contain these exact labels (including the colons), in this order:
Claim reviewed:
Math verdict:
DATA evidence required:
Final verifier status:

Claim reviewed:
<one sentence restating what is being verified>

Math verdict:
<correct/incorrect + brief reason>

DATA evidence required:
<concrete fields, sources, or calculations needed to verify>

Final verifier status:
<PASS or FAIL>

Hard rules:
- Do not write analysis before "Claim reviewed:"—start the substantive answer at Claim reviewed:
- No text after Final verifier status line except optional blank line
- Each section body must be non-empty

Illustrative miniature example (structure only):
Claim reviewed:
The sender asserts Sharpe 3.1 from nine samples without rf.

Math verdict:
Incorrect — unstable Sharpe on short windows.

DATA evidence required:
Daily excess returns; rf series used; variance estimation window.

Final verifier status:
FAIL

---

User verification task:

"""


def strip_reasoning_noise(text: str) -> str:
    """Remove common thinking wrappers so structural checks apply to the verifier body."""
    t = text
    for pat in (
        r"<think>[\s\S]*?</think>",
        r"<think>[\s\S]*?</think>",
    ):
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    # Drop narrative before earliest verifier label
    earliest: int | None = None
    for marker in STRICT_PROMPT_HEADINGS:
        i = t.find(marker)
        if i >= 0 and (earliest is None or i < earliest):
            earliest = i
    if earliest is not None and earliest > 0:
        t = t[earliest:]
    return t.strip()


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


def heuristic_reasoning_score(text: str, headings: tuple[str, ...]) -> float:
    """Rough 0–1 score: headings + length + non-generic."""
    t = text.strip()
    if not t:
        return 0.0
    # Structured verifier replies can be shorter than narrative CoT.
    if len(t) < 80:
        base = 0.12
    elif len(t) < 120:
        base = 0.18
    else:
        base = 0.22
    score = base
    step = 0.125 if len(headings) <= 4 else 0.07
    for h in headings:
        if h in text:
            score += step
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


def structural_pass(text: str, headings: tuple[str, ...]) -> bool:
    return all(h in text for h in headings)


def failure_reasons(
    struct_ok: bool,
    data_ok: bool,
    rq: float,
    reasoning_floor: float,
) -> list[str]:
    out: list[str] = []
    if not struct_ok:
        out.append("structural")
    if not data_ok:
        out.append("insufficient_DATA")
    if rq < reasoning_floor:
        out.append("reasoning_score")
    return out


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
    ap.add_argument(
        "--legacy-headings",
        action="store_true",
        help="Use full 10-line verifier headings + no strict prompt prefix (old behavior)",
    )
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
        raise SystemExit(
            "Install training deps: pip install -r training/requirements-finquant-training.txt\n" + str(e)
        ) from e

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

    headings: tuple[str, ...] = VERIFIER_HEADINGS if args.legacy_headings else STRICT_PROMPT_HEADINGS
    reasoning_floor = 0.45

    results: list[dict[str, Any]] = []
    for case in EVAL_SUITE:
        user_in = case.user_content.strip()
        if not args.legacy_headings:
            user_in = STRICT_VERIFIER_PROMPT_PREFIX + user_in
        text = run_generation(model, tokenizer, user_in, max_new_tokens=args.max_new_tokens)
        scored_text = strip_reasoning_noise(text) if not args.legacy_headings else text
        struct_ok = structural_pass(scored_text, headings)
        data_ok = data_validation_present(scored_text)
        rq = heuristic_reasoning_score(scored_text, headings)
        generic = any(p.search(scored_text) for p in GENERIC_PATTERNS)
        issue_hint = detect_issue_signals(scored_text)
        passed = struct_ok and data_ok and rq >= reasoning_floor and not generic
        if case.expect_detect_issue:
            passed = passed and issue_hint
        if passed:
            fr: list[str] = []
        else:
            fr = failure_reasons(struct_ok, data_ok, rq, reasoning_floor)
            if generic:
                fr = list(dict.fromkeys(fr + ["generic_smell"]))
            if case.expect_detect_issue and not issue_hint:
                fr = list(dict.fromkeys(fr + ["issue_detection"]))
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
                "failure_reasons": fr,
                "strict_prompt": not args.legacy_headings,
                "output_preview": scored_text[:2400],
            }
        )

    summary = {
        "adapter": str(adapter_path),
        "base_model": args.model,
        "cases_total": len(results),
        "cases_pass": sum(1 for r in results if r["pass"]),
        "strict_four_heading_prompt": not args.legacy_headings,
        "structural_headings": "legacy_10" if args.legacy_headings else "strict_4",
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
            "- **Structural pass:** all mandatory headings present "
            "(default: four-section strict prompt; use `--legacy-headings` for 10-heading mode).",
            "- **DATA validation:** substantive `DATA evidence required:` block (≥25 chars before Final status).",
            "- **Reasoning quality:** heuristic score (headings, length, non-generic); floor 0.45.",
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
            fr = r.get("failure_reasons") or []
            if fr:
                lines.append(f"- **failure_reasons:** {', '.join(fr)}")
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
        rp = Path(report_name)
        if rp.is_absolute():
            outp = rp
        else:
            # Accept either `foo.md` or `reports/foo.md` without doubling base/reports/
            parts = rp.parts
            if len(parts) > 1 and parts[0] == "reports":
                rp = Path(*parts[1:])
            outp = base / "reports" / rp
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {outp}")


if __name__ == "__main__":
    main()
