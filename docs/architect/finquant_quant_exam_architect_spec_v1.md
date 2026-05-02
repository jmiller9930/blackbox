# FinQuant Quant Exam — Architect specification v1.1

**Status:** Normative handoff — trainer owns wiring; this document owns **scope, taxonomy, schema contract, pass gates**, and **Reasoning Model (RM) alignment** with Black Box refactor logic (`GT_DIRECTIVE_028`).  
**Audience:** Trainer (integration), engineering (implementation when directed), operator (interpretation of “certified”).  
**Does not replace:** `finquant/docs/FinQuant-1_architecture.md` (narrow verifier mission); this spec **adds** a **second certification layer**: **quant skills**, not verifier structure alone.

---

## 1. Purpose

**Problem:** The current shipped eval path (`finquant/evals/eval_finquant.py`) is **verifier-shaped** (section labels, trap cues, DATA evidence language). That is **necessary** and **already valuable** for v0.4-style models, but it is **not sufficient** to claim **production-grade quant reasoning**.

**Product intent:** Define **`finquant_quant_exam_v1`** — a **versioned case battery** that FinQuant (or any adapter implementing the same I/O contract) must pass before the architect/operator accepts **“quant exam cleared”** for a given model tag (e.g. FinQuant v0.5).

**Non-goal:** This exam is **not** Pattern Game Referee certification, **not** live trading approval, and **not** a replacement for **DATA proof** on real fills. It is **offline reasoning certification** over **fixed cases** with **declared assumptions**.

---

## 2. Relationship to existing artifacts

| Artifact | Role |
|---------|------|
| `finquant/docs/FinQuant-1_architecture.md` | Domain story: verifier + DATA gate; **quant exam is an additional bar**. |
| `finquant/evals/eval_finquant.py` | **Verifier exam** grader; may **coexist** with quant exam or call shared primitives. |
| `nde_factory/layout/finquant/eval/final_exam_v1.json` | **Placeholder** today (`cases: []`); trainer may **repurpose or supersede** with `finquant_quant_exam_v1` payload per §5. |
| `renaissance_v4/game_theory/exam_downstream_frame_generator_v1.py` | **Semantic reference** for **no-lookahead** framing in Black Box (cases should not contradict this rule). |
| `renaissance_v4/game_theory/exam_run_contract_v1.py` | **Policy / brain-profile vocabulary** if cases reference operator exam language (optional cross-link). |
| `finquant/scripts/generate_v0_2b_policy_mismatch_jsonl.py` (and reports) | **Precedent** for **policy mismatch** training/eval content — exam cases should align with that vocabulary where overlap exists. |
| `renaissance_v4/game_theory/directives/GT_DIRECTIVE_028_crypto_perps_reasoning_architecture_directive_0_v1.md` | **Normative RM refactor memo** — single governed **Reasoning Model (RM) box**; deterministic features **feed** RM; exam authoring must stay consistent (§2.1). |
| `renaissance_v4/game_theory/unified_agent_v1/reasoning_router_v1.py` | **026AI router** after entry reasoning — `final_route_v1` vocabulary (e.g. `local_only`, `external_review`) for integrated traces; optional **exam category** in §4. |
| `renaissance_v4/game_theory/rm_preflight_wiring_v1.py` | **RM preflight** before parallel batch — decision snapshot path, trace stages, timeouts; **Pattern Game** gate (not FinQuant adapter **required**, but defines operator RM health). |
| `renaissance_v4/game_theory/reasoning_model_operator_surface_v1.py` | **Operator RM surface** — external API gateway prefs, snapshot schema for `/api/reasoning-model/status`; cross-check when exams mention “external reasoning.” |

### 2.1 Reasoning Model (RM) — architect logic (normative for case design)

**Authority:** `GT_DIRECTIVE_028` — *no brain logic outside RM* for the **Pattern Machine / crypto-perps stack**. FinQuant quant exam cases are **offline** and **adapter-scoped**, but **must not teach or reward** patterns that violate this architecture when the same model is later **wired into** the unified Student + RM path.

**Layered flow (reference):**

