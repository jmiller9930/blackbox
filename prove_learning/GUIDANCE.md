# prove_learning — Guidance Document

**Read this before every work session. Enforce it.**

---

## Mission

Build an autonomous trading and LLM intelligence system focused on **FinQuant** and **crypto markets**.

**No novel or unknown methods without agreement.** Standard, proven industry practices are required.

The system must demonstrate a **productive learning loop** that:
- Uses memory and context to exercise judgment
- Shows a **positive change in trade outcomes** over time
- Uses **pattern recognition** as the primary learning mechanism (unless research shows a better approach)
- Manages risk: losses can be greater in number so long as they are **financially smaller than wins** (positive expectancy)
- Risk management is preferred over raw win rate

---

## What this folder is

A self-contained lab that proves a learning module can work.

**Prove that an agent can learn from its own decisions and measurably improve.**

---

## Scope — hard boundaries

**Work only in:**
```
prove_learning/finquant/unified/agent_lab/
```

**Never touch:**
- Anything outside `prove_learning/`
- `training/` at the repo root
- Any other agent, folder, or system

If a task requires touching something outside this boundary, stop and ask.

---

## The goal, stated precisely

Run an agent through multiple cycles on real market data.
After each cycle, measure:

1. **Win rate** — did the agent make profitable decisions?
2. **Pattern promotion** — did patterns accumulate enough evidence to promote?
3. **Behavioral change** — did the agent make different decisions in cycle N vs cycle 1?

Learning is proven when:
- Win rate with memory **beats** win rate without memory (baseline)
- At least one pattern promoted past candidate
- At least one decision changed because of retrieved memory

Currently: baseline (no memory) = **62.5% win rate, positive PnL**.

**The correct success metric is decision quality across ALL opportunities, not wins ÷ entries.**

| Decision | Outcome | Score |
|---|---|---|
| ENTER_LONG | Win | Good |
| ENTER_LONG | Loss | Bad |
| NO_TRADE | Market flat (correct abstention) | Good |
| NO_TRADE | Market moved (missed opportunity) | Bad |

A correct NO_TRADE is a good decision. An incorrect entry that loses is a bad decision.
Per prime directive R-002: if top two hypothesis confidences differ by < 0.20, output INSUFFICIENT_DATA — do not force a trade.
Per prime directive P-6: optimize dollars won minus dollars lost over the sample. Many small losses are acceptable if wins carry asymmetric R.
Memory must demonstrate **positive expectancy** — wins financially larger than losses — to prove learning.

---

## What is broken right now (known problems)

1. **Memory fires too early** — one PASS makes a record retrievable. One win is not a lesson.
2. **No quality gate on retrieval** — any retrieved record influences decisions regardless of win rate
3. **Volume proxy is wrong** — tick_count ≠ real volume. Volume conditions are unreliable.
4. **No regime awareness** — bull market lessons applied to bear market conditions
5. **No feedback on bad memory** — losing trades don't degrade the source record

---

## Fix order (work through these in sequence)

1. Gate retrieval on quality — only records with win_rate > 0.55 AND min 5 observations are retrievable
2. Wire Qwen as the actual decision maker — not a stub override
3. Tag cases by market regime — retrieval matches regime before firing
4. Close the falsification loop — bad memory-backed trades decay the source record
5. Separate signal confidence from entry — Qwen outputs confidence, rules gate entry

---

## Best practice standards to hold to

- **Memory quality before quantity** — 1 validated lesson beats 10 unvalidated ones
- **Regime match required** — never apply a trending lesson to a ranging market
- **Falsification is mandatory** — every promoted record must be falsifiable and must decay on bad outcomes
- **LLM reasons, rules protect** — Qwen proposes, deterministic guards veto
- **Prove before claiming** — no "learning demonstrated" unless win rate with memory > baseline

---

## Rules for working

1. **Read this document at the start of every session**
2. State which problem from the fix list is being worked on before writing code
3. **No novel or unknown methods without agreement** — use standard proven practices
4. Run tests after every change — all must pass before committing
5. Run the training loop on real data after every significant change
6. **If tests fail or goal is not met: isolate the fault, recode, retest in a loop**
7. Do not move to the next fix until the current one is proven
8. Never claim PASS unless positive expectancy (wins financially larger than losses) is demonstrated
9. Do not build new features until current broken things are fixed
10. **Risk management takes priority** — losses smaller than wins in dollar terms, not just count

---

## Current test baseline

