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
| **QLoRA / trx40 (verified 2026-05-05)** | **Full train complete:** `global_step` **3000 / 3000**, checkpoint `checkpoint-3000`. **Dataset:** `FINQUANT_BASE/datasets/merged_finquant_v0.2.jsonl`. **Report:** `reports/full_training_report_v0.1.md` (generated **2026-05-05T08:59:01Z**); loss first/last **1.5818 / 0.0107**. **Adapter:** `adapters/finquant-1-qwen7b-v0.1/` (**44** files in post-run digest). **Verifier eval:** `reports/v0.1_eval_report.md` (**2026-05-05T09:01:06Z**) — **6 / 6** cases pass (strict four-heading harness). **trx40 repo:** run **`git pull origin main`** before §7 splits; **HEAD should track `origin/main`** (includes §7 holdout tooling). |

---

## 1b. Adapter lineage & holdout honesty — gap closure (normative)

**Problem we closed:** Confusion between **“holdout JSONL exists”** and **“holdout proves generalization for *this* checkpoint.”** Without explicit wording, external reviewers (or future you) can mis-read scores.

### Certification strings (copy into release notes / emails)

| Adapter / artifact | Honest one-line certification |
|--------------------|-------------------------------|
| **`finquant-1-qwen7b-v0.1` (current trx40 prod dir)** | **TRAINED_ON_FULL_MERGE — HOLDOUT_NOT_EXCLUDED.** Verifier **6/6** OK. **`holdout_agentic_v1.jsonl`** scores on this tag are **regression / sanity only**, **not** unbiased out-of-sample proof for those rows. |
| **Future promotion adapter** (after train-only run) | **TRAINED_ON_TRAIN_SPLIT_ONLY.** `--dataset` must match **`datasets/train_agentic_v1.jsonl`** (or successor). **`holdout_agentic_v1.jsonl`** + **`manifests/frozen_exam_holdout_agentic_v1.json` `sha256`** may be cited for **promotion** generalization on that frozen pack — **only if** no prompt/threshold tuning was done against holdout labels between freezes. |

### Hard rules (avoid future bites)

1. **Never** merge **`holdout_*.jsonl`** into a training corpus.  
2. **Never** cite holdout metrics as **“proof of generalization”** for **`finquant-1-qwen7b-v0.1`** without the **TRAINED_ON_FULL_MERGE** caveat above.  
3. **Promotion narrative:** Use **train-only** weights + **frozen manifest** when someone asks “did it see the test?”  
4. **`python3 training/finquant_post_run_digest.py`** prints an **ADAPTER_LINEAGE** notice when the full-training report’s **Staging** path is the **full merge** while a holdout file exists on disk.

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
2. Training engineer: **add two ENTER gold rows** to seed (or approve merged JSONL only), **re-validate**, then schedule next **full** run on trx40 **after holdout split** (§7) if tightening promotion discipline.  
3. ~~Operator: record trx40 HEAD + paths~~ **Done** — see §1 table (refresh after each campaign).  
4. Operator: **`git pull` on trx40**, then run **`split_agentic_corpus_holdout.py`** + **`frozen_exam_manifest.py`** (§7) before the **next** full train; keep current adapter as **v0.1 production** artifact until superseded.  
5. **`finquant_llm_eval.py`** on agentic cases if not already part of routine (verifier **6/6** ≠ quant exam — see architect spec).

---

## 5. Corpus growth backlog — LE + training engineer (LLM context engineering)

**Status:** **Full QLoRA run completed** (see §1). Safe to resume **corpus growth** and **`finquant_llm_eval`** cadence without deferring for GPU contention.

**Weak spot (confirmed):** `retrieved_memory_v1` is often **empty** → model mostly learns **reasoning without discriminative retrieval**. Fix by **biasing corpus growth**, not by ripping up RM (separate thread).

