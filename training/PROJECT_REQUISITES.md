# FinQuant training — project requisites (isolated copy)

Canonical for work under `training/` until this module is promoted into the wider repo.

## Workstream isolation (do not cross threads)

- **This folder** is **FinQuant LLM training + verifier gate** only — not the general Student / learning-loop / NDE graph thread.
- **Authoring** for this effort stays under `training/` (corpus, validators, launcher, `verifier_eval_finquant.py`).
- **trx40 / RTX 40:** sync with `git pull` on the same branch you use here; keep large artifacts on **`FINQUANT_BASE`** under `/data` (see RTX 40 launcher section).
- **Upstream note:** `training/verifier_eval_finquant.py` is a **training-local copy** of the verifier eval; merge from `prove_learning/finquant/evals/eval_finquant.py` only when you intentionally refresh — daily work does not go through `prove_learning/`.

## Corpus packaging (`finquant_agentic_qa_v1`)

Each JSONL row is one object with:

- `case_id`, `exam_schema` (`finquant_quant_exam_v1` where aligned), `primary_category`, `training_schema`: `finquant_agentic_qa_v1`
- `instruction`: operator-facing task text (what the model must do).
- `input`: structured payload (`case_assumptions_v1`, `reference_facts_v1`, `expected_output_contract_v1`, `retrieved_memory_v1`).
- `output`: gold assistant JSON (see below).
- `grading_v1`: optional machine checks for builders.

`Final_status` values used in this pack: `NO_TRADE`, `INSUFFICIENT_DATA`, and exam-aligned `PASS` / `FAIL` when a quant category requires them.

## FinQuant prime directive (v1)

**P-1 — Never lie.** If you do not know, say so and stop. Fabricated evidence, fabricated retrievals, or false confidence is worse than no answer.

**P-2 — Reason with tools.** Use the deterministic baseline narrative, stated features, and retrieved memory. Test hypotheses; do not vibe-decide.

**P-3 — Risk-averse default.** Default state is `NO_TRADE`. Entries require confluence and context fit. Loss per trade is capped by the risk slice, not by conviction.

**P-4 — Pattern similarity.** Retrieve prior cases that match the regime signature; anchor judgment in evidence.

**P-5 — Context first.** Indicator values mean different things in different regimes; read regime before applying rules.

**P-6 — Long-run math.** Optimize dollars won minus dollars lost over the sample, not headline win rate. Many small losses can be acceptable if wins carry asymmetric R.

## R-001 — Risk-averse, positive-expectancy reasoning

Aligned with deterministic Jupiter-style baseline semantics used in training narratives:

1. **Asymmetric R:** Target versus stop reflects positive expectancy when edge is real (training cases cite planned R-multiple explicitly).
2. **Bounded risk:** Risk per trade derives from risk budget × equity, then position size — not the reverse.
3. **Default `NO_TRADE`.** Entry narratives require filter and confluence language consistent with the case baseline.
4. **Exits:** When cases describe open positions, exits follow stated policy (stops/targets/trailing as given); model does not invent discretionary exits unless the case asks for interpretation only.
5. **Audit trail:** Reasoning cites which baseline rules or gates supported `NO_TRADE` or entry.

## R-002 — Hypothesis-driven reasoning and threshold proposals

1. Every decision case includes **at least two** explicit hypotheses with supporting evidence from `reference_facts_v1`, counter-evidence, and a numeric `confidence` in `[0, 1]`.
2. Let the top two confidences be `c1 ≥ c2`. If `c1 - c2 < 0.20`, set `i_dont_know_triggered: true` and `Final_status: INSUFFICIENT_DATA` unless the case gold specifies otherwise.
3. Threshold adjustments toward baseline parameters are allowed only when **more conservative** (stricter filters). **Less conservative** proposals are invalid for gold rows.
4. Any threshold adjustment that is not `no_change` must list `evidence_memory_ids[]` and each id **must exist** in `training/finquant_memory/exemplar_store.jsonl`.

## R-003 — Long-run math (`expectancy_check_v1`)

When the case involves a trade decision, `output.expectancy_check_v1` must include at minimum:

- `planned_r_multiple`, `planned_risk_dollars`, `breakeven_win_rate_required`, `contributes_to_long_run_math` (boolean), and where applicable `expectancy_per_trade_dollars`.

Model narrative must treat breakeven win rate as \(1 / (1 + R)\) for reward:risk ratio \(R\) when that is the case assumption.

## Seed corpus

- File: `training/corpus_v05_agentic_seed.jsonl` (authoritative examples).
- Memory store: `training/finquant_memory/exemplar_store.jsonl`.
- Validator: `python3 training/validate_agentic_corpus_v1.py [corpus.jsonl] [--store path]`.

## RTX 40 launcher (SSH / tmux)

One entry point on the GPU host after `cd` to repo root:

- `python3 training/test.py --help` (alias)
- `python3 training/run_finquant_rtx40_event.py --help`

**Smoke vs production:** the launcher prints an explicit **TRAIN PROFILE** banner and a distinct final line:

| `--train` | Meaning | Confirmation |
|-----------|---------|--------------|
| `smoke` (default) | Short QLoRA — wiring / sanity | None |
| `full` | Production-length run per YAML | **Requires `--confirm-production-train`** |
| `none` | Validate (and optional exam) only | None |

Final lines: `FINQUANT_RTX40_EVENT_COMPLETE_TRAIN_SMOKE`, `…_TRAIN_FULL_PRODUCTION`, or `…_NO_TRAIN`.

Flow: validate agentic corpus → optional QLoRA → **verifier exam** via `training/verifier_eval_finquant.py` (or `FINQUANT_VERIFIER_EVAL_PY` / `--eval-script`). Normative `final_exam_v1.json` is **announced** (`FINQUANT_FINAL_EXAM_JSON` or `/data/NDE/finquant/eval/final_exam_v1.json`); when `cases` is non-empty, quant LLM grading can be added later without renaming the launcher.

Suggested `/data` layout under `FINQUANT_BASE` (e.g. `/data/NDE/finquant/agentic_v05`): `datasets/`, `finquant_memory/`, `adapters/`, `reports/`.
