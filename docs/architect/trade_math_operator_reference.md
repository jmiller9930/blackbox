# Trade math — operator reference

How **PnL** and **MAE** are produced in BLACK BOX for **execution ledger** rows, the **dashboard trade chain**, and **baseline vs Anna pairing**. Use this to reconcile hand calculations (e.g. calculator checks) against the database and UI.

## 1. Core PnL formula (economic rows)

**Source of truth:** `modules/anna_training/execution_ledger.py` — `compute_pnl_usd`.

**Index-style USD PnL** from fill prices and size (no fees, no funding in this function):

| Side   | Formula |
|--------|---------|
| **long**  | `(exit_price - entry_price) * size` |
| **short** | `(entry_price - exit_price) * size` |

**Constraints:** `side` must be `long` or `short`. `size` must be **positive** (magnitude of position).

**Stored PnL:** For modes **`live`** and **`paper`**, the ledger **does not** trust a caller-supplied `pnl_usd` alone — it **recomputes** from `entry_price`, `exit_price`, `size`, and `side` and stores that value (hint must match within tolerance or append fails).

**Not economic:** **`paper_stub`** does **not** store asserted dollar `pnl_usd` as economic truth (see section 4).

## 2. Baseline bridge (lane = baseline, strategy_id = baseline)

**Module:** `modules/anna_training/baseline_ledger_bridge.py` — `run_baseline_ledger_bridge_tick`.

**Intent:** One **baseline** row per **latest** canonical **5m bar**, aligned to the same **`market_event_id`** as Anna paths.

**Synthetic fill (measurement harness):**

- **Side:** `long`
- **Size:** `1.0` (one unit of notional in the price domain used — not a live venue contract multiplier unless you configure elsewhere)
- **Entry price:** bar **open**
- **Exit price:** bar **close**
- **PnL:** `(close - open) * 1` = **`compute_pnl_usd(entry=open, exit=close, size=1, side="long")`**

**Context tag:** `economic_basis`: `canonical_bar_open_to_close_long_1unit`.

If Sean’s calculator uses **different** entry/exit (e.g. intrabar, last tick, or fees), numbers will **not** match — the system is explicitly **open→close on the canonical bar**.

## 3. Parallel Anna runner (lane = anna, economic paper mode)

**Module:** `modules/anna_training/parallel_strategy_runner.py`.

When **`ANNA_PARALLEL_STRATEGY_MODE`** is **`paper`** (default), each configured strategy gets an **Anna** row using the **same bar** as the baseline bridge:

- **Side:** `long`
- **Size:** `1.0`
- **Entry / exit:** bar **open** / **close**
- **PnL:** same `compute_pnl_usd` as baseline bridge for that bar

So **per event**, baseline and parallel Anna **paper** harness rows often share the **same** open→close move; **strategy_id** differs, **lane** differs; **headline book** vs **Anna lane** rollup are separated in **paper capital** (see `paper_capital.py`).

## 4. Paper stub (eval / non-economic)

**Mode:** `paper_stub` (UI label: **eval / non-economic**).

**PnL:** Not stored as economic `pnl_usd` in the ledger for stub semantics; synthetic hints may live in `context_snapshot_json` only.

**Dashboard outcome:** Shown as **Eval**, not WIN/LOSS from dollars.

## 5. MAE (Maximum Adverse Excursion) — dashboard & pairing

**Module:** `modules/anna_training/sequential_engine/mae_v1.py` — `compute_mae_usd_v1`.

**Role:** Used in **`dashboard_bundle`** (`_compact_cell`) and in **vs-baseline pairing** (`_pair_vs_baseline_for_cells`). Pairing requires **both** baseline and Anna cells to have **`pnl_usd`** and **`mae_usd`** (or the pair is **EXCLUDED** → **vs baseline: n/a**).

**Rule (v1):** Over **5m bars** in the trade window from **`market_bars_5m`**, adverse USD vs **entry** (long/short formulas in file header). Requires a **valid symbol**, **entry/exit times**, and a **readable market DB** (`BLACKBOX_MARKET_DATA_DB` or default path). If MAE cannot be computed, **`mae_usd`** is missing → pairing may show **n/a** even when PnL is present.

## 6. WIN / LOSS labels (economic)

**Dashboard bundle:** `_outcome_from_pnl` — from **stored** PnL for that row:

- PnL > `1e-9` → **WIN**
- PnL < `-1e-9` → **LOSS**
- Else → **FLAT**

## 7. Baseline vs Anna (per event)

**Module:** `modules/anna_training/dashboard_bundle.py` — `_pair_vs_baseline_for_cells`.

**Not** a separate “comparator” page: each **Anna** cell can show **`vs baseline: WIN / NOT WIN / n/a`** when pairing runs. **n/a** means **EXCLUDED** (e.g. missing PnL or MAE on either leg). The UI may surface **`vs_baseline_excl`** (e.g. `missing_mae`, `missing_pnl`).

## 8. What this math does **not** include

Unless explicitly added elsewhere in a future phase:

- **Trading fees**, **slippage**, **funding**, **contract multipliers** (e.g. perp coin size)
- **Partial fills**, **multiple exits**
- **Live venue** settlement — **paper** is **model / ledger** math, not exchange confirmation

Discrepancies with a **calculator** are often **definition of entry/exit**, **side**, **size**, or **fees** — not necessarily a bug.

## 9. Quick reconciliation checklist

1. **Row identity:** `trade_id`, `market_event_id`, `lane`, `strategy_id`, `mode`.
2. **Fields:** `entry_price`, `exit_price`, `size`, `side` — recompute with `compute_pnl_usd`.
3. **Baseline bridge:** Confirm **open/close** from the **same** bar row as documented.
4. **Stub:** Do not expect dollar PnL to match a **paper** baseline row.
5. **MAE:** Confirm **market DB path** and **symbol** if pairing is **n/a**.

---

**Related code:** `execution_ledger.py` (append + validation), `baseline_ledger_bridge.py`, `parallel_strategy_runner.py`, `dashboard_bundle.py`, `mae_v1.py`, `paper_capital.py` (lane-scoped rollup).