```
cd prove_learning/finquant/unified/agent_lab
python3 -m pytest tests/ -q
# Must show: 129 passed
```

## Current training baseline (real data)

```
# On trx40 (vanayr@172.20.1.66):
cd /home/vanayr/blackbox
python3 prove_learning/finquant/unified/agent_lab/training_loop.py \
  --cases-dir prove_learning/finquant/unified/agent_lab/cases/market_solperp_15m_v2 \
  --config prove_learning/finquant/unified/agent_lab/configs/stub_lab_config.json \
  --output-dir prove_learning/finquant/unified/agent_lab/outputs \
  --cycles 3
```

Expected: cycle 1 win_rate=62.5% (baseline). Memory must beat this.

---

## Infrastructure available

### Data
- **Primary clawbot host**: `jmiller@clawbot.a51.corp`
- **SQLite market database** — `/home/jmiller/blackbox/data/sqlite/market_data.db`
  - Table: `market_bars_5m` — SOL-PERP, 5m bars from Pyth ingest
  - 7,250+ bars covering April–May 2026 (growing live)
  - Columns: `candle_open_utc`, `open`, `high`, `low`, `close`, `tick_count`, `volume_base`
  - Note: `volume_base` is NULL — `tick_count` is the volume proxy (unreliable, see Problem 3)

- **Extended Pyth / BTC data** — 24+ months available on clawbot
  - Access via same DB or separate tables — confirm schema before use
  - Use the `market_data_bridge.py` to roll up to any timeframe and generate lifecycle cases

- **Live data feed** — Pyth price feed is active and writing to the DB in real time
  - SOL-PERP: live bars being appended continuously
  - BTC: live Pyth data also available
  - Live data makes falsification real — outcomes are actual market results, not simulated

### Two operating modes — both available

| Mode | What it uses | Purpose |
|------|-------------|---------|
| **Backtest** | Historical bars from DB (24+ months) | Validate patterns on known data, measure win rate over past conditions |
| **Live** | Current bars from live Pyth feed | Generate cases from real-time market, falsify against what actually happens next |

This means:
- Train on historical data → establish baseline patterns
- Run live → validate those patterns against current market
- Compare backtest win rate vs live win rate to detect regime shift or overfitting
- Continuously append new live bars → cases never run out, patterns keep accumulating evidence

### Compute / LLM
- **Local LLM host**: `jmiller@172.20.2.230` — Ollama running Qwen 2.5 7B
  - Ollama URL: `http://172.20.2.230:11434`
  - Model: `qwen2.5:7b`
  - Timeout: 30s, max tokens: 400

- **Lab execution host**: `vanayr@172.20.1.66` (trx40)
  - Repo at `/home/vanayr/blackbox`
  - Runs training loops, bridge generation, test suite
  - Access via SSH from local Mac

### Access pattern
- Edit code locally → `git push` → `git pull` on trx40 → run on trx40
- LLM calls from trx40 → Ollama at `172.20.2.230:11434`
- Read-only access to clawbot DB when needed for extended data

---

---

## The Reasoning Module — RMv2

The primary deliverable of this lab. A self-contained, pluggable reasoning module that can be called by any application to get a governed trade decision.

**Package:** `prove_learning/finquant/unified/agent_lab/rmv2/` (`engine.py`, `memory_index.py`, `memory_tiers.py`, `embeddings.py`)  
**Import:** `from rmv2 import ReasoningModule, RMConfig`  
**Version:** RMv2 (learning-loop version)

**Tiered pattern memory:** STM (TTL) plus LTM (promoted after falsification), cosine similarity on embeddings in companion SQLite (`pattern_memory_v1`). Governed rows stay gated; vector neighbors add probabilistic similar-context for the LLM. Set `memory_embedding_backend_v1` to `deterministic` (offline plumbing) or `ollama` (semantic).

### How to build it

Build in layers. Do not skip ahead.

1. Clean entry point — `ReasoningModule.decide(bars, symbol, timeframe) → RMDecision`
2. Quality-gated retrieval wired in — only validated memory influences decisions
3. Qwen as primary reasoning layer — not a stub
4. Regime tagging — retrieval matches regime
5. Memory feedback loop — bad outcomes decay source records

### How to test it

Every layer must have a test before the next layer is built.