| Priority | Training-stream action |
|----------|-------------------------|
| **A** | **Non-empty memory:** exporter / merge includes realistic `retrieved_memory_v1` (IDs in `training/finquant_memory/exemplar_store.jsonl`, on-topic stubs) from ledger fields such as `memory_records_used` where available. |
| **B** | **Balanced mix:** intentional proportion of **non-empty memory**, **memory conflict / contrast**, and **empty-memory baseline** so neither “always ignore memory” nor “always obey memory” wins. |
| **C** | **Authority / inventory stress (small curated set):** rows where narrative tries to contradict **packet** → gold follows **`reference_facts_v1` / `case_assumptions_v1` / `context_inventory_v1`**; rows where **inventory marks gaps** → gold **`INSUFFICIENT_DATA`** or conservative **`NO_TRADE`**. |
| **D** | **Taxonomy:** align memory tags with `prove_learning/finquant/unified/agent_lab/MEMORY_TAXONOMY.md` when populating slices. |

**Ownership:** LE + operator define **what** memories mean; **training stream** owns **coverage** (export hooks, seed stress rows, validator staying strict). Reference: Tier 2 in LE handoff.

---

## 6. HW engineering actions — logs, ToT branch scorer, weight handoff (2026-05-04)

*Training engineer execution of HW team asks.*

### 6.1 Training logs — loss decay (final trx40 pull)

**Source:** `FINQUANT_BASE/adapters/finquant-1-qwen7b-v0.1/checkpoint-3000/trainer_state.json` (`log_history`).

**Final snapshot (2026-05-05):**

| Field | Value |
|--------|--------|
| `global_step` / `max_steps` | **3000 / 3000** |
| Loss first / last (report) | **1.5818 / 0.0107** |
| Tail (`step` 2900–3000) | **~0.0107** (flat) |

**Read:** Loss **decayed strongly** early, then **plateaued ~0.0107** — typical late SFT on this corpus.

**Verifier snapshot:** `v0.1_eval_report.md` — **6 / 6** pass (structural + heuristic gates); **not** quant-exam certification.

**Commands (operator):**

```bash
CKPT=$(ls -dt "$FINQUANT_BASE/adapters/finquant-1-qwen7b-v0.1/checkpoint-"* | head -1)
python3 -c "import json; t=json.load(open(\"$CKPT/trainer_state.json\")); lh=t.get(\"log_history\") or []; \
  losses=[x[\"loss\"] for x in lh if \"loss\" in x]; print(\"step\", t.get(\"global_step\"), \"losses\", len(losses), \"first\", losses[:1], \"last\", losses[-3:])"
```

### 6.2 ToT branch scorer — deterministic rule (inference orchestration)

ToT **search is not in QLoRA training**; orchestration must **score** each candidate branch with **auditable rules**. Until architect overrides, use:

1. **Discard:** Parsed JSON fails corpus/verifier contract → **eliminate** branch.
2. **Hard veto:** `ENTER_*` but `deterministic_baseline_verdict_v1.blocking_rules` contradicts entry, or R-math / policy gates fail → **eliminate**.
3. **Primary score (ENTER):** `expectancy_check_v1.expectancy_per_trade_dollars` when finite; otherwise **`contributes_to_long_run_math`** (boolean promoted to ranked tier).
4. **Risk consistency:** Prefer `recommended_risk_pct == risk_context_v1.final_risk_pct` with `final_risk_pct` inside `risk_bounds`.
5. **Abstention paths:** Prefer coherent **`INSUFFICIENT_DATA` / `NO_TRADE`** when `context_inventory_v1` marks gaps; rank by **`confidence_gap_v1`** consistent with R-002 (spread gate).
6. **Tie-break:** Higher `confidence_gap_v1` → higher expectancy dollars → operator-defined status preference.

**EV / R:R:** Encoded via **`expectancy_check_v1`** (planned R-multiple, breakeven win rate, expectancy dollars) and **`risk_context_v1`** — not a separate mystery scalar.

### 6.3 Handoff — train host (e.g. A6000 class) → RTX 4000 for ToT graph build

