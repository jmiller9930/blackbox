# Anna training — forensic audit primer (code vs intent)

**Audience:** A second agent (or human auditor) doing **forensic analysis** on whether the **repository implementation** supports the **stated training intent**, and whether claims like “Anna learned” can be **grounded in system behavior** rather than vibes.

**Canonical product contract (read first):** [`ANNA_GOES_TO_SCHOOL.md`](ANNA_GOES_TO_SCHOOL.md) — Grade 12, Karpathy loop, gates, paper-only boundary, human graduation.

**Bottom line for audits:** In software, “learning” is **only** what is **defined, logged, gated, and merged into analyst context** along documented paths. Anything else is **governance or human judgment**, not a code truth.

---

## 1. What “must learn” and “must demonstrate” means in this codebase

| Intent (plain language) | Where it is encoded | What “demonstrated” means in **code** |
|-------------------------|---------------------|--------------------------------------|
| Follow a sequenced curriculum | `modules/anna_training/curriculum_tools.py`, `catalog.py`, `progression.py` | Tool checklist booleans; `tool-pass` or auto-attest when benchmarks pass |
| Measured paper outcomes | `modules/anna_training/paper_trades.py`, `gates.py` | Rows in `paper_trades.jsonl`; `evaluate_grade12_gates` PASS/FAIL with blockers |
| Repeated Karpathy practice | `modules/anna_training/karpathy_skill_engine.py`, `scripts/runtime/anna_karpathy_loop_daemon.py` | Iteration counter, heartbeats, skill practice logs — **not** “smarter LLM” by itself |
| Durable “memory” of passing skills | `modules/anna_training/internalized_knowledge.py`, `cumulative.py` | `carryforward_bullets`, internalization stamps; merged into analyst FACTs via `analysis.py` |
| Analyst sees school mandate | `modules/anna_training/school_mandate.py`, `scripts/runtime/anna_modules/analysis.py` | FACT lines derived from gate state |

**Not provable from Python alone:** That an LLM “understood” something, or that paper P&amp;L is **economic** alpha (vs luck or manual `log-trade`). The system can prove **process adherence, predicates, and ledger rows**.

---

## 2. Where the training code lives (map)

| Area | Path | Role |
|------|------|------|
| State (curriculum, tools, iterations) | `modules/anna_training/store.py` → `data/runtime/anna_training/state.json` (override: `BLACKBOX_ANNA_TRAINING_DIR`) | Persistence; internalization hooks on save |
| Paper ledger | `modules/anna_training/paper_trades.py` → `paper_trades.jsonl` | Cohort for numeric gate; quant metrics |
| Grade-12 gates | `modules/anna_training/gates.py` | **PASS** = tools complete **and** numeric predicates (min decisive, win rate, optional P&amp;L envs) |
| Karpathy loop (long-running) | `scripts/runtime/anna_karpathy_loop_daemon.py` | Ticks, heartbeats, skill practice |
| CLI / operator | `scripts/runtime/anna_training_cli.py`, `bin/anna` if present | `school`, `gates`, `status`, `dashboard`, `log-trade`, etc. |
| Launcher (lab) | `scripts/anna_training_launch_server.sh`, `scripts/anna_karpathy_loop_detach.sh` | School + optional tmux daemon |
| Analyst merge | `scripts/runtime/anna_modules/analysis.py`, `proposal.py` | FACTs, regime/signal/strategy layers when wired |
| Fictitious wallet / adaptive weekly goal | `modules/anna_training/paper_wallet.py`, `modules/anna_training/adaptive_paper_goal.py` | **Informational** targets; not the same as graduation unless optional env gates are set |
| Regime / execution signal | `modules/anna_training/regime_signal.py` | Optional `trading_core_signal.json`; execution gating when strict env on |

**Tests (minimum forensic slice):** `tests/test_anna_training.py`, `tests/test_anna_signal_execution.py`, `tests/test_adaptive_paper_goal.py`, `tests/test_strategy_regime_cohort.py`

