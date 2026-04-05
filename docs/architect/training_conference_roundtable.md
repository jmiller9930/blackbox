# Training conference — roundtable record

**Purpose:** Single record of **Agentic Training Advisor ↔ Engineering** on Anna **training governance**, **v1 semantics**, **context/memory**, and related **implementation** — roster, agreements, work, deliverables, and a **standardized exchange log**.

**Maintenance:** On each new Advisor memo or Engineering response, **append one row** to **§6 Exchange log** using the **exact fields** below. **Rewrite §4.1** when memory/control-plane scope changes. Cursor: `.cursor/rules/training-conference-roundtable.mdc`.

---

## 1 — Document map (always this order)

| § | Section |
|---|---------|
| 1 | Document map (this table) |
| 2 | Session roster |
| 3 | Agreed positions (locked or recommended) |
| 4 | Work tracker (ID, owner, status, date) |
| 4.1 | **Rolling summary** — memory & control plane (**update in place**; see below) |
| 5 | Accomplishments (shipped artifacts) |
| 6 | **Exchange log** (canonical conversation — **append only**) |
| 7 | Related paths & pointers |

---

## 2 — Session roster

| Role | Party | Part in the roundtable |
|------|--------|-------------------------|
| **Training Architect** | Human / governance authority | PASS **meaning**, trust, risk, v1 scope; **Confirmed** on contract. |
| **Agentic Training Advisor** | Advisory prompts | Memos: criteria, learning loop, evidence, v1 lock, context engine, confirmations. |
| **Engineering (BLACK BOX)** | Codebase / implementation | As-built truth; recommendations; UI/API when directed. |
| **Operator / lab** | Runtime | Deploy, flush, Karpathy — referenced in ops, not a formal seat. |

*Official legal/product sign-off may live outside this repo.*

---

## 3 — Agreed positions (v1 contract — Option A)

*Recommended by Engineering; Architect **Confirmed** is external to repo.*

| Topic | Position |
|-------|----------|
| **PASS** | **Provisional qualification** — thresholds on **current** ledger at evaluation time; **not** durable across regimes/time. |
| **Promotion** | **Qualified method** — not universal “approved everywhere.” |
| **After PASS** | **No automatic** execution/method preference change (unless policy added). |
| **Degradation** | **Manual review** in v1 — no default auto-demotion in gates. |
| **Improvement** | **Operator / directive / config / code** — primary in v1. |
| **Naming** | Do not sell gate PASS as durable **“skill”** without lifecycle contract. |
| **Data vs semantics** | **No hard reset** for wording; **soft reset** = reporting baseline only. |

---

## 4 — Work tracker

| ID | Work item | Owner | Status | As of |
|----|-----------|-------|--------|--------|
| W1 | Architect **Confirmed** on v1 semantics (or edits) | Architect | Pending external | 2026-04 |
| W2 | Product + API match v1 (`v1_governance_contract`, labels) | Engineering | **Done** | 2026-04 |
| W3 | Advisor artifact (before/after, verification) | Engineering | **Done** | `docs/working/v1_governance_contract_advisor.md` |
| W4 | Optional **alerts-only** (drift/review; no auto-demote) | Eng + Architect | Not implemented | — |
| W5 | Statistical gates (Wilson, regimes, probation) | TBD | Not in v1 UI scope | — |
| W6 | RCA schema / actionable learning loop | Architect | Not implemented | — |
| W7 | **This roundtable** maintained per §6 | Engineering | Ongoing | — |
| W8 | **Context & Memory Contract** (memory-driven; doc + compliance) | Architect + Eng | **Draft published** — [`context_memory_contract_w8.md`](context_memory_contract_w8.md); §8 = gap | 2026-04 |
| W9 | **Implement** W8 (lesson memory, similarity, injection, tests) | Engineering | **Shipped** — W9a–c + behavioral proof + **runtime control plane** (see §4.1, §5) | 2026-04 |
| W10 | **Clawbot remote operational proof** (runtime UI/API, pyth-stream, wallet truth, sequential learning RUNNING, Anna/ledger evidence) | Engineering + Operator | **Open** — partial proof on clawbot; acceptance bar not fully met (see Round 024) | 2026-04 |

