# GT_DIRECTIVE_029 — Directive 1 — Quant / Perps Data & Math Capability Audit

**Date:** 2026-04-27  
**From:** Architect  
**To:** Engineering  
**CC:** Operator  
**Scope:** Pattern Machine / Student Proctor / RM refactor sequence (`renaissance_v4/game_theory/` and **DATA paths** that feed decision packets, DB loaders, scorecards, and learning stores)

**Kind:** **Mandatory audit directive** — evidence-only; **no** new RM intelligence implementation in this ticket.

**Predecessor:** **`GT_DIRECTIVE_028`** (Directive 0 — Reasoning Model refactor alignment) **accepted**; **`docs/rm_refactor_architecture_v1.md`** defines phased migration — **Directive 1 is Phase A**.

**One-line intent:** Directive 0 defined the brain — **Directive 1 tells us what raw material that brain actually has to work with.**

---

## Fault

The codebase mixes **proven plumbing** (Student packet, annex, seal, fingerprints) with **partial intelligence hooks** (deterministic entry scoring, retrieval slices, promotion governance). Without a **single audited map** of:

- what **market/perps DATA** exists vs stub vs absent,
- what **math** is computed vs reported-only vs dead,
- what **actually influences** `decision_synthesis_v1`,
- what **learning-record fields** can support similarity vs signature-only retrieval,

the program risks designing **state models without inputs**, **fake EV**, **memory on incomplete features**, and **garbage learning narratives**. That violates the RM refactor discipline.

---

## Directive

Engineering shall produce a **complete capability audit** — **reality, not intent**. Read paths, DB schemas, contracts, and loaders; cite **file + symbol** for every claim.

### 2.1 Hard gate (enforceable)

Until **this directive is Architect-accepted**:

- Engineering **must not** merge **Directive 2** (RM state model v1), **Directive 3** (pattern fingerprint / similarity), **Directive 4** (EV / risk-cost), **Directive 5** (RM reasoning governance), or **Directive 6** (crypto-perps reasoning exam) **implementation PRs** except **audit-only** tooling or doc fixes explicitly scoped to Directive 1.

**Explicitly forbidden under Directive 1:**

- HMM / NH-HMM / regime neural nets  
- PPO / RL / policy-gradient loops  
- Production trading behavior changes  
- New promotion semantics (`learning_memory_promotion_v1`) beyond documenting current behavior  

Spikes are **not** allowed unless Architect issues a separate exception in writing.

### 2.2 Deliverable (canonical document)

Create and land **`docs/rm_directive_1_quant_perps_data_math_capability_audit_v1.md`** containing **all** sections below. That file is the **single audit artifact** (may embed or link CSV under `docs/` if large).

### 2.3 Section A — DATA layer (truth ingress)

Answer for **each** row: **present in prod path / present but unused / stub only / absent**. Cite where read (module, table/column, env, API).

| Topic | Must answer |
|-------|-------------|
| OHLCV | Timeframes, tables, bar builder path into `student_decision_packet_v1` |
| Funding rates | Available? Granularity? Wired to packet or scorecard only? |
| Open interest | Same |
| Liquidations / crowding proxies | Same |
| Spread / bid-ask / liquidity | Same |
| Order book depth | Same |
| Volume / volume delta | Same |
| Trades / fills | Same |
| Referee outcomes | Path into replay / scorecard / **never** pre-reveal leak |

**Output:** Table **DATA_capability_v1** with columns: `topic`, `status`, `evidence_ref`, `gap_notes`.

### 2.4 Section B — Math / feature layer (what is computed today)

Inventory **formulas and thresholds** that exist **anywhere** in the Pattern Machine / Student path relevant to future RM (not every line of `web_app.py` — scope per judgment, but **don’t hide** parallel metrics).

Must include **explicit** rows for each where applicable:

| Topic | Must answer |
|-------|-------------|
| RSI / EMA / ATR | Periods, functions (`entry_reasoning_engine_v1` and duplicates elsewhere) |
| Returns / rolling volatility | Computed? Where? |
| Z-score | Computed? Where? |
| Drawdown / path metrics | Scorecard vs decision-time |
| Expectancy / win rate | **Batch/scorecard** vs **entry engine** — separate rows |
| Sharpe / Sortino | If present, where; if not, say **absent** |
| Regime labels | Only RSI/EMA/ATR states today? List literals |
| Any other scoring | Bundle optimizer, context memory, panels — **label “decision-time vs report-only”** |

