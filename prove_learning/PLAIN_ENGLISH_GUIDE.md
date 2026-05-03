# FinQuant — Plain English Guide

**What is this and how does it decide?**

---

## What FinQuant is

FinQuant is an automated trading assistant that watches the SOL/USD market and recommends whether to enter a trade or stand down. It makes one decision every 15 minutes based on what the market is doing right now.

It does not execute trades on its own. Every decision it makes is logged and auditable.

---

## How it watches the market

Every 15 minutes, a new price bar closes. FinQuant looks at:

- **Price** — did price go up or down from the last bar?
- **RSI (Relative Strength Index)** — is momentum building or fading? Scale of 0–100. Below 50 = weak, above 50 = strong, above 70 = overheated.
- **ATR (Average True Range)** — how much is price moving? Low ATR = quiet market, high ATR = active market.
- **EMA (Moving Average)** — is the trend pointing up or down over the last 20 bars?

---

## The key signal it looks for: RSI Divergence

The most important thing FinQuant checks is called **RSI divergence**. This is when price and momentum move in opposite directions:

**Bullish divergence (possible long entry):**
> Price makes a lower low (keeps falling) BUT RSI makes a higher low (momentum improving)
> This means sellers are losing strength. A reversal upward may be coming.

**Bearish divergence (possible short entry):**
> Price makes a higher high (keeps rising) BUT RSI makes a lower high (momentum weakening)
> This means buyers are losing strength. A reversal downward may be coming.

**No divergence:**
> Price and RSI moving the same direction. No momentum shift. Usually: stand down.

---

## What FinQuant actually does with this

When a new 15-minute bar closes, FinQuant:

1. **Checks the regime** — is the market trending, ranging, or volatile?
2. **Checks for divergence** — is momentum shifting?
3. **Forms two competing arguments** — one FOR entering, one AGAINST
4. **Measures how confident it is in each** — if the difference is less than 20%, it says "I don't have enough evidence" (INSUFFICIENT_DATA)
5. **Checks the risk/reward** — is the potential gain at least 2.5x the potential loss? If not, stand down.
6. **Makes a decision** — ENTER_LONG, ENTER_SHORT, NO_TRADE, or INSUFFICIENT_DATA

---

## The four decisions it can make

| Decision | What it means |
|---|---|
| **ENTER_LONG** | Buy — agent thinks price will go up |
| **ENTER_SHORT** | Sell short — agent thinks price will go down |
| **NO_TRADE** | Stand down — not enough edge to justify risk |
| **INSUFFICIENT_DATA** | Can't decide — the arguments for and against are too close |

---

## How to tell if a decision was good

A good decision is either:
- An entry that made money (**win**)
- Standing down when the market didn't move significantly (**correct abstention**)

A bad decision is either:
- An entry that lost money (**loss**)
- Standing down when the market made a big move (**missed opportunity**)

**The score that matters:** good decisions ÷ total opportunities. In the most recent test, FinQuant made good decisions on **70.5% of opportunities**. The baseline (no system) is roughly 50%.

---

## The risk rules it must follow

**It must never enter a trade without:**
- A defined stop price (where it would exit if wrong)
- A defined target price (where it would exit if right)
- The target must be at least **2.5× the stop distance** — meaning if you risk $1, you must have the potential to make $2.50

**If it can't define these, it must say NO_TRADE.**

---

## What "memory" means in this context

FinQuant keeps a record of every decision it has made and what happened after. Over time, patterns that have worked well (high win rate, enough evidence) get "promoted" and become available to influence future decisions.

When FinQuant sees a new bar that looks similar to a past winning setup, it can retrieve that memory and factor it into its decision. This is how it learns over time — not from retraining its core reasoning, but from building a library of evidence from real market decisions.

---

## Current performance (as of last validated run)

| Metric | Result |
|---|---|
| Cases analyzed | 200 real SOL-PERP 15m bars |
| Decision quality (good decisions ÷ all opportunities) | **70.5%** on cycle 1 |
| Win rate on trades taken | **52.2%** |
| Net PnL on simulated $100 collateral at 30x | **+$3.68** |
| Patterns promoted to active memory | 2 |
| Patterns retired (suppressed — don't work) | 10 |
| Stop/target computed per trade | Yes (1.6× ATR stop, 4.0× ATR target, R=2.5) |
| Session filter | Active — agent is more conservative during Asian session (00:00–13:00 UTC) |

A new 4-cycle test is running now with all improvements active. Results will update this table when complete.

---

## What this is NOT yet

- Not a fully trained dedicated AI model (that is being built separately on dedicated GPU hardware)
- Not connected to live trade execution
- Not paper trading yet — this is the proof of learning phase

The goal is to prove the reasoning is sound before connecting it to execution. The dedicated FinQuant model, when ready, will replace the general Qwen 7B currently being used.

---

*Full technical audit guide with column definitions and manual math verification: see `OPERATOR_AUDIT_GUIDE.md`*
