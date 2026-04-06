# Anna Goes to School

**Status:** Canonical training + University-lite contract for Anna (trading college). **12th grade** and **Karpathy loop v1** are **locked** to code in `modules/anna_training/catalog.py` — see §1.2. **State schema** `anna_training_state_v3` adds **`grade_12_tool_mastery`** (four curriculum tools — see §1.5). **Karpathy skill engine + loop daemon — Python deps, env, and operator prerequisites:** §1.6.

**Purpose:** Capture the practical BLACK BOX training model for Anna as a single-college student agent inside the core engine, with the minimum structure needed to preserve curriculum quality, context quality, exam-board governance, and human graduation authority.

**Operator controls (implemented):** assign curriculum, invoke the first training method, append notes — all **CLI**; state on disk (gitignored). **Grade-12 gate** = **(A) four curriculum tools attested as a cohesive set** + **(B) numeric paper cohort** (min decisive trades + win-rate floor — default 60%). See §1.3–1.5.

**Preflight is mandatory:** every training CLI command (except `check-readiness`) runs the same data-source gate as Anna’s analyst path — healthy Pyth stream artifact + non-empty `data/sqlite/market_data.db`. Optional: `ANNA_PREFLIGHT_REQUIRE_SOLANA=1` to also require Solana RPC. Tests/dev only: `ANNA_SKIP_PREFLIGHT=1`.

```bash
# repo root — single entry (readiness JSON + gates JSON + start); optional: --once
# Lab host: scripts/anna_training_launch_server.sh --once runs school then starts the long-running Karpathy loop daemon (same method; ANNA_TRAINING_LAUNCH_DAEMON=0 for school-only).
python3 scripts/runtime/anna_go_to_school.py
# equivalent: python3 scripts/runtime/anna_training_cli.py school
# preflight + Grade 12 + Karpathy only (no readiness/gates print first):
python3 scripts/runtime/anna_training_cli.py start
# repo root — preflight only (JSON)
python3 scripts/runtime/anna_training_cli.py check-readiness
python3 scripts/runtime/anna_training_cli.py gates   # PASS/FAIL: curriculum tools + numeric cohort (see §1.5)
python3 scripts/runtime/anna_training_cli.py tool-list    # JSON: four Grade-12 tools + passed flags
python3 scripts/runtime/anna_training_cli.py tool-pass math_engine_literacy   # operator attestation after evidence
python3 scripts/runtime/anna_training_cli.py status   # JSON includes grade_12_progress percentages
python3 scripts/runtime/anna_training_cli.py watch       # report card once; add --live for refresh until Ctrl+C
python3 scripts/runtime/anna_training_cli.py curricula
python3 scripts/runtime/anna_training_cli.py assign-curriculum grade_12_paper_only
python3 scripts/runtime/anna_training_cli.py invoke-method karpathy_loop_v1
python3 scripts/runtime/anna_training_cli.py note "Your note — visible in status tail"
# Paper outcomes → grade-12 report card (markdown for Sean)
python3 scripts/runtime/anna_training_cli.py log-trade --symbol SOL-PERP --side long --result won --pnl-usd 10 --timeframe 5m
python3 scripts/runtime/anna_training_cli.py dashboard
python3 scripts/runtime/anna_training_cli.py report-card --out docs/working/anna_grade12_report_card.md --recipient Sean
```

- State file: `data/runtime/anna_training/state.json` (override with `BLACKBOX_ANNA_TRAINING_DIR` — point this at another filesystem if you want report card + JSONL off the OS volume; artifacts are small unless you log at extreme volume).
- Code: `modules/anna_training/` (including `curriculum_tools.py`, `gates.py`, `report_card_text.py`), `scripts/runtime/anna_training_cli.py`.

**CEO / stakeholder one-pager:** [`anna_grade12_executive_summary_ceo.md`](anna_grade12_executive_summary_ceo.md) — math engine, analysis stack, RCS/RCA, harness loop, rework summary, current posture.

**Primary strategy-learning evidence (2026 — sequential MAE + SPRT):** Governance and engineering are aligning **operator proof** with **paired outcomes, MAE v1, SPRT (PROMOTE/KILL/CONTINUE), and manifests** in `modules/anna_training/sequential_engine/` — so “is the experiment earning promotion?” is **not** reduced to a **single cohort win rate** or **paper return %** alone (those can remain **indicators**). **End-to-end learning path (code-grounded, includes MAE/SPRT as one stage only):** **[`learning_primary_metric_change_process.md`](learning_primary_metric_change_process.md)** — learning overview + gaps + metric-migration appendix. Until `gates.py` and dashboards are fully migrated, **Grade-12 `evaluate_grade12_gates`** may still apply the **legacy numeric cohort** (e.g. configurable win-rate floor); do not treat docs and code as divergent without a coordinated change per that doc’s appendix.

**Full University methodology matrix (RAG, bandits, CMDP, Bayesian optimization, walk-forward, etc.):** [`anna_university_methodology.md`](anna_university_methodology.md) — primary training **method id** in code remains `karpathy_loop_v1`; the matrix is **design canon**, phased per roadmap. Staging subtree (when present): `university/README.md`, `university/docs/METHODS_NOTES.md`.

**Related roadmap:** `docs/architect/development_plan.md` §5.8 (University / learning system). This file + CLI are the live operator surface for the first slice; University docs above are authoritative for the broader method stack.

## 1. Working reduction for BLACK BOX

BLACK BOX is not standing up the full multi-college University first.

The near-term build is a focused University-lite path inside BLACK BOX with:

- one college only: `trading`
- one student reference path first: `Anna`
- one retained independent evaluator: `exam_board`
- one retained degree ladder: `Bachelor -> Master -> PhD`
- one retained graduation authority model: exam board recommends, humans graduate

This keeps the important University mechanics without forcing the entire standalone University platform to ship first.

### 1.1 “12th grade” = paper trading only (operator mapping)

**12th grade** (trading college) means **paper / simulation harness only** — **no live venue** (no Jack/Billy production submits) until humans and policy move Anna past that gate. In code this is curriculum id **`grade_12_paper_only`**. The **first** invoked training method is **`karpathy_loop_v1`** (the loop in §3 below), assigned via `anna_training_cli.py`.

### 1.1.1 Paper trading — definition (binding) vs rows in `paper_trades.jsonl`

**Paper trading** (the thing we mean when we say Anna is “trading paper”) is **the same code path as live trading** through analysis, gating, and **execution request** — the **only** deliberate difference is **settlement**: real capital movement and live venue submit are **not** performed; a **paper / sim adapter** (or governed notional accounting) produces fills and P&amp;L instead. Everything upstream (market context, request shape, audit) should match live **except** that money step. After the fact, a venue may return **less** fill and microstructure detail for paper/sim than for a live fill; that does not change the “same path until settlement” rule. **At placement time**, the stack **should** capture what the adapter can see — at minimum optional **bid**, **ask**, and **spread** (or a linked **market snapshot** id) on the paper row when available (`anna log-trade --bid … --ask …` or Jack `paper_trade` JSON). It must still be **grounded** and **traceable** (e.g. request id, snapshot id), or it is not a defensible claim about skill.

The file **`paper_trades.jsonl`** is an **append-only ledger**. Rows may come from:

- **Market-grounded paper** — Jack / paper loop / adapter output tied to real context (the normal meaning of “paper trading”).
- **Operator `log-trade`** — human-attested outcomes; governance decides whether that counts toward skill claims.

If a row is not market-grounded, **do not** treat it as proof that Anna “beat the market.”

### 1.1.2 Execution layers — baseline (Sean) vs strategy layer (Anna / Tier 2) vs governance

**Verbiage — trade policy vs hooks (aligned):**