---

## 4.1 — Rolling summary (memory & control plane — update in place)

**Purpose:** One place to see **current** training-memory scope without re-reading the exchange log. **Rewrite this subsection** when milestones land; do **not** append here (log stays in §6).

| Topic | Status (as of last edit) |
|-------|---------------------------|
| **Lesson memory (W9)** | SQLite `anna_lesson_memory`, similarity retrieval, validated/promoted-only FACT injection into `build_analysis`, bounded K/min score. |
| **Behavioral impact** | Deterministic `behavior_effect` → `suggested_action` / proposal path; tests in `test_anna_lesson_memory_behavior.py`; proof §7 in `w9bc_checkpoint_proof.md`. |
| **Control-plane engagement** | **Runtime:** `memory_control_plane.py` — signals (`detect_problem_signals`), mode (`select_engagement_mode`), retrieval overrides (`effective_retrieval_params`); integrated in `analysis.py`; output `anna_analysis_v1.memory_control_plane`. Default `ANNA_LESSON_MEMORY_CONTROL_PLANE` on when unset; `=0` restores baseline-only retrieval math. |
| **Tests** | `test_memory_control_plane.py` + existing W9 lesson tests. |
| **Design / gap history** | [`problem_aware_lesson_memory_control_plane.md`](problem_aware_lesson_memory_control_plane.md) (directive + implementation table). |
| **Open** | Per phase: Foreman log / clawbot proof if required by `execution_context.md`. |
| **Risk review (R019)** | Tier 1: operator lesson lifecycle + heuristic CP + similarity = **assistive**; improve via **targeted** tuning and richer situation data—not Tier 2 “adaptation” without contract. |
| **Tier 1 lesson lifecycle** | **Accepted & track closed (R021).** Definition unchanged from R020: operator `candidate` → human `validated` → optional `promoted`; injection **validated/promoted only**; assistive memory; no autonomous learning. **Clarifications:** `promoted` vs `validated` = **governance only** in Tier 1 (same code path); minimum bar = **training plan**, not code enforcement; lesson quality = **training/process** ownership. **Next:** Tier 1 completion validation → Tier 2 transition planning (separate). |
| **Tier 1 final validation (R022)** | **Behavior-focused closure memo** — Engineering: deterministic + gate + ledger paths **test-backed**; LLM path **not** strictly deterministic; live production proof = **operator / primary host** per project standards. |
| **Tier 1 script adherence (R023)** | **Controlled `anna_analysis_v1` proof** — [`docs/working/tier1_behavioral_validation_proof.json`](../working/tier1_behavioral_validation_proof.json) (`ANNA_USE_LLM=0`, memory off). |
| **Clawbot remote runtime (W10)** | **Partially met** — `main` synced on clawbot; `pyth-stream` stable (Hermes probe); Pyth API `healthy`; context engine `healthy`; `market_ticks` advancing; host `anna_training_cli.py loop-daemon` running; execution DB has historical `paper` / `paper_stub` trades and `decision_traces`. **Gaps:** API wallet disconnected (no keypair path in container env); sequential learning API **`idle`** (not started with calibration/events); UI control-plane artifact `runtime_state` **not_connected** / ledger **not_wired** vs live processes; Jupiter quote from API container fails (DNS); dashboard bundle `trade_chain` empty in sampled response. Operator: `.secrets` keypair + `UIUX.Web/.env`, recreate `api`; optional network/DNS for Jupiter; POST sequential **start** + **tick** with valid paths. |

---

## 5 — Accomplishments (shipped)

