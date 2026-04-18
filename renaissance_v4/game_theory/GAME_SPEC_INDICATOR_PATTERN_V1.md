# Indicator Pattern Game — Spec v1

**Status:** Draft — mechanical pins still required before first scored run (see §13).

**Scope:** Crypto / trade only. **Out of scope:** Foreman, non-trade control-plane logs.

---

## 1. Purpose

Run an **empirical pattern game**: the **Player** proposes strategies built only from the **frozen indicator vocabulary** and **Renaissance catalog**; the **Referee** replays history and scores **binary WIN/LOSS** per closed trade. **Wins and losses are both data.** Primary interest is **repeatable pattern structure**, not a dollar-narrative optimization—though **starting capital** is fixed so sizing and feasibility are real.

**Research intent (pattern discovery, indicator context):** The product goal is to find **repeatable pattern → policy** matches validated by replay, not to celebrate one-run PnL. Indicators must eventually be interpreted with **dynamic context** (direction, transition, structure), not raw values alone — see **`QUANT_RESEARCH_AGENT_DESIGN.md`**.

---

## 2. Roles

| Role | Responsibility |
|------|----------------|
| **Referee** | Loads **SOLUSDT** bars **in time order**, runs deterministic replay (`renaissance_v4.research.replay_runner` / `run_manifest_replay`), applies **`outcome_rule_v1`**, emits reports, traces, checksums. **Only** the Referee declares WIN/LOSS. |
| **Player** | Proposes strategies (JSON **strategy manifest** validated against `registry/catalog_v1.json`, optionally PolicySpec **`indicators`** per `policy_spec/indicators_v1.py`). **May not** self-grade. |

**Lane for v1:** Pick **one** primary path (manifest replay **or** PolicySpec intake) for the first implementation so candidates are comparable.

---

## 3. World (market)

- **Instrument:** **SOL** — **SOLUSDT** on the bar feed used by Renaissance ingest (`renaissance_v4.data.binance_ingest` targets this pair by default).
- **Bars:** SQLite `renaissance_v4/data/renaissance_v4.sqlite3`, table **`market_bars_5m`** (and any future aggregated tables if 15m/30m are added).
- **Interval (v1):** **5m** unless/until alternate resolutions are ingested or aggregated with a **single documented rule**.
- **Window:** **12 consecutive calendar months** of bars available to the run (after engine warm-up), or a strict **train / test** split (§8).

**Causality (live-like):** Decisions may use only information **available at or before** the simulated instant per engine rules—**no future bars**, no peeking at the **final** price of the evaluation window when deciding earlier. The Referee enforces this by **forward** replay.

---

## 4. Capital

- **Starting equity:** **USD 1,000** (paper).
- **Use:** Position sizing, margin/feasibility, and whether a trade may be placed—**same rule for every candidate** in a run series.
- **Scoring:** Primary game table remains **binary WIN/LOSS** (§6); dollars are **not** the headline objective.

---

## 5. Allowed moves (closed alphabet)

- **Indicators / declarations:** Kinds and params must match **`renaissance_v4/policy_spec/indicators_v1.py`** and **`indicator_mechanics.py`** when using PolicySpec.
- **Signals / fusion / risk / execution template:** IDs must exist in **`renaissance_v4/registry/catalog_v1.json`** and the chosen manifest schema.
- **No** ad-hoc indicators or off-catalog modules.

The **human** does not micromanage RSI periods or stops; **numerics** are either **Player search** within allowed ranges or **house defaults** (§7).

---

## 6. Outcome rule (binary, versioned)

- Each **closed trade** → **WIN** or **LOSS** under **`outcome_rule_v1`** (implement once in code, e.g. realized P&amp;L after costs **>** 0 ⇒ WIN).
- Log **`outcome_rule`** version string on every run.

---

## 7. Execution & risk (level 1 — practical stance)

