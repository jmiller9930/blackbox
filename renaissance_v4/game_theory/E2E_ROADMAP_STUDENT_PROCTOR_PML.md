# End-to-End Roadmap — Student & Proctor (PML / BLACKBOX)

**Version:** 3.0  
**Date:** 2026-04-20  
**Audience:** Architect, engineering, operators, external reviewers  
**Purpose:** **Binding** delivery bar for the Student–Proctor integration: **operator-demonstrable** learning loop with **strict runtime assertions**, **acceptance criteria**, and a **single proof bundle**. Aligns with `ARCHITECT_BRIEF_STUDENT_LOOP_EXTERNAL.md`, `ARCHITECTURE_PLAN_STUDENT_PROCTOR_PML.md`, `CONTEXT_LOG_PML_SYSTEM_AMENDMENT.md` (§12.x).

---

## 1. Non-negotiable delivery outcome (binding goal)

Implementation is **incomplete** until **all** criteria in §1–§6 are satisfied with **reproducible proof**.

### 1.1 Operator proof-of-work (binding)

The operator **must** be able to:

- **Run** from the **real UI entrypoint** (same path as production-style parallel batches).  
- **See** **Student → learning → outcome** as the **default** view (not buried behind engine-only surfaces).  
- **Execute** **Run A → Run B → Reset → Run C** (see §2, §3 AC-1b).  
- **Observe:**
  - **learning persisted**  
  - **retrieval applied**  
  - **behavior changed** (cross-run, Student-visible artifacts)  
  - **reset restored baseline** (cognitive reset for Student learning track)

If an operator **cannot** run the system and **clearly observe** learning, retrieval, change, and reset — **the system is not complete** (see §7).

---

## 2. Strict runtime assertions (NON-NEGOTIABLE)

| ID | Assertion |
|----|-----------|
| **SR-1 — Trades must exist** | Each proof run must produce **≥1 closed trade** (`replay_outcomes_json` length ≥ 1). **Deterministic gate:** `PYTHONPATH=. python3 scripts/verify_student_loop_sr1.py` must exit **0** with **no** manual DB/window/manifest edits — fixed DB + manifest + scenarios under `runtime/student_loop_lab_proof_v1/` (see README there). |
| **SR-2 — Cross-run difference** | Between **Run A** and **Run B**, at least one must differ among: **`student_output_fingerprint`**, **`confidence_01`**, **`pattern_recipe_ids`**, **`student_decision_ref`** (as exposed in API/audit for the **primary** trade shadow snapshot / seam audit). |
| **SR-3 — Reset equality** | **Run C** must **match Run A** on: **`student_output_fingerprint`**, **`pattern_recipe_ids`**, **`confidence_01`** (same fields as SR-2, baseline restoration after Student learning store reset). |
| **SR-4 — UI primary visibility** | **Student** panel must be **visible without scrolling** and must **render above** engine/DCR panels (primary surface hierarchy). |
| **SR-5 — Atomic proof bundle** | All artifacts must exist in **one folder**, tied to **one commit SHA**: `run_A.json`, `run_B.json`, `run_C.json`, **scorecard excerpt**, **`README.md`** (procedure + how to reproduce). |

---

## 3. Acceptance criteria

| ID | Criterion |
|----|-----------|
| **AC-1 — Execution seam** | Student pipeline runs **post-batch** (or architect-approved equivalent ordering); **Referee** outcomes **unchanged**; Student **no** execution authority. |
| **AC-1b — Unmocked lab proof (CRITICAL)** | Must use **real workers**, **real replay**, **real closed trades**. Must **demonstrate** **Run A → Run B → Reset → Run C** with SR-1–SR-5 satisfied. **Monkeypatched** parallel results **alone** are **not** sufficient for final closeout (see brief §12). |
| **AC-2 — Runtime cross-run proof** | Behavior change **visible in the real system** (not only isolated unit tests without lab parity). |
| **AC-3 — UI primary surface** | **Student triangle** is default; **engine/DCR** is **secondary** and **labeled**. |
| **AC-4 — Observability** | Completed batches expose at least: **`student_learning_rows_appended`**, **`student_retrieval_matches`**, **`student_output_fingerprint`**, **`shadow_student_enabled`** on **batch result JSON** and **scorecard** (and exported CSV when used). |
| **AC-5 — Truth separation** | Must **NOT**: confuse **DCR** with **Student learning**; imply **scorecard clear** clears **Student learning** unless explicitly implemented **and** labeled. |

