# Quant research agent — design & strategy (implementation-ready)

**Purpose:** Single place for *why* this stack exists: **pattern → policy → replay validation**, not “make money in one run.” Aligns with `GAME_SPEC_INDICATOR_PATTERN_V1.md` (Referee = truth; LLM = reasoning only).

**Status:** Normative design. **Not all layers are implemented** — see **§15 Repo alignment** at the end.

---

## 1. Core objective

Build a **quant research system**, not a trading bot and not a generic AI.

The system’s purpose is to discover **repeatable pattern → policy** relationships using:

- an indicator library  
- forward-only market replay  
- structured experimentation  
- LLM-assisted reasoning (proposal / interpretation — **never** scoring)

---

## 2. What we optimize for

### NOT the headline goal

- raw PnL as the only scoreboard  
- win rate alone  
- “did this strategy make money once?”

### The headline goal

**How many valid, repeatable pattern–policy matches were discovered and held up under replay?**

Where:

- a **pattern** exists in market structure (dynamics, not one number)  
- a **policy** recognizes and acts on it  
- the **outcome** confirms it **repeatedly** under the same Referee rules  

---

## 3. Architecture (target)

### 3.1 Deterministic layer (truth engine) — *exists*

- Replay engine (e.g. 12 months intent, 5m candles — bounded by SQLite)  
- Referee: PnL, trades, drawdown, **binary WIN/LOSS** per rules  
- Policy execution from validated manifests  

**This layer defines truth. LLM never overrides it.**

### 3.2 LLM layer (reasoning engine)

**Use for:** candidate policy generation, mutation planning, pattern interpretation, research direction — **structured outputs**.

**Do not use for:** scoring, inventing trade outcomes, replacing replay.

### 3.3 Memory layer (target)

| Store | Role |
|-------|------|
| **Experiment ledger** | policy, generation intent, mutations, results, disposition |
| **Pattern memory** | pattern signatures, winning / losing policy families, recurrence stats |

*Implementation today:* partial — e.g. optional `experience_log.jsonl` per scenario result; not a full ledger DB in this folder.

---

## 4. Structured vs unstructured

Without structure: no durable learning, no reuse, no pattern discovery.  
With structure: memory is queryable, LLM stays bounded, results compound.

---

## 5. Two design rules

### Rule 1 — Every policy explains itself at birth

Generated or hand-authored policies should carry:

- mutation summary (if any)  
- search intent  
- pattern hypothesis  
- expected behavior  

*Hook today:* `agent_explanation` and related scenario echo fields in batch JSON (`scenario_contract` / README).

### Rule 2 — Indicators require context (critical)

> Never log the number without logging what the number is **doing**.

**Bad:** `RSI = 55`  
**Good:** RSI rising 42 → 55; crossing 50 up; flattening in chop.

Same value → different meaning by **state, direction, transition, regime**.

---

## 6. Market context layer (“tide”)

**Core idea:** indicators are **state machines over time**, not scalars.

Example:

| Indicator | Context | Meaning |
|-----------|---------|---------|
| RSI = 55 | rising | bullish momentum |
| RSI = 55 | falling | weakening |
| RSI = 55 | flat | chop |

### Feature categories (per decision bar)

1. **State (static)** — level, band, cross-asset level facts  
2. **Direction (dynamic)** — rising / falling / expanding / contracting / slope  
3. **Transition** — threshold cross, compression → expansion, failed breakout  
4. **Structure** — range, breakout, pullback, continuation, reversal attempt  

*Implementation today:* **not** fully emitted as a standard structured trace from replay; belongs in the feature / signal / logging path as the research kitchen matures.

---

## 7. Search space

With ~20 indicators, raw combinations explode. **Brute force is impossible.**

**Bounded search:** 2–3 indicators, 2–4 rules, 1–3 mutations from parent — enforce in experiment design and manifests.

---

## 8. Iteration strategy (sketch)

| Stage | Role |
|-------|------|
| Discovery | 100–300 candidates — find indicator families |
| Refinement | 200–1,000 — stress-test survivors |
| Specialization | pattern-driven search; bias toward validated winners |

Flyable counts are a **planning** tool; wall-clock depends on precompute + parallelism (below).

---

## 9. Compute model