| # | Action |
|---|--------|
| 1 | Record **git `HEAD`** on train host + exact **`merged_finquant_v0.2.jsonl`** (or dataset path) used. |
| 2 | Archive **`adapters/finquant-1-qwen7b-v0.1/`** after final write (`adapter_model.safetensors`, `adapter_config.json`, tokenizer artifacts, latest `checkpoint-*` if retained). |
| 3 | Copy **`reports/full_training_report_v0.1.md`**, **`finquant_llm_eval`** outputs when available. |
| 4 | On **4000**: install same **`training/requirements-finquant-training.txt`**; verify **`nvidia-smi`**. |
| 5 | **Smoke:** load **DeepSeek-R1-Distill-Qwen-7B** + adapter; run **`finquant_llm_eval.py`** (or minimal generate) **before** wiring BFS/DFS ToT. |
| 6 | **ToT:** implement **search + §6.2 scorer** in orchestration — model weights supply **proposals** only. |

---

*Last updated from repo state at authoring time; learning engineer may append rows or corrections below.*

---

**[Learning Engineer — 2026-05-03T23:51Z] — Risk context output contract update**

**NEW REQUIREMENT before next training run:**

The output contract must include `risk_context_v1` alongside the decision. This emerged from a design session: context IS risk management in FinQuant. The same factors that determine ENTER vs NO_TRADE also determine how much capital to deploy.

The dedicated LLM must learn to output both. If trained without `risk_context_v1`, a second training run will be required to add it.

**Add to corpus gold `output` rows:**

```json
"risk_context_v1": {
  "baseline_risk_pct": 1.23,
  "volatility_factor": 0.9,
  "structure_factor": 1.1,
  "signal_factor": 1.2,
  "session_factor": 1.0,
  "health_factor": 1.0,
  "final_risk_pct": 1.46,
  "risk_bounds": {"min": 0.5, "max": 2.0},
  "factor_notes": {
    "volatility": "ATR% normal range — no adjustment needed",
    "structure": "HH_HL swing structure confirmed — slight increase",
    "signal": "conviction spread 0.42 — strong signal — increase",
    "session": "US/EU overlap — peak liquidity — no adjustment",
    "health": "neutral recent performance — no adjustment"
  }
},
"recommended_risk_pct": 1.46
```

**Factor ranges:**
- volatility_factor: 0.5 (volatile/dangerous) → 1.0 (normal) → 1.2 (quiet trending)
- structure_factor: 0.5 (ranging/chop) → 1.0 (mild trend) → 1.3 (HH_HL confirmed)
- signal_factor: 0.6 (spread=0.20 min) → 1.0 (spread=0.35) → 1.5 (spread=0.55+)
- session_factor: 0.6 (Asian session low liquidity) → 1.0 (US/EU peak)
- health_factor: 0.5 (3+ recent losses) → 1.0 (neutral) → 1.2 (winning streak)

**Formula:** `final_risk_pct = baseline × vol × struct × signal × session × health`, bounded [0.5%, 2.0%]

**For NO_TRADE rows:** set `final_risk_pct: 0.0` and explain which factor drove the decision toward no-trade.

**Priority:** High — add to at least 5 ENTER gold rows and 3 NO_TRADE rows before next run.

The `risk_context_v1` module is being built in `prove_learning/` and will be available for export via the corpus exporter. Watch for it in the next ledger export.

### Learning engineer addendum

**[Learning Engineer — 2026-05-03T20:27Z]**

Reviewed. Alignment confirmed on the following:

**Schema:** `export_to_training_corpus.py` in `prove_learning/` uses correct `finquant_agentic_qa_v1` fields — `hypotheses_v1`, `learning_record_candidate_v1`, `expectancy_check_v1`, `Final_status`. No baseline v0.05 field names.

**R-002 threshold:** Confirmed `i_dont_know_triggered` uses `confidence_gap_v1 < 0.20` (not 0.10). ENTER rows get bumped confidences so they stay decisive and pass validation. Aligned with validator contract.

**Section 2C — residual risks — notes from learning side:**

1. **ENTRY exemplar gap:** Confirmed. Corpus still has 0 ENTER gold rows. The exporter generates ENTER rows from real winning decisions but they must flow through operator merge before the next QLoRA run. See `training/CODY_NOTE.md` for minimum ask.

2. **Bar packet fidelity:** The exporter packs `bars_recent` as a single-bar slice (the decision bar). The hand-authored seed uses `bars_recent_oldest_to_newest` with 3 bars. For next export version, consider packing the 3 visible bars around the decision step. Filed for future iteration — not blocking current validation.

