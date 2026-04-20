# Architect Brief — Student Loop (PML / BLACKBOX)

**Audience:** External architecture team, principal architects, engineering leads  
**Purpose:** Single shareable summary of **intent**, **boundaries**, **directives**, **integration plan**, and **explicit caveats** for wiring the **Student–Proctor training loop** as the **primary operator-facing product** (not merely backend plumbing).  
**Version:** 1.3  
**Date:** 2026-04-20  
**Canonical in-repo companions:** `ARCHITECTURE_PLAN_STUDENT_PROCTOR_PML.md` (full directive text + §12 integration + **§1b** LLM context resolution talking point), `CONTEXT_LOG_PML_SYSTEM_AMENDMENT.md` (product canon + technical gap detail), `E2E_ROADMAP_STUDENT_PROCTOR_PML.md` (**v2.1 — binding**: **SR-1–SR-5**, Run A/B/Reset/C, **atomic proof bundle**, AC-1–AC-5, rejection rule, definition of DONE).

---

## 1. Executive summary

BLACKBOX Pattern Machine Learning (PML) targets a **repeatable training loop** on historic replay:

| Role | Name | Responsibility |
|------|------|----------------|
| **Student** | Agent / Anna | At decision time *t*, reasons from **causal** market view, **indicators + context**, and **retrieved prior learning** — **without** future bars or unrevealed outcomes for the current graded unit. |
| **Referee** | Deterministic engine | **Immutable standard**: execution, ledger, PnL, WIN/LOSS, Referee-computed **quality** scalars. Does **not** coach the Student during the decision. |

After each **graded unit**, a **reveal** joins **Student belief** (structured) with **Referee truth**. **Learning records** persist **matchable** experience so that **a later run** can show **different Student behavior** when similar contexts recur.

**Proof-of-work for this architecture (integration complete):** The operator can **run a test from the UI** on the **same entrypoint** used for production batches; the system **demonstrates** the **Student → learning → outcome** relationship **by default** (not buried under engine telemetry); and **the next run** can **use prior Student knowledge** so that behavior is **not** “one and done.” **Resetting Student learning storage** returns the Student path toward a **no-priors** baseline — i.e. **cognitive reset** for that track.

---

## 2. Product thesis (what operators optimize for)

Operators care about **pattern recognition under uncertainty** with **memory in context**: **not** merely deterministic replay scores, but **whether the agent’s structured decisions and reasoning change** when **prior graded experience** is retrieved for **similar** situations.

- **Outcomes may be positive or negative.** Losses are still graded; **credit assignment** requires reveal on loss as well as win.
- **Learning is “real” only if a future exposure changes decision-relevant behavior** when retrieval matches — not if logs look busy.
- The **Referee** is the **proctor** (grading key). It must be **trusted** and **auditable**, but it is **not** the **headline** of the product story unless something is wrong or an audit is underway.

---

## 3. Current state vs target (honest boundary)

**Shipped today (high level):**

- Strong **Referee / replay** path: manifests, parallel scenarios, `OutcomeRecord` streams, scorecards, harness-style artifacts.
- **Engine-side memory** (e.g. **Decision Context Recall**, signature stores, memory bundles) can **change replay behavior** in **engine-defined** ways — this is **related** to “memory” but is **not** the **Student learning ledger** unless explicitly merged by policy.

**Student–Proctor stack in code (Directives 01–08, largely as **libraries + tests**):**

- Versioned contracts: `student_output_v1`, `reveal_v1`, `student_learning_record_v1`, legal **pre-reveal** packet rules.  
- **Student context builder**, **shadow student** emission, **reveal** join, **append-only learning store**, **cross-run retrieval**, **pytest proofs** (e.g. Directive 07 — observable Student delta when priors exist / reset).

**Gap (product):** The **execution seam** — automatic invocation of **packet → Student output → reveal → append learning row** from the **operator batch entrypoint** — is **not** wired as the **default** runtime path. **Default UI** still **emphasizes** engine telemetry and Referee outcomes more than the **Student triangle**.

**Target:** **Directives 09–11** (see §6) close the gap — **integration + primary UI + observability** — with proof that includes **Flask / operator-visible** behavior, not **only** unit tests.

---

## 4. End-state operator journey (normative)

