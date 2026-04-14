# RenaissanceV4 — Fusion correction v1 (DV-ARCH-CORRECTION-009)

**Date:** 2026-04-14 (UTC)  
**Scope:** `renaissance_v4/core/fusion_engine.py` only — no changes to signals, risk governor, execution, or Phase 8+.

---

## 1. What changed (fusion only)

| Item | Before | After |
|------|--------|--------|
| **Directional contribution** | Product `conf × edge × regime_fit × stability × weight` | **Geometric mean** of the four quality factors (with ε floors), then × signal weight |
| **`MIN_FUSION_SCORE`** | `0.55` | **`0.35`** |
| **Overlap penalty** | Unchanged (`MAX_OVERLAP_BUCKET_COUNT=2`, `0.08` per extra) | **Unchanged** — see §5 |

**Files touched:** `renaissance_v4/core/fusion_engine.py`; `renaissance_v4/research/fusion_contribution_audit.py` (audit imports `_directional_contribution` for consistency).

---

## 2. Measured evidence (pre-change)

Instrumented on **full clawbot history** (`210240` rows, `210191` decision steps) via `fusion_contribution_audit.py`:

### 2.1 Legacy (product) winning-side score (bars with gross > 0, `n=26416`)

| Stat | Value |
|------|--------|
| mean | 0.0136 |
| p90 | 0.0242 |
| p99 | 0.0520 |
| **max** | **0.1146** |

**Conclusion:** No bar could reach **`MIN_FUSION_SCORE = 0.55`** — the threshold was **inconsistent with the scale** of the legacy product.

### 2.2 Proposed GM (same data, same signals) winning-side score

| Stat | Value |
|------|--------|
| p50 | 0.292 |
| p90 | 0.351 |
| p95 | 0.373 |
| max | 0.569 |

**Conclusion:** GM maps active-signal evidence into a **usable band**; **`0.35`** is set near the **upper decile (p90 ≈ 0.351)** of winning-side GM scores so that passing the threshold requires **stronger-than-typical** fused evidence, not noise.

### 2.3 Gross-score “starvation” (why gross = 0)

| Category | Bars | % of steps |
|----------|------|------------|
| No active signal | 183775 | 87.43% |

There were **no** bars where active long/short produced **legacy product exactly zero** with contradictory activations — starvation was dominated by **no qualifying activation**, not by a fusion bug.

### 2.4 Overlap choke

**`overlap_bars_gt2_same_bucket`: 0** — overlap penalty was **not** the limiting factor; **no** overlap parameter change was applied.

---

## 3. Why we did not “tweak until trades appeared”

1. **Product collapse** was demonstrated numerically (max winning contribution **0.11** vs threshold **0.55**).  
2. **GM scale** was measured; **0.35** is anchored to **P90 ≈ 0.35** on winning-side GM, not to replay PnL.  
3. **Overlap** proven non-choke at **0** high-count events.

---

## 4. Before vs after — fusion & risk (full dataset, diagnostic pass)

Counts from `diagnostic_pipeline` output (clawbot, same DB). **Before** = pre-fusion commit (from archived `diagnostic_v1.md`, DV-008). **After** = post-fusion replay of diagnostics.

| Metric | Before | After |
|--------|--------|--------|
| Fusion **`long`** | 0 | **1287** |
| Fusion **`short`** | 0 | **1410** |
| Fusion **`no_trade`** | 210191 | 207494 |
| Risk **`allowed`** (any bar) | 0 | **1** |
| Hypothetical entries (flat, fusion directional ∧ risk allowed) | 0 | **1** |

**Note:** Risk governor was **not** modified; **`allowed=1`** on the full series is expected to be **sparse** under current regime/volatility/persistence rules. Fusion now delivers **directional inputs**; risk remains the separate gate.

---

## 5. Validation replay (clawbot, full history)

Command: `python3 -m renaissance_v4.research.replay_runner`  
Runtime ~6.5 minutes (log: `/tmp/rv4_replay_corr.log` on clawbot).

| Metric | Value |
|--------|--------|
| **Total closed trades** | **1** |
| Win rate | 0.0 |
| Expectancy | -0.20034 (same as average PnL, 1 trade) |
| Max drawdown (equity curve) | 0.20034 |
| **Validation checksum** | `8bdd9e068d325874d4bdb14bcb7c795347b9011df2c4f182d190f2a01c3cb4ac` |

Scorecards populated (e.g. `trend_continuation`, `pullback_continuation` with non-zero trade counts).

**Functional acceptance (DV-009):** **non-zero** fusion directionals, risk receives directional fusion inputs, execution opens and closes **at least one** trade.

---

## 6. Next steps (out of scope for this pass)

- **Risk layer:** Most fusion directionals are still **blocked**; further work may target **risk** or **signal/regime mix** per architecture — **not** done here.  
- **Profitability:** Not required for this correction.  
- Re-run **`run_proof_bundle.sh`** when a full **determinism + baseline** proof package is needed for promotion.

---

## 7. Reproduce

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 -m renaissance_v4.research.fusion_contribution_audit   # contribution stats
python3 -m renaissance_v4.research.diagnostic_pipeline         # stage counts
python3 -m renaissance_v4.research.replay_runner               # trades + baseline_v1.md
```