```
# Unit tests — run after every code change
cd prove_learning/finquant/unified/agent_lab
python3 -m pytest tests/ -q
# Must show: all prior tests pass + new tests for RMv2

# Integration test — run after every significant change
python3 rmv2/engine.py --self-test
# Must show: decision produced, source logged, memory used logged

# Training loop test — run after wiring RMv2 into the loop
python3 training_loop.py \
  --cases-dir cases/market_solperp_15m_v2 \
  --config configs/default_lab_config.json \
  --cycles 3
# Must show: cycle 1 win_rate >= 62.5% baseline
#            cycle 2 win_rate WITH memory > cycle 1
#            decisions_changed > 0
```

### Iteration rule — non-negotiable

**If a test fails or win rate does not improve, do not move to the next fix.**  
Go back. Diagnose. Correct. Re-run. Repeat until the metric improves.  
Do not claim success on partial results.  
Do not move forward while anything is broken.

Success = win rate with memory beats 62.5% baseline AND all tests pass.  
Until that is true, keep iterating.

---

---

## Grok audit findings (2026-05-03) — logged for use

**Cherry-picking risk flagged by Grok:**
Sean's bot 100% win rate on 10 trades (Apr 22–May 2) was entirely ENTER_SHORT during a pure downtrend. When SOL trends up or ranges, the same signal will have a materially different win rate. This is not general strategy performance — it is regime-specific performance.
Implication for FinQuant: regime detection is essential before the signal is trusted across market conditions. FinQuant must prove performance across MULTIPLE regimes, not just one trending period.

**Grok's alignment conclusion:**
- FinQuant = signal generation + learning layer (adaptive brain)
- Sean's bot = execution layer (reliable but static)
- Signal contract defined: action, planned_stop, planned_target, conviction_spread, regime, thesis, pattern_ids_used
- Connection gate: FinQuant decision quality must hold >65% across ALL cycles (not just cycle 1) before integration

## Known issues for next session

1. **R-002 gate too strict**: latest run with full prime directive in prompts caused 0 entries (Qwen stands down on everything). Need to calibrate — allow entries on clear confluence setups while keeping the gate for ambiguous ones.

2. **Hypothesis columns in ledger**: h1/h2 confidence not yet captured from the 100-case run (fields are new). Will be populated in next run after prompt calibration.

3. **Memory not yet activating**: quality gate (5 obs, 55% win rate) still blocking retrieval. With 100 cases and 40% win rate, nothing clears. Next session: either more warmup cycles or seed from stub run's promoted records.

4. **Partner ledger ready** at `prove_learning/ledger_output/` — use with `OPERATOR_AUDIT_GUIDE.md`.

---

## Open gaps worklog (2026-05-04)

### CLOSED ✓
- RSI divergence signal — feature extraction + prompt visibility
- Quality-gated memory (5+ obs, 65% win rate, regime-matched)
- R-002 conviction spread gate (≥ 0.20 to enter)
- Session filter (Asian session blocked, weekend skip M-F only)
- Circuit breaker (3 consecutive losses → 2hr halt)
- Pattern promotion ladder with retirement
- risk_context.py — context-as-risk-management (R is anchor, context is throttle)
- risk_context wired into RMv2 decide() output (risk_pct + factor breakdown logged)
- exit_price and realized_r in live falsification

### OPEN — next iteration ⚠️
- **Risk context calibration** — factors directionally correct, not yet calibrated. Need 50+ live falsified outcomes. Due: end of first live week (May 9).
- **Regime-adaptive R target** — flat 2.5R regardless of regime. Ranging=tighter, trending=wider. Build after calibration data.
- **Swing detection** — HH_HL/LH_LL structure from 20 context bars → add to pattern signature and prompt. High value.
- **Signal contract schema** — formal JSON schema for FinQuant → execution payload. Before wiring to execution.
- **Realized R feedback into memory** — realized_r logged but not yet used to update pattern quality scores.
- **Dedicated LLM integration** — QLoRA on trx40 must pass baseline harness. Training engineer owns.
- **Corpus merge** — 286 gold rows ready in prove_learning/. Operator task.

### LIVE FORWARD TEST STATUS (as of 2026-05-04)
- Session: `finquant_live` on clawbot.a51.corp
- Weekend: skipping correctly
- Resumes: Monday 2026-05-05 13:00 UTC (8:00 AM ET)
- First outcomes: Monday 14:45 UTC
- First weekly report: Friday 2026-05-08 20:00 UTC
- Risk context: logging with every decision ✓
- Exit price / realized R: tracked ✓

**Last updated:** 2026-05-04  
**Status:** Live forward test running in tmux. Weekend skip active. Resumes Monday 13:00 UTC. All pre-test gaps closed.**