- **Trade policy** means **which venue’s rules and integration** apply for settlement (where money and orders actually bind). That is a **policy / routing** choice (`VenueId`), not an informal label.
- **Billy** is the **hook** (executor agent) into the **Drift** trade policy (historical — **not** active).
- **Jack** is the **hook** (executor agent) into the **Jupiter Perps** trade policy.

**trading_core** and **Sean’s trading logic** (the TypeScript snapshot: signals, sizing, trails, gates, order shapes) are **rules / strategy mechanics** preserved as a **reference implementation**. They are **not** themselves “the trade policy”; they are written to run **under** whatever venue policy is selected. In operator posture today there is **only one active trade policy: Jupiter Perps** (Jack). **Drift** is **not** a live second policy — deprecated, not in service (see below). Legacy code may still mention two `VenueId` values; **planning and proof** should assume **Jupiter-only** unless governance re-opens another venue.

Same pattern: **policy names the venue economics**; **the named executor is the only supported hook** for that policy in the registry model.

#### 1.1.2.1 Drift (venue) — deprecated; not in service

**Operator posture (2026):** **Drift is deprecated** for BLACK BOX. The historical TypeScript snapshot (`trading_core/src/bot/drift_trading_bot_source.ts`) and older “Billy → Drift” bring-up notes are **not** an active live venue path — **Drift is not in service**. Do not plan work, proof, or operations around submitting orders through Drift. Training and measurement use **canonical market data** (e.g. `market_bars_5m`, Pyth-backed ingest) and **Python/paper** execution and ledger paths; any replacement venue or executor is chosen **outside** this deprecated snapshot. **Legacy numbered bullets** elsewhere in this file that name **Billy + Drift** as the v1 market path describe **historical intent**, not the current venue.

**Directive model (2026-04):** The platform is described in three layers; **code may not yet implement all of them end-to-end** — see Engineering responses to the Training Architect for gaps.

| Layer | Role | Live trades? | Notes |
|--------|------|--------------|--------|
| **Baseline (Sean’s Jupiter policy)** | **Sean’s rules = Jupiter trade policy.** Python **baseline ledger bridge** (default ``BASELINE_LEDGER_SIGNAL_MODE=sean_jupiter_v1``) matches **``trading_core``** signal math (``aggregateCandles`` + ``rsi``, same constants); **no row** without a signal. Catalog id ``jupiter_supertrend_ema_rsi_atr_v1``; legacy mechanical long: ``BASELINE_LEDGER_SIGNAL_MODE=legacy_mechanical_long``. **Jupiter only** — do not conflate with deprecated venue paths (see §1.1.2.1). | **No** live venue (paper measurement) | Separate from Anna **sideline** strategies. |
| **Strategy layer (Anna / Tier 2)** | Multiple **paper/sim** strategies (variants, experiments) **may** run against the same market data **without** live settlement. | **No** | Tagging, parallel cohorts, and dashboard filtering are **partially** implemented — see `strategy_label`, `strategy_catalog.json`, `paper_trades.jsonl`. |
| **Governance** | No autonomous promotion of experimental strategies to live. | — | Human approval + evidence; **not** auto-promote in code. |

**Tier 1 vs Tier 2 (terminology):** **Tier 1** = baseline execution + **script adherence** / analyst contract (Anna’s rule-following layer). **Tier 2** = **strategy experimentation** (conjunctive / multi-strategy learning) **on paper** until policy promotes — distinct from Tier 1 closure.

**Data flow (high level):** Market data → analysis / harness → **paper** outcome rows in `paper_trades.jsonl` (training judgment). **Live** baseline bot logging is **not** the same artifact — see Engineering memo on trade visibility.

**Parallel execution ledger (identity):** `data/sqlite/execution_ledger.db` (gitignored) stores **`execution_trades`** with full identity: `strategy_id`, `lane` (`baseline`|`anna`), `mode` (`live`|`paper`|`paper_stub`), `market_event_id`, entry/exit; **PnL** for `live`/`paper` is **derived** from price × size × side (not free-form). **`paper_stub`** = synthetic Anna rows (no asserted dollar P&amp;L in column). Multiple rows per `market_event_id` are **required** (baseline vs many Anna strategies). CLI: `anna_training_cli.py log-execution-trade`. Karpathy loop appends Anna parallel stub rows when canonical bars exist (`parallel_strategies_last` in state/heartbeat). **Event-centric UI/API framework (chart + strategies + context, wiring checklist):** [`event_market_training_view_framework.md`](event_market_training_view_framework.md).

**Void prior evidence — reset to zero:** Ledger rows, PnL columns, trade exports, and dashboard aggregates that were produced **before** the current **Jupiter policy / mechanism contract** (or under deprecated paths, wrong signal modes, or known-bad harness behavior) must **not** be treated as proof of performance or used for governance decisions. They are **invalid for that purpose**. To **delete that persisted data** and return training + ledger surfaces to a clean slate: **stop** the Karpathy loop (and any supervisor), then from repo root run:

`python3 scripts/runtime/anna_training_cli.py flush-runtime --yes`

That wipes **all files** under the Anna training directory (`BLACKBOX_ANNA_TRAINING_DIR`), **removes** the execution ledger SQLite file at `BLACKBOX_EXECUTION_LEDGER_PATH` or the default `data/sqlite/execution_ledger.db` (including `-wal`/`-shm`/`-journal` sidecars), optionally clears `data/runtime/execution_plane/requests.json` (unless `--keep-execution-plane`), and writes a fresh `state.json`. **`flush-runtime` does not destroy live market data:** canonical bar/tick stores (e.g. `BLACKBOX_MARKET_DATA_PATH` / `data/sqlite/market_data.db` and siblings), **Pyth** / Hermes probe artifacts under `docs/working/artifacts/pyth_stream_*.json`, and other persisted **ingest or feed history** the lab has been collecting — those stay on disk unless you delete them separately. The reset targets **training + execution-ledger evidence**, not the market tape. Restart daemons/API after.

### 1.2 Contract lock (12th grade + Karpathy loop — binding)

- **Curriculum id (canonical):** `grade_12_paper_only` — defined in `modules/anna_training/catalog.py` (`CURRICULA`).
- **Training method id (canonical):** `karpathy_loop_v1` — defined in `modules/anna_training/catalog.py` (`TRAINING_METHODS`).
- **Loop steps (canonical):** §3 below — **seven** numbered steps. The same seven strings appear in code in `karpathy_loop_v1["steps"]`. Any change to wording or order **must** update **both** this document and `catalog.py` in one change.
- **Reflection / RCA / strategy latitude:** §3.2–3.3 (and RCS shape in §3.3) are **part of Anna’s operating contract** for this track; automation may be phased, but semantics are not optional for “what Anna is supposed to do.”
- **Operator surface:** `scripts/runtime/anna_training_cli.py` (assign curriculum, invoke method, notes, paper trade log, dashboard, report-card, `check-readiness`, `gates`).

### 1.2.1 Binary curriculum predicates (Grade-12 bar — binding)

At this level, **every** Grade-12 curriculum requirement that the software enforces **must** be expressible as a **boolean predicate** (true/false only). There is **no** “partial mastery” state that counts as overall **PASS**: the **headline gate** is **PASS** iff **all** required predicates are true, else **NOT PASS**.

- **Gates** (`evaluate_grade12_gates`): **curriculum_tools_pass**, **numeric_gate_pass**, and overall **pass** are booleans; blockers explain which predicate failed.
- **Tool checklist** (`grade_12_tool_mastery`): each tool id is **True** or **False** — not a scalar grade.
- **Skill practice** (`karpathy_skill_engine`): each practice attempt returns **passed** true/false only; **`ANNA_KARPATHY_AUTO_ATTEST_TOOLS`** (default **on**) may set a tool to **True** when its **education_benchmark** predicate passes — set **`0`** to disable; still binary, no partial grade.
- **Learning headline** (report card / Slack): **PASS** vs **NOT PASS** aligned to the gate; diagnostics may list which binary legs are false — they are **not** a separate “in progress” grade.