---

## 4. Forward execution plan

| Order | Action |
|------:|--------|
| **1** | **SR-1 deterministic trades** — `scripts/verify_student_loop_sr1.py` (fixed DB + `sr1_deterministic_trade_proof_v1` manifest); `parallel_runner` exposes `replay_outcomes_json`. |
| **2** | **CLOSED — SR-5 proof bundle accepted.** Delivered: ``scripts/build_student_loop_sr5_proof_bundle.py`` → ``runtime/student_loop_lab_proof_v1/sr5_atomic_proof_bundle/`` (`run_A.json` … `run_C.json`, `scorecard_excerpt.json`, `README.md`, `COMMIT_SHA.txt`). Gates SR-1+SR-2+SR-3 in script. |
| **3** | **CLOSED — Step 3 accepted.** Operator API proof: **`scripts/verify_student_loop_step3_operator_path.py`**; fresh artifact e.g. `step3_operator_path_proof/step3_proof_fresh.json` — SR-2 / SR-3 / AC-2 on `POST /api/run-parallel` + store clear; **`PATTERN_GAME_STUDENT_LEARNING_STORE`** for isolation. |
| **4** | **CLOSED — Step 4 accepted.** Operator-visible UI proof (SR-4, AC-3): PNGs under `runtime/student_loop_lab_proof_v1/step4_ui_proof/` — `01_completed_run_student_viewport.png`, `02_student_above_terminal_fullpage.png`, `03_terminal_secondary_dcr_not_student_learning.png`, `04_scorecard_secondary_same_flow.png`. Custom scenario: `runtime/student_loop_lab_proof_v1/scenarios_sr1_deterministic.json`; no active uploaded strategy so per-row `manifest_path` preserved. |
| **5** | **CLOSED — Step 5 accepted.** AC-5 copy + tooltips in `web_app` (`PATTERN_GAME_WEB_UI_VERSION` **2.14.1**); HTML contract **`tests/test_pattern_game_ui_step5_truth_separation_copy.py`**. Directive 08 API tests unchanged. |
| **6** | **CLOSED — Step 6 accepted.** Operator runbook: **`runtime/student_loop_lab_proof_v1/README.md`** § *Step 6 — Operator runbook* — UI (Pattern Custom, SR-1 DB env, Run batch), AC-5 clear/reset table, optional Step 4 PNG path, `POST /api/run-parallel` body + manual Python snippet, pointers to `verify_student_loop_*.py` scripts. |
| **7** | **CLOSED — Architect sign-off recorded.** See **§10** (formal record). Covers **§1** (binding delivery outcome), **§1.1** (operator proof-of-work), and the **§1.1 Observe** list (including baseline restoration — acceptance request “§1.4” maps here; this roadmap does not define a separate §1.4). **§3** acceptance criteria cross-walk in §10. |

---

## 5. Rejection rule

The system is **rejected** if **any** of the following holds:

- **No trades** in proof runs (SR-1 fails).  
- **No** behavioral difference between A and B when retrieval should apply (SR-2 fails).  
- **Reset** does **not** restore baseline per SR-3.  
- **UI** is not primary for Student (SR-4 / AC-3 fail).  
- **Only** test-based proof exists — **no** atomic proof bundle / **no** unmocked lab path (AC-1b fails).

---

## 6. Final definition of DONE

The system is **complete** only when:

- **All** strict runtime assertions (**§2**) **pass**.  
- **All** acceptance criteria (**§3**) are **proven** with evidence.  
- **Proof bundle** is **reproducible** (§2 SR-5, §4 step 2).  
- **Architect** signs off (§4 step 7).

---

## 7. Final statement

If an operator **cannot** run the system and **clearly observe** **learning**, **retrieval**, **change**, and **reset** — the system is **not complete**.

---

## 8. Backward prerequisite summary (for planning only)

