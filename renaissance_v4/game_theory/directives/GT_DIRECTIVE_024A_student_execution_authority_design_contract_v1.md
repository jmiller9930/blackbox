# GT_DIRECTIVE_024A — Student execution authority design contract (challenge first)

**Status:** design-only — **no** `run_manifest_replay` behavior change in this deliverable.  
**Parent:** `GT_DIRECTIVE_024_series_student_execution_authority_v1.md`  
**Audience:** Engineering, Product, Referee, Data, UI

**One-line summary:** Prove, from the code, how to move the Student from shadow observer to execution authority without breaking baseline determinism or corrupting scorecard semantics—before writing any replay code.

---

## 1) Current execution truth (proved from code)

### Call graph (parallel Run Exam, operator learning harness)

1. **Worker** — `renaissance_v4/game_theory/parallel_runner.py` — `_worker_run_one`  
   - For `operator_recipe_id` in `OPERATOR_LEARNING_HARNESS_RECIPE_IDS`, calls `run_operator_test_harness_v1` and builds **`out` from `control_replay`**, not from candidate-winner replay:

```188:231:renaissance_v4/game_theory/parallel_runner.py
                hres = run_operator_test_harness_v1(
                    prep.replay_path,
                    ...
                )
            ...
            search_raw = hres["context_candidate_search_raw"]
            proof = search_raw["context_candidate_search_proof"]
            control_replay = search_raw["control_replay"]
            ...
            out = {
                **control_replay,
                "context_candidate_search_proof": proof,
                "manifest_effective": control_replay.get("manifest"),
                "binary_scorecard": score_binary_outcomes(list(control_replay.get("outcomes") or [])),
                ...
            }
```

2. **Harness** — `renaissance_v4/game_theory/operator_test_harness_v1.py` — `run_operator_test_harness_v1`  
   - Calls `run_context_candidate_search_v1` and takes **`control_replay`** from the search result:

```195:217:renaissance_v4/game_theory/operator_test_harness_v1.py
    search_out = run_context_candidate_search_v1(
        mp,
        control_apply=control_apply,
        ...
    )
    proof = search_out["context_candidate_search_proof"]
    control_replay = search_out["control_replay"]
```

3. **Per replay** — `renaissance_v4/game_theory/context_candidate_search.py` — `_replay_with_apply_dict`  
   - Optional `apply_memory_bundle_to_manifest`, then **`run_manifest_replay`** on a temp JSON manifest:

```404:451:renaissance_v4/game_theory/context_candidate_search.py
def _replay_with_apply_dict(
    manifest_path: Path,
    apply_block: dict[str, Any],
    ...
) -> dict[str, Any]:
    from renaissance_v4.research.replay_runner import run_manifest_replay
    ...
        return run_manifest_replay(
            Path(tmp),
            emit_baseline_artifacts=False,
            verbose=False,
            ...
        )
```

4. **Inner loop** — `renaissance_v4/research/replay_runner.py` — `run_manifest_replay`  
   - Builds `exec_manager` from manifest; each bar: signals → `fusion_result` → `risk_decision` → `exec_manager.open_trade` / exits.

### Where trades are “decided” (scored path)

- **Entry** when flat, `risk_decision.allowed`, and `fusion_result.direction` is `long` or `short` — `exec_manager.open_trade(..., direction=fusion_result.direction, ...)`:

```623:645:renaissance_v4/research/replay_runner.py
        flat = exec_manager.current_trade is None or not exec_manager.current_trade.open
        ...
        if (
            flat
            and risk_decision.allowed
            and fusion_result.direction in {"long", "short"}
        ):
            exec_manager.open_trade(
                ...
                direction=fusion_result.direction,
                ...
            )
```

- **Fusion / risk** are manifest-driven; there is no `student_output_v1` in this loop.

### Where `student_output_v1` is produced