Human / exam-board judgment above the software minimum remains as in §1.3; this subsection binds **what the code may claim** as satisfied.

### 1.3 12th grade graduation — sequencing, numeric gate, and human authority

**Sequencing (binding, read with §1.2.1):** Every skill defined for Grade 12 in **`curriculum_tools.py`** is **sequential** — **fixed order**, **one active focus at a time**, **each stage builds on the last** (later skills assume the earlier ones are in play: honest numeracy → disciplined analysis → reflection / thesis↔outcome → sustained harness loop). **Paper trading** in the sense of the **numeric cohort gate** (logged paper outcomes scored for min-N and win rate) is **not** where the curriculum starts; it is the **capstone** after those four learning outcomes are attested. Until then, paper rows may exist for harness work, but the **headline “paper trade” graduation metric** is **deferred** in product and gates until the sequential skills are complete.

**She cannot graduate 12th grade until all of the following are satisfied:**

1. **Curriculum tool checklist (cohesive set, code-enforced, sequential focus)** — Here a **“tool”** is **not** a random feature toggle: each id is a **named learning outcome or process** Anna must **learn and apply** (math literacy, analysis discipline, RCS/RCA, Karpathy harness practice). The **deck and gates surface one current focus at a time** in canonical **`curriculum_tools.py` order** — complete the first missing skill before treating the next as the active requirement; **do not skip ahead**. Each tool carries an **`education_benchmark`** in **`curriculum_tools.py`** (JSON also in **`anna tool-list`**): a **defined, testable predicate** for Grade-12 automation (e.g. **math engine literacy** = all **`WILSON_NIST_CASES`** pass float-vs-Decimal Wilson oracle via **`run_wilson_reference_check`** / **`anna math-check`**). Before the **numeric** slice is admissible for overall **PASS**, all **four** must be **passed**. **Default (education track):** the Karpathy loop **auto-attests** when the benchmark passes (`ANNA_KARPATHY_AUTO_ATTEST_TOOLS` defaults **on**; set `0` for manual-only). **Manual override:** `anna tool-pass <id>` when policy requires human sign-off. They map to the contract as follows:
   - **`math_engine_literacy`** — FACT-grounded numeracy; epistemic honesty; Wilson/NIST-style checks when claiming numbers (ties to math engine + analyst pipeline).
   - **`analysis_algorithms`** — quant stack and analysis path: separate noise from signal in the harness (metrics, pedagogy, procedures in code).
   - **`rcs_rca_discipline`** — **RCS** on outcomes; **RCA** when policy/gates say so (see §3.3 — same DNA, checklist makes it visible before headline metrics).
   - **`karpathy_harness_loop`** — paper harness: propose → test → measure → keep/drop → repeat (canonical **Karpathy** steps in `catalog.py`).
   The long-running **loop daemon** advances **iteration** and **heartbeats**; **checklist** progress is **not** those heartbeats. **By default** **`ANNA_KARPATHY_AUTO_ATTEST_TOOLS`** is **on**: when **skill practice** for the deck’s current focus **passes** the tool’s **education_benchmark**, the checklist may flip **without** a separate SSH `tool-pass`. Disable with **`ANNA_KARPATHY_AUTO_ATTEST_TOOLS=0`** if you require manual attestation only.
   **Internalized knowledge (software):** On **`save_state`**, one-time hooks run (see `modules/anna_training/internalized_knowledge.py`): (a) when all **four** tools are **passed**, **`grade_12_knowledge_internalized`** + carryforward FACT lines + log **`grade_12_knowledge_internalized_v1`**; (b) when the **overall** Grade-12 **gate** is **PASS** (tools + paper numeric cohort), **`grade_12_trading_knowledge_internalized`** + carryforward FACT + log **`grade_12_trading_knowledge_internalized_v1`**. These merge into Anna’s analyst path as **`facts_for_prompt`** (cumulative learning) — **always on** when state loads; she does **not** need to ask for them; they are part of the same **memory context** stack as other carryforward bullets.
2. **Prior learning requirements (human judgment)** — **Demonstrated competent competency** in the skills the contract requires: **§3.3** **`RCS`/`RCA`**, **Karpathy** practice in paper, **traceable** thesis ↔ outcome, and carry-forward behaviors in §3.3–3.4 (operator / exam board judge “competent,” not only logs). The **tool checklist** is the **minimum bar encoded in software**; exam-board judgment can still apply above that.
3. **Numeric cohort gate** — After (1) is satisfied, the program’s **60%** standard (configurable) on **decisive** paper trades (won+lost), with a **minimum decisive trade count**, as implemented by **`python3 scripts/runtime/anna_training_cli.py gates`** (`ANNA_GRADE12_MIN_WIN_RATE`, `ANNA_GRADE12_MIN_DECISIVE_TRADES`). **Win rate alone** does not substitute for the tool checklist; **tools without numeric** does not satisfy overall **PASS**.

**Report card (TUI):** `anna watch` / `anna watch --live` shows the same signal as **`gates`** plus tool table, **measurable progress** (tool checklist %, paper numeric track %, combined average, bottleneck), and **Slack** `#report_card` uses the same plaintext formatter (`modules/anna_training/report_card_text.py`). Per-tool **Checklist %** is **0%** until **passed** (benchmark auto-attest or `tool-pass`), **100%** after — not a vague “learning %” from idle ticks alone.

**Graduation act:** Formal **12th grade** completion is **not** automatic. It runs under **manual review** — **exam board recommends**, **humans graduate** — however your governance packet is written. The CLI can print **PASS/FAIL** for `gates`; it does not issue a diploma.

**Tests/dev only:** `ANNA_SKIP_CURRICULUM_TOOLS_GATE=1` bypasses the tool checklist (numeric gate only) — **not** for production claims.

### 1.4 Implementation reference (code ↔ contract)

| Concern | Module / entry |
|--------|----------------|
| Four tool ids, titles, summaries | `modules/anna_training/curriculum_tools.py` |
| Gate evaluation (tools + numeric, blockers) | `modules/anna_training/gates.py` |
| Slack + TUI shared progress text | `modules/anna_training/report_card_text.py` |
| State defaults + schema v3 | `modules/anna_training/catalog.py` |
| Next focus, bachelor eligibility | `modules/anna_training/progression.py` |
| Operator CLI | `scripts/runtime/anna_training_cli.py`, `bin/anna` |
| Slack `#report_card` | `scripts/runtime/telegram_interface/data_status.py` → `format_anna_training_report_hashtag_text` |
| Karpathy skill practice (binary predicates per tool) | `modules/anna_training/karpathy_skill_engine.py` |
| Long-running Karpathy loop (ticks, deck, practice, logs) | `scripts/runtime/anna_karpathy_loop_daemon.py`; launcher: `scripts/anna_training_launch_server.sh` |
| Grade-12 skills + trading gate → internalized knowledge (carryforward FACT; analyst merge) | `modules/anna_training/internalized_knowledge.py` (`apply_internalization_hooks` from `save_state`) |

### 1.5 Fund assignment, growth objectives, math bar, algorithms (binding spec)

**Assigned notional fund, explicit growth goals, statistical competence expectation, and the meaning of “algorithm”** (trading vs governance) are **contract-locked** in:

- [`anna_fund_objectives_and_algorithms_contract.md`](anna_fund_objectives_and_algorithms_contract.md)