Foundation work (contracts **01**, context **02**, shadow **03**, reveal **04**, store **05**, retrieval **06**, cross-run tests **07**, truth separation **08**) and integration (**09** seam, **10** UI, **11** observability) are **necessary** but **not sufficient** until **§1–§6** above are satisfied. Detailed historical mapping lived in roadmap v2.0; **v2.1** is the **operator+lab proof contract**.

---

## 9. Revision history

| Version | Date | Notes |
|---------|------|--------|
| 1.0 | 2026-04-20 | Initial backward ladder + milestones. |
| 2.0 | 2026-04-20 | Binding BW table + AC-1b emphasis + F-plan. |
| **2.1** | **2026-04-20** | **Strict runtime assertions SR-1–SR-5**; operator Run A/B/Reset/C; **atomic proof bundle**; **rejection rule**; **definition of DONE**; final statement. |
| **2.2** | **2026-04-20** | **SR-1 strict:** deterministic DB + `sr1_deterministic_trade_proof_v1` manifest; `verify_student_loop_sr1.py` + `RENAISSANCE_V4_DB_PATH`. |
| **2.3** | **2026-04-20** | **Step 2 (SR-5):** `build_student_loop_sr5_proof_bundle.py`; atomic folder under `sr5_atomic_proof_bundle/`. |
| **2.4** | **2026-04-20** | **Step 2 closed — SR-5 accepted:** roadmap row §4 step 2 marked complete; proceed to §4 step 3. |
| **2.5** | **2026-04-20** | **Step 3:** `verify_student_loop_step3_operator_path.py` (blocking `/api/run-parallel`); `PATTERN_GAME_STUDENT_LEARNING_STORE` override in `default_student_learning_store_path_v1`. |
| **2.6** | **2026-04-20** | **Step 3 closed (accepted);** Step 4: SR-4 / AC-3 — Student primary, Terminal + scorecard secondary labels; UI version bump. |
| **2.7** | **2026-04-20** | **Step 4 closed (accepted):** operator UI proof PNGs in `step4_ui_proof/` (four files); SR-4 / AC-3 evidenced. |
| **2.8** | **2026-04-20** | **Step 5 closed (accepted):** AC-5 UI copy audit — scorecard “replay lane” vs Student, panel hint, button `title`s; Step 5 test file. |
| **2.9** | **2026-04-20** | **Step 6 closed (accepted):** operator runbook consolidated into `runtime/student_loop_lab_proof_v1/README.md` (Step 6 section). |
| **3.0** | **2026-04-20** | **Architect sign-off:** §10 added; §4 step 7 closed — **§1** / **§1.1** delivery bar + §3 AC cross-walk; roadmap **complete** per §6. |

---

## 10. Architect sign-off record

**Status:** **ACCEPTED** (2026-04-20)

**Scope (acceptance request):** Non-negotiable delivery outcome **§1**, operator proof-of-work **§1.1**, including Run **A → B → reset → C** and all **Observe** bullets under **§1.1** (learning persisted, retrieval applied, behavior changed, **reset restored baseline**).

**Note on “§1.4”:** This roadmap uses **§1.1** for operator proof-of-work; there is **no** separate **§1.4**. The requested acceptance maps to **§1.1** and especially the **fourth Observe bullet** (reset / baseline restoration).

**Evidence index (operator-reproducible):**

| Bar | Where proven |
|-----|----------------|
| SR-1 · trades | `scripts/verify_student_loop_sr1.py`; `runtime/student_loop_lab_proof_v1/README.md` |
| SR-2 / SR-3 / AC-2 | `scripts/verify_student_loop_step3_operator_path.py`; SR-5 bundle script + `sr5_atomic_proof_bundle/` |
| SR-4 / AC-3 | `step4_ui_proof/*.png`; `tests/test_pattern_game_ui_step4_hierarchy.py` |
| AC-5 | `tests/test_pattern_game_ui_step5_truth_separation_copy.py`; Directive 08 API tests |
| Runbook | `runtime/student_loop_lab_proof_v1/README.md` § Step 6 |

**§3 criteria:** Satisfied together with the strict assertions and rejection rule (§5); execution seam and AC-1b are covered by real replay + parallel API path + atomic bundle (not mocks-alone).

This record completes **§4 step 7** and satisfies **§6** (definition of DONE) for this roadmap revision.