| Deliverable | Location |
|-------------|----------|
| v1 governance JSON + dashboard labels | `UIUX.Web/api_server.py` (`V1_GOVERNANCE_CONTRACT`, digest + scorecard) |
| Advisor handoff (v1 semantics) | `docs/working/v1_governance_contract_advisor.md` |
| Context engine as-built | `docs/architect/context_engine_as_built.md` |
| **W8 contract (draft) + gap analysis** | `docs/architect/context_memory_contract_w8.md` |
| **W9 implementation plan (MVP slice)** | `docs/architect/w9_implementation_plan.md` |
| **W9b/c proof package** | `docs/working/w9bc_checkpoint_proof.md` |
| **W9 behavioral proof** (outcomes vs wording) | `tests/test_anna_lesson_memory_behavior.py`; `policy.apply_lesson_memory_to_suggested_action` |
| **Control-plane memory engagement (runtime)** | `scripts/runtime/anna_modules/memory_control_plane.py`; wired in `analysis.py`; `tests/test_memory_control_plane.py`; [`problem_aware_lesson_memory_control_plane.md`](problem_aware_lesson_memory_control_plane.md) |
| **Tier 1 lesson lifecycle (governance)** | This file — **§4.1** (rolling) + **§6 Round 020** (exchange log); operator `candidate` → human `validated` → optional human `promoted`; no autonomous promotion |
| Roundtable + update rule | This file; `.cursor/rules/training-conference-roundtable.mdc` |

**Deploy:** Restart API after pull for UI/API changes.

---

## 6 — Exchange log (canonical format)

**Rules**

- **Append** new rounds only (do not rewrite history unless correcting factual errors).
- Each round uses **one row** in the table below with **all columns filled** (use `—` if N/A).
- **Round** = monotonic integer (001, 002, …).

**Columns**

| Column | Meaning |
|--------|---------|
| **Round** | Sequential id |
| **Date** | ISO `YYYY-MM-DD` (approximate ok: `YYYY-MM`) |
| **From** | `Advisor` \| `Engineering` \| `User` \| `Advisor+Eng` |
| **Topic** | Short title |
| **Summary** | What was asked or stated (1–3 sentences) |
| **Outcome / artifacts** | Decisions, doc paths, code paths, W# updated |
| **Status** | `open` \| `closed` \| `deferred` \| `info-only` |

---

### Exchange log (table)