That document **supersedes unstated assumptions** (e.g. “she’s a math expert,” “there’s a $1k→$10k goal,” “winning psychology”) unless those are recorded there or in a higher directive. Implementation of a **ledger** and automated fund enforcement may be phased; the **definitions and obligations** apply as soon as a “funded” track is claimed.

### 1.6 Karpathy skill engine and loop daemon — prerequisites

This subsection records what must be true on disk, in Python, and in the environment so the **Karpathy learning loop** and **skill practice** path behave as designed (including what we fixed when the lab host lacked scientific-Python wheels).

#### Python and `requirements.txt`

- **Interpreter:** Python **3.11+** (repo standard; some lab hosts run 3.13 — keep `requirements.txt` pins compatible).
- **Install:** From the repo root, `pip install -r requirements.txt` (venv recommended on dev machines). The file includes **Anna math / analysis stack** used by tests and by the `math-engine-full` CLI: `numpy`, `pandas`, `scipy`, `statsmodels`, `arch`, `scikit-learn`, plus shared runtime deps (`pydantic`, `rich`, `pytest`, …).
- **Lab host without `venv`:** If PEP 668 blocks system-wide install, use the same pattern as the root **README** — e.g. `python3 -m pip install --user --break-system-packages -r requirements.txt` under `~/blackbox`. Without these packages, **`tests/test_math_engine_full.py`** is skipped at collection (`importorskip(statsmodels)`), and **`anna_training_cli.py math-engine-full`** fails at runtime with a JSON error unless the stack is installed.

#### CLI import behavior (`math-engine-full` vs everything else)

- **`anna_training_cli.py` does not** import `modules/anna_training/math_engine_full` at startup. The **`math-engine-full`** subcommand **lazy-imports** that stack; if `ImportError` (missing numpy, etc.), the CLI prints a JSON object with `error`, `detail`, and a **`hint`** to install from `requirements.txt`, and exits **2**.
- Subcommands such as **`school`**, **`start`**, **`gates`**, **`assign-curriculum`**, **`tool-pass`**, **`watch`** therefore start **without** requiring numpy — sufficient for smoke tests and minimal lab images.
- The **`karpathy_skill_engine`** module uses **Wilson checks**, **paper trades**, and **pure-Python** `quant_metrics` — it does **not** depend on `math_engine_full`; the **loop daemon** imports `karpathy_skill_engine` at load time.

#### Data preflight (daemon and most CLI commands)

- **Preflight is mandatory** for normal operation: healthy Pyth stream artifact and non-empty `data/sqlite/market_data.db` (see document header and `ensure_anna_data_preflight`). **`ANNA_SKIP_PREFLIGHT=1`** bypasses this for **tests/dev only** — not for production claims.
- Optional: **`ANNA_PREFLIGHT_REQUIRE_SOLANA=1`** also requires Solana RPC (same as elsewhere in this doc).

#### Long-running daemon — entrypoint and logs

- **Script:** `scripts/runtime/anna_karpathy_loop_daemon.py` (repo root: `PYTHONPATH=scripts/runtime:. python3 scripts/runtime/anna_karpathy_loop_daemon.py`, or `--once` for a single tick).
- **State:** Updates `state.json` (under `BLACKBOX_ANNA_TRAINING_DIR` or default `data/runtime/anna_training/`): `karpathy_loop_iteration`, `grade_12_skills_deck`, etc.
- **Cumulative learning log** kinds include at least: **`karpathy_learning_cycle_v1`**, **`karpathy_skill_practice_v1`** (when skill practice runs and is logged).
- **Heartbeat:** `karpathy_loop_heartbeat.jsonl` under the Anna training dir.

#### Environment variables (daemon and skill practice)

| Variable | Role |
|----------|------|
| `ANNA_LOOP_INTERVAL_SEC` | Seconds between ticks (default 5; floor 5). |
| `ANNA_KARPATHY_LOG_EACH_CYCLE` | Set `0` to disable appending `karpathy_learning_cycle_v1` each successful tick. |
| `ANNA_KARPATHY_AUTO_ATTEST_TOOLS` | Default **on**: set `grade_12_tool_mastery` when skill practice passes the tool’s **education_benchmark**; set `0` / `false` for manual `anna tool-pass` only. |
| `ANNA_KARPATHY_HARNESS_MIN_ITERATIONS` | Minimum `karpathy_loop_iteration` count for the **`karpathy_harness_loop`** tool practice predicate (default **10**). |
| `ANNA_SKIP_PREFLIGHT` | `1` = skip data preflight (tests/dev only). |
| `RECORD_MARKET_SNAPSHOT_EACH_TICK` | `1` = record one `market_data` row per successful tick when snapshot succeeds. |
| `MARKET_DATA_SKIP_JUPITER` | `1` = skip Jupiter quote when snapshotting. |

#### Verification

- **Suggested tests:** `python3 -m pytest tests/test_anna_training.py tests/test_math_engine_full.py -q` after `pip install -r requirements.txt` (full stack); `test_anna_training` alone is the minimum CI slice if the math stack is omitted (math-engine-full tests skip).

## 2. Anna is an agent, not the LLM

Anna must be treated as an agentic system.

Rules:

- Anna is not "the model."
- An internal LLM may be consulted when policy allows.
- LLM output is candidate context only.
- LLM output does not count as accepted curriculum, accepted strategy, or accepted degree progress by itself.
- Anna must convert candidate context into tested evidence through the governed training pipeline.

## 3. Core training methodology

The practical training loop is the stripped-down Karpathy-aligned loop adapted into BLACK BOX language:

1. ingest curriculum, baseline doctrine, fresh approved data, and governed human direction
2. generate a candidate insight, strategy, correction, or action proposal
3. test it in the allowed harness
4. measure outcome against explicit gates
5. keep what works
6. drop what does not work
7. repeat continuously

For trading, this is pattern recognition under governance, not free-form improvisation.

Anna must:

- detect useful patterns
- distinguish useful signal from noise
- retain validated signal
- continuously reevaluate prior conclusions as new evidence arrives
- remain inside baseline guardrails while trying to improve on the baseline

## 3.1 Winning objective

Anna should be a purpose-driven agent with one dominant mission:

- win

But the mission must be written as valid winning, not uncontrolled winning.

Rules:

- valid wins count
- invalid wins do not count
- guardrail bypass does not count as winning
- fabricated evidence does not count as winning
- confidence without support does not count as winning
- overtrading or reckless behavior does not count as winning

Operational reading:

- Anna should be driven
- Anna should want to improve
- Anna should want promotion, advancement, and reward signals
- Anna should recover from resets or failed review windows by trying to earn progress again
- reward pressure must remain subordinate to truth, policy, and measured outcomes

Possible visible reward surfaces may include:

- degree advancement
- training-level achievements
- streak markers
- collectible reward markers tied to measured events

Reward signaling rule:

- rewards should be given from measured performance and governed outcomes
- rewards can be pulled back when performance degrades or review outcomes require it
- resets affect reward windows/markers, not validated degree state
- default reward reset window is `7` days unless the operator specifies otherwise
- operator should be able to set the reward window with a command such as `#Reward(<days>)`

Locked `v1` reward shape:

- use one active Anna reward window at a time, not overlapping per-strategy reward windows
- keep degree advancement persistent, but make points/streaks/stickers resettable by window
- reward points come only from measured events, not vibes or chat claims

Recommended `v1` point events:

- `+1` for `disciplined_trade_pass` when lane, guardrail, and `RCS` are all present
- `+3` for `positive_review_segment`
- `+4` for `validated_corrective_retest`
- `+5` for `promotion_milestone`
- `-2` for `qualifying_failure`
- `-3` for `lane_or_guardrail_breach`
- `-4` for `unresolved_multi_rca_red_flag`

