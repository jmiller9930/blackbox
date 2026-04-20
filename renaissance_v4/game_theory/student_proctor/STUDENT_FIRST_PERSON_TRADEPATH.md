# The Student across from the Proctor — what I need to “make a trade”

**End goal (read this first):** this system is a **training application for agents**: it exists so agents (the **Student** role) can **learn to trade effectively** — pattern sense, risk posture, memory across runs — in a setting where **truth about fills and grading** is held by a separate authority (**Proctor / Referee**), not by the Student’s wishful narrative. Architecture, UX, and metrics should be judged against **that** outcome, not only against plumbing.

**Authoritative definitions — what a trade is; what learned behavior is:** `ARCHITECTURE_BACKWARD_LADDER_STUDENT_TABLE.md` **§0** (**0.2** trade = contract-valid **intent** from **provided** pre-reveal data; **0.3** learned behavior = match / approximate match + **positive vs baseline** on **pre-registered** metrics). That section is the **binding deliverable** language for this initiative.

**Audience:** Product, architect, engineering — anyone aligning **two-sided table** semantics with **what exists today**.  
**Companion:** `ARCHITECTURE_PLAN_STUDENT_PROCTOR_PML.md`, `ARCHITECT_BRIEF_STUDENT_LOOP_EXTERNAL.md`, `E2E_ROADMAP_STUDENT_PROCTOR_PML.md`, `ARCHITECTURE_BACKWARD_LADDER_STUDENT_TABLE.md` (**§0**).  
**This doc:** the **Student’s** operational path, **what each side sees**, and an **explicit gap list** so the next architecture pass does not re-litigate basics in chat.

---

## 1. Who matters first, and what is allowed to change

**The Student is the most important part of the system** — that is what **operators** care about: whether the agent being trained is **getting better** at trading-shaped decisions, memory, and discipline. Product attention, UX priority, and roadmap energy should default to the **Student learning surface**, not to “balancing” the narrative with engineering plumbing.

**The Referee is plumbing** — engineering **substrate**: replay/manifest truth, closed-trade outcomes, the **immutable** grading line the Student is measured against at reveal. Treat it as **baked in** and **not** the usual lever for iteration. We **expect** it **not** to change; the **only** thing that should be moving forward by default is the **Student’s learning ability** — policy, retrieval, records, reveal UX, training metrics, ablations.

**If** the Referee path needed modification someday (new instrument rules, compliance, replay contract change), that would be an **exception**, scoped and justified — **not** something assumed on the horizon today. Until then, churn belongs on the **Student** side.

---

## 2. Across the table — two seats

| | **The Student (agent-in-training)** | **The Proctor (authority / Referee path)** |
|---|-------------------------------------|---------------------------------------------|
| **Metaphor** | Sits on **this** side: partial tape, the exercise is **decide under uncertainty**. | Sits **across**: holds the **graded answer** — what actually happened on the manifest/replay **ledger**. |
| **What I see** | **Causal** context up to decision time: bars-including-up-to-*t*, signals allowed by contract, optional **retrieved memory** from prior runs — **not** the Proctor’s post-hoc verdict inside that packet. | **Outcome truth**: closed trade, PnL, WIN/LOSS, the **Referee** record. That is **not** “what the Student wished”; it is **what the scenario says happened.** |
| **What I must do** | Emit **trade intent** (structured `student_output_v1` and eventually richer **trade_intent**): act/direction/risk/recipes — the **candidate** decision I will defend at reveal. | **Grade** the Student against that truth **once**, at **reveal** — merge intent ↔ outcome, persist **learning** so the **next** run is not amnesiac. |
| **What I must not do** | Pretend I executed the Referee’s fills, or smuggle labels I only know **after** the fact into the **pre-reveal** packet. | Substitute for the Student’s learning loop or own the **pattern** story — Proctor is **authority on outcome**, not **coach** unless the product explicitly adds that lane. |

**“Make a trade”** in this training app means **(A)** above all: **state intent under partial information**; **(B)** is the **Proctor’s ledger line**, which the Student **does not own** but **must** be compared to at reveal so **training** has a ground truth.

---

## 3. Words the Student uses

- **“Make a trade”** splits into:
  - **A) Trade intent** — I (the Student) decide **enter / not**, **direction**, **risk posture** (and eventually size/horizon) **under partial information** at time *t* — **before** I am allowed to treat this unit as graded.
  - **B) Fills on the ledger** — the **Referee / replay** path: actual closed trades, PnL, WIN/LOSS from the **manifest strategy**.

**Today, in code, (B) is not mine.** I do not own execution. What exists is closest to **(A)** as **`student_output_v1`**, often built **after** the batch has already produced Referee outcomes — unless **Phase 2** puts the Student’s decision **before** outcome in **process order** and/or adds a **paper / hypothetical** line to compare at reveal.

