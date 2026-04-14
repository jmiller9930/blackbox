# Jupiter V3 (Sean) — Blackbox vs Sean tooling: one sheet of music

**Purpose:** Remove ambiguity when someone asks whether “SeanV3” and “Blackbox JUPv3” use the **same policy**. They should — with two separate questions: **(1) same math** and **(2) same bars**.

---

## 1. Canonical policy (Blackbox runtime)

**Authoritative implementation:** `modules/anna_training/jupiter_3_sean_policy.py`

- Entry evaluation for production baseline / ledger / dashboard flows goes through **`evaluate_jupiter_3_sean`** (via `sean_jupiter_baseline_signal.evaluate_sean_jupiter_baseline_v3`, etc.).
- **Catalog id:** `jupiter_3_sean_perps_v1`
- **Gates, constants, BOS window, volume-spike definition** are defined here. This is the **sheet of music** for what Blackbox **means** by Jupiter V3.

---

## 2. Sean reference port (Node / VS Code)

**Reference implementation:** `vscode-test/seanv3/jupiter_3_sean_policy.mjs`

- Header states intent: **match Python numerics for OHLCV inputs** (`generateSignalFromOhlcV3` ↔ Python `generate_signal_from_ohlc_v3`).
- **Not** a second “truth” for Blackbox production — it is for **Sean-side tooling**, parity checks, and local experimentation without the Python stack.
- **Must stay in lockstep** with Python: same constants (`RSI_*`, `VOLUME_SPIKE_MULTIPLIER`, `MIN_EXPECTED_MOVE`, `BOS_LOOKBACK_CANDLES`, `MIN_BARS`, etc.). If one file changes, the other must be updated in the same change set (or parity is explicitly broken and documented).

---

## 3. Two kinds of “alignment”

### A. Policy math alignment (formula + constants)

**Aligned when:** For the **same** ordered series of closed bars (same OHLCV arrays, same length, same floating-point inputs), Python **`evaluate_jupiter_3_sean`** and Node **`generateSignalFromOhlcV3`** yield the **same** long/short gate outcomes (within defined float tolerance if any cross-lang tests exist).

**Proof:** Unit tests in `tests/test_jupiter_3_sean_policy.py`; optional cross-lang harness (same vectors → compare booleans).

### B. Bar data alignment (what gets fed into the policy)

**Not the same thing as (A).** Identical formulas with **different** per-bucket OHLCV still produce **different** signals.

| Path | Typical bar source | Role |
|------|---------------------|------|
| **Blackbox production** | `binance_strategy_bars_5m` in `market_data.db` (Binance REST sync) | **Truth for dashboard / policy_evaluations / baseline** |
| **Sean parity / lab capture** | `sean_binance_kline_poll` (e.g. klines mini / Sean app SQLite) | **Compare** to Blackbox for the **same** `market_event_id` — see `modules/anna_training/jup_v3_parity_compare.py` |

**Aligned when:** For each compared bucket, OHLCV used by Blackbox **matches** OHLCV used by Sean tooling (within agreed epsilon). If they differ (timing, kline source, rounding, missing volume), **policy can disagree even when code is identical**.

---

## 4. Lifecycle / exits (Blackbox only)

**Paper baseline entry/exit / ledger** are implemented in **Python** (`baseline_ledger_bridge`, `jupiter_3_baseline_lifecycle`, etc.). A **Node-only** lifecycle is **not** Blackbox truth unless explicitly bridged and governed.

So: **entry rules** = Jupiter V3 policy above; **exit mechanics** = follow Blackbox Python paths for anything that must match operator dashboard and `execution_trades`.

---

## 5. What to tell the architect (closure criteria)

| Question | Answer |
|----------|--------|
| Same policy definition? | **Yes** — Python module is canonical; Node is a **port** for Sean tooling, must match constants + math. |
| Automatically same signals in prod vs Sean demo? | **Only if** same **closed-bar series** and same **inputs** — validate with parity compare + tests. |
| “Not fully aligned until proven” | Correct: **prove (A)** with tests/harness and **prove (B)** with OHLCV comparison on shared `market_event_id`s. |

---

## 6. If SeanV3 “triggers a trade” — what Blackbox should do

**Important:** Blackbox does **not** subscribe to Sean’s Node process. It runs **`evaluate_jupiter_3_sean`** / **`evaluate_sean_jupiter_baseline_v3`** on its own bar pipeline when the **baseline ledger bridge** (and related jobs) runs. **Expectation is about parity of *outcome* for the *same bar inputs*, not a push integration.**

When **policy math** says entry (long or short signal after gates, including **short-over-long** if both fire — see `jupiter_3_sean_policy.py`):

| Layer | Expected Blackbox behavior |
|-------|----------------------------|
| **Policy result** | `Jupiter3SeanPolicyResult.trade == True`, `side` in `long` / `short`, `reason_code` `jupiter_3_long_signal` or `jupiter_3_short_signal` (from Python evaluator). |
| **Policy evaluations** | For that `market_event_id`, with `signal_mode=sean_jupiter_v3`, a row with **`trade=true`** and features JSON containing the same diagnostics/gates snapshot (when `BASELINE_POLICY_EVALUATION_LOG` is on). |
| **Paper baseline lifecycle** | Bridge may **open** a tracked paper position (subject to existing open position, bridge tick ordering, and lifecycle rules — not a live venue order). |
| **Dashboard / tile** | Shows the JUPv3 narrative and gates consistent with that evaluation for the **same** closed bar. |

**If Sean Node shows “trade” but Blackbox shows “no trade”** for the **same** candle: treat as a **bug or data mismatch** — compare OHLCV for that `market_event_id` (`jup_v3_parity_compare`) and confirm **Jupiter V3** is the active baseline slot (not V2).

**If bars differ** (Sean DB vs `binance_strategy_bars_5m`): different outcomes are **expected** until inputs match; fix data alignment, not “policy name.”

---

## 7. Related files

- Policy: `modules/anna_training/jupiter_3_sean_policy.py`
- Sean Node port: `vscode-test/seanv3/jupiter_3_sean_policy.mjs`
- Baseline bridge: `modules/anna_training/baseline_ledger_bridge.py`
- Parity CLI: `python3 -m modules.anna_training.jup_v3_parity_compare <sean_sqlite.db>`
- Operator-facing gate list: constants + `jupiter_v3_gates` in policy diagnostics; dashboard renders `jupiter_v3_gates_v1`.