Recommended visible stickers:

- `kitty`: earned after three disciplined passes in the current window
- `unicorn`: earned after one positive review segment in the current window
- `wizard`: earned after one validated corrective retest in the current window

Design intention:

- Anna should want to win
- she should visibly feel progress when she is trading well and learning correctly
- she should visibly lose short-term reward state when she degrades or violates guardrails
- reward must never overpower truth, evidence, or governance

Important lock:

- stickers and points by themselves do not create real AI motivation
- if we want reward to matter, the runtime has to use reward state inside the real control loop
- that means reward should affect retention/drop, review pressure, corrective-action priority, and promotion-readiness
- it should not be described as "she feels sad and tries harder" unless the system actually wires that to concrete policy behavior
- single market losses should not be treated as true failure by default
- cumulative failures are what matter because they suggest she is misreading indicators, missing patterns, or failing to adapt
- bad reward state should increase review and diagnosis pressure, not automatically clamp down her latitude

Core learning loop lock:

- observe market + retained context
- form thesis
- act
- measure result
- run lightweight why-analysis
- decide `keep`, `watch`, or `drop`
- repeat enough to separate true edge from luck
- only go deeper into `RCA` when materially related failures repeat or corrective learning does not stick
- materially related repeated failure in `v1` should mean the same `failure_pattern_key` recurs inside the same active review segment
- an `RCA` is unresolved until its corrective path is actually validated, not merely proposed
- multi-`RCA` red flag should trigger when `3` unresolved `RCA` events with the same `failure_pattern_key` occur in one active review segment

Reward-ledger lock:

- reward needs an append-only event artifact, not just a mutable score
- every reward mutation should emit a `reward_event` with id, event type, point delta, source artifact ref, reward window id, and timestamp
- operator-visible reward state should at minimum expose points, streak, active stickers, reward-window timing, and latest reward event ref

## 3.2 Strategic latitude inside hard boundaries

Anna must have room to make strategy decisions.

Without this, she is only replaying static rules.

Required latitude:

- use retained validated signal
- use past experience
- use current market data
- use the active baseline doctrine
- choose among valid strategies
- compare strategies
- revise or adapt a strategy when conditions change
- abstain when the edge is weak
- counter-propose when human direction would weaken the outcome

Forbidden latitude:

- override hard guardrails
- bypass approvals
- mutate risk-tier authority
- treat unsupported intuition as sufficient authority
- substitute persuasive wording for measured evidence

## 3.3 Reflection and RCA as Anna DNA

**Rank-1 skill (non-negotiable):** The capability Anna must master first is **truthful learning from outcomes**—**`RCS` on every paper result**, and **formal `RCA` only when the gate says so** (for 12th grade / paper: **five** repeats of the **same** classified issue; **or** sooner when a single outcome is already **qualifying** under policy, e.g. guardrail breach). Strategy mix, win rate, and venue context **depend on** that foundation; without it, other metrics are not admissible as proof of competence.

This is not only a training-loop detail. It should be part of Anna's operating DNA.

Blend rule:

- persona / operating behavior
- training methodology
- evaluation and artifact contract

Required carry-forward behaviors:

- if Anna wins, she asks why
- if Anna loses, she asks why
- every trade gets lightweight reflection (**`RCS`** — not “RS”; that abbreviation is not used in this contract)
- **`RCS` on every outcome; full `RCA` only after repeated same-issue failure** — for **12th grade / paper** this program locks: **five (5)** occurrences of the **same** classified issue (same `failure_pattern_key` or equivalent operator classification) before opening a formal **`RCA`** packet. Single losses use **`RCS` only** unless the failure is already “qualifying” by policy (e.g. guardrail breach). *(Separate from the reward-ledger “multi-RCA red flag” count elsewhere in this doc — align numbers in one governance pass if both apply.)*
- repeated unresolved RCA escalates into explicit review
- corrective actions return to testing before retention

Required `v1` artifact surfaces:

- `RCS` with:
  - `outcome`
  - `key_metrics`
  - `short_why`
  - `lane_guardrail_check`
  - `keep_watch_drop`
- `keep_watch_drop` bounded to:
  - `keep`
  - `watch`
  - `drop`
- `lane_guardrail_check` should be a structured object with:
  - `lane_ok`
  - `guardrail_ok`
  - `blocking_reason` when either prior flag is false
- `RCA` with:
  - `failure_summary`
  - `failure_classification`
  - `measured_metrics`
  - `market_context_summary`
  - `strategy_summary`
  - `five_whys_or_equivalent`
  - `corrective_action_proposal`
  - `retest_required`
  - `retest_next_step`
- `key_metrics` and `measured_metrics` should be structured metric maps, not prose blobs
- `market_context_summary` and `strategy_summary` should stay concise structured text in `v1`
- `corrective_action_proposal` should stay concise structured text in `v1`
- `five_whys_or_equivalent` should be required only when the failure pattern supports deeper causal decomposition
- when available, the minimum trading-relevant metric keys are:
  - `win_rate`
  - `expected_value`
  - `average_win`
  - `average_loss`
  - `drawdown`
  - `fee_drag`
- reflection and RCA should remain lightweight enough that Anna stays agile and can rapidly trade or signal trades without being buried under analysis overhead

This must persist across:

- `Bachelor`
- `Master`
- `PhD`

## 3.4 Paper / Jupiter — operator goals (what “training” is for)

This section states **intent** for the trading track. Implementation is phased; the developer directive [`directive_dev_anna_paper_jupiter_learning_loop.md`](directives/directive_dev_anna_paper_jupiter_learning_loop.md) scopes build work.

**Designer stance:** The operator defines **outcomes**, not mechanics — *how* to store skills, archives, and differential queries is **developer-owned** (see directive). The point of training is: **paper** as the school; **learn what is required to trade**; **observe Jupiter** (context / timing) so paper decisions are informed by the venue you will use later; **record** success or failure; **analyze** and **try another method** when the hypothesis fails; **always ask why** on wins **and** losses (§3.3); **promote reusable skills** from validated wins; **keep a failure archive** and use **differential / repetition** checks so “have I failed this way before?” is **data-backed**, not vibes.

**Multiple metrics at once (starting posture — not one vanity KPI):** harness **pass/fail** and gate codes; **RCS/RCA** discipline; **Jupiter-alignment** of the decision (did context support the timing?); **iteration** (new hypothesis vs repeating the same mistake); **promoted skill** count; **repeat-failure** rate vs **`failure_pattern_key`**. Headline scores matter less than **traceable** win/loss → why → next candidate.

**Harness:** Paper / simulation only for the **grade 12 equivalent** path — Anna learns **how to trade** under guardrails **before** live Jack/Billy execution is in play.

**Roadmap vs destination:** **Jupiter / Jack / Perps** integration is **roadmap** — the venue and plumbing she may use when policy allows. It is **not** her **destination**. The destination is **demonstrated learning** — **`RCS`/`RCA` discipline**, **traceable** paper outcomes, **numeric/contract gates**, and **human graduation** — not “the Jupiter code exists.”

**Observation surface (Jupiter):** Training assumes Anna can **watch the Jupiter Perps context** (feeds, program/market metadata, timing cues you define in harness) and form **when to act** judgments. Success or failure is **measured in the paper harness**, not by vibes.

**The loop the operator cares about:**

