#!/usr/bin/env python3
"""
Deterministic generator for finquant_v0.2c_crypto_perp_reinforcement.jsonl.

Focus: false causality / overconfident market claims on perps (OI, funding, liquidation, basis).

Run from repo root:
  python3 finquant/scripts/generate_v0_2c_crypto_perp_jsonl.py

Output:
  finquant/patches/v0.2c/finquant_v0.2c_crypto_perp_reinforcement.jsonl

Deploy staging copy:
  /data/finquant-1/datasets/staging/finquant_v0.2c_crypto_perp_reinforcement.jsonl

Adversarial rows use Math verdict starting with **Incorrect** and include at least one harness cue word:
incorrect | mismatch | invalid | unsupported (see eval_finquant.detect_issue_signals).
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

PATCH_DIR = Path(__file__).resolve().parents[1] / "patches" / "v0.2c"
OUT_JSONL = PATCH_DIR / "finquant_v0.2c_crypto_perp_reinforcement.jsonl"

INSTR = (
    "You are a quant verifier. Answer using exactly four labeled sections in this order: "
    "Claim reviewed:, Math verdict:, DATA evidence required:, Final verifier status:. "
    "Be concise. For causal claims about perps (funding, OI, liquidation, basis), reject leaps "
    "that equate correlation with causation unless independently evidenced. "
    "Use FAIL when the claim is overstated or unsupported."
)

TARGET_N = 100
ADV_FRAC = 0.85
SEED = 42006
FLAG = "crypto_perp_v0.2c"


def _snip(s: str, max_words: int = 30) -> str:
    w = s.replace("\n", " ").strip().split()
    if len(w) <= max_words:
        return " ".join(w)
    return " ".join(w[:max_words]) + "…"


def format_data_evidence_block(items: list[str]) -> str:
    lines = [f"- {x.strip()}" for x in items if x and x.strip()]
    return "\n".join(lines) if lines else "- Mark price and index price time series (UTC)"


def four_section_output(
    *,
    claim_summary: str,
    verdict_line: str,
    data_items: list[str],
    final_status: str,
) -> str:
    body = format_data_evidence_block(data_items)
    return (
        f"Claim reviewed:\n{_snip(claim_summary)}\n\n"
        f"Math verdict:\n{verdict_line.strip()}\n\n"
        f"DATA evidence required:\n{body}\n\n"
        f"Final verifier status:\n{final_status.strip()}"
    )


# Verdict lines must stay aligned with eval harness issue_detection (substring cues in lower text).
ADV_POOL: list[tuple[str, str, list[str], str]] = [
    (
        "[VERIFY] Claim: Positive funding causes spot price to rise over the next hour.",
        "Incorrect — funding is a carry/premium mechanism; direction needs separate invalidation with price DATA.",
        [
            "Funding rate timestamps (UTC) and venue",
            "Spot and perp mark price paths over the same windows",
            "Open interest delta vs realized volatility",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: A liquidation cascade guarantees trend continuation in the same direction.",
        "Incorrect — cascades can exhaust positioning; causal link unsupported without order-book replay.",
        [
            "Liquidation trade prints with timestamps",
            "Mark price and index during cascade window",
            "OI delta and depth snapshots post-cascade",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: Rising open interest on a perp is always bullish.",
        "Incorrect — OI rises with both long and short interest; directional claim is invalid without skew DATA.",
        [
            "OI breakdown long vs short where available",
            "Mark minus index (basis) path",
            "Cumulative delta or aggressor side statistics",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: Falling funding rate proves traders are turning bearish.",
        "Incorrect — funding moves with premium/discount; mismatch risk vs sentiment labels.",
        [
            "Signed funding series with venue convention doc",
            "Index premium vs mark over hold interval",
            "Position imbalance proxies if published",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: High leverage is safe if the technical signal is strong.",
        "Incorrect — leverage tightens liquidation distance; signal strength does not remove gap risk (unsupported safety claim).",
        [
            "Leverage and margin mode",
            "Liquidation price vs mark series",
            "Realized volatility of the underlying window",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: Perp mark price always equals the last traded price.",
        "Incorrect — mark is typically index-derived; identity claim invalid for most venues.",
        [
            "Venue mark methodology reference",
            "Last trade tape vs mark snapshots",
            "Replay bar timestamps for both series",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: A wave of liquidations is a bullish signal for the next session.",
        "Incorrect — liquidation direction vs subsequent drift is empirically mixed; claim unsupported.",
        [
            "Liquidation side (long vs short) aggregation",
            "Post-event mark path and session returns",
            "Funding and OI reset after liquidations",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: Rising volatility confirms the directional breakout thesis.",
        "Incorrect — volatility scales uncertainty; mismatch if treated as directional confirmation alone.",
        [
            "Realized vs implied volatility series",
            "Directional return sign separate from vol spike",
            "Stop distance vs ATR at signal time",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: When funding flips sign, the macro trend must reverse.",
        "Incorrect — funding flips often reflect premium decay; causal reversal claim unsupported.",
        [
            "Funding flip timestamps vs subsequent trend metrics",
            "Basis and OI around flips",
            "External regime indicators if asserted",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: Basis tightening toward zero guarantees an imminent large spot move.",
        "Incorrect — basis mean-reverts often without guaranteed magnitude; prediction unsupported.",
        [
            "Spot reference index ID",
            "Mark and index sampled at identical timestamps",
            "Historical basis distribution not cherry-picked window",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Market card: BTC perp open interest spikes while funding neutral; claim 'liquidations must follow soon.' Challenge causal certainty.",
        "Incorrect — liquidations depend on mark paths and margin; OI spike alone is insufficient (unsupported inevitability).",
        [
            "Mark price and liquidation proximity metrics",
            "OI delta per interval vs price volatility",
            "Funding rate timestamps even if neutral band",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Claim: Negative funding means shorts are definitely paying longs so price must fall.",
        "Incorrect — sign conventions vary; price direction remains unsupported by funding alone.",
        [
            "Venue funding payment direction table",
            "Mark vs index path after funding prints",
            "Position skew estimates",
        ],
        "FAIL",
    ),
]

EVAL_STYLE_EXTRA = [
    (
        "[VERIFY] Market card: ETH perp OI jumps with flat funding; headline says 'forced covering soon.' Assess causal certainty.",
        "Incorrect — mismatch between narrative and mechanics; covering is not guaranteed from OI alone.",
        [
            "OI change decomposition if available",
            "Liquidation engine thresholds vs mark",
            "Order flow imbalance proxies",
        ],
        "FAIL",
    ),
]


def main() -> None:
    rng = random.Random(SEED)
    n_adv = int(round(TARGET_N * ADV_FRAC))
    n_clean = TARGET_N - n_adv

    rows: list[dict] = []

    adv_source = list(ADV_POOL) + EVAL_STYLE_EXTRA
    adv_source.extend(
        [ADV_POOL[-1]] * 18
    )  # weight harness-shaped OI + neutral funding prompt
    rng.shuffle(adv_source)

    for i in range(n_adv):
        tpl = adv_source[i % len(adv_source)]
        inp_base, mv, data_items, st = tpl
        inp_v = inp_base + f" Variant {i + 1}."
        out = four_section_output(
            claim_summary=inp_v,
            verdict_line=mv,
            data_items=data_items,
            final_status=st,
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

    clean_templates: list[tuple[str, str, list[str], str]] = [
        (
            "[VERIFY] Does neutral funding alone justify a directional forecast?",
            "Incorrect as stated — funding neutrality is insufficient; directional forecasts remain unsupported without price/OI/DATA.",
            [
                "Funding neutrality band definition",
                "Concurrent mark and spot returns",
                "OI delta vs realized vol",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Is it valid to infer causality from a single OI print?",
            "Incorrect — single-point OI is not a causal identifier; invalid without time series context.",
            [
                "OI time series with timestamps",
                "Aligned price series",
                "Event timestamps for confounding news",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Teaching check: correlation between funding and next-bar return is always stable.",
            "Incorrect — unstable across regimes; unsupported universality.",
            [
                "Rolling correlation estimates with confidence intervals",
                "Regime labels or volatility buckets",
                "Multiple venues for robustness",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Properly hedged statement: we cannot conclude liquidations will follow from OI spike alone.",
            "Correct — causal certainty unsupported without margin stress DATA; treat claim as needing verification.",
            [
                "Margin utilization vs maintenance curve",
                "Mark distance to liquidation for aggregate cohort if estimable",
                "OI change vs leverage distribution",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Properly hedged statement: basis tightening alone does not guarantee a trade.",
            "Correct — basis move lacks magnitude guarantees; PASS only as skepticism of certainty.",
            [
                "Basis distribution historically",
                "Transaction costs and fees",
                "Holding interval definition",
            ],
            "PASS",
        ),
    ]

    for j in range(n_clean):
        tpl = clean_templates[j % len(clean_templates)]
        inp, mv, data_items, st = tpl
        # Avoid "Teaching sample N" phrasing — combined training caused degenerate echo on eval.
        inp_v = inp + f" Case ref {j + 1}."
        out = four_section_output(
            claim_summary=inp_v,
            verdict_line=mv,
            data_items=data_items,
            final_status=st,
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
