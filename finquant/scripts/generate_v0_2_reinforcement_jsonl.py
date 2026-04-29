#!/usr/bin/env python3
"""
Deterministic generator for finquant_v0.2_reinforcement.jsonl (v0.2 substance patch).

Run from repo root:
  python3 finquant/scripts/generate_v0_2_reinforcement_jsonl.py

Output: finquant/patches/v0.2/finquant_v0.2_reinforcement.jsonl
(deploy copy to /data/finquant-1/datasets/staging/ on trx40)
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "patches" / "v0.2" / "finquant_v0.2_reinforcement.jsonl"

INSTR = (
    "You are a quant verifier. Answer using exactly four labeled sections in this order: "
    "Claim reviewed:, Math verdict:, DATA evidence required:, Final verifier status:. "
    "Be concise. Use FAIL when any premise is false or unsupported."
)

TARGET_N = 400
ADV_FRAC = 0.725  # >= 70% adversarial
SEED = 42002


def _claim_reviewed_snip(s: str, max_words: int = 22) -> str:
    w = s.replace("\n", " ").strip().split()
    if len(w) <= max_words:
        return " ".join(w)
    return " ".join(w[:max_words]) + "…"


def four_section_output(
    *,
    claim_summary: str,
    verdict_line: str,
    data_bullets: list[str],
    final_status: str,
) -> str:
    data_body = "; ".join(data_bullets) if data_bullets else "Venue funding schedule; historical premium series."
    return (
        f"Claim reviewed:\n{_claim_reviewed_snip(claim_summary)}\n\n"
        f"Math verdict:\n{verdict_line.strip()}\n\n"
        f"DATA evidence required:\n{data_body}\n\n"
        f"Final verifier status:\n{final_status.strip()}"
    )


def main() -> None:
    rng = random.Random(SEED)
    n_adv = int(round(TARGET_N * ADV_FRAC))
    n_clean = TARGET_N - n_adv

    rows: list[dict] = []

    # --- Adversarial pools (false or dangerously sloppy claims) ---
    adv_inputs = [
        (
            "[VERIFY] Claim: Long perpetuals always earn positive funding on every major venue.",
            "Incorrect — funding sign depends on premium/discount vs index; longs can pay.",
            [
                "Signed funding rate series",
                "Mark-index premium window",
                "Venue funding formula doc",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Positive funding means the market is bullish for long holders.",
            "Incorrect — positive funding (longs pay) increases carry cost; not a directional signal alone.",
            [
                "Funding interval logs",
                "OI and premium jointly",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: If RSI is oversold, liquidation risk can be ignored on high leverage.",
            "Incorrect — liquidation uses margin vs mark; RSI does not set maintenance margin.",
            [
                "Margin ratio vs mark",
                "Maintenance parameters",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Perpetual mark price is always identical to the last traded price.",
            "Incorrect — mark is typically an index/mark composite for liquidations; differs from last trade.",
            [
                "Mark composition",
                "Last trade tape",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Rising open interest always proves trend strength and direction.",
            "Incorrect — OI rises with both new long and new short interest; not directional alone.",
            [
                "OI decomposition",
                "Signed delta positioning if available",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: At 50x leverage, cumulative funding is negligible vs PnL so it can be ignored.",
            "Incorrect — funding accrues per interval; at high leverage small moves dominate liquidation not funding negligibility.",
            [
                "Cumulative funding paid",
                "Hold horizon",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: The last candle was green so entry is valid regardless of liquidation distance.",
            "Incorrect — candle color does not bound liquidation buffer vs maintenance.",
            [
                "Liquidation price vs mark",
                "Leverage and mmr",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Negative funding always helps longs because it reduces their position cost.",
            "Incorrect — convention-dependent; negative funding can mean shorts pay longs or reverse per venue display.",
            [
                "Venue sign convention",
                "Who pays whom table",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Funding is paid every eight hours so intraday strategies never pay funding.",
            "Incorrect — boundaries can charge at settlement windows; intraday can still cross intervals.",
            [
                "Settlement timestamps",
                "Position open/close logs",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Basis is zero when mark equals index on a perp.",
            "Incorrect — basis is perp vs spot; even if close, funding carries non-zero carry expectation.",
            [
                "Spot reference index",
                "Perp mark definition",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: OI spike plus neutral funding guarantees imminent cascading liquidations.",
            "Incorrect — requires imbalance + price movement near liquidation clusters; not deterministic.",
            [
                "Liquidation heatmap",
                "Funding sign history",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Cross-exchange funding rates must always match exactly.",
            "Incorrect — index composition and intervals differ; arb reduces but not identical.",
            [
                "Venue A vs B formula",
                "Index constituents",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Expected value of holding ignores funding because it averages to zero.",
            "Incorrect — cumulative expectation depends on premium regime over horizon.",
            [
                "Premium regime stats",
                "Horizon length",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Index price is always safe for liquidation checks.",
            "Incorrect — liquidations use mark; gap matters during volatility.",
            [
                "Mark/index divergence stats",
            ],
            "FAIL",
        ),
    ]

    for i in range(n_adv):
        tpl = adv_inputs[i % len(adv_inputs)]
        inp, mv, data_bullets, st = tpl
        inp_v = inp + (f" Variant {i//len(adv_inputs)+1}." if i >= len(adv_inputs) else "")
        out = four_section_output(
            claim_summary=inp_v,
            verdict_line=mv,
            data_bullets=data_bullets,
            final_status=st,
        )
        cat = (
            "funding_liquidation"
            if any(
                k in inp_v.lower()
                for k in ("funding", "perp", "liquidation", "leverage", "mark", "oi", "basis")
            )
            else "cross_cutting"
        )
        rows.append(
            {
                "instruction": INSTR,
                "input": inp_v + "\n",
                "output": out,
                "source_ids": ["v0.2_reinforcement_synth", f"adv_{i+1:04d}"],
                "category": cat,
                "adversarial": True,
                "quality_flags": [
                    "substance_v0.2",
                    "adversarial_trap",
                    hashlib.sha256(inp_v.encode()).hexdigest()[:8],
                ],
            }
        )

    # --- Non-adversarial: correct mechanics teaching ---
    clean_templates = [
        (
            "[VERIFY] Explain whether longs always receive funding when the rate is positive under typical venue conventions.",
            "Correct — positive funding often means longs pay shorts when perp trades above index; verify venue sign convention.",
            [
                "Premium index history",
                "Official funding equation",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Does mark price for liquidation equal last traded price?",
            "Incorrect as a universal claim — mark is derived for fairness; last trade can diverge.",
            [
                "Mark methodology PDF",
                "Last trade feed",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] How does leverage affect liquidation distance holding funding fixed?",
            "Correct — higher leverage tightens distance to liquidation for same mark move.",
            [
                "Maintenance margin curve",
                "Entry price and leverage",
            ],
            "PASS",
        ),
    ]

    for j in range(n_clean):
        tpl = clean_templates[j % len(clean_templates)]
        inp, mv, data_bullets, st = tpl
        inp_v = inp + f" Teaching sample {j+1}."
        out = four_section_output(
            claim_summary=inp_v,
            verdict_line=mv,
            data_bullets=data_bullets,
            final_status=st,
        )
        rows.append(
            {
                "instruction": INSTR,
                "input": inp_v + "\n",
                "output": out,
                "source_ids": ["v0.2_reinforcement_synth", f"clean_{j+1:04d}"],
                "category": "funding_liquidation",
                "adversarial": False,
                "quality_flags": ["substance_v0.2", "reference_answer"],
            }
        )

    rng.shuffle(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    adv_n = sum(1 for r in rows if r.get("adversarial"))
    print(json.dumps({"path": str(OUT), "total": len(rows), "adversarial": adv_n, "seed": SEED}, indent=2))


if __name__ == "__main__":
    main()
