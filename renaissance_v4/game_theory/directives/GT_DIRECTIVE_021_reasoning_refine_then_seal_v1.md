# GT_DIRECTIVE_021 — Student reasoning: **refine-then-seal** (controlled second pass)

**Date:** 2026-04-24  
**Status:** **ACCEPTED v1 (spec locked)** — **NOT IMPLEMENTED** in code until engineer ships + proof; this file is the **binding** product/architect contract.  
**From:** Architect (binding direction)  
**To:** Engineering  
**CC:** Product, Referee  
**Scope:** `renaissance_v4/game_theory/student_proctor` — LLM Student emit path (`student_ollama_student_output_v1.py`), Student loop seam (`student_proctor_operator_runtime_v1.py`). **Does not** change §1.0 thesis **requirements on the sealed object**; **does** define a **pre-seal** draft pass with weaker validation only.

**Cross-refs:** **GT_DIRECTIVE_015** (brain profile / run contract), **GT_DIRECTIVE_017** (L3 truth — draft **out of scope**), **GT_DIRECTIVE_018** (learning governance — **final only**). **Does not** subsume a future “temperature = 0” or deliberation H1–H4 directive.

---

## Fault (why this exists)

Single-shot LLM emit can produce **`student_output_v1`** that is structurally valid but **thesis-incomplete** or **internally inconsistent** before operators see a sealed row. A **single correction pass** before commitment—same shape, stricter seal—improves reasoning quality **without** a “thinking loop,” new persisted artifact types, or L3 surface drift.

---

## Architectural stance (non-negotiable)

021 is **not** an LLM “thinking system,” **not** a persisted draft decision, **not** a dual evaluation path. It is:

> **One correction pass before commitment** — draft in memory only; refine output **replaces** draft; **one** object sealed and persisted.

---

## Directive — Draft contract

- **Draft is not a new schema** and **not** a forked contract.  
- Draft uses the **same `student_output_v1` shape** as today (same keys / merge rules as the existing emit path).  
- **Draft validation:**  
  - **MUST** pass `validate_student_output_v1` (base contract).  
  - **MUST NOT** run `validate_student_output_directional_thesis_required_for_llm_profile_v1` on the draft.  
- **No new persisted fields** on `student_output_v1` for “draft mode” — draft exists **only in process memory** between the two passes.

---

## Directive — Seal rule

- **Exactly one** object is ever **sealed, persisted, and used downstream** (reveal → learning → L3 → 018 inputs as today).  
- **Draft is never** written to the learning store, **never** embedded as the decision in `reveal_v1`, **never** sent to L3 as the Student decision snapshot.  
- **Refine output fully replaces** the in-memory draft for the purpose of sealing.  
- **Only** the refined object runs `validate_student_output_directional_thesis_required_for_llm_profile_v1` (when the LLM profile requires thesis) **then** proceeds through existing reveal / record / governance paths.  
- **No dual objects,** no ambiguity, no “pick draft or refine” at persistence.

---

## Directive — Determinism

- **Do not** change Ollama **`temperature`** as part of 021.  
- **Keep** `temperature = 0.15` (and any other generation options) **identical** for both draft and refine HTTP calls unless a **single** shared options dict is built once and reused for both (no hidden drift between passes).  
- Rationale: the system is already non-deterministic at the model layer; 021 **does not** introduce a *new* nondeterminism class—it adds a **second** sample under the **same** parameters. A move to `temperature = 0` is **out of scope** (separate directive).

---

## Directive — Caps and audit

- The **refine** HTTP completion **counts as an LLM call** (operator-visible, not invisible).  
- Add audit field: **`llm_refine_attempts_v1`** (or equivalent name agreed in seam audit schema) — increment / record per refine attempt as specified in implementation notes below.  
- **Do not** silently **double-count** refine against **`PATTERN_GAME_STUDENT_LLM_MAX_TRADES`** (or successor cap) **without** explicit product behavior: default interpretation for v1 — **one trade may consume up to two LLM completions** (draft + refine), both **visible** in audit and both subject to **documented** cap semantics (engineer must document chosen rule in proof: e.g. cap = “completions per trade” = 2 max for 021 path, or cap applies to “trades receiving LLM” with internal counter — **must not** be ambiguous in tests).