| Layer | Responsibility | Exam implication |
|--------|----------------|------------------|
| **DATA** | Canonical inputs and outcomes (bars, funding assumptions declared in case, etc.) | `reference_facts_v1` + `case_assumptions_v1` are **DATA**; grader uses them as ground truth. |
| **Signal / feature** | **Deterministic** transforms only (RSI, EMA, ATR, …) — **no proprietary final “decision”** here | Precomputed `indicator_values` in a case = **feature layer**; model **interprets**, does not invent numbers. |
| **RM box** | **Intelligence**: interpretation, state/EV narratives as designed, reasoning governance, learning promotion **semantics** | FinQuant answers on quant cases should **separate** “given feature values” vs “inference / trade thesis” — see category `rm_data_feature_inference_boundary_v1` in §4. |
| **Student** | Decision / thesis under contracts (seal, authority) when integrated | Quant exam **does not** replace Student contract tests; **integration** is a separate gate. |
| **Referee** | Post-hoc outcome grading | Quant exam **does not** certify Referee alignment. |

**Forbidden patterns (exam content must not reward):**

- **Shadow brain:** A **separate “exam-only” scoring story** that **cannot** be retraced through the same DATA → features → RM → Student narrative the product uses.
- **Feature leakage as decision:** Treating **raw indicators** as if they were **final actions** with no explicit reasoning step (when the case asks for interpretation).
- **Unauditable policy:** Mixing two policies **without** calling out mismatch (already covered under `policy_mismatch`; see §4).

**Pattern Machine touchpoints (when operator compares FinQuant to live stack):**

- **No-lookahead** downstream semantics: `exam_downstream_frame_generator_v1.py` — quant cases with “path B” bars must **not** imply future OHLC in the **past** packet.
- **Router trace:** `reasoning_router_decision_v1` stages in learning trace — **optional** advanced cases may ask the model to **classify** when **local-only** vs **external** review is appropriate *given a stub scenario* (text-only; no live API required).

**Integration boundary (architect rule):** The trainer **chooses** runner layout (standalone script, NDE graph step, adapter CLI). The **normative** contract is **case JSON + grading outcomes** (§5–§7), not a mandatory file path inside NDE. **RM alignment** constrains **what good answers look like**, not where the runner lives.

---

## 3. Exam identity and versioning

| Field | Value |
|-------|--------|
| `exam_schema` | `finquant_quant_exam_v1` |
| `exam_version` | Monotonic integer (1, 2, …) — bump when **any** case text, expected outcome, or pass rule changes. |
| `model_under_test` | Opaque string (e.g. adapter id + checkpoint id) — **recorded in results**, not gated by this spec. |

**Certification statement (operator-facing):**  
“**FinQuant quant exam v\<N\> PASS**” means: all **required** cases in that version met **pass predicates** (§7) under the **declared grader revision**.

---

## 4. Scope: case categories (trainer bucket → architect intent)

**Minimum quant battery (non-placeholder):** each **core** row below through `no_trade_abstention` **must** have at least **one** case in v1. Categories are **orthogonal**; a case belongs to **one** `primary_category` (may add `secondary_tags[]`).

**RM integration battery (recommended** when the certified model is intended for **unified Pattern Machine / Student + RM** wiring**):** include at least **one** case per **`rm_*`** row. These encode **`GT_DIRECTIVE_028`** boundaries without requiring a live `POST /api/run-parallel` (stub prompts + deterministic grading).

