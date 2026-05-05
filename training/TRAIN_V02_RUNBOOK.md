# FinQuant v0.2 Training Runbook

**Purpose:** Remediation run following adversarial exam FAIL (2026-05-05).  
**Adapter target:** `finquant-1-qwen7b-v0.2`  
**New data:** 100 targeted rows (`remediation_corpus_v0.3.jsonl`) covering 5 hard failure categories.

---

## Prerequisites

- trx40 SSH access (`vanayr@172.20.1.66`)
- GPU free (RTX A6000 — check with `nvidia-smi`)
- `FINQUANT_BASE=/data/NDE/finquant/agentic_v05`

---

## Step 1 — Pull latest repo

```bash
ssh vanayr@172.20.1.66
cd ~/blackbox
git pull origin main
```

Expected: `training/remediation_corpus_v0.3.jsonl` and `training/config_v0.2.yaml` present.

---

## Step 2 — Build merged v0.3 corpus

```bash
export FINQUANT_BASE=/data/NDE/finquant/agentic_v05
source /data/NDE/finquant/.venv-finquant/bin/activate

# Merge train split + remediation rows
cat $FINQUANT_BASE/datasets/train_agentic_v1.jsonl \
    ~/blackbox/training/remediation_corpus_v0.3.jsonl \
    > $FINQUANT_BASE/datasets/merged_finquant_v0.3.jsonl

# Count rows (expect ~346)
wc -l $FINQUANT_BASE/datasets/merged_finquant_v0.3.jsonl
```

---

## Step 3 — Validate

```bash
python3 ~/blackbox/training/validate_agentic_corpus_v1.py \
    $FINQUANT_BASE/datasets/merged_finquant_v0.3.jsonl \
    --store ~/blackbox/training/finquant_memory/exemplar_store.jsonl
```

Expected: `OK — /data/NDE/finquant/agentic_v05/datasets/merged_finquant_v0.3.jsonl`

---

## Step 4 — Smoke run (wiring check, ~5 min)

```bash
tmux new-session -s fq_v02_smoke \
  "source /data/NDE/finquant/.venv-finquant/bin/activate && \
   export FINQUANT_BASE=/data/NDE/finquant/agentic_v05 && \
   python3 ~/blackbox/training/train_qlora.py smoke \
     --config ~/blackbox/training/config_v0.2.yaml \
     --dataset \$FINQUANT_BASE/datasets/merged_finquant_v0.3.jsonl \
     --base \$FINQUANT_BASE \
     2>&1 | tee \$FINQUANT_BASE/reports/smoke_v02.log; echo SMOKE_DONE"
```

Check: `tmux attach -t fq_v02_smoke` — confirm no errors, loss starts decreasing.

---

## Step 5 — Full train (~18-24h)

```bash
tmux new-session -s fq_v02_train \
  "source /data/NDE/finquant/.venv-finquant/bin/activate && \
   export FINQUANT_BASE=/data/NDE/finquant/agentic_v05 && \
   python3 ~/blackbox/training/train_qlora.py full \
     --config ~/blackbox/training/config_v0.2.yaml \
     --dataset \$FINQUANT_BASE/datasets/merged_finquant_v0.3.jsonl \
     --base \$FINQUANT_BASE \
     2>&1 | tee \$FINQUANT_BASE/reports/train_v02.log; echo TRAIN_DONE"
```

Monitor: `tmux attach -t fq_v02_train`  
Do NOT detach with `exit` — use `Ctrl+B, D` to detach safely.

---

## Step 6 — Post-run digest

```bash
python3 ~/blackbox/training/finquant_post_run_digest.py \
    --adapter adapters/finquant-1-qwen7b-v0.2
```

Expected: `adapter_files > 0`, `full_training_report_v0.1.md` present.  
The digest will also print `ADAPTER_LINEAGE` note confirming train-only dataset.

---

## Step 7 — Merge v0.2 adapter and re-run exam

```bash
python3 ~/blackbox/training/merge_adapter_to_ollama.py \
    --adapter $FINQUANT_BASE/adapters/finquant-1-qwen7b-v0.2 \
    --model-tag finquant-1-qwen7b-v0.2

python3 ~/blackbox/training/exams/finquant_exam_proctor.py \
    --cases ~/blackbox/training/exams/finquant_adversarial_exam_v1_cases.jsonl \
    --model finquant-1-qwen7b-v0.2 \
    --ollama-url http://localhost:11434 \
    --out $FINQUANT_BASE/reports/exam_results/ \
    --run-label finquant_v0.2_certification
```

**Pass criteria:** Economic ≥ 75%, Process ≥ 80%, zero hard rule violations.  
**Exam SHA256 to cite:** `6cc73f9b9d9db310dcf644c594b702228011a5e1a07e314308f52aeb255aa7e7`

---

## Certification string (if passes)

```
FinQuant quant exam v3 PASS — finquant-1-qwen7b-v0.2 — [date]
Exam SHA256: 6cc73f9b9d9db310dcf644c594b702228011a5e1a07e314308f52aeb255aa7e7
Dataset: merged_finquant_v0.3.jsonl (346 rows, train-only split)
```