---

## 4. What the Student can do today (concrete steps)

1. **Operator runs a parallel batch** (UI **Run batch** or `POST /api/run-parallel`) on a scenario with closed trades in replay.
2. After the run, the **Student seam** (`PATTERN_GAME_STUDENT_LOOP_SEAM` on) walks **Referee’s closed trades** from `replay_outcomes_json`.
3. For each such trade, the system builds the **decision packet**: **bars only up to entry time** (`bars_inclusive_up_to_t`), **pre-reveal** rules — the Student is **not supposed** to get the Referee “answer key” inside that packet.
4. **Cross-run retrieval** may attach **prior learning slices** matched by **context signature** — **memory** can change what the Student emits.
5. A **stub** policy emits **`student_output_v1`**: `act`, `direction`, `confidence_01`, `pattern_recipe_ids`, `student_decision_ref`, etc. — **not** a full broker order, but **more than a single label**.
6. Rows append to **`student_learning_records_v1.jsonl`** so the **next** run can retrieve.

**What that enables for training:** comparable **decision objects**, **retrieval-driven deltas**, **persistence** — the **foundation** for teaching agents pattern-and-memory behavior.

**What it does not yet prove:** that **Student intent** moved headline outcomes, or a full **independent** second trade lifecycle, until **metrics and experiments** are defined for “trade effectively.”

---

## 5. What the Student still needs (to match “at the table / learn to trade effectively”)

| Need | Why |
|------|-----|
| **Decision before outcome in *job order*** | The seam runs **after** batch results today. True “blind until reveal” needs a **hook or second pass** where the Student does **not** depend on `OutcomeRecord` already existing. |
| **`trade_intent_v1` (or extended output)** | Explicit **size/stop/horizon** if “conducting a trade” means more than act/direction. |
| **Paper / hypothetical PnL or lifecycle** | Without comparable economics vs Proctor at **reveal**, “trade” stays **abstract** — weak for **training agents** on real trade-shaped feedback. |
| **`reveal_v1` as the only merge** | Join **Student intent** ↔ **Proctor truth** once; must be the **binding** product story. |
| **Pre-registered metrics** | Sliding **quality** scale; learning from **wins and losses** with fields that fire on both. |
| **Ablation** | Memory on/off, retrieval match vs no match — or claims that training **caused** improvement stay ungrounded. |

---

## 6. Pack into the *next* architecture round

- **Single north-star doc** — revise **in place** with a **changelog**, not new fragments per meeting.
- **Scope gate:** **paper on tape** vs **live orders** — different epics and safety bar.
- **Success criteria:** mechanism / training effectiveness / UX — **separate gates**.
- **UI contract:** **Student** owns the learning story **across from** scorecard/terminal truth (Referee output is **read-only context** for the operator, not a second product hero); **copy/export** for operators.
- **Governance:** who signs that “Student trades” means **intent line** vs **live execution** — one explicit line in charter.
- **Tests:** shadow/referee separation if Student moves **into** replay ordering.

---

## 7. One-line truth for stakeholders

**We built **Referee-side plumbing** (expected stable) so the **Student** can have **causal packets**, **structured decisions**, **memory**, and **records** — what remains is **Student learning depth** (process order, richer intent, paper economics, provable training lift); that is **Phase 2** in the companion roadmap. The **default** place to invest is the **Student**; Referee changes are **out of scope** unless something external forces them.**

---

## 8. Why this paragraph lives in the repo (does it “fix” behavior?)

**For people:** a short charter at the top reduces **scope creep** and **wrong metaphors** (e.g. conflating Student with Referee).

**For automation:** any assistant or agent that **loads** this file (or a pointer in `AGENTS.md`) gets the same constraint **in context** — it does **not** magically change models with no context, but **repeat review against this doc + code** catches drift earlier than tribal chat memory.

If you want this end goal **always** in play for coding agents, **link one line** from root `AGENTS.md` or the game-theory `AGENTS.md` to **this file** (optional follow-up).

---

## 9. Revision history

| Version | Date | Notes |
|---------|------|--------|
| 1.0 | 2026-04-20 | Initial: first-person path, gaps, pack list. |
| 2.0 | 2026-04-20 | Student vs Proctor across the table; training agents to trade effectively as end goal; renamed from Anna-specific draft; §6 behavioral anchor. |
| 3.0 | 2026-04-20 | §1: operator priority (Student first); Referee as baked-in plumbing; evolution defaults to Student learning; Referee change exceptional / not assumed. |
| 4.0 | 2026-04-20 | Pointer + companion to `ARCHITECTURE_BACKWARD_LADDER_STUDENT_TABLE.md` **§0** (binding **trade** / **learned behavior** definitions). |