| `primary_category` | What competence must be demonstrated |
|--------------------|--------------------------------------|
| `indicator_interpretation_rsi_ema_atr` | Correct use of **RSI / EMA / ATR** definitions on **given** numeric inputs (bars or precomputed series). No hallucinated indicator values; if values supplied in case, model must **use them** or **state missing data**. Indicators sit in the **feature layer**; interpretation belongs in **reasoning** (§2.1). |
| `lookahead_leakage` | Detect **future information** or **illegal ordering** in the prompt (e.g. post-hoc label, future bar in “past” narrative). Expected: **FAIL** verdict on the claim or **explicit leak flag** per output schema. Aligns with **no-lookahead** downstream semantics in `exam_downstream_frame_generator_v1.py`. |
| `pnl_accounting` | **Direction, fees, rounding** — closed trade PnL, simple portfolios, or fee drag — with **numerical answer** matching grader tolerance or structured **Math verdict** + number. |
| `position_sizing` | Size from **risk budget**, **equity**, **contract multiplier** (if provided), caps; **units** explicit. |
| `risk_reward` | TP/SL vs **R-multiple** or payoff ratio; consistency with **stated** entry/stop/target. |
| `perp_funding_semantics` | Sign / period / **who pays whom** under **case-declared** convention (exam must **fix** convention in `case_assumptions_v1`; model must not invent exchange rules). |
| `liquidation_risk` | Distance to liquidation, margin mode **as stated**; no fantasy formulas — if simplified linear margin in case, model follows case math. |
| `policy_mismatch` | **Two** policy fragments + one factual setup; answer must **not** blend incompatible rules; must identify **conflict** or **which policy governs** per case instructions. |
| `no_trade_abstention` | Under **weak edge** or **insufficient data**, model **refrains** from forced trade or **states** non-action with **evidence gap** — must not invent edge. |
| `rm_data_feature_inference_boundary_v1` | Given **fixed** `reference_facts_v1` (bars and/or `indicator_values`), the answer must **explicitly separate** **observed / given quantities** vs **hypothesis or action**; must **not** treat features as a final **enter/exit** decision without a labeled reasoning step. |
| `reasoning_router_route_choice_v1` | **Stub scenario only:** short narrative of **when** **local** reasoning suffices vs when **external / escalated** review is appropriate, consistent with constraints stated in the case (e.g. budget cap, missing DATA, high-stakes policy). Grader checks for **coherence** + **no** contradiction with `case_assumptions_v1`; optional machine check for vocabulary alignment (`local_only` / `external_review`-style language in free text **or** structured enum in `grading_v1`). |

**Explicit non-goals for v1:** Live order routing; chain-specific protocol quirks unless baked into `case_assumptions_v1`; full Pattern Game replay integration (optional **future** bridge); **replacing** `rm_preflight_wiring_v1` or **RM preflight** — quant exam certifies **FinQuant reasoning**, not server **parallel batch** health.

---

## 5. Normative case object schema (`finquant_quant_exam_v1`)

Trainer SHALL serialize cases as JSON objects in a top-level array or `{ "cases": [...] }` wrapper. Minimum fields:

```json
{
  "case_id": "FQ-Q-0001",
  "exam_schema": "finquant_quant_exam_v1",
  "exam_version": 1,
  "primary_category": "pnl_accounting",
  "secondary_tags": ["fees", "perp"],
  "difficulty": "easy",
  "prompt_markdown": "... full operator-visible prompt ...",
  "case_assumptions_v1": {
    "symbol": "SYNTH-PERP",
    "quote_ccy": "USDT",
    "fee_bps": 5,
    "funding_convention_v1": "long_pays_short_when_funding_positive",
    "margin_model_v1": "isolated_linear_simplified",
    "notes": "Any fixed numbers the grader must use."
  },
  "reference_facts_v1": {
    "bars": [],
    "indicator_values": {},
    "closed_trade": null
  },
  "expected_output_contract_v1": {
    "schema": "finquant_quant_exam_response_v1",
    "required_sections": ["Claim_reviewed", "Math_verdict", "Numeric_answer", "Leakage_check", "Policy_alignment", "DATA_or_assumption_gaps", "Final_status"],
    "final_status_enum": ["PASS", "FAIL", "INSUFFICIENT_DATA"]
  },
  "grading_v1": {
    "kind": "deterministic_jsonpath",
    "rules": [
      {
        "id": "numeric_delta_abs",
        "path": "$.numeric_answer",
        "expect_type": "number",
        "max_abs_error": 0.01
      }
    ],
    "notes": "Trainer may substitute regex, LLM-as-judge, or hybrid — must document grader_id in result bundle."
  }
}
```

**Architect rules:**