- **After** the batch: `renaissance_v4/game_theory/student_proctor/student_proctor_operator_runtime_v1.py` — `student_loop_seam_after_parallel_batch_v1` walks `replay_outcomes_json` and emits Student output (stub / Ollama) per trade—**not** before worker replay:

```251:264:renaissance_v4/game_theory/student_proctor/student_proctor_operator_runtime_v1.py
def student_loop_seam_after_parallel_batch_v1(
    *,
    results: list[dict[str, Any]],
    run_id: str,
    ...
) -> dict[str, Any]:
    """
    For each successful scenario row with ``replay_outcomes_json``, process each trade.
```

- Stub contract: `renaissance_v4/game_theory/student_proctor/shadow_student_v1.py` — `emit_shadow_stub_student_output_v1` is **shadow-only** (no replay import; not order authority) — file header in repo.

### One-line verdict

**Confirmed:** for the **parallel operator-harness** path, **Referee control replay** owns the trades that end up in `out` / `replay_outcomes_json` for the worker row; **Student** is **post-hoc** to that execution for scoring/audit purposes → **Student is shadow-only for *scored execution* today** (does not call `open_trade`).

---

## 2) Candidate injection points (evaluate — no code)

### A. Replay hook (post-fusion / pre-`open_trade`)

| Pros | Cons / risks |
|------|----------------|
| Single choke point; can gate **entry** on Student intent in principle | **Highest blast radius** in `run_manifest_replay`: touches DCR, `signal_behavior_proof_v1`, drill rings, and **per-bar** semantics |
| | Student intent is currently produced **per trade / seam**; fusion loop is **per bar**—requires **time alignment** and **no double-entry** rules |
| | Hard to keep **baseline** and **Student** in one run without forking state machines |

**Determinism impact:** any change to order of gating or `open_trade` conditions changes `validation_checksum` (`replay_runner.py` ~909–914) unless strictly lane-scoped and separately checksum’d.

### B. Apply / candidate lane (Student as a **separate** replay)

| Pros | Cons / risks |
|------|----------------|
| **Already the pattern** for “another replay” — `run_context_candidate_search_v1` runs `control_replay` then **candidate** replays with `c["apply_effective"]` (see `context_candidate_search.py` ~557–597) | Parallel batch **does not** score candidate replay today; **policy** must add a **second scored row** for Student (or replace nothing on control) |
| Keeps `run_manifest_replay` **defaults** for baseline when Student lane = off | Need a **legal** mapping: `student_execution_intent_v1` → **manifest-allowed** `apply` **or** a new cataloged apply shape |
| Clear place to tag `execution_authority_v1` | Must not relabel **recall** as **Student** |

**Determinism impact:** a **separate** invocation of `run_manifest_replay` for Student lane with `emit_baseline_artifacts=False` and **lane-specific** digest preserves **control** path bit-for-bit when inputs unchanged.

### C. Other surfaces

- **Harness selection** (`parallel_runner` / `run_operator_test_harness_v1`): add `student_replay` dict alongside `control_replay` in the result — **orchestration**, still needs B or A underneath.
- **Execution manager / new policy object**: possible for live-like hooks; **larger** surface than 024A should commit without 024B schema.

### Recommendation (design)

**B — Use an explicit Student-controlled replay as a second lane** (orchestrated from harness / batch), implemented via **existing** `_replay_with_apply_dict` + **new** apply contract and/or a **dedicated** “student lane” replay entry, **not** by silently replacing `control_replay`.  
**A (narrow post-fusion hook)** is a **contingency** only if 024B/024C prove that **no** safe manifest-legal apply can express Student entry/no-trade, or if per-bar override is a hard product requirement.  
**C (larger refactor)** triggers if: intent cannot be mapped without breaking catalog validation, or if a single process must interleave two authorities without two replays (anti-pattern for proof).

**Final answer letter: B** — *Existing apply / separate replay lane is the correct primary path*; A is fallback; C if mapping or proof fails.

---