| Round | Date | From | Topic | Summary | Outcome / artifacts | Status |
|-------|------|------|-------|---------|---------------------|--------|
| 001 | 2026-04 | Advisor | Training alignment (promotion, evidence, failure handling, anti-gaming) | Series of memos mapping criteria vs implementation. | Engineering mapped to `gates.py`; gaps named; memo path to Architect. | closed |
| 002 | 2026-04 | Advisor | Learning loop (NOT PASS, RCA, exploration, memory) | Whether learning is enforced vs operator-only. | Evaluation-first v1; RCA habit not full schema; `carryforward` as-built. | closed |
| 003 | 2026-04 | Advisor | Evidence strength, regimes, probation, drawdown, fragile passes | Statistical / lifecycle gates beyond point WR+N. | Not default in code; architect decisions for future; no code change in thread. | info-only |
| 004 | 2026-04 | Advisor | RCA contract, adaptation triggers, exploration | Where logic lives; autonomous vs guided. | Policy-heavy; engineering: operator/harness/agent boundaries documented. | closed |
| 005 | 2026-04 | Advisor | v1 scope (evaluation vs guided vs autonomous) | Single operating model for v1. | Recommend evaluation-first + operator learning. | closed |
| 006 | 2026-04 | Advisor | PASS meaning (capability vs condition), promotion semantics, naming | Trust and durability. | Option A provisional; QUALIFIED wording; repeated confirmation memos. | closed |
| 007 | 2026-04 | User | Implement v1 semantics in product + artifacts + roundtable | Match UI/API to contract; soft vs hard reset; persistent log. | **W2, W3 done**; `V1_GOVERNANCE_CONTRACT`; `v1_governance_contract_advisor.md`; this doc + rule. | closed |
| 008 | 2026-04 | Advisor | Context engine & memory (full as-built) | Eight-part system explanation request. | **`docs/architect/context_engine_as_built.md`**; **W8** opened. | closed |
| 009 | 2026-04 | User | Reformat roundtable to standard tracking format | Adhere to implemented conversation format. | This §6 table + §1 map; prior bullets merged into Rounds 001–009. | closed |
| 010 | 2026-04 | Engineering | Context engine contract memo — **formal reply to Architect / Advisor** | Same eight-part request; official answer package for governance. | Memo below + `context_engine_as_built.md` (authoritative detail). | closed |
| 011 | 2026-04 | Advisor | **W8 enforcement** — memory-driven contract (doc + code + tests mandatory) | Requires similarity retrieval, structured lessons, separation history/memory/ops, proof artifacts. | **`context_memory_contract_w8.md`** — **gap identified** (§8); **W9** opened; not compliant as-built. | closed |
| 012 | 2026-04 | Advisor | **W9 in-scope now** — not optional; core training capability | Direction: implement minimum memory-driven behavior; W9 = active track. | **`w9_implementation_plan.md`** — MVP slice, code areas, tests, safety; W9 status → active. | closed |
| 013 | 2026-04 | Engineering | **W9a checkpoint** — schema + `lesson_memory` + tests | Sliced delivery; validation rules explicit (`candidate` never injects). | Schema `schema_phase4_anna_lessons.sql`, `lesson_memory.py`, 5 pytest green; plan §8–9 updated. | closed |
| 014 | 2026-04 | Advisor | **W9b/W9c** — wire memory into `build_analysis`; E2E proof | On vs off; FACT injection; prompt snapshot; `anna_analysis_v1` fields. | `analysis.py` wiring; `test_anna_lesson_memory_e2e.py`; `w9bc_checkpoint_proof.md`; plan §10. | closed |
| 015 | 2026-04 | Advisor | **W9 behavioral acceptance** — memory must change outcomes, not only wording | Controlled on/off; trade/proposal-relevant deltas required. | `test_anna_lesson_memory_behavior.py`; `LESSON_BEHAVIOR_TIGHTEN_SUGGESTED` + `apply_lesson_memory_to_suggested_action`; `w9bc_checkpoint_proof.md` §7. | closed |
| 016 | 2026-04 | Architect | **Gap: problem-aware engagement** — as-built vs intent | Engagement was env+path, not risk/confidence/conflict-modulated. | Engineering gap response; [`problem_aware_lesson_memory_control_plane.md`](problem_aware_lesson_memory_control_plane.md) (gap + options). | closed |
| 017 | 2026-04 | Architect | **Directive: control-plane code implementation** | Runtime layer required — signals, modes, retrieval, `anna_analysis_v1` visibility. | `memory_control_plane.py`; `analysis.py` integration; `lesson_memory`/`policy` hooks; `test_memory_control_plane.py`; design doc implementation §. | closed |
| 018 | 2026-04 | Architect | **Verification — proof of implementation** | Code + runtime + tests, not design-only. | Pytest evidence; `build_analysis` JSON excerpts (`memory_control_plane`); behavioral comparison baseline vs problem-state. | closed |
| 019 | 2026-04 | Architect | **Context engine — risk review & forward alignment** (Tier 1 / Tier 2) | Supply chain, heuristics, similarity vs recognition, engagement, effect scope, tier boundaries; no scope expansion request. | Engineering assessment: operator-governed lesson lifecycle default; heuristics sufficient for Tier 1 with telemetry-led tuning; similarity MVP appropriate; targeted improvements path; Tier 1 = assistive only. See reply in thread / this round. | closed |
| 020 | 2026-04 | Architect | **Tier 1 — lesson lifecycle locked (operational)** | Creation / validation / promotion / minimum usable set; no Tier 2 automation; gap is process not code. | Engineering definition: operator creates `candidate` → human validates → optional human `promoted`; minimum bar by phase in training plan; implementation gaps = no mandatory UI queue, `validated`≡`promoted` for injection. **Canonical:** Round 020 summary in this row + Engineering memo. | closed |
| 021 | 2026-04 | Architect | **Acceptance — Tier 1 lesson lifecycle** | Lock and close track; clarifications on promoted vs validated (governance only), minimum bar in training plan, ownership = training/process. | **Accepted as written.** No additional code for Tier 1 lifecycle; no automation of validation/promotion; no Tier 2 expansion from this track. **Next:** Tier 1 completion validation → Tier 2 transition planning. **Track closed.** | closed |
| 022 | 2026-04 | Architect | **Tier 1 closure — final validation** (behavior) | Script, signals, `anna_analysis_v1`, ledger, gates, determinism; proof where applicable. | Engineering response: deterministic paths + gates + ledger logic **substantiated** by automated tests; LLM-on path **not** strictly deterministic; production primary-host proof **out of scope** for this memo. See Round 022 Engineering reply. | closed |
| 023 | 2026-04 | Architect | **Tier 1 — behavioral validation (script adherence)** | Controlled scenarios: input, expected, full `anna_analysis_v1`, pass/fail; no metrics-only closure. | **`docs/working/tier1_behavioral_validation_proof.json`** — `build_analysis`, `ANNA_USE_LLM=0`, lesson memory off; scenarios S1–S6; duplicate-input determinism verified separately. | closed |
| 024 | 2026-04-05 | Engineering | **W10 — Clawbot-only operationalization** (Git sync, pyth-stream, wallet, sequential, Anna/learning proof) | Architect directive: prove system on **clawbot** only; no local-only proof; fix unhealthy services; truthful wallet; RUNNING sequential + trade-and-train evidence. | **Shipped:** `scripts/trading/pyth_stream_probe.py` (fixes `pyth-stream` crash — missing script); `UIUX.Web/docker-compose.yml` env passthrough (`KEYPAIR_PATH`, `BLACKBOX_SOLANA_KEYPAIR_PATH`, `SOLANA_RPC_URL`, `BLACKBOX_LIVE_TRADING_BLOCKED`, `BLACKBOX_EXECUTION_LEDGER_PATH`); `modules/wallet/solana_wallet.py` governance flag; `scripts/runtime/operational_readiness_clawbot.sh`. **Clawbot verified (SSH):** `main` @ `7fd7cd90bd9dda4062589617317fb8b9a705c796`; containers Up; Pyth `healthy`; sequential API **`idle`**; wallet **`wallet_connected: false`** (no keypair in container); `runtime/status` **not_connected**; Anna host process running; DB counts non-zero historically. **Not accepted** vs full directive until wallet wired, sequential **running**, unified dashboard proof. **W10** open. | open |

