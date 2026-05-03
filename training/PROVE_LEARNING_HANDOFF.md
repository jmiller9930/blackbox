# prove_learning → training handoff note

**From:** Cody (prove_learning thread)  
**To:** Training thread agent  
**Date:** 2026-05-03  
**Status:** Corrected after training engineer feedback — read before touching corpus

---

## DIRECTIVE — ACTION REQUIRED WHILE THE MODEL TRAINS

The QLoRA run is at ~36% on trx40. You have approximately 3–4 hours before it finishes. Use that time now.

**The corpus has 3 examples — all NO_TRADE. The model cannot learn to enter trades it has never seen.**

The baseline showed the model fails on:
- Schema validity: 7% (needs 98%)
- Risk plan: missing on 93/100 decisions
- Learning record validity: 52%
- Decision: 100% NO_TRADE — model refuses all entries

These failures are **corpus failures**, not model failures. Fix the corpus now so the NEXT run is better.

---

### Step 1 — Audit the current corpus (30 minutes)

Read `training/corpus_v05_agentic_seed.jsonl`. The correct schema uses:
- `hypotheses_v1` (array, minimum 2) — **not** `competing_hypothesis`
- `learning_record_candidate_v1` — **not** `learning_record_candidate`
- `expectancy_check_v1` with `planned_r_multiple`, `breakeven_win_rate_required`, `expectancy_per_trade_dollars`
- `Final_status`: `"ENTER_LONG"` or `"ENTER_SHORT"` for entries, `"NO_TRADE"`, `"INSUFFICIENT_DATA"`
- `deterministic_baseline_verdict_v1` with `verdict` and `blocking_rules`
- Stop: **1.6× ATR14** (from `config_v0.1.yaml: planned_stop_atr_multiple: 1.6`)
- Target: **4.0× ATR14** (from `config_v0.1.yaml: planned_target_atr_multiple: 4.0`)

Confirm: does at least one row have `Final_status: "ENTER_LONG"` or `"ENTER_SHORT"`? If no — the model has never been shown an entry example.

---

### Step 2 — Add at least 20 gold examples in correct schema (2 hours)

Add rows covering:
- 5 × `Final_status: "ENTER_LONG"` — bullish RSI divergence (price lower low + RSI higher low), EMA long bias, `hypotheses_v1` with ≥2 hypotheses
- 5 × `Final_status: "ENTER_SHORT"` — bearish RSI divergence (price higher high + RSI lower high)
- 5 × `Final_status: "NO_TRADE"` — chop/ranging with specific indicator values cited in `hypotheses_v1`
- 3 × `Final_status: "INSUFFICIENT_DATA"` — `confidence_gap_v1 < 0.20`, `i_dont_know_triggered: true`
- 2 × `Final_status: "NO_TRADE"` — high volatility trap with expectancy veto

Every ENTER row `expectancy_check_v1` must show correct math from config:
```
stop_distance    = 1.6 × ATR14
target_distance  = 4.0 × ATR14
planned_r_multiple = 4.0 / 1.6 = 2.5
breakeven_win_rate_required = 1 / (1 + 2.5) = 0.2857
expectancy_per_trade_dollars = (win_rate × target_dollars) − (loss_rate × risk_dollars)
contributes_to_long_run_math = true  (when estimated win_rate > 0.2857)
```

Example structure for an ENTER_LONG row (use `finquant_agentic_qa_v1` schema):
```json
{
  "Final_status": "ENTER_LONG",
  "hypotheses_v1": [
    {
      "id": "H1_bullish_divergence",
      "claim": "Bullish RSI divergence: price lower low (130.20→129.85), RSI higher low (48.2→51.4). EMA20 above EMA50. Entry justified.",
      "supporting_evidence": ["rsi14 rising while price declining", "ema20 > ema50", "atr_ratio near 1.0 = normal volatility"],
      "counter_evidence": ["RSI not yet in bullish_strong zone (< 58)"],
      "confidence": 0.68
    },
    {
      "id": "H2_dead_cat",
      "claim": "Price bounce is a dead cat; trend still down.",
      "supporting_evidence": ["short-term lower highs still intact"],
      "counter_evidence": ["RSI divergence confirmed on this bar"],
      "confidence": 0.32
    }
  ],
  "confidence_gap_v1": 0.36,
  "i_dont_know_triggered": false,
  "deterministic_baseline_verdict_v1": {
    "policy_id": "jupiter_2_sean_perps_v1",
    "verdict": "ENTER_LONG",
    "blocking_rules": []
  },
  "expectancy_check_v1": {
    "planned_r_multiple": 2.5,
    "planned_risk_dollars": 100.0,
    "planned_target_dollars": 250.0,
    "breakeven_win_rate_required": 0.2857,
    "this_setup_estimated_win_rate": 0.52,
    "expectancy_per_trade_dollars": 52.0,
    "contributes_to_long_run_math": true,
    "note": "Bullish divergence with EMA alignment gives estimated 52% win rate vs 28.6% breakeven at R=2.5"
  },
  "learning_record_candidate_v1": {
    "setup_signature": "bullish_divergence_rsi_48_52_ema_long_atr_normal",
    "decision_taken": "ENTER_LONG",
    "lesson_if_win": "Bullish divergence with EMA long bias and normal ATR produced profitable entry at R=2.5.",
    "lesson_if_loss": "Divergence signal failed — likely false positive in ranging market or regime shift.",
    "promotion_candidate": true,
    "do_not_promote_reason": null
  }
}
```

---

### Step 3 — DPO is OUT OF SCOPE for current SFT pipeline

`train_qlora.py` is SFT-only. Do **NOT** add negative example rows to `corpus_v05_agentic_seed.jsonl` — they would be used as assistant targets and poison SFT. Negative/rejection examples require a separate DPO/ORPO stage. Skip until that pipeline exists.

---

### Step 4 — Validate before next run

```bash
cd /home/vanayr/blackbox
python3 training/validate_agentic_corpus_v1.py training/corpus_v05_agentic_seed.jsonl
```

Must pass clean. Specifically check that ENTER rows exist and that `expectancy_check_v1` math is consistent with `config_v0.1.yaml` multiples (1.6 stop, 4.0 target).

---

### Step 5 — What prove_learning is sending

Cody is building an exporter that converts real SOL-PERP decisions from the training loop into `finquant_agentic_qa_v1` format. Run it with:

```bash
python3 training/export_ledger_rows_to_agentic_corpus.py \
  --ledger prove_learning/ledger_output/train_20260503T012636Z_e2c07190_decisions.json \
  --output training/prove_learning_export.jsonl \
  --min-confidence-spread 0.20 \
  --good-only
```

The `--output` path is your choice — validate and merge into `corpus_v05_agentic_seed.jsonl` before the next run.

---

## What prove_learning has established

- Decision quality: **70.5%** on cycle 1 (200 real 15m SOL-PERP cases with Qwen 7B)
- Win rate: **52.2%** on entries, PnL: **+$3.68**
- Key feature: RSI divergence (bullish = price lower low + RSI higher low; bearish = price higher high + RSI lower high) surfaced explicitly in prompt — 96% citation rate
- Pattern ladder: 2 ACTIVE patterns, 27 provisional, 10 retired
- Latest ledger: `prove_learning/ledger_output/train_20260503T012636Z_e2c07190_decisions.csv`

**Do not modify anything in `prove_learning/` — that is Cody's scope.**