---

## Directive — L3 (017)

- **Draft is not shown in L3.**  
- Draft is **audit-only** (seam / execution audit if needed — optional structured log line; **not** `student_decision_record_v1`, not L3 payload).  
- Rationale: **017** is truth of **system state** after seal; draft is internal reasoning, not system state.  
- Any future operator-visible draft is **out of scope** — new directive.

---

## Directive — Learning governance (018)

- **Only the final sealed output** may enter the learning append path (unchanged 018 behavior on that object).  
- **Draft never** touches the learning store.  
- **No** secondary append for the same trade, **no** dual evaluation of draft vs refine in governance.  
- **018 logic** for the persisted row remains **unchanged**; 021 only supplies a **better** `student_output_v1` snapshot into the same gates.

---

## Directive — Failure policy

**Strict and simple:**

- If **refine** fails (HTTP error, parse error, **`validate_student_output_v1`** failure, or **`validate_student_output_directional_thesis_required_for_llm_profile_v1`** failure on the refined object): **reject the entire trade** for the LLM emit path (same class of outcome as today’s failed emit — **no** row appended for that trade on that path).  

**Explicitly forbidden for v1:**

- Fallback to draft as sealed output.  
- Automatic retry loops beyond the single refine pass defined here.  
- Partial sealing (draft persisted as decision).

This keeps behavior **aligned with current LLM failure handling** in `student_loop_seam_after_parallel_batch_v1` (continue / no stub for LLM profile on emit failure).

---

## Implementation locus (informative — from repo map)

Engineering must implement **only** within these boundaries unless a new directive expands scope:

| Area | Primary files |
|------|----------------|
| Two-pass emit + validation order | `student_proctor/student_ollama_student_output_v1.py` — `emit_student_output_via_ollama_v1` (or a helper called from it) |
| Seam order, audit, caps | `student_proctor/student_proctor_operator_runtime_v1.py` — `student_loop_seam_after_parallel_batch_v1` |
| Base vs thesis validators | `student_proctor/contracts_v1.py` — `validate_student_output_v1`, `validate_student_output_directional_thesis_required_for_llm_profile_v1` |
| Reveal re-validation | `student_proctor/reveal_layer_v1.py` — `build_reveal_v1_from_outcome_and_student` (**unchanged** contract: still one `student_output`) |

**Insertion point (conceptual):** after first model JSON is parsed into the **`student_output_v1` dict**, run **base** validation only → **refine** (second completion, prompt includes draft constraints per engineer spec) → **full** validation including thesis → return single object to seam **or** `None` + errors on any hard failure.

---

## Proof required (acceptance)

1. **Unit tests** — draft passes base validator, fails thesis validator if called; refined object passes thesis when required; refine failure returns no sealed output.  
2. **No persistence leak** — tests or assertions that draft dict is never passed to `build_reveal_v1_from_outcome_and_student` / append path unless it equals the post-refine single object (same identity or provably replaced).  
3. **Audit** — `llm_refine_attempts_v1` (or chosen name) present and correct for 0/1/2-call scenarios; cap behavior **documented in test names** and proof doc.  
4. **L3 unchanged** — no new keys in L3 payload for draft; snapshot tests or grep guard.  
5. **Doc** — This directive; **§** row in `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` when implemented; short proof under `docs/proof/exam_v1/` if repo convention requires.

---

## Deficiencies log

Track **“GT_DIRECTIVE_021 — refine-then-seal”** until **Accepted** (implementation + proof) or **Deferred in writing**.

---

## Engineer update

**Status:** pending implementation

Engineer must append: summary, files changed, proof, tests, explicit line **`Requesting architect acceptance`**.

---

## Architect review

**Status:** pending — spec **locked** 2026-04-24; acceptance after implementation + proof.

---

## One-line summary

021 formalizes a **single in-memory correction pass** before seal: same `student_output_v1` shape, **base** validation on draft, **full** validation on refine only, **one** persisted object, **no** L3 draft, **no** learning on draft, **reject trade** if refine fails—second LLM call **visible** in audit and **not** silently cap-doubled.