**SL/TP — Player-searchable, bounded:** The **Player** may propose **stop** and **take-profit** as **ATR multiples** (or a small **discrete** set of presets) within **fixed min/max** bounds (e.g. floor on minimum stop distance so settings cannot be “hair trigger” only). Every candidate is still judged by the **same** `ExecutionManager` mechanics—implementation work is to **thread** these multiples from the manifest (or game config) into the path that sets `open_trade` stop/target, replacing the current **module-level constants** for **game runs only** if desired.

**Why:** The Player needs to align exit geometry with the **pattern** in the data; that is part of search, not only entry signals.

**Guards:** **Max trials** + **max wall time** (§9); optional **min ATR multiple** / **max** multiple; symmetric treatment **long** and **short**. In-sample overfitting on one 12‑month window is expected under mode **A** (§8); **splits** (B/C) apply when claiming generalization.

**House reference:** Today’s code uses fixed multiples in `renaissance_v4/core/execution_manager.py`; the game pins **searchable** bounds in the spec/runner and logs chosen values per trial.

**Anti-whipsaw (long and short):** Reduce churn with **symmetric** rules, e.g.:

- **Regime / fusion:** Searchable **min fusion** / regime usage where the catalog allows.
- **Cooldown / min hold / flip delay:** If added, as **explicit** house rules or **bounded** search parameters (same for long and short).

Whipsaw can be **mitigated**, not eliminated, without sometimes missing real moves.

### Machine learning (post-Referee, not blocking level 1)

- **After** the Referee produces **logs** (candidates, WIN/LOSS, traces), ML may **rank** candidates, **cluster** losses, or **propose** the next manifest—**never** as a substitute for replay scores.
- **Scores** remain **only** from Referee outputs. ML “memory” of past trials is **proposal policy**, not ground truth; mitigate **search overfitting** to one window with **max trials**, and later **held-out** data when you claim OOS performance.
- **Batch scenario JSON** (parallel runs) may attach **`tier`** (e.g. **T1**), **`evaluation_window`** (e.g. **12 calendar months** declarative intent), **`agent_explanation`**, and related ids per scenario. The Referee **ignores** these for scoring; they are **echoed** next to replay summaries for audit and training traces. See `game_theory/README.md` (Scenario JSON contract, templates under `examples/`).

---

## 8. Search vs test (honesty)

Choose **one** and record it in the run metadata:

- **A — Single 12-month window:** Exploratory; cap **max trials** + **min trades**; acknowledge in-sample risk.
- **B — Split:** e.g. months **1–9** search, months **10–12** **frozen** strategy, single final evaluation.
- **C — Walk-forward:** e.g. quarterly folds; define folds in the run config.

**Design peeking:** Optimizing on the **same** window you report as “final” inflates apparent edge. Splits address that; causality inside replay addresses **bar** lookahead only.

---

## 9. Scoring & stop rules

- Record: **WIN count**, **LOSS count**, **WIN rate**, **trade count**; optional slices (e.g. by month or regime).
- **Ranking (example):** WIN rate subject to **minimum closed trades N**, optional **max drawdown** or **complexity** tie-break (fewer knobs).
- **Stop the search:** **Max trials** and/or wall time; optional **complexity cap**.

---

## 10. Provenance

Log: dataset path, **SOLUSDT** symbol, bar interval, date range, **USD 1,000** sizing rule, **`outcome_rule_v1`** version, manifest hash, execution template, **per-trial ATR stop/target multiples** (if searchable), and existing **reason traces**. Natural-language explanations must **cite** these artifacts.

---

## 11. Player prohibitions

The **Player** (human or AI) **must not**:

1. **Invent ground truth** — Declare WIN/LOSS, win rate, or “this pattern works” **without** a completed **Referee** run on the **agreed** dataset and **`outcome_rule_v1`**. Story is not a score.

2. **Invent indicators or modules** — Add indicator kinds, signals, fusion engines, or code paths **outside** **`indicators_v1` + `indicator_mechanics`** and **`registry/catalog_v1.json`** (for the chosen lane). No custom math in chat that bypasses the repo.

3. **Peek at the future (inside the sim)** — Use any bar or label **after** the bar index used for the decision at that time. The Referee’s forward replay is the authority; the Player does not load “full CSV for optimization” **into** the simulator as a substitute for causal replay.

