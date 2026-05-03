# prove_learning → training handoff note

**From:** Cody (prove_learning thread)  
**To:** Training thread agent  
**Date:** 2026-05-03  
**Status:** Read this before touching the corpus

---

## DIRECTIVE — ACTION REQUIRED WHILE THE MODEL TRAINS

The QLoRA run is at ~36% on trx40. You have approximately 3–4 hours before it finishes. Use that time now.

**The corpus has 3 examples. The model cannot be reliable with 3 examples.**

The baseline showed the model fails on:
- Schema validity: 7% (needs 98%)
- Risk plan: missing on 93/100 decisions
- Learning record validity: 52%
- Decision: 100% NO_TRADE — model refuses all entries

These failures are **corpus failures**, not model failures. The model never saw enough examples of correct FinQuant decisions to know what they look like.

### What you must do before the training run finishes:

**Step 1 — Audit the current corpus (30 minutes)**

Read `training/corpus_v05_agentic_seed.jsonl`. Verify:
- Does each row have `risk_plan` with `stop_logic`, `target_logic`, `max_loss_awareness`, `position_sizing_comment`?
- Does each row have `competing_hypothesis`?
- Does each row have `learning_record_candidate` with `setup_signature`, `lesson_if_win`, `lesson_if_loss`?
- Does at least one row show `ENTER` with `direction: LONG` or `SHORT`?

If the answer to any of these is no — those corpus rows are teaching the model the wrong behavior.

**Step 2 — Add at least 20 gold examples before next training run (2 hours)**

The model needs to see correct decisions to learn them. Add corpus rows covering:
- 5 × clean `ENTER LONG` with bullish RSI divergence, full risk plan, valid learning record
- 5 × clean `ENTER SHORT` with bearish RSI divergence, full risk plan
- 5 × correct `NO_TRADE` in chop/ranging with specific reason (not generic)
- 3 × `INSUFFICIENT_DATA` where confidence spread < 0.20
- 2 × `NO_TRADE` in high volatility trap with explicit reason

Each row must have:
```json
{
  "output": {
    "decision": "ENTER",
    "direction": "LONG",
    "confidence": 0.72,
    "thesis": "Bullish RSI divergence confirmed: price lower low (130.20→129.85) while RSI higher low (48.2→51.4). EMA bias LONG. ATR% 0.52% normal volatility.",
    "competing_hypothesis": "Counter: RSI at 51 not yet in bullish_strong zone — could be dead cat bounce.",
    "invalidation": "Exit if close below 129.50 (prev low) or RSI drops back below 48.",
    "risk_plan": {
      "stop_logic": "1.5x ATR below entry: 130.20 - (0.52*1.5) = 129.42",
      "target_logic": "1.23R above entry: 130.20 + (0.78*1.23) = 131.16",
      "max_loss_awareness": "3% collateral at risk. Stop is 0.60% below entry.",
      "position_sizing_comment": "Risk slice = 3% of wallet. Collateral = wallet * 0.03."
    },
    "learning_record_candidate": {
      "setup_signature": "bullish_divergence | volatile | ema_bias_long | rsi_50_55",
      "decision_taken": "ENTER_LONG",
      "lesson_if_win": "Bullish divergence in volatile regime with EMA long bias produced profitable entry.",
      "lesson_if_loss": "Divergence signal failed — check if regime shifted to ranging before entry.",
      "promotion_candidate": true,
      "do_not_promote_reason": null
    }
  }
}
```

**Step 3 — Add negative examples (DPO pairs) (30 minutes)**

For each good example, add a corresponding bad example showing what NOT to do:
- `ENTER LONG` in clear downtrend with no divergence → wrong
- `NO_TRADE` with empty `why_no_trade` → wrong
- Any decision with `risk_plan: null` → wrong

Label these with `"is_negative_example": true` so the training pipeline can use them as rejection pairs.

**Step 4 — Validate corpus before next run**

```bash
cd /home/vanayr/blackbox
python3 training/validate_agentic_corpus_v1.py training/corpus_v05_agentic_seed.jsonl
```

Must pass before the next training iteration starts.

---

### What prove_learning is providing

`prove_learning/` is generating real SOL-PERP decisions with divergence signal, H1/H2 hypotheses, and outcome labels. Those decisions are in `prove_learning/ledger_output/`. A corpus exporter to convert them to `finquant_agentic_qa_v1` format is being built. Watch for `training/PROVE_LEARNING_CORPUS_EXPORT.jsonl` — that will be the output.

**Do not wait for the current training run to finish before fixing the corpus. The next run depends on it.**

---

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
