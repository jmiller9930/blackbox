# Anna — Grade 12 (paper) training: executive summary

**Audience:** CEO / leadership  
**Date:** aligned with repo `main` (training operator surface + gates v3)  
**Companion detail:** [`ANNA_GOES_TO_SCHOOL.md`](ANNA_GOES_TO_SCHOOL.md) (full contract), [`anna_fund_objectives_and_algorithms_contract.md`](anna_fund_objectives_and_algorithms_contract.md) (fund / growth / algorithm definitions)

---

## 1. What “12th grade” is

Anna’s **Grade 12** path is **paper and simulation only** — **no live trading** through Jack/Billy until policy and humans graduate her past that boundary. In product terms: she must **learn how to trade under guardrails** and **prove it with traceable paper evidence** before venue execution is in scope.

---

## 2. The four pillars (what we measure before headline numbers)

We encoded a **cohesive checklist** of four skills. **Overall Grade-12 gate PASS** requires **all four** to be operator-attested **and** a **numeric paper cohort** (minimum decisive trades + win-rate floor — default **60%** on decisive outcomes). At this level the bar is **binary** only (each requirement is pass/fail; no partial credit for overall PASS). **Order matters:** tools first, then the numeric bar — so we do not optimize a vanity percentage while skipping fundamentals.

| Pillar | Plain English | Contract tie-in |
|--------|----------------|------------------|
| **Math engine literacy** | She cites **FACT-grounded** numbers, avoids invented stats, uses disciplined checks when claiming figures. | Math engine + analyst pipeline; Wilson/NIST-style rigor where applicable. |
| **Analysis & algorithms** | She uses the **quant / analysis stack** to separate **signal from noise** in the allowed harness — not vibes. | Metrics, pedagogy paths, procedures wired in code (`analysis_math`, prompts, pipeline). |
| **RCS / RCA discipline** | **RCS** (light reflection) on every outcome; **RCA** (deep dive) only when the gate/policy says so — traceable **why** on wins and losses. | Same DNA as §3.3 in `ANNA_GOES_TO_SCHOOL.md` — this checklist makes that discipline **visible** before revenue-style headlines. |
| **Karpathy harness loop** | **Propose → test in harness → measure → keep/drop → repeat** until gates are met. | Canonical seven-step loop in `karpathy_loop_v1`; continuous improvement, not one-off chat. |

**Important:** The **long-running training loop** (daemon) keeps the **process** alive; by default it does **not** mark skills “mastered.” **Progress on the checklist** is **operator attestation** after evidence (`anna tool-pass`), plus **logged paper trades** for the numeric slice. Optional env **`ANNA_KARPATHY_AUTO_ATTEST_TOOLS=1`** can flip a tool to passed only when **binary** automated practice for that tool succeeds — still a true/false outcome, not a partial grade.

---

## 3. What we reworked (why the bar looks stricter now)

| Topic | Before | After |
|-------|--------|--------|
| **Gate** | Mostly **numeric** (win rate + min N). | **Tools (four) + numeric** — both must pass for overall PASS. |
| **Visibility** | Hard to see “is she moving?” vs idle loop. | **Report card TUI** (`anna watch`), **progress %** (tool checklist %, paper track %, combined, bottleneck), **Slack `#report_card`** matches the same text. |
| **Attestation** | Implicit in prose. | Explicit **`anna tool-list` / `anna tool-pass`** and state field **`grade_12_tool_mastery`**. |
| **Operator clarity** | Confusion between **heartbeat** and **learning**. | Documented: **heartbeats ≠ checklist %** until attestation + paper evidence. |

This rework aligns **software** with the **contract** already in `ANNA_GOES_TO_SCHOOL.md`: **basics before headline performance** — if she does not demonstrate the pillars, she does not “graduate” the numeric bar in a meaningful way.

---

## 4. Where Anna is right now (how to read status)

**Truthful answer for leadership:** “Where she is” is **whatever is in the current report card** — preflight, curriculum/method, **tool checklist (0–100% attestation)**, **paper cohort** (trades logged to `paper_trades.jsonl`), **numeric track %**, and **gate PASS/FAIL**. There is **no** separate magic “% learned” from the loop alone.

**Typical early posture:** **0%** on each tool until the operator **attests** them after review; **0%** on the numeric track until **decisive paper trades** exist at volume — **even if the loop has been running for days.** That is **intended**: running is **necessary**, not **sufficient**.

**Commands for a snapshot:** `anna watch` (once) or `anna watch --live`; `anna gates` (JSON); `anna status` (includes **`grade_12_progress`**); Slack **`#anna` `#report_card`**.

---

## 5. What we are *not* claiming in this summary

- **Live trading** readiness — **not** until policy moves beyond **Grade 12 paper**.
- **Automatic skill scoring** from LLM output — **not** without additional instrumentation; checklist **%** today is **attestation + paper metrics**, not autonomous grading.
- **Fund P&L promises** — see **`anna_fund_objectives_and_algorithms_contract.md`** for binding definitions.

---

## 6. Bottom line for the CEO

We put a **clear, sequenced bar** in place: **four named skills** (math literacy, analysis, RCS/RCA discipline, Karpathy harness) **plus** a **paper numeric cohort** — with **transparent reporting** (TUI, Slack, CLI). Anna **earns** the next stage by **evidence**, not by uptime alone.

For technical operators, the single source of truth remains **`ANNA_GOES_TO_SCHOOL.md`** and the **`modules/anna_training/`** code referenced there.
