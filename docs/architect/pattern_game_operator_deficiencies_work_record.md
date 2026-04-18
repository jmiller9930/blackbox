# Pattern game & operator expectations — deficiencies work record

**Purpose of this document:** Capture **evidence-based gaps** between what the platform was engineered to do, what operators reasonably expected, and what we observe in code and behavior today. Each item is written so it can be **tracked, prioritized, and closed** without losing context.

**Audience:** Architect, operator, engineering.  
**Scope:** Pattern-game lab UI, Referee replay, “learning” claims, deploy/sync hygiene, and related operator surfaces unless noted otherwise.

**How to use:** Treat each **DEF-###** as a work item. Update the **Status** line when addressed (open / in progress / done + commit or proof).

---

## DEF-001 — Automatic learning from replay outcomes

| Field | Content |
|--------|--------|
| **Engineered purpose** | The Renaissance stack includes a **`LearningLedger`** and research paths to **record trade outcomes** and compute **aggregate metrics** during replay analysis. Parameter governance was intentionally kept **out of band** (manifests, humans, future optimizers). |
| **Expected operator outcome** | Language such as “learning,” “scorecard,” and “memory” often implies the **system improves its own policy** from batch runs (weights, fusion rules, or strategy parameters update from results). |
| **Observed now (evidence)** | `LearningLedger` documents that it **does not** tune strategy parameters, fusion weights, or execution geometry (`renaissance_v4/research/learning_ledger.py`). The Referee path is **deterministic replay** with fixed rules from manifest + engine (`renaissance_v4/game_theory/run_session_log.py`). Governance copy states that **“learning” requires changing inputs** and comparing differences, not automatic in-loop updates (`renaissance_v4/game_theory/anna_hard_rules.py`). Pattern-game core does not wire `LearningLedger` as an online learner. |
| **Requested remediation** | (1) **Rename and signpost** in UI and docs: e.g. “metrics ledger” vs “learning” where it means human iteration only. (2) **Single explicit disclaimer** on the pattern-game page: no in-band parameter learning unless a future feature is toggled on. (3) If product requires **true** learning later, specify a **separate initiative** (optimizer contract, scope, proof) rather than overloading current components. |
| **Status** | open |

---

## DEF-002 — UI metrics mistaken for “did the system learn?”

| Field | Content |
|--------|--------|
| **Engineered purpose** | Batch scorecard and panels expose **operational** and **Referee** statistics: timing, run completion, session WIN share, trade win rates, etc. |
| **Expected operator outcome** | High **Run OK %** or headline percentages are read as proof of **successful learning** or strategy validation. |
| **Observed now (evidence)** | **Run OK %** reflects **worker/job completion**, not edge or adaptation. Session and trade-win metrics describe **that replay’s paper statistics**, not an improving agent. UI copy was partially clarified (legend, columns, version badge); risk of misread remains if operators skip the legend. |
| **Requested remediation** | Keep **three-way distinction** visible by default (ops vs session vs trade-level). Add a **one-line “What this does not show”** near the scorecard. Optional: link to this work record or a short FAQ from the UI. |
| **Status** | partially addressed (copy + columns); verify in browser after each deploy |

---

## DEF-003 — Subsystem visibility (“is ML / memory / X actually on?”)

| Field | Content |
|--------|--------|
| **Engineered purpose** | Multiple optional paths exist: **Groundhog** merge, **retrospective** JSONL, **hunter** suggestions, **context bundles**, **data health**, fusion/signals under manifest control. |
| **Expected operator outcome** | A clear **health or status** view: which subsystems are **enabled**, **reachable**, and **used in the last run**—similar in spirit to deployment proof (version label). |
| **Observed now (evidence)** | Strips exist for some concerns (data, search space estimate, groundhog text), but there is **no unified, named module list** with consistent semantics (enabled vs active vs used). Operators infer from scattered hints and logs. |
| **Requested remediation** | Define a **v1 status model** (even JSON from `/api/...`): list **applications → modules** with state enum + short proof string. Surface the summary on the pattern-game page (`<details>` for detail). Align naming with DEF-001 so “ML” is not one ambiguous lamp. |
| **Status** | open |

---

## DEF-004 — Source-of-truth and deploy: code on disk vs process on port

| Field | Content |
|--------|--------|
| **Engineered purpose** | Lab workflow: **push → pull on host → restart** services that cache code (Flask reloads `web_app` on restart; not hot-reloaded on every request for all layers). |
| **Expected operator outcome** | After “sync,” the **browser** always reflects the **latest** HTML/JS and server behavior. |
| **Observed now (evidence)** | If the remote repo was **not pulled** to the commit that contains UI changes, or Flask was **not restarted**, the UI stays stale. Earlier state: clawbot lagged **origin** until pull; version header **`X-Pattern-Game-UI-Version`** and visible **v1.x** badge were added precisely to **prove** which bundle is live. |
| **Requested remediation** | **Standard command:** `./scripts/sync_pattern_game.sh` (or `python3 scripts/gsync.py --pattern-game`) from repo root so **stage game_theory paths (incl. untracked) → commit → push → remote pull → always restart Flask**. Operators verify with **badge**, **tab title**, or **`curl -sI … \| grep X-Pattern-Game-UI`**. Document in operator runbook; re-run after every UI change. |
| **Status** | addressed in tooling; discipline and verification remain operator responsibilities |

---

## DEF-005 — Git hygiene: untracked files never reached the server

| Field | Content |
|--------|--------|
| **Engineered purpose** | `gsync` auto-commit used **`git add -u`** (track changes to **already tracked** files only). |
| **Expected operator outcome** | New files under `renaissance_v4/game_theory/` are **included** in commits and appear on the remote after push. |
| **Observed now (evidence)** | **Untracked** files are **not** staged by `git add -u`, so commits could omit new modules; push then **cannot** deliver them. |
| **Requested remediation** | **`--pattern-game` mode** stages explicit paths (including `renaissance_v4/game_theory/`) before commit. Prefer **`sync_pattern_game.sh`** for pattern-game work. Default `gsync` behavior unchanged for other workflows; document the trap for game_theory contributors. |
| **Status** | addressed for pattern-game path; document for all contributors |

---

## DEF-006 — Parallelism UX (workers vs scenario count)

| Field | Content |
|--------|--------|
| **Engineered purpose** | **Worker count** is capped by **`min(slider, scenario count, host limit)`**; one scenario uses one process. |
| **Expected operator outcome** | Slider value **equals** parallel utilization; high slider always speeds up the **current** batch. |
| **Observed now (evidence)** | With **one scenario**, only **one** process runs; slider >1 does not speed up that batch. This is correct but **felt like a bug** without explanation. Copy and panels were added (effective parallelism, renamed banners). |
| **Requested remediation** | Keep the **parallelism panel** and short explanation **always visible** when N=1; optional tooltips on Search space line. User-test with fresh operator. |
| **Status** | largely addressed; monitor feedback |

---

## Closing note

None of the above is a moral failure of the build: the engine was largely designed for **deterministic evaluation** and **human-governed iteration**. The **deficiency** is mainly **expectation alignment** (language, UI, status) and **process** (git + restart proof). Close DEF items with **evidence** (commit hash, screenshot, API output), not with intent alone.

When adding **real** in-system learning in the future, add a **new DEF** with an explicit **acceptance test** so it cannot be confused with logging and replay.