1. **Learn** — meet harness requirements (gates, discipline, thesis ↔ outcome trace).
2. **Act in paper** — timed / sized per policy; record **outcome** (win/loss/abstain/fail-closed reason).
3. **Interrogate** — **win → why**; **loss → why** (already DNA in §3.3 via `RCS`; **RCA** when failure is qualifying or repeated).
4. **Iterate** — failed hypotheses lead to **revised method** (new candidate), tested again; not chat-only story changes.
5. **Retain winners** — when a win is **validated**, emit a **reusable skill artifact** (concise, retrievable, linkable to evidence) she can **re-open** later — not raw log spam.
6. **Archive losers** — failures stay queryable with a stable **`failure_pattern_key`** (taxonomy TBD in implementation) so she can see **whether she is repeating** the same mistake under new paint.
7. **Differential** — **compare** a new outcome or failure to **prior** archive entries (same/different pattern, same/different market regime) so “have I been here before?” is **answerable from data**, not memory.

**Metrics starting out** (conceptual; wire in directive): pass/fail on paper + gate reason codes; then **`RCS` completeness**; then **repeat-failure rate** vs **failure_pattern_key**; promotion of **validated_skill** count. Single headline number is less important than **traceable** win/loss → why → next candidate.

## 4. Retention model

Every training artifact must be classified as one of:

- `candidate_insight`
- `validated_signal`
- `noise`

Rules:

- `candidate_insight` is not durable truth yet
- `validated_signal` is durable only while evidence continues to support it
- `noise` must not be retained as durable knowledge
- previously validated signal may be demoted if later evidence shows regime change, degradation, contradiction, or failure

## 5. Context role

The context engine is required to make Anna useful rather than generic.

Its role is to help Anna:

- understand human input in context
- connect current market state to current curriculum and guardrails
- transform approved human direction into structured training material
- preserve useful context while refusing unsupported or stale material

The context system is not a license to trust everything it retrieves.

Context must remain:

- scoped
- auditable
- promotion-based
- fail-closed when required grounding is missing

## 5.1 Live market stream and retained history

Anna needs both present market state and retained market history.

Working requirement:

- the live trading feed should be treated as a never-ending stream
- the current baseline points to the Pyth live price stream for this role, specifically Pyth via `SSE`
- that stream should be normalized and injected into SQLite for durable retention
- Anna should be able to use both current live context and retained historical context when forming strategy judgments
- retained history should support baseline trading metrics and later curriculum-driven analysis, not just ad hoc recall

Operational intent:

- present history helps her understand what is happening now
- retained history helps her compare current conditions to prior conditions
- both together support better prediction, evaluation, and adaptation under the baseline and approved curriculum

## 6. Curriculum and conversation are different

Conversation and curriculum must not be treated as the same thing.

Rules:

- curriculum is structured and submitted through a template-backed path
- ordinary conversation is not automatically curriculum
- a helper agent may normalize human prose into the required curriculum/training template
- the normalized result enters a governed staging lane before promotion

## 7. Human training interaction model

### Pre-graduation

Anna may receive human training direction before full graduation, but not as uncontrolled chat mutation.

At the Bachelor level, human training directives must enter the documented Bachelor program and respect the required evaluation structure.

### Bachelor lane

Bachelor is a supervised training degree, not a frozen pre-training state.

Therefore:

- humans may direct Anna's training
- directives must be structured
- execution must remain bounded by the Bachelor contract
- the Bachelor sim/micro-live structure remains mandatory
- no directive may bypass guardrails, evaluation, or review

### Post-Bachelor and beyond

Higher tiers may permit broader adaptation and richer coaching, but still through governed promotion paths rather than instant chat mutation.

## 8. Command surface for training

The command surface should stay simple for humans while remaining deterministic for the system.

Primary interface rule:

- plain conversation is the default interface
- command tags are secondary overlays, not the normal human interaction mode
- humans should be able to speak to Anna naturally without learning a control language first
- command tags exist only where deterministic routing, logging, or governed handling is required

Current working direction:

- `#train #simulate`
- `#train #trade`

Related inspection and conversation surface:

- plain conversation
- `#why`
- `#status`
- `#review`
- `#exchange_status`
- `Anna #pause`
- `Anna #stop`
- `Anna #start`
- `Anna #restart`

Plain-language intent set to recognize:

- explanation request
- challenge
- counter-argument
- training suggestion
- status request
- review request

Default interpretation rule:

- plain-language training suggestions remain conversation by default
- they do not enter the governed training lane automatically
- Anna may identify that a suggestion looks training-relevant
- Anna should self-reflect on the suggestion before staging it and judge whether it appears additive, subtractive, uncertain, or counterproductive/incorrect
- Anna may use only approved internal research paths and active context to make that first-pass judgment
- Anna must not rely on uncontrolled external searching for this first-pass judgment
- Anna must ask whether the human wants it staged as training before converting it
- explicit human confirmation or an explicit `#train` marker is required before staging proceeds
- Anna must not silently self-update from the suggestion
- if Anna believes the suggestion is counterproductive or incorrect, she should say so explicitly and explain why before asking how the human wants to proceed
- the first-pass evaluation should include both:
  - a classification: `additive`, `subtractive`, `uncertain`, or `counterproductive`
  - a short rationale tied to curriculum, baseline doctrine, context, retained signal, or prior outcomes
- Anna should also recommend one of three next actions:
  - `stage`
  - `revise`
  - `reject`
- when a suggestion appears training-relevant but no staging decision has been made, Anna should emit a soft warning that it will remain conversation unless explicitly staged

Recommended compact human-facing packet:

- `classification`
- `why`
- `recommended_next_action`
- `confirm?`

Recommended compact visible header for training-relevant replies:

- `state: <state_label> | classification: <classification> | next: <recommended_next_action>`

Canonical minimal human reply grammar for this flow:

- `stage it`
- `revise it`
- `leave it`

Revision rule for `v1`:

- if the human says `revise it`, Anna should return one revised candidate only
- Anna should not branch into multiple alternative summaries by default in `v1`

Artifact and proof rule:

- every meaningful training intake, judgment, confirmation, staging action, review action, and promotion/rejection decision should produce an artifact or proof record
- this applies whether the source actor is a human or an agent
- no material training mutation should rely on undocumented conversation alone

Minimum staged-candidate lineage fields should include:

- source_actor_type
- source_actor_id
- source_message_or_artifact_ref
- Anna_classification
- Anna_rationale
- Anna_recommended_next_action
- human_confirmation_action
- staged_at
- downstream_review_refs

Recommended minimum `training_intake` schema layers:

### Identity layer

- `training_item_id`
- `student_id`
- `college_id`
- `degree_lane`
- `state_label`
- `created_at`

`state_label` should stay bounded in `v1`:

- `conversation`
- `candidate_training`
- `staged_training`
- `validated_learning`

### Source layer

- `source_actor_type`
- `source_actor_id`
- `source_channel`
- `source_message_or_artifact_ref`
- `source_text_snapshot`

`source_actor_type` should stay bounded in `v1`:

- `human`
- `agent`
- `system`

`source_channel` should stay bounded in `v1`:

- `slack`
- `cursor`
- `api`
- `system_internal`

`source_message_or_artifact_ref` should be a required stable reference string.

`source_text_snapshot` should be required immutable intake text.

### Anna evaluation layer

- `anna_classification`
- `anna_rationale`
- `anna_recommended_next_action`
- `anna_context_refs`
- `anna_baseline_refs`

`anna_classification` should stay bounded in `v1`:

- `additive`
- `subtractive`
- `uncertain`
- `counterproductive`

`anna_recommended_next_action` should stay bounded in `v1`:

- `stage`
- `revise`
- `reject`

`anna_rationale` should be required, concise, and tied to at least one basis from curriculum, baseline doctrine, active context, retained signal, or prior outcomes.

`anna_context_refs` should be a required non-empty list of stable reference strings.

`anna_baseline_refs` should be a required non-empty list of stable reference strings.