1. Operator opens the **pattern-game web UI** → selects **pattern / recipe / scenario batch**.  
2. Operator clicks **Run** (parallel batch).  
3. For each **graded unit** (v1: **closed trade**, aligned with `OutcomeRecord`):  
   - **Pre-reveal:** legal decision packet (causal-only).  
   - **Student:** `student_output_v1` (shadow stub first; **no execution authority** unless a future ADR explicitly allows it).  
   - **Post-reveal:** `reveal_v1` joins Student + Referee.  
   - **Persist:** append `student_learning_record_v1`.  
4. **Primary** operator readout: **belief → what was stored / retrieved → Referee outcome / quality** — **easy to understand** without reading fusion internals.  
5. **Subsequent run:** retrieval enriches the packet; **observable** Student fields differ when priors match (same **logic** as proven in tests, **executed** in runtime).

---

## 5. Logical dataflow (ASCII)

```
  [Scenarios / manifest] ──► [Replay / parallel workers] ──► OutcomeRecord[]
                                        │
                                        ▼
                    STUDENT TRAINING SEAM (integration target)
                    packet → student_output_v1 → reveal_v1 → append learning row
                    store: student_learning_records_v1.jsonl
                    next run: retrieve → enriched packet → different Student output
                                        │
                                        ▼
  [UI — PRIMARY]   Student / Learning / Outcome triangle + “training happened” signals
  [UI — SECONDARY] Scorecard, DCR/engine detail, deep telemetry (troubleshooting / audit)
```

---

## 6. Directive map (01–11)

**Directives 01–08** — **Contract and library phase** (isolation, schemas, builders, shadow, reveal, store, retrieval, cross-run **test** proof, truth-separation hooks):

| ID | Theme | Notes |
|----|--------|------|
| 01 | Contract freeze | Schemas + leakage rules |
| 02 | Student context builder | Legal causal packets |
| 03 | Shadow Student | `student_output_v1`, zero execution authority |
| 04 | Reveal layer | `reveal_v1` as only sanctioned join |
| 05 | Learning store | Append-only JSONL, query without LLM |
| 06 | Cross-run retrieval | Priors into legal packets only |
| 07 | Cross-run proof | Automated behavior delta + reset — **today: proven in tests** |
| 08 | UI truth separation | Scoreboard visibility ≠ learning reset |

**Directives 09–11** — **Integration & product phase** (this brief’s “close the loop”):

| ID | Theme | Acceptance gist |
|----|--------|----------------|
| **09** | **Execution seam** | Operator entrypoint **invokes** the Student pipeline per outcome (or batch post-pass); Referee results still authoritative; optional **soft-fail** Student on errors per policy. |
| **10** | **Primary UI** | Default surface = **Student triangle**; engine/DCR **secondary** (collapsible). |
| **11** | **Observability** | Explicit fields (e.g. rows appended, retrieval matches) — **do not** infer “Student trained” from **DCR** counters alone. |

---

## 7. Memory reset semantics (critical)

- **Student learning ledger** (append-only records used for **retrieval into Student packets**): clearing this store **≈ cognitive reset** for the **Student** path — **next run** should behave like **no priors** (modulo other unchanged inputs).  
- **Engine memory** (DCR JSONL, bundles, etc.) is **architecturally separate** until an explicit merge ADR. Clearing **one** does **not** imply clearing the **other**.  
- **Scorecard / visible run history** is **not** the same as **learning state** — operators need **distinct** semantics (“scoreboard paper” vs “trophy case”).

---

## 8. Caveats (read carefully)

1. **Referee immutability.** No LLM or Student path may **authorize orders** or **rewrite** Referee numbers. Student influence on **execution**, if ever introduced, is a **separate gated phase** (not the default of Directives 09–11).

2. **Shadow vs “made money.”** Early proof may show **Student belief / retrieval / output** changing run-over-run while **Referee PnL** is **unchanged** (shadow mode). That can still **prove the learning loop**. Claiming **profit improvement** is a **stronger** product statement and may require **additional** policy and proof — **not** assumed by this integration charter alone.

3. **Two memory stories.** **Engine** recall (DCR, signatures) and **Student** learning records are **not interchangeable**. UI and metrics must **label** them; using DCR metrics as a proxy for “Student learned” is **forbidden** in Directive 11.

4. **Hot path vs post-pass.** For latency and audit, the first **runtime** integration may run the Student pipeline as a **post-pass** over `OutcomeRecord[]` after replay completes — still **valid** if ordering and artifacts are deterministic and the operator sees results. **LLM-in-hot-loop** requires a **separate ADR**.

