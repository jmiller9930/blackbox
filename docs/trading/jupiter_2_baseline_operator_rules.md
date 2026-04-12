# Jupiter_2 baseline — operator rules (canonical)

**Engine:** `modules/anna_training/jupiter_2_sean_policy.py` (`evaluate_jupiter_2_sean`, `generate_signal_from_ohlc`).  
**Tile / narrative:** `modules/anna_training/sean_jupiter_baseline_signal.py` (`format_jupiter_tile_narrative_v1`, `_build_operator_tile_jupiter2`).  
**Catalog id:** `jupiter_2_sean_perps_v1`.

This document is the **non-negotiable contract** for how baseline “Signal Breakdown” and entry filters relate. UI mockups and dashboard copy should not contradict it.

---

## 1. Primary: Signal Breakdown (core long / core short)

Core signals are **AND** conditions on the **closed** bar (same definitions as `generate_signal_from_ohlc`).

### Long (core)

**Long=true** iff all of:

| Predicate (tile labels) | Meaning |
|-------------------------|---------|
| Supertrend | **Bullish** Supertrend (long side needs uptrend regime) |
| AboveEMA | Close **>** EMA200 |
| RSI>52 | RSI(14) **>** 52 |
| HigherClose | Current close **>** previous close |

Constants: `RSI_LONG_THRESHOLD = 52.0` in `jupiter_2_sean_policy.py`.

### Short (core)

**Short=true** iff all of:

| Predicate (tile labels) | Meaning |
|-------------------------|---------|
| Supertrend | **Bearish** Supertrend (not bullish) |
| BelowEMA | Close **<** EMA200 |
| RSI<48 | RSI(14) **<** 48 |
| LowerClose | Current close **<** previous close |

Constants: `RSI_SHORT_THRESHOLD = 48.0`.

### Consistency rule (operator expectation)

The narrative lines:

- `Signal Breakdown → Long=<bool> (Supertrend=…, AboveEMA=…, RSI>52=…, HigherClose=…)`
- `Signal Breakdown → Short=<bool> (Supertrend=…, BelowEMA=…, RSI<48=…, LowerClose=…)`

must use **`long_ok` / `short_ok` that match the core** from policy: **`long_ok` == AND of the four long predicates**, **`short_ok` == AND of the four short predicates**. If the four inner flags are all true for a side, the aggregate for that side must be **true**, not false (otherwise the tile contradicts the engine).

Implementation: `long_ok` / `short_ok` are driven by `long_signal_core` / `short_signal_core` in the policy features (`_build_operator_tile_jupiter2`).

---

## 2. Secondary: entry filters (only when core would allow a side)

After core long/short are computed, **entry** can still be blocked. **Implementation order** in `generate_signal_from_ohlc` is:

1. **ATR ratio gate** — if `atr_ratio < 1.35` (`ATR_RATIO_MIN`), **no entry**; core outputs are forced to **no trade** for that evaluation path (see code: early return with block `atr_ratio_below_1_35`).
2. **Extreme RSI gate** — if core **long** is true but **RSI > 75**, skip; if core **short** is true but **RSI < 25**, skip (block `rsi_extreme`).

**Operator mental model:** “First decide if the **primary** long/short setup fires; **then** apply **volatility (ATR)** and **extreme RSI** skips.” The **code** evaluates **ATR before** extreme RSI; if ATR fails, you do not reach the RSI-extreme branch for that bar.

### Summary table

| Condition | Effect |
|-----------|--------|
| Core **Long=true** | Required for a long entry before filters |
| Core **Short=true** | Required for a short entry before filters |
| `ATR ratio < 1.35` | Skip entry (either side) |
| Long=true and **RSI > 75** | Skip entry (extreme RSI) |
| Short=true and **RSI < 25** | Skip entry (extreme RSI) |

Tile filter strings (examples): `Filter: ATR ratio below 1.35 – skipping entry`; `Filter: extreme RSI (long blocked if RSI>75, short if RSI<25) – skipping entry` (`format_jupiter_tile_narrative_v1`).

---

## 3. Learning dataset (Phase 1) — baseline lifecycle only

**Package:** `modules/anna_training/learning_layer/` (schema, labels, dataset builder, walk-forward report).  
**Schema version:** `learning_dataset_baseline_v1` (see `learning_layer/schema.py` and `schema_dict()`).

**Data lineage (authoritative, no parallel policy):**

| Source | Role |
|--------|------|
| `execution_trades` | Baseline lane, `exit_reason` in `STOP_LOSS` / `TAKE_PROFIT`, economic modes; prices, size, `pnl_usd` |
| `context_snapshot_json` | `entry_market_event_id` for entry bar join |
| `policy_evaluations` | Policy features at **entry** `market_event_id` (`signal_mode` e.g. `sean_jupiter_v1`) |
| `market_bars_5m` | OHLC at entry and exit mids; `volume_base` only if present (nullable) |

**Canonical label definitions** (must match code in `learning_layer/label_specs.py`):

| Label | Definition |
|-------|------------|
| `trade_success` | `exit_reason == TAKE_PROFIT` |
| `stopped_early` | `exit_reason == STOP_LOSS` |
| `beats_baseline` | Phase 1: `pnl_usd > 0` (vs **flat**; not a second baseline series). Future schema may add paired-strategy deltas. |
| `whipsaw_flag` | `stopped_early` **and** within the next `WHIPSAW_LOOKAHEAD_BARS` closed 5m bars after the exit bar: **long** — `max(high) >= entry_price`; **short** — `min(low) <= entry_price`. |

**Walk-forward (Phase 1):** time-ordered row index splits in `walk_forward_report.py` — no random shuffles; report exposes counts, label balance, `row_quality`, and Phase 2 blockers.

**Scope:** Phase 1 does **not** train models, run shadow scorers, or change baseline execution.

---

## 4. Related docs

- [`docs/architect/ANNA_GOES_TO_SCHOOL.md`](../architect/ANNA_GOES_TO_SCHOOL.md) — baseline vs Anna context  
- [`docs/architect/learning_primary_metric_change_process.md`](../architect/learning_primary_metric_change_process.md) — learning governance / metrics (broader than this baseline dataset)  
- [`basetrade/README.md`](../../basetrade/README.md) — parity harness for `evaluate_sean_jupiter_baseline_v1`  
- [`UIUX.Web/mockups/jupiter_tile_rule_colors_mockup.html`](../../UIUX.Web/mockups/jupiter_tile_rule_colors_mockup.html) — **UI intent only** (colors / readability); does not change policy math