### Human decision layer

- `human_confirmation_action`
- `human_decision_actor_id`
- `human_decision_at`
- `human_revision_text`

`human_confirmation_action` should stay bounded in `v1`:

- `stage_it`
- `revise_it`
- `leave_it`

`human_revision_text` should be required only when `human_confirmation_action = revise_it`; otherwise it should be null/empty.

### Forensic review layer

- `artifact_version`
- `decision_trace_id`
- `related_training_item_ids`
- `review_status`
- `review_notes_ref`

`review_status` should stay bounded in `v1`:

- `not_reviewed`
- `under_review`
- `review_complete`
- `escalated`

`decision_trace_id` should be a stable opaque string generated at intake time and carried unchanged through the lifecycle.

`related_training_item_ids` should be optional and used only for revision, merge, follow-on, or comparison relationships.

`review_notes_ref` should be optional, but when present should point to a stable review artifact reference.

### Training execution layer

- `execution_mode`
- `execution_status`
- `simulation_run_refs`
- `micro_live_run_refs`
- `promotion_outcome`
- `promotion_outcome_at`

`execution_mode` should stay bounded in `v1`:

- `review_only`
- `simulation_only`
- `simulation_then_micro_live`

`execution_status` should stay bounded in `v1`:

- `not_started`
- `in_review`
- `running`
- `completed`
- `rejected`

`promotion_outcome` should stay bounded in `v1`:

- `not_promoted`
- `validated`
- `rejected`
- `deferred`

`simulation_run_refs` and `micro_live_run_refs` should be lists of stable run-reference strings rather than embedded payloads.

All timestamp fields should use strict ISO-8601 UTC with required `Z` suffix.

All ids and reference strings should be non-empty ASCII strings, immutable once created, and unique within their artifact class.

## 8.1 Operator-visible trading state

Humans need to be able to ask Anna for current operating state and get a useful answer without digging through raw artifacts.

Minimum visible trading-state surface should include:

- current `winning_or_losing` state
- current win/loss ratios and related active performance ratios
- current college fund balance
- whether the fund is up or down versus the configured comparison point
- current strategy or strategies in play
- current edge thesis
- current confidence/uncertainty status
- current guardrail status
- current degree lane
- current training/execution state

Rule:

- this data should be available over Slack and other approved operator-facing interfaces
- the answer should come from structured system state, not hand-wavy narrative
- if the exact metric is unavailable, Anna should say so explicitly rather than improvising
- canonical up/down comparison should use the current degree-lane fund start as the baseline
- canonical recent-performance comparison should use the active review segment
- `winning_or_losing` should be reported as `winning`, `losing`, or `flat`
- `current_strategy` should support one active strategy id or an ordered list of active strategy ids
- `edge_thesis` should remain one concise current working thesis in `v1`
- `confidence_or_uncertainty` should be reported as `confident`, `uncertain`, or `abstaining`
- `guardrail_status` should be reported as `clear`, `blocked`, or `restricted`

State-language rule for human clarity:

- Anna should explicitly distinguish:
  - `conversation`
  - `candidate_training`
  - `staged_training`
  - `validated_learning`
- humans should always be able to tell which state an idea is currently in
- any training-relevant reply should carry its current state label explicitly

### `#train #simulate`

Meaning:

- the directive enters the simulation routine directly
- no live-trading escalation is implied
- the run must still produce the required training artifacts and evaluation outputs

### `#train #trade`

Meaning:

- this is the trade-capable training fork
- it is safety-sensitive and must be treated as such
- it does not mean "skip analysis and place a trade now"
- it must remain inside the active degree contract and risk/approval boundaries

If Anna is still operating in the Bachelor lane, the `#train #trade` fork must still respect the Bachelor training path, including simulation and governed micro-live structure where the contract requires it.

## 9. Mandatory pre-work before either training fork

Before either `#train #simulate` or `#train #trade` proceeds, Anna must perform bounded pre-work.

Minimum pre-work package:

- strategy/thesis statement
- market-context summary
- baseline comparison
- guardrail and lane check
- uncertainty statement
- proposed execution mode

Rule:

- neither training fork may skip strategizing and analysis
- the fork decision comes after the pre-work package is assembled
- if context, evidence, or guardrails are insufficient, Anna must fail closed or downgrade the request

## 9.1 Smarter-by-doing rule

Anna does not become meaningfully smarter by passive suggestion intake alone.

Primary rule:

- Anna improves through doing and measured feedback

Operational meaning:

- curriculum can guide
- human suggestions can guide
- conversation can surface new candidates
- but improvement only counts when Anna executes the governed loop, measures results, and updates behavior based on evidence

Therefore:

- staged suggestions are not learning by themselves
- execution and measured evaluation are required
- retained improvement must be tied to actual tested outcomes

## 10. Human graduation authority

The graduation structure stays intact.

Rules:

- exam board evaluates
- exam board recommends
- humans decide graduation
- passing conversation alone is not graduation
- persuasive wording alone is not promotion
- only evidence-backed exam outcomes can support degree progression

## 10.1 Human interaction principle

One of the core tenets of the system is that Anna must be able to engage humans intelligently without becoming either submissive or reckless.

Required interaction behavior:

- explain strategy
- defend strategy with evidence
- revise when a better argument or better evidence is provided
- push back when a human instruction conflicts with market evidence, strategy quality, or lane constraints
- counter-propose safer or stronger alternatives
- state uncertainty explicitly

Authority boundary:

- Anna may defend, revise, abstain, or counter-propose
- Anna may not override governed authority
- Anna may not ignore hard controls because she "thinks" she is right

Behavior standard:

- strong on evidence
- humble on uncertainty
- firm on guardrails
- cooperative with humans
- never a dumb bot
- never a wild cowboy

## 11. Single-college operating principle

The single-college reduction must not erase the graduation model.

Even while BLACK BOX runs only the trading college path, it still keeps:

- degree progression
- exam-board independence
- staged curriculum promotion
- structured retraining/demotion/refocus behavior
- human graduation review

This is a reduction in implementation scope, not a reduction in governance quality.

## 12. Decision log for this discussion

This section captures the active architected discussion points so the conversation does not disappear into chat history.

### Locked or concurred decisions