5. **Graded unit v1.** Closed-trade alignment is the **default** recommendation; finer granularity is future scope.

6. **Directive closure = proof, not intent.** No directive closes on narrative alone — reproducible evidence (tests, e2e, API JSON, screenshots per directive) is required. See **Closure Rule** in the full architecture plan.

7. **External team dependency:** DB paths, PML runtime root, deployment (Flask on 8765, etc.) must match **environment**; this brief is **logical** architecture — **ops** details live in repo runbooks/scripts.

---

## 9. Non-goals (this charter)

- Replacing Referee math with LLM opinion.  
- Claiming RL / bandit frameworks without an approved minimal pipeline.  
- Treating “high DCR recall counts” as proof of **Student** learning.  
- Collapsing **clear scorecard** into **reset learning** without explicit operator consent.

---

## 10. Handoff

| Owner | Responsibility |
|-------|----------------|
| **Architect** | Approves Directive 09–11 scope, soft-fail policy, UI information hierarchy, any merge between Student store and engine memory. |
| **Engineering** | Implements seam + UI + observability; preserves isolation tests (e.g. replay hot path does not import learning store). |

---

## 11. References (in repository)

| Document | Role |
|----------|------|
| `renaissance_v4/game_theory/ARCHITECTURE_PLAN_STUDENT_PROCTOR_PML.md` | Full directive text, §12 integration detail, closure rules; **§1b** LLM context resolution layer (talking point — revisit) |
| `renaissance_v4/game_theory/CONTEXT_LOG_PML_SYSTEM_AMENDMENT.md` | Canon, Story A vs B, gaps §12.x, §15 operator surface |
| `renaissance_v4/game_theory/student_proctor/` | Implementation modules |

---

## 12. Architect acceptance — Student loop integration (critical closeout)

This architecture is **approved as implemented** for the integration charter **only if** the following are demonstrated with **reproducible proof** (tests, API payloads, screenshots, or scripted runs as applicable), **not** by narrative alone:

**Directive 09 — proof tiering:** Automated API tests with a **monkeypatched** outcome source are **accepted** as **seam-wiring** evidence (ongoing CI), **not** as **final** Directive 09 closeout. **Final** closeout requires **one unmocked lab proof** with **real workers**: replay itself produces **closed trades**, and the full **UI/API** flow shows **write → retrieve → changed Student output → reset → baseline** (detail: `ARCHITECTURE_PLAN_STUDENT_PROCTOR_PML.md` §12.4).

1. **Execution seam (Directive 09)**  
   A pattern-game batch started from the **operator entrypoint** (same path as the web UI) runs, for each **closed trade** (graded unit v1), the chain: **legal pre-reveal packet → `student_output_v1` → `reveal_v1` → append `student_learning_record_v1`**, without mutating Referee math or granting the Student execution authority. **Hot replay** remains isolated from direct `student_learning_store` import as required by existing boundary tests. **Soft-fail** behavior (if any) is documented and matches architect policy. **Architect closeout** needs the **unmocked lab** bar above, not monkeypatched batch/outcome alone.

2. **Cross-run behavior (runtime parity with proof)**  
   A **second** run with **matching** context and **non-empty** Student learning store shows **observable, decision-relevant** differences in **Student** artifacts versus a **no-retrieval** or **cleared-store** baseline; the delta **disappears** when Student learning state is reset appropriately.

3. **Primary operator surface (Directive 10)**  
   The **default** post-run experience foregrounds **Student → learning → outcome** (belief, what was stored/retrieved, Referee outcome/quality). Engine-only surfaces (DCR, fusion detail) are **secondary** and **labeled**; the UI does **not** imply that clearing **scorecard** clears **Student learning** unless that is explicitly implemented and labeled.

4. **Observability (Directive 11)**  
   Completed batches expose **explicit** machine-readable fields for Student training (e.g. rows appended, retrieval match counts, fingerprints as specified) — **not** inferred solely from **DCR** or engine recall metrics.

5. **Caveats honored**  
   **Student learning** is **not** conflated with **engine** memory in copy or metrics unless covered by a **separate** merge ADR. **Shadow** proof is not misrepresented as **guaranteed PnL improvement** without additional approved scope.

**Signatures / dates:** _________________  

---

*End of architect brief — suitable for copy/export to other architecture teams. Amend version header when material constraints change.*