---

*Last updated: 2026-04-05 — Round 024; W10 clawbot operational proof (partial).*

---

## 7 — Related paths

| Path | What |
|------|------|
| `docs/working/v1_governance_contract_advisor.md` | v1 UI/API implementation proof |
| `docs/architect/context_engine_as_built.md` | Context & memory as-built |
| `docs/architect/context_memory_contract_w8.md` | **W8** — memory-driven contract, gap, phased plan |
| `docs/architect/w9_implementation_plan.md` | **W9** — MVP slices, files to change, tests, safety |
| `docs/working/w9bc_checkpoint_proof.md` | W9b/c + behavioral checkpoint proof |
| `docs/architect/problem_aware_lesson_memory_control_plane.md` | Control-plane directive + implementation pointers |
| **This file — §4.1 + §6 R020–021** | **Tier 1 lesson lifecycle** (definition R020; **acceptance / track closure** R021) |
| **This file — §6 R024, W10** | **Clawbot operational proof** — partial status, gaps, commit pointers |
| `scripts/trading/pyth_stream_probe.py` | Hermes Pyth poller for `docs/working/artifacts/pyth_stream_*.json` (docker `pyth-stream`) |
| `scripts/runtime/operational_readiness_clawbot.sh` | Remote curl + compose checks (run on clawbot after pull) |
| `scripts/runtime/anna_modules/memory_control_plane.py` | Problem signals → mode → retrieval (runtime) |
| `modules/anna_training/gates.py` | Grade-12 gate evaluation |
| `.cursor/rules/training-conference-roundtable.mdc` | Reminder to append §6 |
