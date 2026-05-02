#!/usr/bin/env python3
"""
FinQuant-1 v0.1 JSONL generator — synthetic, verifier-contract aligned.
Does not train models. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from typing import Any

# Allocation @ 6000 total (exact plan proportions scaled from 15k; sum = 6000)
CAT_COUNTS: list[tuple[int, int]] = [
    (1, 480),
    (2, 560),
    (3, 960),
    (4, 880),
    (5, 240),
    (6, 320),
    (7, 240),
    (8, 360),
    (9, 480),
    (10, 280),
    (11, 680),  # adjusted −40 vs naive scale to hit 6000
    (12, 160),
    (13, 360),
]


def _vb(
    claim: str,
    math_v: str,
    risk_v: str,
    ind_v: str,
    regime: str,
    fail_modes: str,
    leak: str,
    policy: str,
    data_ev: str,
    status: str,
) -> str:
    return (
        f"Claim reviewed: {claim}\n"
        f"Math verdict: {math_v}\n"
        f"Risk/PnL verdict: {risk_v}\n"
        f"Indicator validity: {ind_v}\n"
        f"Regime considerations: {regime}\n"
        f"Failure modes / edge cases: {fail_modes}\n"
        f"Leakage / overfit concerns: {leak}\n"
        f"Policy-vs-implementation concerns: {policy}\n"
        f"DATA evidence required: {data_ev}\n"
        f"Final verifier status: {status}"
    )


def _golden(cat: int) -> str:
    if cat in (1, 4, 9, 12, 13):
        return "quant_stat"
    if cat in (2, 5, 6):
        return "crypto_derivatives"
    if cat in (3, 7, 8):
        return "indicator"
    if cat in (10, 11):
        return "code_review"
    return "mixed"


def gen_record(cat: int, seq: int, rng: random.Random, adversarial: bool) -> dict[str, Any]:
    sym = rng.choice(["BTC", "ETH", "SOL", "AVAX"])
    perp = f"{sym}-PERP"
    fee = rng.randint(2, 10)
    lev = rng.choice([3, 5, 10, 25])

    # Deterministic variety from seq
    tag = f"v01-c{cat}-s{seq}"

    if cat == 1:
        if adversarial:
            ins = (
                f"[{tag}] Verify reported net PnL on {perp} long when funding cashflows are omitted "
                f"and fees are applied to margin not notional."
            )
            inp = (
                f"Position {rng.randint(1, 50)} {sym}; entry {rng.randint(40000, 70000)}, exit +{rng.randint(50, 400)} USD notional move; "
                f"claimed profit uses mid marks only; per-side fee {fee} bps on notional; positive funding ignored."
            )
            out = _vb(
                claim=f"Net trade economics on {perp} ignoring funding and possibly mis-stating fee base.",
                math_v="incorrect / insufficient until funding and fee basis match venue policy.",
                risk_v="Risk controls based on false PnL may mis-size exposure.",
                ind_v="N/A",
                regime=f"Perpetual funding regime applies every interval—cannot assume equity spot logic.",
                fail_modes="Confusing fee base (notional vs margin); omitting funding; using chart mid vs fills.",
                leak="N/A unless labels used future marks.",
                policy="Cross-check fee tier JSON vs matching engine rounding mode.",
                data_ev=f"Funding ledger rows for position id; fee invoices; actual fills vs mid reconstruction.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Reconcile spot-equivalent PnL including fees for a fully specified perp round-trip."
            inp = (
                f"{perp} long 2 contracts; entry mark 62_000; exit 62_400; round-trip fee {fee} bps notional each side; "
                f"funding paid −0.005% on entry notional once. Provide net USD."
            )
            out = _vb(
                claim="Fully specified fee+funding perp PnL.",
                math_v="correct once formulas applied with venue definitions (verify rounding).",
                risk_v="Sizing sound only if liquidation buffer unchanged.",
                ind_v="N/A",
                regime="High leverage raises liquidation proximity—monitor margin asset volatility.",
                fail_modes="Rounding at settlement boundaries; partial fills vs assumptions.",
                leak="N/A for this toy ledger.",
                policy="Ensure fee schedule matches VIP tier used.",
                data_ev="Signed fills CSV + funding rows + fee tier snapshot.",
                status="pass",
            )

    elif cat == 2:
        if adversarial:
            ins = f"[{tag}] Challenge claim that OI↑ and price↑ alone imply imminent bearish unwind on {perp}."
            inp = "Open interest and spot rose together for 3 sessions; author concludes crowded long must collapse."
            out = _vb(
                claim="OI+price joint rise implies predictable reversal.",
                math_v="insufficient — causal structure unspecified.",
                risk_v="Positioning inference risk if hedging flows ignored.",
                ind_v="N/A",
                regime="Trend vs chop regimes interpret OI differently.",
                fail_modes="Retail-only OI; leverage composition unknown; external hedgers.",
                leak="N/A",
                policy="Positioning dashboards must disclose venue coverage.",
                data_ev="OI by tenor; liquidations feed; basis & funding distribution.",
                status="needs proof",
            )
        else:
            ins = f"[{tag}] Explain basis spot-vs-{perp} under persistent positive funding."
            inp = "Perp trades rich vs index spot for multiple intervals; funding positive and stable."
            out = _vb(
                claim="Interpret rich perp vs spot under positive funding.",
                math_v="directionally coherent but magnitude needs borrow/latency costs.",
                risk_v="Carry drag may dominate short scalps.",
                ind_v="N/A",
                regime="Funding regimes flip—carry traders vs hedgers.",
                fail_modes="Stale index composition; oracle latency.",
                leak="N/A",
                policy="Mark/index methodology documented.",
                data_ev="Index constituents; oracle timestamps; borrow curves.",
                status="needs proof",
            )

    elif cat == 3:
        ind = rng.choice(["RSI(14)", "MACD(12,26,9)", "Bollinger(20,2)", "ATR(14)", "VWAP(session)"])
        if adversarial:
            ins = f"[{tag}] Trap: treat {ind} oversold reading as automatic mean-reversion buy in strong trend."
            inp = f"ADX high trend day on {sym}; RSI prints oversold twice; author buys spot assuming bounce."
            out = _vb(
                claim=f"{ind} oversold implies bounce suitable for spot entry.",
                math_v="indicator arithmetic may be fine but inference incorrect.",
                risk_v="Trend exhaustion risk underestimated.",
                ind_v=f"{ind} invalid as standalone MR signal in strong trend—persistent extremes occur.",
                regime="Trend vs chop—indicator semantics shift materially.",
                fail_modes="Lag; periodic extremes in momentum regimes; volatility crush.",
                leak="If labels peek future troughs—invalidate.",
                policy="Strategy doc must state MR filters vs trend filters.",
                data_ev="ADX series; regime labels methodology; trade list.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Describe what {ind} measures and how regime changes interpretation on {perp}."
            inp = f"Provide assumptions and failure modes—not trading instructions."
            out = _vb(
                claim=f"Educational summary of {ind} interpretation constraints.",
                math_v="correct at definitional level—verify parameter window matches feed.",
                risk_v="Misapplication risk when volatility shifts abruptly.",
                ind_v=f"{ind} measures constructed statistic—not destiny.",
                regime="Volatility expansion/contraction changes signal persistence.",
                fail_modes="Sampling gaps; session resets for VWAP; stale feeds.",
                leak="N/A",
                policy="Indicator params frozen vs research drift.",
                data_ev="Feed spec; parameter JSON; exchange timestamp alignment.",
                status="pass",
            )

    elif cat == 4:
        if adversarial:
            ins = f"[{tag}] Trap: pair-trade hedge using stable rolling correlation on {sym}/ETH during stress."
            inp = "Uses 30d rolling corr=0.92 to size hedge; March shock week ignored in rationale."
            out = _vb(
                claim="Static correlation suffices for hedge sizing under stress.",
                math_v="incorrect — correlation unstable; conditional beta shifts.",
                risk_v="Severe tail mismatch—basis jump risk.",
                ind_v="Correlation instability invalidates naive z-score MR assumptions.",
                regime="Stress regime breaks cointegration maintenance.",
                fail_modes="Regime shift; liquidity disappearance; funding asymmetry.",
                leak="If correlation uses future-centered window—fatal.",
                policy="Risk limits must enforce stress correlation shocks.",
                data_ev="Rolling corr series; EWMA vs Pearson; tail dependence metrics.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Assess rolling realized vol window sensitivity for {perp} risk caps."
            inp = "Compare 10-bar vs 30-bar realized vol on 1h bars—same annualization assumptions."
            out = _vb(
                claim="Vol estimate stability across windows.",
                math_v="correct comparison if annualization formula identical and bars aligned.",
                risk_v="Wrong window mis-calibrates VaR bands.",
                ind_v="Vol estimator choice is statistical assumption-heavy.",
                regime="Vol clustering means short windows noisy.",
                fail_modes="Microstructure noise at low liquidity; missing bars.",
                leak="Centered windows leak if used live.",
                policy="Risk engine documents vol estimator.",
                data_ev="Bar construction logs; clock sync; missing bar policy.",
                status="needs proof",
            )

    elif cat == 5:
        if adversarial:
            ins = f"[{tag}] Infer aggressive buy delta from 1m OHLC alone on {sym}."
            inp = "Only OHLC candles—claims signed volume delta reconstructed precisely."
            out = _vb(
                claim="Signed order flow from OHLC.",
                math_v="incorrect — information insufficient (aggregation destroys aggressor side).",
                risk_v="Flow-driven strategies falsely calibrated.",
                ind_v="N/A",
                regime="Auction vs continuous matching assumptions unstated.",
                fail_modes="Hidden iceberg; wash prints.",
                leak="If hidden tape used—disclose.",
                policy="Data subscription tier must match claim.",
                data_ev="L2 snapshots or trades tape with aggressor flags.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Evaluate linear market impact model limits for large clip on thin {sym} book."
            inp = "Model: Δprice = λ * signed_volume; λ constant across sizes."
            out = _vb(
                claim="Linear impact forever.",
                math_v="insufficient — convex impact typical.",
                risk_v="Underestimates tail cost.",
                ind_v="N/A",
                regime="Liquidity episodic—λ not stable.",
                fail_modes="Self-impact loops; latency arbitrage.",
                leak="N/A",
                policy="Simulator params bounded vs production.",
                data_ev="Historical impact curves; depth snapshots.",
                status="needs proof",
            )

    elif cat == 6:
        if adversarial:
            ins = f"[{tag}] Trap: single 8h funding print as definitive sentiment on {perp}."
            inp = "Funding +0.03% once; concludes longs must pay forever upward."
            out = _vb(
                claim="Single funding observation proves sustained carry burden.",
                math_v="insufficient — distribution unknown.",
                risk_v="Trade thesis fragile.",
                ind_v="Funding rate is noisy funding-pressure statistic—not price oracle.",
                regime="Funding spikes cluster around squeezes.",
                fail_modes="Oracle glitch; settlement delays; exchange-specific caps.",
                leak="N/A",
                policy="Funding caps / clamps documented.",
                data_ev="Historical funding series; premium index components.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Compare funding trend vs single print for {perp} carry reasoning."
            inp = "Series last 14 intervals stable positive vs one-off spike yesterday."
            out = _vb(
                claim="Trend vs spike distinction matters for carry forecasts.",
                math_v="coherent—quantify trend slope confidence.",
                risk_v="Borrow/latency may dominate tiny funding.",
                ind_v="Treat funding as probabilistic pressure gauge.",
                regime="Trending premium vs mean-reverting premium differs.",
                fail_modes="Cross-exchange arbitrage breaks local narrative.",
                leak="N/A",
                policy="Which venue reference for portfolio.",
                data_ev="Interval-aligned funding pulls; premium constituents.",
                status="needs proof",
            )

    elif cat == 7:
        if adversarial:
            ins = f"[{tag}] Predict breakout direction from Bollinger squeeze alone on {sym}."
            inp = "Bandwidthmin percentile 5%; author opens long before breakout."
            out = _vb(
                claim="Squeeze implies directional breakout bias.",
                math_v="insufficient — squeeze signals compression not direction.",
                risk_v="False breakout both ways.",
                ind_v="Bollinger squeeze ≠ directional edge absent confirming structure.",
                regime="Mean-reverting chop produces repeated squeezes.",
                fail_modes="Flash wicks; feed outages widening bands artificially.",
                leak="Future volatility labels in training—trap.",
                policy="Research sandbox vs prod params frozen.",
                data_ev="Band formula; feed quality metrics.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Explain vol expansion cycle vs prior compression on {perp} risk sizing."
            inp = "ATR rising after multi-week range—risk desk cuts leverage halving."
            out = _vb(
                claim="Vol expansion warrants leverage reduction.",
                math_v="reasonable heuristic—quantify tail thresholds.",
                risk_v="Over-correction may miss continuation.",
                ind_v="ATR reactive—lags abrupt shocks.",
                regime="Trending volatility vs single spike.",
                fail_modes="Gap openings; oracle jumps.",
                leak="N/A",
                policy="Leverage schedule documented.",
                data_ev="ATR feed; leverage enforcement logs.",
                status="pass",
            )

    elif cat == 8:
        if adversarial:
            ins = f"[{tag}] Multi-TF conflict: 1m MACD buy vs 1d downtrend—pick winner without rules."
            inp = "Retail bot buys 1m MACD cross while daily structure bearish."
            out = _vb(
                claim="Lower TF signal overrides higher TF trend absent governance.",
                math_v="insufficient — conflict resolution undefined.",
                risk_v="Whipsaw amplification.",
                ind_v="Indicators conflict—priority rules required—not implicit.",
                regime="Higher TF dominance assumption must be explicit.",
                fail_modes="Repainting lower TF indicators; session boundaries.",
                leak="Using closed daily bar before hour closes intraday features.",
                policy="Conflict playbook in strategy spec.",
                data_ev="Timestamp-aligned bars; higher TF completion proofs.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Document stacked lag when RSI(14) on 15m aligns with EMA slope on 4h."
            inp = "Describe interaction—not a trading rule."
            out = _vb(
                claim="Explain lag accumulation across stacked indicators.",
                math_v="consistent if windows aligned—verify alignment math.",
                risk_v="Double-counting momentum exposure.",
                ind_v="Interaction terms matter—avoid redundant signals.",
                regime="Fast TF noise vs slow TF bias.",
                fail_modes="Alignment coincidence vs structural coupling.",
                leak="Peak future returns used to tune alignment.",
                policy="Feature independence tests documented.",
                data_ev="Covariance matrix across horizons.",
                status="needs proof",
            )

    elif cat == 9:
        if adversarial:
            ins = f"[{tag}] Detect lookahead in join between trades and 1m features on {sym}."
            inp = "SQL join uses feature_timestamp <= trade_timestamp but features table accidentally includes bar close timestamp labeled open."
            out = _vb(
                claim="Join keyed without lookahead.",
                math_v="incorrect — subtle timestamp semantics leak future bar info.",
                risk_v="Backtest Sharpe overstated.",
                ind_v="N/A",
                regime="Bar labeling conventions differ venues.",
                fail_modes="Inclusive inequalities; timezone DST.",
                leak="High confidence — leakage suspected.",
                policy="Canonical clock policy per venue.",
                data_ev="Explain plans; row-level invariant checks; hash replay.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Survivorship bias risk when universe = listed perps only still trading."
            inp = "Backtest winners only—delisted contracts omitted."
            out = _vb(
                claim="Historical universe matches tradable reality.",
                math_v="insufficient — survivorship biases returns upward.",
                risk_v="Capital deployment assumptions false.",
                ind_v="N/A",
                regime="Listing churn regime crypto-high.",
                fail_modes="Manual removals; contract migrations.",
                leak="Drop labels informed by future delisting.",
                policy="Universe freeze timestamps.",
                data_ev="Contract lifecycle table; inclusion criteria.",
                status="needs proof",
            )

    elif cat == 10:
        if adversarial:
            ins = f"[{tag}] Policy PDF rounds fees down; production code rounds nearest cent asymmetrically."
            inp = "Mismatch causes systematic sub-cent drift vs treasury ledger."
            out = _vb(
                claim="Fee rounding consistent with policy.",
                math_v="incorrect — divergence detected.",
                risk_v="Compliance & treasury reconciliation breaks.",
                ind_v="N/A",
                regime="High-volume amplifies drift.",
                fail_modes="Bankers rounding vs truncate; currency conversions.",
                leak="N/A",
                policy="Patch code or policy—single source of truth.",
                data_ev="Diff ledger vs policy simulator on shadow traffic.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Verify hidden leverage cap in risk engine matches operator handbook."
            inp = "Handbook 10x max; code constant MAX_LEV=5 for retail tier flag True."
            out = _vb(
                claim="Effective leverage bound consistent.",
                math_v="needs_proof until tier routing confirmed.",
                risk_v="Users may assume 10x.",
                ind_v="N/A",
                regime="Retail vs pro tiers.",
                fail_modes="Flag mis-set during deploy.",
                leak="N/A",
                policy="Release notes + config hash pinned.",
                data_ev="Config artifact + ABAC tier assignments.",
                status="needs proof",
            )

    elif cat == 11:
        if adversarial:
            ins = f"[{tag}] Code review: pandas rolling mean signal uses center=True unintentionally on {sym} returns."
            inp = "rolling(14).mean() default center=False OK—but author set center=True without noticing lookahead."
            out = _vb(
                claim="Rolling features computed without lookahead.",
                math_v="incorrect — centered rolling leaks future inside window.",
                risk_v="Backtest inflated.",
                ind_v="N/A",
                regime="Any bar frequency.",
                fail_modes="Off-by-one warm-up; tz-aware index bugs.",
                leak="Critical — centered window.",
                policy="Lint rule forbidding center=True in signal gen.",
                data_ev="Git blame + unit tests boundary rows.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Review numpy float accumulation in large ledger summation."
            inp = "Sums 10M np.float32 rows for equity — drift vs Decimal policy."
            out = _vb(
                claim="Float accumulation acceptable for treasury-grade totals.",
                math_v="insufficient — may violate tolerance policy.",
                risk_v="Silent drift vs auditors.",
                ind_v="N/A",
                regime="Large N amplifies error.",
                fail_modes="Kahan summation absent.",
                leak="N/A",
                policy="Decimal mandated above threshold.",
                data_ev="Parallel sum hashes vs Decimal slow path.",
                status="needs proof",
            )

    elif cat == 12:
        if adversarial:
            ins = f"[{tag}] Light table QA: revenue walk ignores contra-revenue line in excerpt."
            inp = "Mini income statement snippet JSON — user nets revenue without contra adjustments."
            out = _vb(
                claim="Net revenue calculation from partial table.",
                math_v="incorrect / incomplete — contra revenue omitted.",
                risk_v="Margin ratios mis-stated.",
                ind_v="N/A",
                regime="GAAP vs non-GAAP mix.",
                fail_modes="FX translation row confusion.",
                leak="N/A",
                policy="Mapping table line IDs.",
                data_ev="Full filing segment + footnotes cross-ref.",
                status="fail",
            )
        else:
            ins = f"[{tag}] Map table rows to net change assertion with explicit units."
            inp = "Two-line excerpt gross vs discounts provided — compute net."
            out = _vb(
                claim="Net from explicit rows.",
                math_v="correct if units homogeneous.",
                risk_v="ImmMaterial omissions.",
                ind_v="N/A",
                regime="Seasonality commentary out of scope.",
                fail_modes="Thousands vs millions scaling.",
                leak="N/A",
                policy="Unit encoding metadata.",
                data_ev="Source filing cell coordinates.",
                status="pass",
            )

    else:  # cat == 13
        if adversarial:
            ins = f"[{tag}] Vendor claims Sharpe 6 on {sym} strategy—what DATA falsifies fastest?"
            inp = "Marketing deck only—no raw returns."
            out = _vb(
                claim="Vendor Sharpe superiority.",
                math_v="insufficient — cannot verify.",
                risk_v="Allocation risk if believed.",
                ind_v="N/A",
                regime="Any.",
                fail_modes="Cherry window; inflated fills.",
                leak="Suspicion high.",
                policy="Vendor diligence checklist.",
                data_ev="Tick-accurate fills; benchmark RF; full trade log signed.",
                status="needs proof",
            )
        else:
            ins = f"[{tag}] Enumerate DATA queries to prove no lookahead in feature pipeline."
            inp = "Describe joins & invariant checks—not SQL dumps."
            out = _vb(
                claim="Negative lookahead provability plan.",
                math_v="N/A",
                risk_v="Model risk if unproven.",
                ind_v="N/A",
                regime="Any.",
                fail_modes="Clock skew.",
                leak="Define PASS/FAIL invariant.",
                policy="Replay harness ownership.",
                data_ev="SQL explain; max(feature_ts)<=trade_ts grouped; hash parity replay.",
                status="needs proof",
            )

    rec = {
        "instruction": ins,
        "input": inp,
        "output": out,
        "meta": {
            "category_id": cat,
            "golden_bucket": _golden(cat),
            "polarity": "adversarial" if adversarial else "positive",
            "tag": tag,
        },
    }
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--total", type=int, default=6000, help="Must match sum CAT_COUNTS")
    args = ap.parse_args()

    total = sum(c for _, c in CAT_COUNTS)
    if args.total != total:
        raise SystemExit(f"--total {args.total} != configured sum {total}")

    rng = random.Random(args.seed)
    rows: list[dict[str, Any]] = []

    for cat, n in CAT_COUNTS:
        # Target ≥52% adversarial per category then global trim
        n_adv = max(int(round(n * 0.52)), int(n * 0.5) + (1 if n % 2 else 0))
        if n_adv > n:
            n_adv = n
        flags = [True] * n_adv + [False] * (n - n_adv)
        rng.shuffle(flags)
        for i in range(n):
            rows.append(gen_record(cat, i, rng, flags[i]))

    rng.shuffle(rows)

    out_path = args.out
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            # Training triple + meta strip-friendly: keep meta for QA JSONL
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Deterministic fingerprint
    h = hashlib.sha256(open(out_path, "rb").read()).hexdigest()[:16]
    print(out_path, "samples", len(rows), "sha256-prefix", h)


if __name__ == "__main__":
    main()