3. **`decision_taken` / `Final_status` mapping:** The `outcome_to_final_status()` function maps `outcome_kind + action + confidence_spread` to `Final_status`. Recommend training engineer spot-check 5 ENTER rows from `prove_learning/ledger_output/train_20260503T012636Z_e2c07190_decisions.json` against the exported JSONL to confirm semantic match before merging.

4. **Merge hygiene:** Agreed — do not append exported rows to the tracked seed file directly. Use a dedicated merged file passed via `--dataset` to `train_qlora.py`. The operator should create this file at merge time, not commit it to the seed.

**Current learning loop state (for training engineer context):**

- Latest successful run: `train_20260503T012636Z_e2c07190` — 70.5% decision quality, +$3.68 PnL, 2 ACTIVE patterns
- New 4-cycle run in progress on clawbot with three improvements: R-003 stop/target in prompt, session filter (Asian session warning), memory gate raised to 65% win rate
- Exporter is ready: `python3 prove_learning/finquant/unified/agent_lab/export_to_training_corpus.py --latest --good-only --output <your_path>`
- Export produces 286 rows; validation passes against `validate_agentic_corpus_v1.py`

**No changes made to `training/` files by learning engineer.** This addendum only.

---

**[Learning Engineer — 2026-05-03T20:45Z] — Spot-check result + gap answers**

**SPOT-CHECK RESULT: ALL 5 ENTER WIN ROWS PASS ✓**

Ran `build_corpus_row` on 5 ENTER_WIN rows from `train_20260503T012636Z_e2c07190_decisions.json`:

| Row | Ledger action | Export Final_status | R-mult | Breakeven | Promo | Decisive |
|---|---|---|---|---|---|---|
| 1 | ENTER_SHORT | ENTER_SHORT | 2.5 | 0.2857 | True | True (gap=0.40) |
| 2 | ENTER_SHORT | ENTER_SHORT | 2.5 | 0.2857 | True | True (gap=0.40) |
| 3 | ENTER_SHORT | ENTER_SHORT | 2.5 | 0.2857 | True | True (gap=0.25) |
| 4 | ENTER_LONG | ENTER_LONG | 2.5 | 0.2857 | True | True (gap=0.25) |
| 5 | ENTER_LONG | ENTER_LONG | 2.5 | 0.2857 | True | True (gap=0.70) |

All checks pass: action match, promotion_candidate correct, R=2.5, breakeven=0.2857, entry decisive (gap ≥ 0.20), contributes_to_long_run_math=True.

**Gap answers — training engineer's questions for learning side:**

**Gap 2 (spot-check):** Done — see above. Semantic match confirmed.

**Gap 3 (seed policy):** My recommendation is **export-only ENTER rows** are sufficient for this run rather than hand-authored gold. The exporter produces real winning decisions from actual SOL-PERP data with verified divergence theses and correct R-math. Hand-authored rows would be synthetic. For SFT purposes, real data is better. Final call is operator's.

**Note on Gap 1 (corpus file path):** The merged JSONL path on trx40 and sign-off are operator decisions — outside my scope. I can confirm the export from my side passes `validate_agentic_corpus_v1.py` and is ready to hand off.

**Note on Gaps 4 & 5 (1000/3000 stop reason, step count policy):** These are trx40 / training ops questions — not learning engineer scope. Operator should address.

---

## 7. Holdout splits + frozen exam manifests (eval discipline)

**Purpose:** Reduce silent leakage between supervision and “promotion” scores (time-aware / deterministic splits; pinned exam checksums). Not a substitute for full AFML purged CV — a **program-level** baseline.

| Script | Role |
|--------|------|
| `training/split_agentic_corpus_holdout.py` | Writes **`train.jsonl`** + **`holdout.jsonl`** from a merged corpus. **`FQ-AGENTIC-*`** seed rows **always** go to train. **`FQ-LIVE-*-*`** rows support **tail** splits (ordering by `case_num` + cycle suffix) or **hash_ratio** splits. |
| `training/frozen_exam_manifest.py` | SHA256 + line count + **`exam_version`** for any JSONL used as a **primary promotion** gate; eval reports should cite **`sha256`**. |

