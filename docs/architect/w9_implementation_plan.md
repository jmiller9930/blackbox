# W9 — Implementation plan (memory-driven lessons — MVP slice)

**Status:** **Active track** (per Agentic Training Advisor direction, 2026-04).  
**Parent contract:** [`context_memory_contract_w8.md`](context_memory_contract_w8.md).  
**As-built baseline:** [`context_engine_as_built.md`](context_engine_as_built.md).

---

## 1. Objective (MVP)

Deliver the **minimum** end-to-end capability that satisfies W8 intent:

1. **Structured lesson memory** — records that are **not** raw ledger rows or unbounded carryforward bullets.  
2. **Similarity-based retrieval** — **better than exact-match Q&A**; MVP uses **scored situation match** (symbol / regime / timeframe / tags) with **near-match** rules.  
3. **Operational injection** — retrieved lessons merge into the analyst **FACT layer** (or explicit advisory sublayer) so the **LLM path** sees them.  
4. **Bounded relevance** — caps, thresholds, validation gate.  
5. **Tests + proof artifacts** — pytest scenarios T1–T5 subset and **prompt snapshot** hooks for audit.

**Explicit non-goals for MVP:** full embedding index across all history; automatic lesson mining from every `paper_trades.jsonl` row without validation; production vector DB requirement.

---

## 2. Proposed MVP slice (phased inside W9)

### Slice W9a — Schema + CRUD (foundation)

| Item | Detail |
|------|--------|
| **New SQLite table** | `anna_lesson_memory` (name TBD in migration): `id`, `created_at`, `updated_at`, `lesson_text` (required), `symbol`, `regime_tag`, `timeframe`, `outcome_class`, `context_tags` (JSON or comma list), `source` (`rca` \| `operator` \| `gate` \| `derived`), `validation_status` (`candidate` \| `validated` \| `promoted`), `situation_summary` (short text for display), optional link `paper_trade_id` / `request_id`. |
| **Migration** | New file `data/sqlite/schema_phase4_anna_lessons.sql`; `ensure_schema` in `_db.py` loads it after existing files (append to tuple order). |
| **Module** | `scripts/runtime/anna_modules/lesson_memory.py` — `upsert_lesson`, `retrieve_lessons_for_situation`, scoring. |
| **CLI / admin** | Minimal: `anna lesson-add` / JSON import **or** seed from tests only in first merge (operator CLI can follow). |

### Slice W9b — Similarity (non-exact)

| Item | Detail |
|------|--------|
| **Situation vector** | Built from `build_analysis` inputs: `extract_slots` on `input_text`, `infer_regime_from_phase5_market` when tick present, optional symbol normalization (`SOL` ↔ `SOL-PERP`). |
| **Scoring** | Integer score: exact symbol +3, regime +2, timeframe +1, tag overlap +1 each (cap); **near symbol** +1 (normalized family). **Threshold:** `ANNA_LESSON_MIN_SCORE` (default e.g. 3). **Top-K:** `ANNA_LESSON_MAX_INJECT` (default 3). |
| **Fallback** | If no row ≥ threshold → **no injection** (T3 no-memory). |

*Future W9c:* optional embedding column + cosine for fuzzy text match; **not** blocking MVP.

### Slice W9c — Injection into analysis

| Item | Detail |
|------|--------|
| **Hook** | In `build_analysis`, **after** carryforward merge, **before** `resolve_answer_layers`: merge layer `lesson_memory` with `facts_for_prompt` lines: `FACT (lesson memory): …` only for `validation_status >= validated` (configurable). |
| **Transparency** | Add `analysis["lesson_memory"] = { "injected": [...], "scores": [...] }` for dashboard/API. |
| **Kill switch** | `ANNA_LESSON_MEMORY=0` disables retrieval (default **1** when Advisor wants it on — **recommend default 0 until first validated lessons exist**, then flip to 1 in lab). |

### Slice W9d — Validation & proof

| Item | Detail |
|------|--------|
| **Tests** | `tests/test_anna_lesson_memory.py` — in-memory or temp SQLite: seed lessons, assert retrieval order/score, assert injection into merged facts, assert no injection when below threshold. |
| **Scenarios** | Map Advisor T1–T5 to: (1) two lessons same bucket, (2) near-match symbol, (3) empty table, (4) restart DB file, (5) many rows only top-K. |
| **Artifacts** | Test logs or `--dump-prompt` debug flag on harness (optional follow-up). |

---

## 3. Code areas that will change