4. **Confuse search and test** — Tune on the **evaluation** slice and then report that slice as **out-of-sample** without declaring the protocol broken. **Design peeking** is prohibited when claiming honest generalization.

5. **Move the arena mid-compare** — Change symbol, interval, **`outcome_rule_v1`**, capital rule, or cost model **between** candidates in the same comparison **without** logging a new **run id** and version bump.

6. **Prove with prose** — Treat natural-language explanation as **evidence** of performance. Only **artifacts** (replay output, manifest hash, traces, checksums) count.

7. **Run unbounded search without rules** — Ignore **max trials**, **min trades**, or agreed **search vs test** (§8) and still claim a **single** “best” winner without qualification.

**Allowed:** Any proposal that **validates** against the catalog/schema and is **executed** by the Referee; iterative search within those bounds.

---

## 12. Enforcement (hardcoded / non-bypassable)

Policy alone cannot stop a bad actor; **implementation** must make cheating **mechanical failure**, not a honor rule.

| Layer | What to hardcode |
|--------|-------------------|
| **Moves** | **Reject** manifests / PolicySpec that fail **`validate_manifest_against_catalog`** or **`validate_indicators_section`** (or equivalent) before any replay starts. |
| **Scores** | **WIN/LOSS** only from **Referee** code paths that read **closed trades** / P&amp;L from the replay result — **no** parameter that lets an LLM or client **inject** outcomes. |
| **Data** | Bar feed **only** from the configured SQLite path and time bounds; **no** alternate “secret” full-series path inside the game runner. |
| **Audit** | Persist **manifest hash**, **`outcome_rule_v1`** version, dataset bounds, and **replay checksum** (if available) on every scored run. |

**Note:** The game **runner** (script or service) should be the **only** entry point that can produce an **official** scorecard. LLM output is **proposal-only** until validated and replayed.

---

## 13. Mechanical checklist (before first official game run)

- [x] **`outcome_rule_v1`** — Implemented as **`outcome_rule_v1_pnl_strict`** in `renaissance_v4/game_theory/pattern_game.py` (`score_binary_outcomes`: WIN if `pnl > 0`, else LOSS).
- [ ] **\$1,000** wired consistently to sizing in the chosen replay path (spec constants in `pattern_game.py`; risk governor still uses tiered `notional_fraction`).
- [ ] **12 months** (or train/test ranges) defined as **SQL `open_time` bounds** or manifest dates if supported.
- [ ] **Search vs test** mode (A/B/C) selected and logged.
- [ ] **Anti-whipsaw** levers: documented (searchable fusion/regime where applicable).
- [x] **SL/TP (ATR)** — `ExecutionManager` accepts optional **`atr_stop_mult` / `atr_target_mult`**; manifest keys validated **[0.5, 6.0]**; `build_execution_manager_from_manifest` passes them through.
- [ ] **ML** (optional): only **after** logs exist; proposals only, never injected scores.
- [ ] Full bar count verified on the **host** that holds production-scale history (not assumed from a smoke DB).
- [x] **Official runner** — `python3 -m renaissance_v4.game_theory.pattern_game` (validate → `run_manifest_replay` → binary scorecard; no injected scores).

**Run (repo root, `PYTHONPATH=.`):**

`python3 -m renaissance_v4.game_theory.pattern_game --manifest renaissance_v4/configs/manifests/baseline_v1_recipe.json`

Optional overrides: `--atr-stop-mult 2.0 --atr-target-mult 3.0`

---

## 14. References (repo)

- Catalog: `renaissance_v4/registry/catalog_v1.json`
- Indicators vocabulary: `renaissance_v4/policy_spec/indicators_v1.py`
- Replay: `renaissance_v4/research/replay_runner.py`
- Pattern game runner: `renaissance_v4/game_theory/pattern_game.py`
- Game theory / agent docs folder: `renaissance_v4/game_theory/`
- Example manifest: `renaissance_v4/configs/manifests/baseline_v1_recipe.json`
- Execution defaults: `renaissance_v4/core/execution_manager.py`
