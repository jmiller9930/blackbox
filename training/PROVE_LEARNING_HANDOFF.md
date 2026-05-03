# prove_learning → training handoff note

**From:** Cody (prove_learning thread)  
**To:** Training thread agent  
**Date:** 2026-05-03  
**Status:** Read this before touching the corpus

---

## What prove_learning has established

The `prove_learning/finquant/unified/agent_lab/` lab has proven a working learning loop on real SOL-PERP data. Key results from the latest run:

- **Decision quality: 70.5%** on cycle 1 (200 real 15m SOL-PERP cases)
- **Win rate: 52.2%** on entries taken
- **PnL: +$3.68** — first profitable run on real data
- **Pattern promotion: 2 ACTIVE patterns, 27 provisional, 10 retired**
- **LLM used: Qwen 2.5 7B via Ollama at 172.20.2.230:11434**

The key improvement that drove this: **RSI divergence signal** (Sean's signal) added to the feature extraction and surfaced explicitly in the prompt. Qwen now sees:

```
=== RSI DIVERGENCE — KEY ENTRY SIGNAL ===
*** BULLISH DIVERGENCE: price lower low + RSI higher low = momentum improving ***
```

96% of LLM decisions now cite divergence in their thesis.

---

## What the training corpus needs from this work

Every good decision from the training loop is a candidate corpus row in `finquant_agentic_qa_v1` format. The decisions in `prove_learning/ledger_output/` have:

- Real SOL-PERP OHLC + indicators (RSI, ATR%, EMA, divergence flags)
- Two competing hypotheses (H1/H2 with confidence — R-002 format)
- Confidence spread (gate: ≥0.20 → act, <0.10 → INSUFFICIENT_DATA)
- Action with reasoning that cites divergence and regime
- Outcome label (win/loss/no_trade_correct/no_trade_missed)

**The gap to bridge:** `prove_learning/` produces good decisions but not in the exact `finquant_agentic_qa_v1` schema yet. The `output` field needs `expectancy_check_v1` (R-003) and `Final_status` alignment.

---

## What the baseline run showed (v005)

The training thread baseline (`runs/baseline_20260502T005503Z/`) measured DeepSeek-R1 14B:
- Schema valid rate: **7%**
- All decisions: **NO_TRADE** (refused all entries)
- Missing risk plan: **93/100**
- Status: **BASELINE_BLOCKED_BY_SCHEMA_OR_LEARNING_RECORDS**

The model cannot produce valid FinQuant decision JSON. It needs:
1. The structured output contract trained in (the exact JSON schema)
2. Two-hypothesis reasoning trained in (R-002)
3. RSI divergence as a named signal trained in
4. Risk plan (planned_stop, planned_target, planned_r_multiple) trained in

---

## What prove_learning can supply when ready

A pipeline to convert training loop decisions into corpus rows:
- `prove_learning/finquant/unified/agent_lab/operator_ledger.py` already extracts decisions with H1/H2/spread/outcome
- Needs a converter to `finquant_agentic_qa_v1` format (not yet built — within my scope to build when directed)
- Good decisions (is_good_decision=True, confidence_spread≥0.20) are the gold examples
- Bad decisions with correct labels are the negative examples

---

## Current state of the live loop

- Cases: `prove_learning/finquant/unified/agent_lab/cases/market_solperp_15m_clawbot/` (2,461 real 15m SOL-PERP cases)
- Latest results: `prove_learning/finquant/unified/agent_lab/outputs/train_20260503T012636Z_e2c07190/`
- Ledger: `prove_learning/ledger_output/train_20260503T012636Z_e2c07190_decisions.csv`

**Do not modify anything in `prove_learning/` — that is Cody's scope.**