**Output:** Table **MATH_inventory_v1** with columns: `metric_or_formula`, `role` (`decision_time` \| `report_only` \| `governance_only` \| `dead_code`), `location`, `formula_summary`, `notes`.

### 2.5 Section C — Decision layer (`decision_synthesis_v1`)

Must answer **precisely**:

1. **What inputs** feed `final_score` and `action` in `run_entry_reasoning_pipeline_v1` (indicator score, memory score, prior outcome delta, thresholds, conflict clamps, risk gates)?  
2. **What code paths** can override or shadow that action **after** synthesis (`student_decision_authority_v1`, unified router, lifecycle 026c) — list **order of application**.  
3. **Dead vs active:** List modules that **look** like scoring but **do not** affect sealed Student direction (panels, drills, exports) — **explicit “inactive for decision”**.

**Output:** Subsection **DECISION_path_v1** with a short bullet timeline **Packet → ERE → overrides → apply_engine_authority → seal**.

### 2.6 Section D — Memory layer (learning records & similarity readiness)

Must answer:

1. **Schema** of `student_learning_record_v1` (and related slices): fields that exist **today**.  
2. **Retrieval:** How `retrieved_student_experience_v1` is built; **signature_key** vs **similarity** — state **exact** mechanism.  
3. **Promotion:** Summarize `classify_trade_memory_promotion_v1` inputs/outputs (no behavior change — document only).  
4. **Gap:** What is **missing** for **pattern vectors** (continuous similarity) vs current retrieval — explicit list.

**Output:** Table **MEMORY_field_usability_v1**: `field`, `usable_for_similarity_yes_no`, `notes`.

### 2.7 Section E — Gap summary (required)

Single consolidated table:

| Gap ID | Area | Missing | Blocks |

Minimum gaps to address (if missing — confirm or deny with evidence): state inputs, EV inputs, similarity features, perps-specific DATA, unified RM façade.

### 2.8 Conflicts with prior informal inventory

If the audit **contradicts** any prior chat or draft inventory, **say so** and treat **this document + repo citations** as authoritative.

---

## Proof required

Acceptance requires **all** of:

1. **`docs/rm_directive_1_quant_perps_data_math_capability_audit_v1.md`** merged with Sections A–E complete.  
2. Every **non-trivial** claim has **≥1** code reference (`path:symbol` or stable doc pointer).  
3. **`DECISION_path_v1`** explicitly lists **active vs dead** scoring for **direction**.  
4. **`MEMORY_field_usability_v1`** answers similarity readiness **YES/NO per field group**.  
5. **`git push`** to **`origin`** on the merged commit (operator can verify hash).  
6. Engineer appends **Engineer update** below requesting Architect acceptance.

**Optional:** Minimal pytest or script that fails if a documented “required” table is empty — **not** mandatory unless Engineer proposes it as guardrail (Architect decides).

---

## Deficiencies log update

If **`docs/architect/directive_execution_log.md`** or **`docs/blackbox_master_plan.md`** tracks RM refactor phases, update **in the same PR** with **Directive 1** status **audit complete / pending acceptance** per governance (if those files are in use on this branch). If not in use, **skip** and note in Engineer update.

---

## Canonical workflow record

This file is the canonical record for **Directive 1**.

Workflow:

1. Engineer completes audit document + proof list.  
2. Engineer appends Engineer update; pushes to `origin`.  
3. Operator notifies Architect.  
4. Architect appends **Accepted** or **Rejected — rework** with concrete missing rows.

---

## Engineer update

**Status:** pending engineer response

Engineer must append:

- Summary of audit methodology (how you traced DATA and decision path).  
- Link to **`docs/rm_directive_1_quant_perps_data_math_capability_audit_v1.md`**.  
- `git rev-parse HEAD` for merged commit.  
- Explicit line: **`Requesting architect acceptance for GT_DIRECTIVE_029`**.  
- Any **disagreements** with RM boundary (stop-and-explain per Directive 0).

---

## Architect review

**Status:** pending architect review

Architect will append **Accepted** only when Sections A–E and proof bar are satisfied; otherwise **Rejected — rework** with required missing subsections.
