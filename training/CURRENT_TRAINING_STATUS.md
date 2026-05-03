# FinQuant training — current status report

**Purpose:** Single snapshot for operator + learning engineer review.  
**Concern under review:** Corpus shape and completeness (seed vs exported ledger rows vs validator contract).

---

## 1. Where we stand

| Area | Status |
|------|--------|
| **Tracked seed corpus** | `training/corpus_v05_agentic_seed.jsonl` — **3 rows**, all **`NO_TRADE` / `INSUFFICIENT_DATA`**. **No `ENTER_LONG` / `ENTER_SHORT` gold rows yet** (see `training/CODY_NOTE.md` — minimum ask before next serious run). |
| **Validator** | `python3 training/validate_agentic_corpus_v1.py training/corpus_v05_agentic_seed.jsonl` → **OK** on current seed. |
| **Ledger → agentic export** | Implemented as `prove_learning/finquant/unified/agent_lab/export_to_training_corpus.py` (not under `training/`). Supports `--ledger PATH` or `--latest`, `--good-only`, `--min-confidence-spread`. |
| **Export validation check** | On latest `prove_learning/ledger_output/*_decisions.json`, **`--good-only` full export = 286 lines**; **`validate_agentic_corpus_v1.py` on that file → OK** (after fixes for `--latest` path + R-002 `confidence_gap_v1` / `i_dont_know_triggered` + decisive ENTER confidences). |
| **QLoRA / trx40** | Not re-verified from this workspace in this report. Operator should confirm under `FINQUANT_BASE`: `full_training_report_v0.1.md`, non-empty `adapters/finquant-1-qwen7b-v0.1/`, and verifier reports after last full run. |

---

## 2. Corpus correctness — what was wrong, what is fixed

**A. Schema vocabulary**

- Early handoff examples sometimes used **baseline v0.05**-style fields (`decision`, `direction`, flat `risk_plan`). **Authoritative training schema** is **`finquant_agentic_qa_v1`** (`hypotheses_v1`, `deterministic_baseline_verdict_v1`, `expectancy_check_v1`, `learning_record_candidate_v1`, `Final_status`, etc.) — see seed rows.
- **Export output** is aligned to **agentic** shape and passes **`validate_agentic_corpus_v1.py`**.

**B. Validator rules (R-002)**

- Exporter initially used **`confidence_gap_v1` as `h1−h2`** (could be wrong sign) and **`i_dont_know_triggered` only when gap &lt; 0.10**, while the validator requires: if **`confidence_gap_v1` &lt; 0.20** and `i_dont_know_triggered` is false → **fail**.
- **Fixed:** gap = **sorted top-two hypothesis confidences**; `i_dont_know_triggered` when gap &lt; **0.20**; **ENTER_*** rows get bumped confidences so entry gold stays decisive and valid.

**C. Residual risks (learning engineer to confirm)**

1. **Seed still lacks ENTRY exemplars** — model may still default to abstain-heavy behavior until those rows exist (per `CODY_NOTE.md`).
2. **Exported rows** use **real indicators** from the ledger but **bars** may be sparse; exporter packs a **`bars_recent`** slice — not identical to the full three-bar `bars_recent_oldest_to_newest` narrative in hand-authored seed. Training still sees coherent JSON; **fidelity vs live chart** is a separate audit question.
3. **`learning_record_candidate_v1.decision_taken`** and **`Final_status`** use exporter mapping (`outcome_to_final_status`) — should be spot-checked against a handful of ledger rows for **semantic** match (not just JSON validity).
4. **Merge hygiene:** appending export JSONL into the **tracked** seed twice **duplicates** lines — prefer a **dedicated merged file** under `/data` + `--dataset`, or one intentional commit.

---

## 3. Workstream boundary (unchanged)

- **`prove_learning/`** — learning loop, ledger, exporter source.
- **`training/`** — corpus, validator, launcher, `train_qlora`, verifier.
- **Operator** merges validated export into whatever file the next QLoRA run uses (`--dataset`).

---

## 4. Suggested next actions (for review / edit)

1. Learning engineer: **annotate Section 2C** if lab expects different bar packet or `Final_status` mapping rules.  
2. Training engineer: **add two ENTER gold rows** to seed (or approve merged JSONL only), **re-validate**, then schedule next **full** run on trx40.  
3. Operator: **record last trx40 HEAD commit + artifact paths** in a line below when known.

---

*Last updated from repo state at authoring time; learning engineer may append rows or corrections below.*

### Learning engineer addendum

*(space for additions)*