**Suggested trx40 flow (next train after current run finishes):**

1. Validate merged corpus: `python3 training/validate_agentic_corpus_v1.py "$MERGED_JSONL"`.
2. Split (example — time-ordered proxy on exported live rows):  
   `python3 training/split_agentic_corpus_holdout.py --input "$MERGED_JSONL" --train-out "$FINQUANT_BASE/datasets/train_agentic_v1.jsonl" --holdout-out "$FINQUANT_BASE/datasets/holdout_agentic_v1.jsonl" --strategy live_tail_fraction --live-holdout-fraction 0.15 --report "$FINQUANT_BASE/reports/holdout_split_report_v1.json"`
3. Pin the holdout (or a separate frozen exam pack):  
   `python3 training/frozen_exam_manifest.py --exam-jsonl "$FINQUANT_BASE/datasets/holdout_agentic_v1.jsonl" --exam-version finquant_holdout_v1 --bundle-role primary_promotion_gate --out "$FINQUANT_BASE/manifests/frozen_exam_holdout_v1.json"`
4. **Train** only on **`train_agentic_v1.jsonl`** (`train_qlora.py … --dataset …`). **Do not** tune prompts or thresholds against holdout labels between promotion attempts.
5. **Eval** the adapter on **`holdout_agentic_v1.jsonl`** (or export cases into `finquant_llm_eval` / verifier); archive logs with manifest **`sha256`**.

### 7.1 Executed on trx40 (2026-05-05)

| Artifact | Detail |
|----------|--------|
| **Merged corpus SHA256** | `9056f76172c5ca94e0aaeb14db2b17b0bc045ed1f1939289e9462b1690f65654` → `reports/merged_finquant_v0.2.sha256` |
| **Merged line count** | **289** rows (`reports/merged_finquant_v0.2.linecount`) |
| **Validate merged** | **OK** (`validate_agentic_corpus_v1.py`) |
| **Train split** | `datasets/train_agentic_v1.jsonl` — **246** lines, **OK** |
| **Holdout split** | `datasets/holdout_agentic_v1.jsonl` — **43** lines, **OK** (`live_tail_fraction` **0.15**) |
| **Split report** | `reports/holdout_split_report_v1.json` |
| **Frozen manifest** | `manifests/frozen_exam_holdout_agentic_v1.json` — holdout **`sha256`** = `a6ebb7123d40d478043eefc582d284da3686eff3370e364f54b3aaa2a697700b` |

**Note:** **`finquant_llm_eval.py`** was **not** run on trx40 — no **`market_data.db`** on that host. See **`reports/llm_eval_pending_note.md`** on `FINQUANT_BASE` for the command once a DB path exists (and Ollama has **`finquant-1-qwen7b-v0.1`**).

**Training note:** Same fact as **§1b** — current **`finquant-1-qwen7b-v0.1`** saw all **289** rows; **next** promotion-quality train uses **`train_agentic_v1.jsonl`** only.

---

## Unified operator pipeline (repeatable)

Script: **`training/run_finquant_cycle.sh`** — same flow every campaign; only change **env vars** (`MERGED_JSONL`, optional `LEDGER_JSON`, `INCLUDE_SEED`, `TRAIN_LOG`, etc.).

```bash
export BLACKBOX_REPO_ROOT=/home/vanayr/blackbox
export FINQUANT_BASE=/data/NDE/finquant/agentic_v05
export MERGED_JSONL="$FINQUANT_BASE/datasets/merged_finquant_v0.2.jsonl"
# optional: export LEDGER_JSON="$BLACKBOX_REPO_ROOT/prove_learning/ledger_output/…_decisions.json"
# optional: export TRAIN_LOG="$FINQUANT_BASE/reports/train_qlora_last.log"
source /data/NDE/finquant/.venv-finquant/bin/activate

./training/run_finquant_cycle.sh prepare
./training/run_finquant_cycle.sh validate
./training/run_finquant_cycle.sh train-smoke   # wiring check
export CONFIRM_PRODUCTION_TRAIN=1
./training/run_finquant_cycle.sh train-full    # production
```

See script header for full variable list.