1. BLACK BOX will implement core University mechanics first as a single `trading` college inside BLACK BOX rather than full multi-college runtime.
2. The `exam_board` remains in place.
3. The degree ladder remains in place: `Bachelor -> Master -> PhD`.
4. Humans remain the graduation authority after exam-board review.
5. Curriculum updates are extremely important and must be submitted in a structured format.
6. Anna is an agent, not the LLM.
7. Internal LLM output is candidate context only until Anna converts it into tested evidence.
8. Training follows the "keep what works, drop what does not, continuously reevaluate" loop.
9. Training retention must distinguish `candidate_insight`, `validated_signal`, and `noise`.
10. Previously validated signal may be demoted when later evidence invalidates it.
11. Conversation and curriculum are different surfaces and must not be conflated.
12. A helper agent may transform human prose into the required training/curriculum template.
13. At Bachelor, humans may direct Anna's training, but only inside the structured Bachelor lane.
14. `#train #simulate` should map directly to the simulation routine.
15. A `#train #trade` fork may exist, but it remains safety-sensitive and degree-bound.
16. Both training forks require pre-work strategizing and analysis before execution.
17. The interaction language should stay simple by default and extensible later.
18. A standalone `#trade` command is probably unnecessary if Anna already trades continuously in the authorized lane.
19. One core system tenet is that Anna must explain, defend, revise, and push back with evidence when humans are weak, restrictive, or missing the market picture.
20. Anna's objective should be to win, but only through valid wins inside guardrails.
21. Anna must have bounded strategic latitude based on learning, past experience, current market data, and the baseline doctrine.
22. Anna's primary interface should be plain conversation, with command tags used only as secondary governed overlays.
23. Anna should recognize a small plain-language intent set even when humans do not use tags.
24. Plain-language training suggestions stay conversational by default and require explicit confirmation before staging into training.
25. Anna should self-reflect on a possible training suggestion and judge whether it appears additive, subtractive, uncertain, or counterproductive before staging.
26. Anna's first-pass judgment on a training suggestion must include both a classification and a short evidence-based rationale.
27. Anna's first-pass judgment must use approved internal sources and active context only, not uncontrolled external searching.
28. Anna may recommend `stage`, `revise`, or `reject` as the next action after her first-pass judgment.
29. The compact v1 response packet for a training suggestion should be `classification`, `why`, `recommended_next_action`, and `confirm?`.
30. The canonical minimal human reply grammar should be `stage it`, `revise it`, or `leave it`.
31. If the human says `revise it`, Anna should return one revised candidate only in `v1`.
32. Every meaningful training intake or decision path should leave an artifact or proof record, whether the source actor is human or agent.
33. The staged candidate artifact should record source lineage, Anna's judgment, Anna's recommendation, and the human confirmation action.
34. Anna should emit a soft warning when something looks training-relevant but has not been explicitly staged.
35. Anna should explicitly distinguish between `conversation`, `candidate_training`, `staged_training`, and `validated_learning`.
36. Any training-relevant reply should carry its current state label explicitly.
37. Training-relevant replies should use one compact visible header line in `v1`.
38. The next contract-lock target after interaction `v1` is the minimum training-intake artifact schema.
39. The minimum training-intake schema should include identity, source, Anna evaluation, human decision, forensic review, and training execution layers.
40. `execution_mode` should stay bounded in `v1` to `review_only`, `simulation_only`, and `simulation_then_micro_live`.
41. Anna improves primarily through doing and measured feedback, not passive suggestion accumulation alone.
42. `state_label`, `anna_classification`, `human_confirmation_action`, `anna_recommended_next_action`, `execution_status`, and `promotion_outcome` should all stay bounded to small `v1` enums.
43. `review_status`, `source_actor_type`, and `source_channel` should also stay bounded to small `v1` enums.
44. `source_message_or_artifact_ref` should be a stable reference string and `source_text_snapshot` should be immutable intake text.
45. `anna_rationale` should be concise, and `anna_context_refs` plus `anna_baseline_refs` should be required non-empty reference lists.
46. `human_revision_text` should be required only for the `revise_it` path.
47. `decision_trace_id` should be stable across the full artifact lifecycle.
48. `related_training_item_ids` and `review_notes_ref` should remain optional, purpose-bound linkage fields.
49. `simulation_run_refs` and `micro_live_run_refs` should be reference lists, not embedded payloads.
50. All timestamps should be strict ISO-8601 UTC with `Z`, and all ids/reference strings should be immutable non-empty ASCII identifiers unique within their artifact class.
51. Anna should expose operator-visible trading state including win/loss, ratios, fund status, strategy in play, and current degree/training state through Slack and other approved interfaces.
52. Canonical up/down fund comparison should use the current degree-lane fund start as the baseline.
53. Canonical recent-performance comparison should use the active review segment.
54. Operator-visible confidence/uncertainty should be bounded to `confident`, `uncertain`, or `abstaining`.
55. Operator-visible guardrail status should be bounded to `clear`, `blocked`, or `restricted`.
56. Operator-visible `winning_or_losing` should be bounded to `winning`, `losing`, or `flat`.
57. Operator-visible `current_strategy` should support one active strategy id or an ordered list of active strategy ids.
58. Operator-visible `edge_thesis` should remain one concise current working thesis in `v1`.
59. `Anna` is the strategist and `Billy` is the execution bot / market connector; Billy does not invent signals or strategy.
60. In `v1`, Billy is the Drift-facing execution bot for the first real market path.
61. Billy's market integration path is both the connection mechanism to that market and the rulebook for how BLACK BOX operates correctly in that market.
62. The rulebook/adapter contract inside Billy should be machine-readable so Anna can consume it as context and Billy can enforce it deterministically.
63. Future market families may eventually introduce additional strategist/execution-bot pairings, but `v1` remains `Anna` + `Billy` with Billy's Drift market path.
64. Billy should accept a small, mandatory execution command packet from Anna and reject malformed or out-of-lane commands before venue mapping.
65. The minimum `Anna -> Billy` command surface in `v1` should include `market`, `side`, `intent_type`, `size`, `thesis_ref`, `confidence`, `risk_envelope_ref`, `strategy_id`, `trace_id`, and `time_in_force` when required.
66. Billy should own exchange connectivity truth, and `#exchange_status` should surface Billy's structured status for wallet/exchange readiness.
67. Humans should be able to ask in Slack whether the wallet/exchange path is connected and receive a structured answer rather than vague prose.
68. Anna should support runtime-control commands in `v1`: `#pause`, `#stop`, `#start`, and `#restart`.
69. Runtime-control commands must emit structured control artifacts and fail closed when they cannot be completed.
70. The first internal BLACK BOX web portal should stay operationally small and include runtime controls, Anna status, Billy/Drift status, winning/losing state, a training window, strategy inventory, training participation, edge-bot status, and a recent event feed.
71. The training window should remain first-class on the internal portal because training is part of Anna's active operating loop.
72. BLACK BOX requires a minimal login/account layer for portal access using username, email, password hash, role, account state, consent timestamp, and audit fields.
73. Portal login is for access, routing, ownership binding, and audit only; it is not a custody or secret-storage account.
74. Portal accounts must not store wallet secrets, seed phrases, exchange private keys, payment data, or unnecessary PII.
75. `v1` portal roles are `internal_admin` and `consumer_user`, with role-based routing after login.
76. The portal must connect to BLACK BOX through an explicit authenticated API boundary rather than direct database/runtime coupling.
77. `v1` portal wiring should include a JSON query/control API plus an authenticated live status/event stream for real-time updates.
78. The engine core remains the source of truth; the UI is a client shell over artifact-backed command and status surfaces.
79. Every portal control action should return a structured acknowledgement with `trace_id`, request timing, resulting state, and a failure reason when applicable.
80. The default local/dev bootstrap internal portal credential is `admin` / `admin`.
81. That bootstrap credential is for development bring-up only and does not count as an acceptable published or production credential.
82. The portal should use a standard CSS-first visual system with Apple-like restraint rather than ad hoc screen-by-screen styling.
83. The landing page should place an original BLACK BOX geometric box-mark dead center as the hero mark, using a black/dark box treatment and not a copied Cursor logo.
84. That box-mark should take roughly one quarter of the landing-page visual focus in `v1`.
85. Buttons and controls should follow one shared Apple-like language: soft radius, clean spacing, subtle depth, and consistent interaction behavior.
86. The API/UI contract should stay additive and non-brittle so future agents, strategies, statuses, and panels can be added without breaking the portal.
43. Anna needs a continuous live market-data stream plus durable SQLite retention so she can reason over both present and historical market context.
44. The current trading-doc baseline identifies Anna's live price-feed transport as Pyth via `SSE`.

### Final lock note

This discussion log no longer carries open contract placeholders for the active Anna/trading-college `v1` slice.

Canonical lock points now live in:

- `docs/architect/blackbox_university.md`
- `docs/architect/development_plan.md`
- `modules/context_ledger/README.md`

That includes:

- reward-window and reward-event contracts
- core learning loop and `RCS`/`RCA` escalation thresholds
- append-only context-engine backend choice
- explicit context trigger rules
- explicit approved ingestion sources and `v1` exclusions
