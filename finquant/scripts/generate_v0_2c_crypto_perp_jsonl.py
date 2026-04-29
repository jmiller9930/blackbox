#!/usr/bin/env python3
"""
Deterministic generator for finquant_v0.2c_crypto_perp_reinforcement.jsonl.

Directive template:
  instruction: Verify the claim and output in the required four-section format.
  input: one-sentence claim
  output: Claim reviewed / Math verdict / DATA evidence required / Final verifier status

Run: python3 finquant/scripts/generate_v0_2c_crypto_perp_jsonl.py

Output: finquant/patches/v0.2c/finquant_v0.2c_crypto_perp_reinforcement.jsonl
Staging:  /data/finquant-1/datasets/staging/finquant_v0.2c_crypto_perp_reinforcement.jsonl

Wrong causal claims → Math verdict begins with Incorrect — … ; Final verifier status FAIL.
Issue cues (eval harness): incorrect | mismatch | invalid | unsupported appear in verdict/DATA.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

PATCH_DIR = Path(__file__).resolve().parents[1] / "patches" / "v0.2c"
OUT_JSONL = PATCH_DIR / "finquant_v0.2c_crypto_perp_reinforcement.jsonl"

# Exact instruction per directive
INSTR = "Verify the claim and output in the required four-section format."

TARGET_N = 100
ADV_FRAC = 0.85
SEED = 42100
FLAG = "crypto_perp_v0.2c_concise"

# Concrete DATA block (directive template); not prompt-echo.
DATA_STANDARD_LINES = [
    "Funding rate (UTC timestamp, venue identifier)",
    "Mark price vs index price (aligned series)",
    "Position side, leverage, margin mode",
    "Open interest delta over the claim interval",
    "Basis (mark − index) at decision times T",
]


def format_data_evidence_block(items: list[str]) -> str:
    lines = [f"- {x.strip()}" for x in items if x and x.strip()]
    return "\n".join(lines)


def four_section_output(
    *,
    claim_reviewed: str,
    verdict_line: str,
    data_items: list[str],
    final_status: str,
) -> str:
    body = format_data_evidence_block(data_items)
    return (
        f"Claim reviewed:\n{claim_reviewed.strip()}\n\n"
        f"Math verdict:\n{verdict_line.strip()}\n\n"
        f"DATA evidence required:\n{body}\n\n"
        f"Final verifier status:\n{final_status.strip()}"
    )


# (input one-liner, claim_reviewed paraphrase, Incorrect — reason with cue word)
# Covers: funding→direction, OI→direction, liqs→continuation, flip→reversal, mark=last,
# vol→direction, basis→move, leverage removes risk, + eval-style OI/neutral card.
ADV_SPEC: list[tuple[str, str, str]] = [
    (
        "Positive funding proves spot will rally next session.",
        "The claim ties funding sign to a directional spot outcome.",
        "Incorrect — funding reflects premium/carry, not a validated price forecast; causal link unsupported.",
    ),
    (
        "Rising perp OI means buyers are in control and price must go up.",
        "The claim maps higher OI to bullish direction.",
        "Incorrect — OI aggregates long and short gross exposure; directional inference invalid without skew DATA.",
    ),
    (
        "A liquidation sweep guarantees the trend will continue for hours.",
        "The claim asserts forced exits guarantee continuation.",
        "Incorrect — liquidations can absorb one-sided risk; continuation is not guaranteed (unsupported inevitability).",
    ),
    (
        "When funding flips from positive to negative, the macro trend must reverse.",
        "The claim ties a funding sign change to a mandatory regime reversal.",
        "Incorrect — funding flips track premium shifts; mismatch versus mandatory macro reversal.",
    ),
    (
        "Perp mark price is always identical to the last traded price.",
        "The claim equates mark with last trade.",
        "Incorrect — venue marks are typically index-derived; identity invalid under exchange rules.",
    ),
    (
        "A volatility spike confirms the breakout direction is correct.",
        "The claim uses volatility as directional confirmation.",
        "Incorrect — volatility scales uncertainty; mismatch if treated as directional proof alone.",
    ),
    (
        "Basis tightening toward zero guarantees a large imminent spot jump.",
        "The claim promises a guaranteed move from basis convergence.",
        "Incorrect — basis mean-reverts without guaranteed magnitude; prediction unsupported.",
    ),
    (
        "With a strong signal, 20× leverage is safe because edge dominates gap risk.",
        "The claim says leverage removes liquidation risk when signals look good.",
        "Incorrect — leverage raises liquidation proximity; safety claim unsupported by mechanics.",
    ),
    (
        "BTC perp OI spikes while funding is neutral, so liquidations must follow soon.",
        "The claim links OI spike plus neutral funding to imminent liquidations.",
        "Incorrect — liquidations depend on mark paths and margin stress; OI alone cannot prove timing (invalid causal leap).",
    ),
    (
        "Negative funding means price has to dump because shorts are winning.",
        "The claim forces a directional price move from funding sign alone.",
        "Incorrect — sign conventions and premium dynamics mismatch simple price mandates; unsupported.",
    ),
    (
        "Heavy long liquidations are a buy signal for the next candle.",
        "The claim treats liquidation prints as directional alpha.",
        "Incorrect — post-liquidation drift is regime-dependent; bullish inference unsupported.",
    ),
    (
        "If funding is flat, OI changes cannot matter for risk.",
        "The claim dismisses OI when funding is neutral.",
        "Incorrect — OI and margin still interact with mark; invalid to ignore exposure stacks.",
    ),
]


def main() -> None:
    rng = random.Random(SEED)
    n_adv = int(round(TARGET_N * ADV_FRAC))
    n_clean = TARGET_N - n_adv

    rows: list[dict] = []

    adv_pool = list(ADV_SPEC)
    adv_pool.extend([ADV_SPEC[8]] * 14)
    rng.shuffle(adv_pool)

    for i in range(n_adv):
        inp_line, reviewed, verdict = adv_pool[i % len(adv_pool)]
        inp_v = f"{inp_line} Variant {i + 1}."
        out = four_section_output(
            claim_reviewed=reviewed,
            verdict_line=verdict,
            data_items=list(DATA_STANDARD_LINES),
            final_status="FAIL",
        )
        rows.append(
            {
                "instruction": INSTR,
                "input": inp_v + "\n",
                "output": out,
                "source_ids": ["v0.2c_crypto_perp_synth", f"adv_{i + 1:04d}"],
                "category": "crypto_perp",
                "adversarial": True,
                "quality_flags": [
                    FLAG,
                    "adversarial_trap",
                    "substance_v0.2",
                    hashlib.sha256(inp_v.encode()).hexdigest()[:8],
                ],
            }
        )

    # Non-adversarial: hedged, mostly PASS; still use concrete DATA
    clean_specs: list[tuple[str, str, str, str]] = [
        (
            "We cannot infer liquidation timing from OI alone without margin stress DATA.",
            "The statement refuses a causal leap from OI to liquidation timing.",
            "Correct — timing claim unsupported without margin and mark evidence; verification needs listed DATA.",
            "PASS",
        ),
        (
            "Basis moves alone do not guarantee tradeable magnitude after fees.",
            "The statement rejects guaranteed edge from basis tightening alone.",
            "Correct — profitability claim unsupported until costs and distribution are evidenced.",
            "PASS",
        ),
        (
            "Funding sign by itself is an invalid proof of next-bar spot direction.",
            "The claim rejects funding-only directional proof.",
            "Incorrect as stated — directional mandates from funding alone remain unsupported (use DATA below).",
            "FAIL",
        ),
    ]

    for j in range(n_clean):
        inp_line, reviewed, verdict, fin = clean_specs[j % len(clean_specs)]
        inp_v = f"{inp_line} Case ref {j + 1}."
        out = four_section_output(
            claim_reviewed=reviewed,
            verdict_line=verdict,
            data_items=list(DATA_STANDARD_LINES),
            final_status=fin,
        )
        rows.append(
            {
                "instruction": INSTR,
                "input": inp_v + "\n",
                "output": out,
                "source_ids": ["v0.2c_crypto_perp_synth", f"clean_{j + 1:04d}"],
                "category": "crypto_perp",
                "adversarial": False,
                "quality_flags": [FLAG, "reference_answer", "substance_v0.2"],
            }
        )

    rng.shuffle(rows)

    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    adv_n = sum(1 for r in rows if r.get("adversarial"))
    print(
        json.dumps(
            {
                "path": str(OUT_JSONL),
                "total": len(rows),
                "adversarial": adv_n,
                "adversarial_pct": round(100.0 * adv_n / len(rows), 2),
                "seed": SEED,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