1. **`case_assumptions_v1`** MUST contain anything non-obvious (funding sign, margin model). Ambiguity is a **spec defect**, not a model failure.
2. **`reference_facts_v1`** SHOULD supply **ground truth** for indicators/PnL when `grading_v1.kind` is deterministic.
3. **`expected_output_contract_v1`** MAY be stricter than the legacy four-line verifier; quant exam responses SHOULD expose a **machine-readable `numeric_answer`** (number or null) when category demands it.
4. **`grading_v1`** is **trainer-wired** but MUST emit a **normalized result row** per §7.

---

## 6. Model / adapter I/O contract (normative minimum)

**Input:** UTF-8 string = `prompt_markdown` + optional system preamble fixed per run (trainer-defined; logged).

**Output:** UTF-8 string **parsable** into JSON matching `expected_output_contract_v1` **or** a **structured extraction** step (regex/JSON fence) defined by trainer. Architect recommendation: **require valid JSON** for quant exam v1 to avoid brittle parsing.

**Failure modes:**

- Unparseable output → **case FAIL** (infrastructure or model).
- Missing required section → **FAIL**.
- `Final_status: PASS` contradicted by numeric grader → **FAIL** (consistency check).

---

## 7. Pass gates and result bundle

**Per case result row (normative):**

```json
{
  "case_id": "FQ-Q-0001",
  "exam_schema": "finquant_quant_exam_v1",
  "exam_version": 1,
  "pass": true,
  "primary_category": "pnl_accounting",
  "grader_id": "deterministic_jsonpath_v1",
  "failure_codes": [],
  "latency_ms": 0,
  "raw_model_output_sha256": "...",
  "notes": ""
}
```

**Exam-level PASS:** `pass == true` for **all** cases where `grading_v1.required == true` (default **true** if key omitted).

**Category coverage PASS (recommended for “not placeholder”):** at least **one** `pass` case per **core** `primary_category` in §4 (through `no_trade_abstention`). **RM-extended certification:** add **one** `pass` per `rm_*` category when claiming **RM-integration-ready** FinQuant.

---

## 8. Alignment with trainer narrative (v0.4 → v0.5)

| Trainer statement | Architect stance |
|-------------------|------------------|
| “Verifier / reasoning exam passed” | Maps to **existing** `eval_finquant.py` — **retain**. |
| “Not quant-trained enough yet” | **Expected** until **quant exam** (this spec) passes. |
| “Add RSI/EMA/ATR, lookahead, PnL, …” | Maps 1:1 to §4 categories — **no optional interpretation**. |
| “Rerun same adapter; if fail, train v0.5 from failures” | **Supported**: failures export `case_id` + `failure_codes` + `raw_model_output_sha256` for curriculum mining. |

---

## 9. Governance

- **Change control:** Bump `exam_version` for any case or rule change; keep **frozen copies** of case packs used to certify a model tag.
- **Honesty:** Do not label a run “quant certified” if only the **verifier** exam passed.
- **RM honesty:** Do not label a model “**RM-aligned**” on quant skills alone — use **explicit** language: **“quant exam + RM integration battery”** or **`rm_*` categories PASS** per §4 / §7.
- **Black Box:** Quant exam success **does not** imply Student seam learning rows, Referee approval, **RM preflight PASS**, **reasoning trace completeness**, or Jupiter policy activation — those remain **separate** gates (`rm_preflight_wiring_v1`, `learning_trace_events_v1`, etc.).

---

## 10. Handoff checklist for trainer

- [ ] Populate case pack (minimum: **one case per core category** in §4 through `no_trade_abstention`).
- [ ] If targeting **Pattern Machine / RM integration**, add **§4 `rm_*`** cases and document that in the certification string.
- [ ] Pin `exam_version` and publish checksum of case file.
- [ ] Implement or extend grader (`grading_v1`) + result bundle (§7).
- [ ] Wire adapter I/O (§6); log `raw_model_output_sha256` per case.
- [ ] Document **operator-facing** one-line certification string (§3).
- [ ] Optional: mirror case file under `nde_factory/layout/finquant/eval/` or FinQuant runtime — **trainer choice**.

---

**Document owner:** Architect / Black Box product.  
**Last updated:** 2026-04-30 — **v1.1**: Reasoning Model (`GT_DIRECTIVE_028`) alignment, router/preflight/operator-surface references, `rm_*` exam categories.
