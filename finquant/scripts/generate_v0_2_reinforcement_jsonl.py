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
# Bump seed when DATA-evidence templates materially change (reproducible shuffle).
SEED = 42003

DATA_SCHEMA_NOTE = "data_evidence_tightened_v0.2b"


def _claim_reviewed_snip(s: str, max_words: int = 22) -> str:
    w = s.replace("\n", " ").strip().split()
    if len(w) <= max_words:
        return " ".join(w)
    return " ".join(w[:max_words]) + "…"


def format_data_evidence_block(items: list[str]) -> str:
    """Concrete verifier DATA asks — no echo of the user prompt."""
    lines = [f"- {x.strip()}" for x in items if x and x.strip()]
    return "\n".join(lines) if lines else "- Venue funding schedule with timestamps (UTC)"


def four_section_output(
    *,
    claim_summary: str,
    verdict_line: str,
    data_items: list[str],
    final_status: str,
) -> str:
    data_body = format_data_evidence_block(data_items)
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

    # --- Adversarial pools: DATA evidence lines are concrete requests (no prompt echo).
    adv_inputs = [
        (
            "[VERIFY] Claim: Long perpetuals always earn positive funding on every major venue.",
            "Incorrect — funding sign depends on premium/discount vs index; longs can pay.",
            [
                "Funding rate timestamps (UTC) and venue identifier",
                "Official funding payment direction convention for this venue",
                "Signed funding rate per interval vs index premium",
                "Mark price and index price at each funding snapshot",
                "Position side (long/short) for the position under review",
                "Basis (mark − index) time series for the claim window",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Positive funding means the market is bullish for long holders.",
            "Incorrect — positive funding (longs pay) increases carry cost; not a directional signal alone.",
            [
                "Funding rate timestamps and venue",
                "Funding payment direction: who pays whom (long vs short) per venue docs",
                "Mark price and index price path across holds",
                "Open interest delta per interval (ΔOI)",
                "Replay bar timestamps for premium/dispute window",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: If RSI is oversold, liquidation risk can be ignored on high leverage.",
            "Incorrect — liquidation uses margin vs mark; RSI does not set maintenance margin.",
            [
                "Mark price and liquidation price from exchange risk engine",
                "Leverage and margin mode (cross/isolated)",
                "Maintenance margin bracket for the instrument",
                "Entry price and position size",
                "Replay bar timestamps covering RSI window vs margin checks",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Perpetual mark price is always identical to the last traded price.",
            "Incorrect — mark is typically an index/mark composite for liquidations; differs from last trade.",
            [
                "Mark methodology PDF / API field definitions",
                "Last traded price stream with exchange timestamps",
                "Mark vs last trade divergence stats for the session",
                "Index constituents feeding mark",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Rising open interest always proves trend strength and direction.",
            "Incorrect — OI rises with both new long and new short interest; not directional alone.",
            [
                "Open interest delta per bar with timestamps",
                "Long/short OI split if venue publishes it",
                "Mark price path aligned to OI bars",
                "Funding rate timestamps in same window",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: At 50x leverage, cumulative funding is negligible vs PnL so it can be ignored.",
            "Incorrect — funding accrues per interval; at high leverage small moves dominate liquidation not funding negligibility.",
            [
                "Cumulative funding paid over holding interval",
                "Fee schedule (maker/taker, funding) for the account tier",
                "Holding interval boundaries (open → close UTC)",
                "Leverage setting used by risk engine",
                "Mark price series for liquidation proximity check",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: The last candle was green so entry is valid regardless of liquidation distance.",
            "Incorrect — candle color does not bound liquidation buffer vs maintenance.",
            [
                "Replay bar timestamps for entry candle and subsequent bars",
                "Liquidation price vs current mark",
                "Leverage and margin mode",
                "Entry price and maintenance margin parameters",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Negative funding always helps longs because it reduces their position cost.",
            "Incorrect — convention-dependent; negative funding can mean shorts pay longs or reverse per venue display.",
            [
                "Venue funding payment direction convention (document link or API enum)",
                "Funding rate timestamp series with sign interpretation table",
                "Position side and size",
                "Mark price and index price at assessment time",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Funding is paid every eight hours so intraday strategies never pay funding.",
            "Incorrect — boundaries can charge at settlement windows; intraday can still cross intervals.",
            [
                "Official funding settlement timestamps (UTC) for the instrument",
                "Position open/close event log with millisecond timestamps where available",
                "Funding rate applied each crossing interval",
                "Fee schedule including funding caps/floors",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Basis is zero when mark equals index on a perp.",
            "Incorrect — basis is perp vs spot; even if close, funding carries non-zero carry expectation.",
            [
                "Spot reference index ID and constituents",
                "Perp mark calculation inputs from venue",
                "Mark price and index price sampled at same timestamps",
                "Basis time series (mark − index)",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: OI spike plus neutral funding guarantees imminent cascading liquidations.",
            "Incorrect — requires imbalance + price movement near liquidation clusters; not deterministic.",
            [
                "Liquidation cluster prices with replay bar timestamps",
                "Open interest delta aligned to price bars",
                "Funding rate timestamps showing neutral vs crowded skew",
                "Mark price path vs liquidation ladder",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Cross-exchange funding rates must always match exactly.",
            "Incorrect — index composition and intervals differ; arb reduces but not identical.",
            [
                "Venue A funding timestamps and venue B funding timestamps (paired UTC)",
                "Index constituents for each venue’s mark/index",
                "Funding formula parameters per venue",
                "Basis between venues if applicable",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Expected value of holding ignores funding because it averages to zero.",
            "Incorrect — cumulative expectation depends on premium regime over horizon.",
            [
                "Historical premium regime statistics for the asset",
                "Holding interval length and funding intervals crossed",
                "Cumulative funding paid vs projected from rate curve",
                "Mark price volatility over hold (liq risk)",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] Claim: Index price is always safe for liquidation checks.",
            "Incorrect — liquidations use mark; gap matters during volatility.",
            [
                "Mark price vs index price time series during volatile window",
                "Liquidation engine rule: mark vs index reference",
                "Replay bar timestamps for gap events",
                "Leverage and liquidation price output from exchange API",
            ],
            "FAIL",
        ),
    ]

    for i in range(n_adv):
        tpl = adv_inputs[i % len(adv_inputs)]
        inp, mv, data_items, st = tpl
        inp_v = inp + (f" Variant {i//len(adv_inputs)+1}." if i >= len(adv_inputs) else "")
        out = four_section_output(
            claim_summary=inp_v,
            verdict_line=mv,
            data_items=data_items,
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
                    DATA_SCHEMA_NOTE,
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
                "Venue funding payment direction convention (official doc)",
                "Funding rate timestamps (UTC) and signed rate series",
                "Mark price and index price at funding snapshots",
                "Position side and contract multiplier",
                "Fee schedule row used for the account",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Does mark price for liquidation equal last traded price?",
            "Incorrect as a universal claim — mark is derived for fairness; last trade can diverge.",
            [
                "Mark calculation specification from venue",
                "Last traded price log with timestamps",
                "Liquidation price engine output (mark-based)",
                "Replay bar timestamps around liquidation tests",
            ],
            "FAIL",
        ),
        (
            "[VERIFY] How does leverage affect liquidation distance holding funding fixed?",
            "Correct — higher leverage tightens distance to liquidation for same mark move.",
            [
                "Leverage setting and margin mode",
                "Entry price; mark price; liquidation price from risk API",
                "Maintenance margin curve parameters",
                "Open interest not required but optional position ID for audit",
            ],
            "PASS",
        ),
    ]

    for j in range(n_clean):
        tpl = clean_templates[j % len(clean_templates)]
        inp, mv, data_items, st = tpl
        inp_v = inp + f" Teaching sample {j+1}."
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
