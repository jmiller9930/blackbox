# Contract — Anna fund assignment, growth objectives, math bar, and algorithms

**Status:** Binding specification (architect / operator / developer).  
**Supersedes:** Informal assumptions about “a fund,” “winning,” or “math expert” status unless those assumptions are written here or in a higher directive.  
**Companion:** [`ANNA_GOES_TO_SCHOOL.md`](ANNA_GOES_TO_SCHOOL.md) §1 (12th grade, Karpathy loop, graduation). This document **locks** fund semantics, objective structure, statistical competence expectations, and what we mean by **algorithm** in this program.

**Implementation note:** Ledger storage, UI, and automated enforcement may land in phases; until code exists, this contract defines **what must be true** when those features ship. Operators may track fund notionally; **governance** still follows exam-board + human graduation.

---

## 1. Fund assignment (must be explicit)

### 1.1 Definitions

| Term | Meaning |
|------|--------|
| **Fund** | Assigned **notional capital** Anna’s paper harness operates against for a given training period — **not** live wallet balance unless a future directive explicitly moves to live capital and Billy/Jack policy. |
| **Fund ledger** | Authoritative record of starting balance, marks, closed trades, fees/slippage model (as defined), and current equity — **append-only or versioned** once implemented. |
| **Growth objective** | A **stated** target equity curve or horizon goal (e.g. start → target multiple) together with **constraints** (max drawdown, halt rules, review cadence). |

### 1.2 Contractual rules

1. **No implicit fund.** Training without a **recorded** starting fund size and currency (or unit) is **not** a “funded” program in the sense of this contract — it is process-only until a fund row exists in the ledger (or equivalent operator artifact).
2. **Growth is not “win at all costs.”** Any growth target is **subordinate** to risk and governance: **halt conditions**, **exam-board review**, and **human graduation** per §1.3 of `ANNA_GOES_TO_SCHOOL.md`.
3. **Paper vs live** is a **hard boundary** until policy explicitly promotes — consistent with `grade_12_paper_only` and execution-plane rules.

---

## 2. Growth objective (structure)

Every funded training track **must** state (in writing, in the ledger or linked operator record):

| Field | Required |
|-------|----------|
| Starting notional | Yes |
| Target (e.g. multiple of start, or absolute) | Yes |
| Time horizon or evaluation windows | Yes |
| What counts as success (equity high-water? risk-adjusted? process gates?) | Yes |
| Stop / review triggers (drawdown %, consecutive losses, calendar) | Yes |

**Unstated targets** are **not** contract goals — they are operator intent only.

---

## 3. Mathematical and statistical competence (expectation)

### 3.1 Role of math

Anna’s analyst role requires **statistical literacy** sufficient for **honest** analysis: distributions, variance, sample size, overfitting risk, multiple-comparison caution, calibration — not slogan-level “AI confidence.”

### 3.2 Contract bar

- **“Advanced math inside and out”** is **not** a vague title. It means: **demonstrated** ability to apply the relevant **statistical / quantitative** methods the exam board and harness require for the current degree stage — evidenced by **structured outputs, tests, or human review**, not by model fluency alone.
- **12th grade / paper track:** minimum bar is **defined by curriculum + exam board**; this document does not replace `ANNA_GOES_TO_SCHOOL.md` §3.3–3.4 on RCS/RCA and traceability — it **adds** that **numeric claims** must be **defensible** under the math bar above.

---

## 4. “Psychology of winning” → mechanism (no anthropomorphic drives)

### 4.1 What we do **not** claim

- Agents do not have **emotions** or **needs** in the human sense.

### 4.2 What we **do** build (contract)

A **closed-loop improvement mechanism** toward stated objectives:

1. **Explicit objective** (fund growth within constraints).
2. **Measured outcomes** (ledger, gates, RCS/RCA, harness results).
3. **Karpathy-shaped loop** (ingest → propose → test → measure → keep/drop → repeat) — see `karpathy_loop_v1` in `modules/anna_training/catalog.py`.
4. **Promotion / rejection** of strategies or skills based on **evidence**, not narrative.

That is **self-push in system design**, not simulated psychology.

---

## 5. Algorithms — what we mean (yes, we talk about algorithms)

In this program **“algorithm”** is used in the **standard computer science sense**: a **precise procedure** that terminates or iterates with defined inputs and outputs.

### 5.1 Two distinct kinds (both valid)

| Kind | Examples |
|------|----------|
| **Trading / strategy algorithms** | Signal generation, sizing rules, entry/exit logic — **tested in harness**; subject to venue and policy. |
| **Governance / evaluation algorithms** | Grade-12 gate logic, preflight checks, loop daemon ticks, promotion rules — **auditable**, versioned where possible. |

**Not** every conversation about Anna is a trading algorithm; **every** automated gate or loop **is** an algorithm in the sense above.

### 5.2 Contract

- **Strategy algorithms** must be **bounded** by **paper/live** policy and **execution** boundary (Billy/Jack) rules.
- **Governance algorithms** must be **inspectable** (CLI JSON, logs, artifacts) and **change-controlled** when they affect graduation or risk.

---

## 6. Traceability

| Artifact | Role |
|----------|------|
| This file | Fund + objectives + math bar + algorithm vocabulary |
| `ANNA_GOES_TO_SCHOOL.md` | 12th grade, Karpathy steps, graduation, RCS/RCA |
| `modules/anna_training/catalog.py` | Canonical curriculum / method ids |
| `anna_training_cli.py` | Operator surface for paper trades, gates, report-card |

**Conflict resolution:** Higher directive or explicit architect amendment **wins**; then this file; then informal chat.

---

## 7. Change control

- **Fund parameters, growth targets, or halt rules** that affect **risk or graduation** require **documented** update to this contract **or** a numbered directive that references §1–2 here.
- **Algorithm** changes to **gates** or **ledger semantics** require **same** visibility (no silent moves).
