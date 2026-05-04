# FinQuant Memory Taxonomy

**Version:** 1.0  
**Owner:** Learning Engineer (prove_learning/)  
**Purpose:** Defines pattern signature classes, retrieval rules, and memory taxonomy
so that the training corpus and the LLM stay aligned on when to cite, abstain, or flag conflict.

---

## Pattern Signature Structure

Every decision bar produces a pattern_id hashed from these components:

```python
components = {
    "symbol_v1":           "SOL-PERP",          # instrument
    "timeframe_minutes_v1": 15,                  # candle size
    "trend_v1":            "trend_up|trend_down|trend_mixed",  # EMA/price relationship
    "rsi_bucket_v1":       "rsi_50_55|rsi_55_60|...",          # 5-point RSI bins
    "atr_bucket_v1":       "atr_under05|atr_05_1|...",         # ATR magnitude bins
    "volatility_v1":       "vol_high|vol_normal|vol_low",
    "volume_v1":           "vol_expand|vol_contract",
    "position_v1":         "pos_flat|pos_open",
}
pattern_id = sha256(json.dumps(components, sort_keys=True))[:16]
```

Two bars with the same bucket values → same pattern_id → same learning unit accumulates evidence.

---

## Memory Classes

| Class | Description | Retrieval rule |
|---|---|---|
| `ENTER_LONG` | Pattern produced a long entry that won | Retrieve when current regime + RSI bucket matches AND current action candidate is ENTER_LONG |
| `ENTER_SHORT` | Pattern produced a short entry that won | Retrieve when current regime + RSI bucket matches AND current action candidate is ENTER_SHORT |
| `NO_TRADE_CORRECT` | Pattern correctly stood down | Retrieve when evidence is ambiguous — use as caution signal |
| `RETIRED` | Pattern accumulated losses — suppressed | **Never retrieve.** If pattern_id matches a RETIRED unit, note the retirement in the thesis. |
| `CONFLICTING` | Same pattern_id has both wins and losses | Retrieve but flag as conflicting — must lower confidence |

---

## Retrieval Rules

**When retrieval is ALLOWED:**
- Pattern status: `provisional`, `validated`, or `active` (not `candidate` or `retired`)
- Pattern win_rate >= 0.65 (configurable via `retrieval_min_win_rate_v1`)
- Pattern observations >= 5 (configurable via `retrieval_min_obs_v1`)
- Regime match: retrieved pattern's regime must match current bar's regime
- Symbol match: same instrument

**When retrieval is FORBIDDEN:**
- Pattern status: `candidate` — not enough evidence yet
- Pattern status: `retired` — proven not to work, must suppress
- Regime mismatch: different market structure context invalidates the lesson
- Win rate < 0.65 — pattern has insufficient edge to influence decisions

**When retrieval should note CONFLICT:**
- Retrieved pattern has win_rate between 0.40-0.65 — marginal pattern
- Multiple retrieved patterns disagree (some long, some short)
- Pattern regime partially matches (e.g. volatile vs trending_up)

In corpus gold rows: if a conflicting memory is retrieved, the `hypotheses_v1` must explicitly note the conflict and the confidence spread should reflect the uncertainty.

---

## Corpus Row Memory Rules

**ENTER gold rows (ENTER_LONG or ENTER_SHORT):**
- `retrieved_memory_v1` should include at least one matching ENTER pattern if available
- If memory retrieved: h1 must reference it explicitly
- If no qualifying memory: h1 must note "no validated pattern for this setup — reasoning from indicators only"

**NO_TRADE gold rows:**
- `retrieved_memory_v1` may include cautionary NO_TRADE_CORRECT patterns
- If retrieved: cite as "prior similar setup produced correct stand-down"
- If no memory: that's fine — NO_TRADE from indicators alone is valid

**INSUFFICIENT_DATA gold rows:**
- Only retrieve memory if it would resolve ambiguity — otherwise abstain from citing it
- Do not cite conflicting memory to justify INSUFFICIENT_DATA (circular reasoning)

**RETIRED pattern encountered:**
- Do NOT include in `retrieved_memory_v1`
- DO note in `DATA_or_assumption_gaps_v1`: "Pattern signature {id} has been retired (win_rate below threshold). Reasoning from indicators only."

---

## Contrastive Pair Structure

A contrastive pair teaches the model when memory misleads:

**Pair A (positive):**
- Same bar data
- Memory retrieved: validated ENTER_LONG pattern matches
- Gold output: ENTER_LONG with memory explicitly cited in h1
- `Final_status`: ENTER_LONG

**Pair B (negative — same packet, memory conflicts):**
- Same bar data
- Memory retrieved: RETIRED ENTER_LONG pattern (win_rate collapsed)
- Gold output: NO_TRADE — memory warns against entry
- `Final_status`: NO_TRADE
- h2 must cite: "Retired pattern {id} warns this setup failed historically"

The model learns: memory can support OR contradict a decision. Volume alone can't teach this — only curated contrastive pairs.

---

## Implementation Notes

**Exporter** (`export_to_training_corpus.py`):
- Currently passes `retrieved_memory_v1: []` (no memory in export)
- Next version: populate from the live forward test's `live_memory.jsonl` for the matching bar timestamp
- Tags each row with `memory_class` based on the pattern's current status

**Validator** (`validate_agentic_corpus_v1.py`):
- Should check: if `Final_status=ENTER_LONG` and `retrieved_memory_v1` has RETIRED entries → fail
- Should check: if memory IDs cited in output exist in the allowed retrieved list → fail if invented
- `risk_context_v1.final_risk_pct` must be 0.0 when `Final_status=NO_TRADE` or `INSUFFICIENT_DATA`

**Training engineer:** implement the validator hardening rules above before next corpus merge.

---

*Last updated: 2026-05-04 | Learning Engineer*