## 3) Execution contract — `student_execution_intent_v1` (definition only, no wiring)

**Purpose:** A **sealed, validated** object that **replay (or an adapter)** may consume. Not identical to `student_output_v1` (thesis can be rich); intent is **execution-scoped**.

### Fields (required shape)

| Field | Type / notes |
|-------|----------------|
| `schema` | `student_execution_intent_v1` |
| `schema_version` | int |
| `source_student_output_digest_v1` | hex digest of sealed `student_output_v1` (or `source_student_output_id` if store assigns ids) |
| `job_id` | run id |
| `fingerprint` | per GT015 / MCI / operator audit rules |
| `scenario_id` | scenario row id |
| `trade_id` or `graded_unit_id` | one closed-trade / decision window anchor as chosen in 024B |
| `action` | `enter_long` \| `enter_short` \| `no_trade` |
| `direction` | `long` \| `short` \| `flat` — must be **consistent** with `action` |
| `confidence_01` | [0, 1] |
| `confidence_band` | e.g. low / medium / high (aligned with `contracts_v1`) |
| `invalidation_text` | string |
| `supporting_indicators`, `conflicting_indicators` | `list[str]` |
| `context_fit` | string |
| `created_at_utc` | ISO-8601 Z |
| `intent_digest_v1` | **deterministic** SHA-256 over canonical JSON of semantic fields (exclude timestamps if dual-run compare requires) — policy in 024B |

### Validation rules (summary)

- `action` / `direction` / `no_trade` invariants: e.g. `no_trade` → no entry; `enter_long` ↔ `long`; `enter_short` ↔ `short`; `flat` only with `no_trade` where specified.
- LLM profile: require full thesis **before** intent emission (per existing `THESIS_*` rules).
- **Determinism:** same `student_output_v1` bytes → same `intent_digest_v1` (and stable `source_*` digest).

### Map (or not) to `DecisionContract` / `exec_manager`

- **`renaissance_v4/core/decision_contract.py` — `DecisionContract`** is the **per-cycle** object (decision_id, symbol, direction, execution_allowed, …) used in replay-style flows — **not** the same as intent today; 024B should define an **adapter** (even if not implemented in 024A): e.g. “intent at bar T maps to `execution_allowed` + direction override for **Student lane** only.”
- **`exec_manager.open_trade`**: today takes **long/short** from `fusion_result` — direct mapping from `student_execution_intent_v1` only **if** a hook (path A) or a **synthetic** fusion/risk result is produced. **Path B** avoids faking `DecisionContract` if apply blocks can steer manifest/risk to match intent; otherwise adapter + lane-scoped open path in a **forked** execution path (→ tends toward C).

**024A defers the adapter implementation to 024B/C.**

---

## 4) Execution lanes and authority (explicit)

| Value | Meaning |
|-------|--------|
| `execution_lane_v1` | `baseline_control` — current scored worker path (`**control_replay` fold). |
| | `student_controlled` — replay whose **outcomes** are attributed to **Student** when intent is **consumed** (024C). |
| | `recall_biased` — same physical replay path as today when **DCR / fusion bias** is on (`run_manifest_replay` kwargs) — must stay taggable. |
| `execution_authority_v1` | `manifest` — fusion/risk/execution as today. |
| | `student_thesis` — execution driven by `student_execution_intent_v1` (after validation). |
| | `recall_bias` — memory / recall nudging fusion; **not** `student_thesis`. |

**Rules**

- **Baseline** remains default: **unchanged** `control_replay` scoring when Student lane is off.
- **Student** lane: **separate** outcomes blob and hashes; **never** merge into `baseline_control` row without explicit `execution_lane_v1` on the scorecard.
- **Recall-biased** must keep **distinct** `execution_authority_v1=recall_bias` (or a sub-tag) so L1 does not conflate with Student.

---

## 5) Scorecard and L1/L2/L3 separation (proposed fields — no implementation)

Proposed (additive; exact names in 024D):