---

## 3. How it fits together (control flow)

1. **Preflight** (`modules/anna_training/readiness.py` / CLI `check-readiness`): Pyth artifact + `market_data.db` (+ optional Solana). Fails closed for most commands if unhealthy (unless `ANNA_SKIP_PREFLIGHT=1` for dev).

2. **Daemon tick:** Preflight (if not skipped) → increment iteration → skill deck / practice (`karpathy_skill_engine`) → append heartbeat (`karpathy_loop_heartbeat.jsonl`) → optional learning cycle log.

3. **Gates:** Tools must be complete **before** numeric paper gate is evaluated for overall PASS (see `gates.py` and doc §1.2.1).

4. **Internalization:** On `save_state`, hooks may append carryforward FACT lines when tools or full gate PASS (`internalized_knowledge.py`).

5. **Analyst path:** Analysis loads state + paper + math + mandate FACTs; **LLM output is not** curriculum completion by itself (`ANNA_GOES_TO_SCHOOL.md` §2).

---

## 4. Forensic verdict rubric (true / false / not decidable)

Use this to avoid over-claiming.

| Question | If **true** in repo, you should find… | If **false** or **not decidable** |
|----------|----------------------------------------|-----------------------------------|
| “The system enforces a binary Grade-12 bar.” | `gates.py` + `curriculum_tools.py` predicates; tests | N/A |
| “Anna’s analyst receives cumulative learning FACTs when internalization fired.” | `carryforward_bullets` / internalization keys in state; merge in `analysis.py` | Cannot verify **quality** of reasoning |
| “Paper trading is the same path as live until settlement.” | Execution plane + paper append paths; `ANNA_GOES_TO_SCHOOL.md` §1.1.1 | Full venue parity is a **phase** claim — diff adapters |
| “Heartbeat count = learning.” | **False** as sole metric — doc says checklist % is not idle ticks |
| “15% weekly goal = must pass to graduate.” | Only if `ANNA_GRADE12_*` / return envs require it; else goal is **informational** | Read `gates.py` env section |

**Verdict template**

- **Implementation aligned with intent:** Gates, persistence, FACT merge, and exclusions match `ANNA_GOES_TO_SCHOOL.md` for the **software-enforced** slice.
- **Intent overstated in ops:** Marketing “she learned” without `gates` PASS + traceable paper cohort + internalization stamps.
- **Unknown:** Requires runtime logs on `primary_host`, exam-board records, or live channel behavior — **not** in git alone.

---

## 5. Suggested audit procedure (deep dive order)

1. Read `docs/architect/ANNA_GOES_TO_SCHOOL.md` §1.2–1.5 (binary predicates, ordering).
2. Trace `evaluate_grade12_gates` in `gates.py` — list every blocker string and env tunables.
3. Trace `save_state` → `apply_internalization_hooks` → `maybe_grade12_internalize` / trading internalize.
4. Trace `build_school_mandate_fact_lines` and where FACTs attach in `analysis.py`.
5. Inspect **disk truth** on the lab host: `state.json`, `paper_trades.jsonl`, last lines of `karpathy_loop_heartbeat.jsonl`, `gates` JSON output.
6. Run `python3 -m pytest tests/test_anna_training.py` (and related tests above) on the same commit as production.

**Red flags:** `ANNA_SKIP_PREFLIGHT=1` / `ANNA_SKIP_CURRICULUM_TOOLS_GATE=1` in production claims; empty or hand-filled paper ledger passed off as harness; gate PASS with zero decisive trades (should be impossible if predicates hold).

---

## 6. One-line agent mandate (for the forensic agent)

> Prove or disprove, from **code + persisted artifacts + gate JSON**, whether the **implemented** training system can **measure and record** the learning outcomes the contract describes; separately state what **requires human or live-system evidence**.

---

*This file is the single primer for training forensics; extend it in place rather than duplicating.*
