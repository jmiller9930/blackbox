# prove_learning — Guidance Document

**Read this before every work session. Enforce it.**

---

## What this folder is

A self-contained lab that proves a learning module can work.

That is the only goal. Not a trading system. Not an agent platform. Not a demo.
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

Currently: baseline (no memory) = **62.5% win rate**. Memory must beat that to prove learning.

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

1. Read this document at the start of every session
2. State which problem from the fix list is being worked on before writing code
3. Run tests after every change — 129 must pass before committing
4. Run the training loop on real data after every significant change
5. If the result does not improve, diagnose before moving to the next fix
6. Never claim PASS unless win rate with memory beats 62.5% baseline
7. Do not build new features until current broken things are fixed

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

**Last updated:** 2026-05-02  
**Status:** Working on Fix 1 — quality gate on retrieval