- `execution_lane_v1`, `execution_authority_v1`
- `student_execution_intent_digest_v1`
- `outcomes_hash_v1` (per lane)
- `control_replay_outcomes_hash_v1` (optional echo for A/B)
- `student_replay_outcomes_hash_v1` (when Student lane present)
- `l1_e_value_source_v1` / `l1_p_value_source_v1` — must encode **which lane** the scalar refers to (convention: suffix or embedded object)

**UI:** never show a single E/tr or exam E without **which lane**; comparison tables group by `execution_authority_v1` + `execution_lane_v1` (per 024D).

---

## 6) Trace proof requirements (LangGraph alignment)

Minimal **runtime** events (to be emitted in 024C/024E, names stable):

- `student_execution_intent_created`
- `student_execution_intent_consumed`
- `student_controlled_replay_started`
- `student_controlled_replay_completed`
- `referee_used_student_output` — `true` \| `false` \| `unknown` (true only if Referee path **consumed** intent for the **scored** Student lane)

**`evidence_provenance_v1` (per node):** each graph node that claims execution truth must list among `trace_store` / `scorecard` / `recall` / `unknown` as today; after 024E, **Student authority** requires **`trace_store` +** consumption event ids / digests (detailed in 024E).

---

## 7) Determinism and proof

- **Baseline `validation_checksum`:** `replay_runner.py` builds `vchk` from `validation_checksum(summary, exec_manager.cumulative_pnl, len(ledger.outcomes))` (~909–914). **Unchanged** when Student lane = off and `run_manifest_replay` inputs = today’s control path.
- **Student lane:** either **separate** checksum for `student_replay` dict, or `outcomes_hash_v1` + **lane tag** in scorecard; **do not** reuse baseline checksum for a different `outcomes` list.
- **Tests:** golden **control** row checksum / outcome count invariants; new tests for “Student lane on” that **assert** `control_replay` row unchanged when run in same job with dual-lane; regression suite for DCR (recall) vs Student tags.

---

## 8) Minimal viable path (phased; names only)

| Phase | Name |
|-------|------|
| 024B | `student_execution_intent_v1` schema + validation + digest tests |
| 024C | Student replay lane in harness/parallel; trace events; no scorecard L1 change yet (or dual-write behind flag) |
| 024D | Scorecard + L1/L2/L3 field separation; UI grouping |
| 024E | Learning-loop trace verdicts; coupling node; fingerprint compare by lane |

**Blast radius:** 024C touches harness/parallel; **highest** — feature flag / env kill-switch for Student lane.  
**Rollback:** disable Student lane (env); scorecard reverts to **single** `baseline_control` metrics; no overwrite of history rows.

---

## Non-negotiables (re-stated)

- **Do not** change default `run_manifest_replay` behavior in 024A.  
- **Do not** mix Student outcomes into baseline metrics.  
- **Do not** infer authority in trace — **proven** or **UNKNOWN** / `referee_used_student_output=unknown` until events exist.

---

## Required final answer (single letter)

**B. Existing apply / candidate (separate Student replay) lane is the correct primary path** — with 024B intent schema and 024C harness/batch policy to score a **separate** `student_controlled` replay.  
**A** (hook inside `run_manifest_replay`) is **not** the first choice — reserved if B is infeasible.  
**C** applies if intent cannot be expressed safely or proof cannot be separated without a broader execution refactor.

---

## Done condition (024A)

- [x] Code-cited truth for current path and Student seam.  
- [x] Options A/B/C evaluated; **B** recommended with A/C as contingencies.  
- [x] `student_execution_intent_v1` sketched; mapping to `DecisionContract` / `exec_manager` **explicitly deferred** to 024B/C.  
- [x] Lanes, scorecard, trace, determinism, phases, rollback **named**.  
- [x] **No** replay implementation in this file.

**Next:** 024B — `student_execution_intent_v1` validation + tests only (per series document).
