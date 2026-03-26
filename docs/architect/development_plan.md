# BLACK BOX — Development Plan (Phase 5+)

**Canonical master roadmap:** [`docs/blackbox_master_plan.md`](../blackbox_master_plan.md) — this file lists **actionable tasks** for **Phase 5** and marks **Phase 6 / 7** as out of scope for the current sprint.

**Status synchronization:** Updates that change phase scope or completion must update **`docs/blackbox_master_plan.md`** and **`docs/architect/directives/directive_execution_log.md`** in the same change set (`Plan/log status sync: PASS`).

---

## Phase 5 — Core trading engine (next active build)

**Goal:** One path (**Anna + Billy**) from **live data** → **signal** → **Layer 3 approval** → **Layer 4 intent** → **venue execution** (paper/sandbox first), with risk and observability.

### 5.1 Market data ingestion — tasks

- [ ] Select and integrate **primary** feed (e.g. Pyth) for initial symbol set (e.g. SOL).
- [ ] Implement **fallback** (e.g. Coinbase REST) when primary fails freshness/health.
- [ ] Define **canonical snapshot schema**; implement **normalization** pipeline.
- [ ] Add **health checks** and **gap detection**; alert or fail closed per policy.

### 5.2 Market data store — tasks

- [ ] Provision **production** (non-sandbox) store for time-series / snapshots.
- [ ] Expose **query** API or batch readers for strategy and backtest.

### 5.3 Strategy engine — tasks

- [ ] Implement **deterministic** strategy v1 (single symbol / small universe).
- [ ] Emit **signals** with **confidence** and structured fields (align to master plan signal contract).
- [ ] Wire **backtest / simulation** loop reading **stored** data only.

### 5.4 Signal → approval binding — tasks

- [ ] Create **candidate trade artifact** from signal (size, risk, expiry).
- [ ] Route to **Layer 3** approval flow; **no** execution without **APPROVED** artifact.

### 5.5 Execution adapter — tasks

- [ ] Implement **single venue** adapter (e.g. Coinbase); **paper/sandbox** first, then **small-size live** behind gates.
- [ ] Consume **Layer 4 execution intent** per [`layer_4_execution_interface_design.md`](layer_4_execution_interface_design.md) (section 13 mitigations).
- [ ] Integrate **Billy** for **edge execution** (execution only; no signal invention).

### 5.6 Risk & controls — tasks

- [ ] Enforce **per-trade** and **per-account** limits.
- [ ] Enforce **approval expiry** (aligned with Layer 3/4).
- [ ] Wire **global kill switch** and Layer 4 kill contract.
- [ ] **Position / PnL** tracking (minimum viable).

### 5.7 Observability & operations — tasks

- [ ] **Metrics:** feed health, signals, approvals, executions.
- [ ] **Logs** and **failure** taxonomy; runbook links.
- [ ] **Runbooks:** halt, rollback, revoke paths.

### First slice (approved paper loop) — checklist

Aligned with **Phase 5 — First approved slice** in [`blackbox_master_plan.md`](../blackbox_master_plan.md).

- [ ] Pyth ingestion (**SOL**).
- [ ] Normalized snapshot store.
- [ ] Deterministic strategy → SOL signal contract.
- [ ] L3 approval binding.
- [ ] Execution intent contract post-approval.
- [ ] Billy poll + Coinbase **sandbox** adapter.
- [ ] Outcome ingestion + durable storage.

**Stop condition:** “One approved signal → one paper trade → verified outcome → stored” before scope expansion.

---

## Phase 6 — Intelligence & self-improvement

> **NOT IN SCOPE for current sprint. FUTURE / STUB ONLY.**

No scheduled tasks. See [Phase 6 — Intelligence & Self-Improvement (Future)](../blackbox_master_plan.md#phase-6--intelligence--self-improvement-future) in the master plan.

---

## Phase 7 — Bot hub / ecosystem

> **NOT IN SCOPE for current sprint. FUTURE / STUB ONLY.**

No scheduled tasks. See [Phase 7 — Bot Hub / Ecosystem (Future)](../blackbox_master_plan.md#phase-7--bot-hub--ecosystem-future) in the master plan.

---

## Document control

- **Path:** `docs/architect/development_plan.md`
- **Purpose:** Actionable development tasks; **not** a substitute for the master plan’s full architecture narrative.