- Dataset scale: ~100k+ 5m bars for a long window.  
- Per candidate: full forward pass over bars unless indicators are **precomputed once** per series.  

**Critical:** precompute indicator series once per run / dataset; avoid recomputing per candidate in tight Python loops.

**Philosophy:** use compute for **scale**, not waste — parallelize, prune losers early, reinvest in promising families.

---

## 10. LLM strategy

**Do:** generation + reasoning with **schemas**, manifests, checklists.  
**Don’t:** free-form truth, unconstrained policy blobs, “the model said it’s green.”

---

## 11. Plan A vs Plan B

**Plan A (this repo’s path):** strengthen **now** — truth layer + structured runs + logging + optional Anna narrative from facts.

**Plan B (LLM-centric greenfield):** only after the loop produces **data** you trust.

**Correct move:** keep Plan A, **inject** LLM as accelerator and scribe, not judge.

---

## 12. Identity statement

This is **not** a trading bot, not a prediction oracle, not generic chat AI.

It **is** a **structured market research system** aimed at discovering which **indicator dynamics** reliably correspond to **recognizable, replay-validated** patterns — then iterating policies that exploit those structures under governance.

---

## 13. One-line truths

- Structure creates intelligence.  
- Context gives meaning to indicators.  
- Iteration creates learning.  
- The LLM proposes — the **system proves** (Referee).  
- Patterns are **relationships over time**, not static values.

---

## 14. Why value-only patterns are brittle (RSI example)

**Raw value alone is weak:** `RSI = 55` tells you almost nothing.

**Same number, three different meanings** (abbreviated):

| Scenario | Idea |
|----------|------|
| **A — Momentum building** | RSI *rising* into 55, crossed up through 50, ATR *expanding*, price above long EMA, breakout structure, volume up → continuation energy. |
| **B — Momentum fading** | RSI *falling* to 55 from overbought, ATR *contracting*, price below EMA, failed breakout → trap / reversal risk. |
| **C — Chop** | RSI *flat*, no crosses, low ATR, range structure, neutral volume → **no signal**; the 55 is noise. |

**Core insight:** identical `RSI = 55`; **interpretation** depends on **direction, transition, volatility regime, trend alignment, structure, flow**.

**What the system must eventually store (per bar or per decision), not just the scalar:**

- Value, **direction** (rising / falling / flat), **delta** from prior  
- **Position** vs key levels (e.g. vs 50, bands)  
- **Recent transitions** (crosses, acceleration, deceleration)  
- **Volatility state** (expanding / contracting / low)  
- **Trend alignment** (e.g. vs EMA)  
- **Market structure** (range, breakout, pullback, continuation, reversal attempt)  

**General rule for any indicator:**

| Dimension | Question |
|-----------|------------|
| Value | What is it now? |
| Direction | What is it doing? |
| Velocity | How fast is it changing? |
| Position | Where vs important levels? |
| Transition | What just changed? |
| Environment | What kind of market (regime / structure)? |

**Principle:** the number is a coordinate; **context** is what turns it into a **pattern** you can search and replay under the Referee.

---

## 15. Repo alignment (honest snapshot)

| Topic | In repo today |
|-------|----------------|
| Forward replay, Referee scores, manifests | **Yes** — `replay_runner`, `pattern_game`, parallel batch |
| “Patterns over one-off PnL” as spec intent | **Yes** — see `GAME_SPEC_INDICATOR_PATTERN_V1.md` §1, §4 |
| LLM narrative only (Anna / player agent) | **Yes** — advisory text; no score injection |
| **Structured indicator context** (direction / transition / structure on every bar) | **Partial / future** — requires feature pipeline + logging contracts; **not** guaranteed in current replay JSON |
| Experiment ledger + pattern memory DB | **Not** as first-class services here — JSONL + git + docs are the current hooks |
| Precomputed indicator tape for search | **Directionally required** for large candidate counts — **verify** in kitchen / replay perf work, not asserted here |

**Next engineering steps (when you prioritize):** define a small **schema** for “indicator snapshot + context” on decision bars; emit it from the feature path; store in ledger; keep Referee binary scoring unchanged.

---

*Consolidated from operator / architect conversation — implementation-ready intent.*