| Area | Change |
|------|--------|
| `data/sqlite/schema_phase4_anna_lessons.sql` | **New** |
| `scripts/runtime/_db.py` | Include new schema file in `ensure_schema` |
| `scripts/runtime/anna_modules/lesson_memory.py` | **New** — retrieval + store |
| `scripts/runtime/anna_modules/analysis.py` | Call lesson retrieval + merge layer; export `lesson_memory` in output |
| `scripts/runtime/anna_modules/pipeline.py` | No change if facts flow through `rule_facts`; else ensure snippets see lesson lines |
| `modules/anna_training/regime_signal.py` | Reuse `infer_regime_from_phase5_market` (already imported in analysis) |
| `tests/test_anna_lesson_memory.py` | **New** |
| `docs/architect/context_memory_contract_w8.md` | Update §8 compliance when slices land |

---

## 4. Test plan & proof artifacts

| ID | Scenario | Proof |
|----|----------|--------|
| T1 | Known pattern | Seed 2 lessons in bucket A; situation A → both retrieved in prompt facts |
| T2 | Near-match | Seed lesson symbol SOL-PERP; query SOL → score ≥ threshold → retrieved |
| T3 | No memory | Empty table → `lesson_memory.injected` empty; no FACT lines |
| T4 | Persistence | SQLite file persists; re-run retrieve after new connection |
| T5 | Noise cap | Seed 10 lessons; only top-K + threshold appear |

**Artifacts:** pytest output; optional JSON fixture `tests/fixtures/lesson_memory_proof.json` with before/after `facts_for_prompt` slice.

---

## 5. Safety & bounded rollout

| Constraint | Rationale |
|------------|-----------|
| **Default `ANNA_LESSON_MEMORY=0`** until operator seeds **validated** lessons | Avoid injecting empty/candidate noise in production |
| **Only `validated` or `promoted` rows inject** (env to relax for dev) | Fail-closed on lesson quality |
| **Hard cap K** and **min score** | Bounded context |
| **No auto-ingest from full ledger in MVP** | Lessons created via explicit API/CLI/test — **reduces** spurious patterns |
| **Human review path** for `candidate → validated` | Aligns with governance; can be CLI in W9a follow-up |
| **Separate table from `anna_context_memory`** | Preserves exact-match Q&A path; lessons are **situation-scoped** |

---

## 6. Ordering (suggested merge sequence)

1. Schema + `lesson_memory.py` + unit tests (retrieve/score only).  
2. `build_analysis` integration + analysis output field.  
3. CLI or seed path for real lessons on clawbot.  
4. Flip default env in lab after smoke.  
5. Update W8 §8 compliance table.

---

## 7. Open decisions (Architect / Advisor)

- **Default env:** `ANNA_LESSON_MEMORY=0` vs `1` at first merge (Engineering recommends **0** until data exists).  
- **Validation workflow:** who promotes `candidate` → `validated` (operator-only vs automated after N ticks).  
- **Timeline:** calendar dates — **not** set in-repo; track in project plan.

---

## 8. Validation rules (locked for W9a — do not drift)

| Status | Injectable? | Meaning |
|--------|-------------|---------|
| **`candidate`** | **No** | Stored for review; **never** merged into FACT layer by retrieval. |
| **`validated`** | **Yes** (if score ≥ threshold) | Human/operator-approved for training use. |
| **`promoted`** | **Yes** (if score ≥ threshold) | Highest trust; same injection path as validated. |

Only **`validated`** and **`promoted`** participate in `retrieve_lessons_for_situation`.  
Promotion API: `update_validation_status(conn, lesson_id, "validated")` (or CLI in a later slice).

---

## 9. W9a delivered (checkpoint)

| Item | Location |
|------|----------|
| Schema | `data/sqlite/schema_phase4_anna_lessons.sql` |
| Loader | `scripts/runtime/_db.py` (schema file order) |
| Module | `scripts/runtime/anna_modules/lesson_memory.py` |
| Tests | `tests/test_anna_lesson_memory.py` (5 passed) |

**Proof:** pytest demonstrates candidate exclusion, validated retrieval, near-symbol scoring, empty table, top-K cap. **FACT snapshot:** `build_lesson_memory_fact_lines` output (used in tests). **W9b–d:** follow-on slices per plan.

---

## 10. W9b / W9c delivered (checkpoint)

| Item | Location |
|------|----------|
| **`build_analysis` wiring** | `scripts/runtime/anna_modules/analysis.py` — after strategy/regime FACT merge, before `resolve_answer_layers` |
| **Env** | `ANNA_LESSON_MEMORY_ENABLED=1` to inject; default **off** |
| **Debug** | `ANNA_LESSON_MEMORY_DEBUG=1` — full `authoritative_facts_all` on `lesson_memory` payload |
| **Output** | `anna_analysis_v1.lesson_memory`, `pipeline.lesson_memory` |
| **E2E tests** | `tests/test_anna_lesson_memory_e2e.py` (side-by-side on/off) |
| **Advisor proof doc** | `docs/working/w9bc_checkpoint_proof.md` |

**W9d (remaining):** broader CI, optional prompt dump CLI, RCA → lesson promotion path — as needed.

---

*Engineering — W9 plan. W9a–c checkpoints complete.*
