# JUPv3 — Jupiter V3 (Sean) policy

**Purpose:** Single place for **what governs** Jupiter V3 Sean behavior, how BlackBox and SeanV3 relate, and where the code lives. Read this before arguing about “the same policy” or which file is “truth.”

**Control model:** Trading behavior is **not** free‑form. The runtime **points at a named policy implementation** (Python canonical + Node mirror below); that policy **defines what constitutes an entry signal** and the **gates** for long/short. Engines, bridges, and ledgers **apply** that policy to bar data and then run lifecycle/ledger rules. **Change trading intent by changing the policy module (and its mirror),** not by scattering one‑off logic elsewhere.

---

## 1. Policy (authoritative)

| Role | Path |
|------|------|
| **Canonical implementation (BlackBox)** | `modules/anna_training/jupiter_3_sean_policy.py` |
| **Required mirror (SeanV3 Node)** | `vscode-test/seanv3/jupiter_3_sean_policy.mjs` |

- **Catalog id:** `jupiter_3_sean_perps_v1`
- BlackBox baseline / ledger / dashboard entry evaluation uses **`evaluate_jupiter_3_sean`** (via `sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v3`, etc.).
- The Node file is **not** a second truth for production: it **must** stay in lockstep with Python (constants, BOS window, volume spike, RSI thresholds, short-over-long tie-break). Change both in the same change set, or document intentional parity break.

**Gates and constants** (EMA9/21, RSI(14), ATR(14), volume spike vs average, BOS over 5 candles, `MIN_EXPECTED_MOVE`, etc.) are defined in these modules.

---

## 2. Where policy turns into trades

### SeanV3 (paper, lab)

| Layer | File |
|-------|------|
| Process entry (Binance 5m poll) | `vscode-test/seanv3/app.mjs` |
| Engine: signal + paper open/close | `vscode-test/seanv3/sean_engine.mjs` |
| SL/TP, breakeven, trail, bar exits | `vscode-test/seanv3/sean_lifecycle.mjs` |
| SQLite ledger | `vscode-test/seanv3/sean_ledger.mjs` |

Docker runs **`node --experimental-sqlite app.mjs`** — not `vscode-test/superjup.ts` (that file is a separate Jupiter Perps stub and does **not** drive SeanV3).

### BlackBox (baseline / operator surfaces)

| Layer | File |
|-------|------|
| Policy evaluation | `jupiter_3_sean_policy.py` (above) |
| Paper baseline lifecycle / ledger bridge | `modules/anna_training/baseline_ledger_bridge.py`, `jupiter_3_baseline_lifecycle` (Python) |
| Execution ledger | `modules/anna_training/execution_ledger.py` |

Node lifecycle in SeanV3 is **Sean-side** empirical truth for parity; BlackBox dashboard and `execution_trades` follow **Python** paths unless explicitly bridged.

---

## 3. Two kinds of alignment

**A. Policy math** — Same ordered closed-bar OHLCV → Python `evaluate_jupiter_3_sean` and Node `generateSignalFromOhlcV3` should agree on long/short gates (tests: `tests/test_jupiter_3_sean_policy.py`).

**B. Bar data** — Same formulas with **different** per-bucket OHLCV → different signals. Compare using the **same** `market_event_id` and aligned feeds (`binance_strategy_bars_5m` vs `sean_binance_kline_poll`). Parity helper: `python3 -m modules.anna_training.jup_v3_parity_compare <sean_sqlite.db>`.

---

## 4. If SeanV3 fires a trade — BlackBox expectation

BlackBox does **not** subscribe to the Node process. It evaluates policy on its **own** bar pipeline when the baseline bridge runs. Expectation is **same outcome for the same bar inputs**, not a push integration.

When policy says entry (including **short over long** if both fire):

| Layer | Expected BlackBox behavior |
|-------|----------------------------|
| Policy result | Trade true, side long/short per Python evaluator |
| Policy evaluations | Row for that `market_event_id`, `signal_mode=sean_jupiter_v3`, when logging is on |
| Paper baseline | Bridge may open/update per existing lifecycle rules |
| Dashboard | JUPv3 narrative consistent with that bar |

**Sean trade but no BlackBox trade** on the same candle → treat as bug or **data** mismatch; confirm OHLCV and active baseline slot (JUPv3 vs V2).

---

## 5. Switching policies (BlackBox baseline) — hardened selector

You **can** switch which baseline Jupiter policy the BlackBox runtime uses (**`jup_v2`** vs **`jup_v3`**) without rewriting unrelated code. That is the point of a **selector** separate from the policy modules.

**Mechanism (single source of truth):**

| Source | Precedence |
|--------|------------|
| Persisted operator value | `baseline_operator_kv` key `baseline_jupiter_policy_slot` (e.g. dashboard **POST** `/api/v1/dashboard/baseline-jupiter-policy`) |
| Else | Environment **`BASELINE_JUPITER_POLICY_SLOT`** |
| Else | Default **`jup_v2`** |

**Hardening (fail closed):**

- Allowed slots are **`VALID_BASELINE_JUPITER_POLICY_SLOTS`** in `modules/anna_training/execution_ledger.py` (currently `jup_v2`, `jup_v3`). Aliases like `v3`, `jupiter_3` normalize to those constants.
- **Unknown** strings do **not** silently select a policy: **`get_baseline_jupiter_policy_slot`** ignores invalid KV/env (stderr warning) and falls back; **`set_baseline_jupiter_policy_slot`** and **`signal_mode_for_baseline_policy_slot`** raise **`ValueError`**.
- Adding a **future** slot (e.g. `jup_v4`) requires an explicit code change: new constant, extend the valid set, bridge/dashboard branches, and evaluator wiring — not a free-form string. **Standard package layout** for new policies (Sean → engineering): [`policy_package_standard.md`](policy_package_standard.md).

**SeanV3 container** does not read this KV; it runs the Node policy in `vscode-test/seanv3/`. Parity is “same policy math + same bars,” not automatic cross-process coupling.

---

## 6. Related files (quick index)

- Policy: `modules/anna_training/jupiter_3_sean_policy.py`
- Sean mirror: `vscode-test/seanv3/jupiter_3_sean_policy.mjs`
- Baseline bridge: `modules/anna_training/baseline_ledger_bridge.py`
- Parity CLI: `python3 -m modules.anna_training.jup_v3_parity_compare`

**Superseded pointer:** Older one-pager lived at `docs/trading/jupiter_3_blackbox_sean_alignment.md` (now redirects here).

- Selector + validation: `modules/anna_training/execution_ledger.py` (`normalize_baseline_jupiter_policy_slot`, `VALID_BASELINE_JUPITER_POLICY_SLOTS`)
