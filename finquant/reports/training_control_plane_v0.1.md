# FinQuant Training Control Plane — Design v0.1

**Status:** Normative design — implementation follows in phased rollout.  
**Deploy mirror:** `/data/finquant-1/reports/training_control_plane_v0.1.md`  
**Scope:** Govern FinQuant-1 training/eval without replacing existing scripts (`source_to_training.py`, `train_qlora.py`, `eval_finquant.py`). Those remain **execution engines**; the control plane **schedules, versions, gates, and audits** them.

**NDE Factory:** This control-plane pattern applies to **NDE: FinQuant** first; the cross-domain factory framing is **`finquant/reports/nde_factory_v0.1.md`**.

---

## 1. Stack recommendation

| Layer | Choice | Role |
|-------|--------|------|
| Orchestration | **Prefect** | Queueable/resumable workflows, retries, human-in-the-loop blocks, run history. |
| Experiment & artifacts | **MLflow** | Metrics, params, artifacts, dataset lineage hooks, **model registry** for adapters ([MLflow datasets](https://mlflow.org/docs/latest/ml/dataset/)). |
| Dataset versioning | **DVC** *or* **manifest hashing** (repo baseline) | Content-addressed datasets / deterministic hashes aligned with existing staging JSONL + `manifest.json`; DVC optional if Git+LFS acceptable on host. |
| Runtime | **Docker** | Pin CUDA, PyTorch, HF stack; match `requirements-finquant-training.txt`; reproducible agents on trx40. |
| Trainer | **Existing Python** | TRL/HF QLoRA unchanged ([TRL PEFT](https://huggingface.co/docs/trl/peft_integration)); invoke via subprocess from Prefect tasks. |

**Verdict:** **Prefect + MLflow + Docker** is the **recommended core** for FinQuant v0.1. **DVC** is **recommended** where operators want Git-bound dataset reproducibility; otherwise **SHA256 manifests** already produced by `source_to_training.py` + `dataset_proof.py` satisfy **minimum** dataset versioning until DVC is adopted.

---

## 2. Principles

1. **Wrap, don’t fork:** `train_qlora.py`, `eval_finquant.py`, and dataset pipeline steps are **CLI subprocess targets** with injected env and paths.
2. **One run folder per logical job:** `/data/finquant-1/runs/<run_id>/` is source of truth for logs and pointers.
3. **Promotion is opt-in:** eval pass + **operator approval** before registry “Production” or export routing.
4. **VRAM safety:** workflow **pre-flight** gates training when GPU memory is below threshold or when conflicting processes (e.g. Ollama) hold VRAM.

---

## 3. Identifier schemes

| Concept | Format | Example |
|---------|--------|---------|
| **run_id** | `fq-{utc_compact}-{short_rand}` | `fq-20260429T143022-a3f9c2` |
| **dataset_version_id** | `ds-{sha256[:12]}-{staging_name]` | `ds-a1b2c3d4e5f6-finquant_staging_v0.1` |
| **config_version_id** | `cfg-{sha256[:12]}-{basename]` | `cfg-9e8d7c6b5a43-config_v0.1` |
| **adapter_version_id** | Same as MLflow **registered model version** or `{run_id}-adapter` until registry | `fq-...-adapter@v3` |

**MLflow experiment naming:**

- `finquant-training` — parent experiment.
- Tags: `phase`=`dataset_build`|`proof`|`train`|`eval`, `mode`=`smoke`|`full`, `finquant_version`=`v0.1`.

---

## 4. Job submission format (API / CLI contract)

**Canonical payload (JSON)** stored as `runs/<run_id>/submit.json`:

```json
{
  "run_id": "fq-20260429T143022-a3f9c2",
  "dataset_ref": {
    "type": "staging_jsonl",
    "path_relative": "datasets/staging/finquant_staging_v0.1.jsonl",
    "dataset_version_id": "ds-a1b2c3d4e5f6-finquant_staging_v0.1"
  },
  "config_ref": {
    "path_relative": "training/config_v0.1.yaml",
    "config_version_id": "cfg-9e8d7c6b5a43-config_v0.1"
  },
  "mode": "smoke",
  "requested_by": "operator|ci",
  "dry_run": false
}
```

**CLI mapping (minimum target):**

```bash
finquantctl submit --dataset datasets/staging/finquant_staging_v0.1.jsonl \
  --config training/config_v0.1.yaml --mode smoke
finquantctl submit --dataset ... --config ... --mode full
finquantctl status <run_id>
finquantctl eval <run_id>
finquantctl promote <run_id>
```

`submit` creates `run_id`, materializes `runs/<run_id>/`, writes `submit.json` + resolved snapshot, enqueues Prefect flow.

---

## 5. End-to-end flow (governed)

1. **Artifact intake:** New source/data/config arrives (Git pull, artifact upload, or manifest bump).
2. **Dataset build** (optional step): `source_to_training.py pull` / `build` — subprocess; hashes recorded → **dataset_version_id**.
3. **Dataset proof gate:** `dataset_proof.py` — **must exit 0**; else run → `failed`, no train.
4. **VRAM pre-flight:** Check `nvidia-smi`; if free VRAM < **N MiB** or **Ollama**/configured denylist processes present → **blocked** (queued or failed per policy), **no train**.
5. **Training:** `train_qlora.py {smoke|full}` — MLflow **start_run**, log params/hyperparams from resolved YAML, stream metrics (loss), **artifact** adapter dir.
6. **Eval gate:** `eval_finquant.py` — **artifact** eval report; MLflow metrics e.g. `eval.pass_count`.
7. **Promotion gate:** If eval criteria met → state **pending_promotion**; **operator** must `promote` (or UI) → MLflow registry transition; else **rejected**.

---

## 6. Run folder layout

**Path:** `/data/finquant-1/runs/<run_id>/`

| File / dir | Purpose |
|-------------|---------|
| `submit.json` | Original request. |
| `resolved/config.yaml` | Snapshot of config used (symlink or copy). |
| `resolved/dataset_manifest.json` | Hashes, paths, `dataset_version_id`. |
| `logs/train.stdout`, `logs/train.stderr` | Captured subprocess logs. |
| `logs/preflight.json` | VRAM/process check results. |
| `mlflow/run_id.txt` | MLflow run UUID. |
| `artifacts/adapter/` | Symlink or copy to `FINQUANT_BASE/adapters/...` for this run. |
| `artifacts/eval_report.md` | Eval output. |
| `promotion.json` | `{ "status": "pending|approved|rejected", "by": "...", "ts": "..." }` |
| `FAILED.txt` | Present if failed; contains reason. |
| `state.json` | Machine-readable: `smoke|full|failed|promoted|rejected|blocked_vram`. |

---

## 7. Failure handling & resume

| Scenario | Behavior |
|----------|----------|
| Proof fails | Run **failed**; no train; `FAILED.txt`. |
| Train OOM | Mark **failed**; MLflow **FAILED**; optional **resume** from last HF checkpoint if `train_qlora` checkpoint exists (same `run_id` retry policy). |
| Eval fails promotion thresholds | **completed_train_failed_eval**; adapter retained as artifact; **no promotion**. |
| Preflight VRAM | **blocked** (not failed): retry with backoff or operator clears Ollama. |

**Resume policy:** New Prefect **retry** of same flow only if `state.json` allows **idempotent** resume (e.g. skip proof if dataset hash unchanged and proof artifact exists). Otherwise **new run_id**.

---

## 8. Operator approval & notifications

- **Promotion:** CLI `finquantctl promote <run_id>` updates `promotion.json` and MLflow registry stage (e.g. Staging → Production).
- **Notifications (minimal):** Webhook URL env `FINQUANT_NOTIFY_WEBHOOK` **or** append-only log `/data/finquant-1/reports/control_plane_events.jsonl` for operator dashboards; optional Slack/email in v0.2.

---

## 9. Prevent accidental full retraining

- **full** runs require `--confirm-full` **or** env `FINQUANT_ALLOW_FULL=1` **or** operator token in `submit.json`.
- Separate Prefect **deployment** tags: `training-smoke` vs `training-full` with **stricter IAM** / deployment approval on full.

---

## 10. Prevent training while Ollama / large models occupy VRAM

- **Preflight task** (before GPU steps): parse `nvidia-smi` process table; denylist **ollama**, configurable PIDs/names; **minimum free VRAM** threshold (e.g. 40 GiB on A6000 for 7B QLoRA).
- If fail → **blocked**, write `logs/preflight.json`, do not start `train_qlora`.

---

## 11. Run states (canonical)

| State | Meaning |
|-------|---------|
| `queued` | Accepted, not started. |
| `running_dataset` / `running_proof` / `running_train` / `running_eval` | In progress. |
| `smoke` | Completed smoke train path (subset). |
| `full` | Completed full train path. |
| `failed` | Error or gate failure with reason. |
| `blocked_vram` | Preflight prevented start. |
| `pending_promotion` | Train+eval OK; awaits operator. |
| `promoted` | Adapter registered / approved. |
| `rejected` | Operator declined promotion. |

---

## 12. MLflow artifact & registry mapping

- **Params:** seed, `max_steps`, paths to resolved config, `dataset_version_id`.
- **Metrics:** training loss steps; `eval.pass_count`, `eval.cases_total`.
- **Artifacts:** adapter bundle (or URI), `eval_report.md`, `dataset_manifest.json`.
- **Registry:** Registered model name e.g. `finquant-qwen7b-lora`; version ties to **adapter_version_id**.

---

## 13. Minimal implementation plan (phased)

| Phase | Deliverable |
|-------|-------------|
| **M1** | Design approval (this doc) + `runs/` layout + `state.json` schema in repo. |
| **M2** | Prefect flow wrapping **proof → train → eval** subprocesses; MLflow logging; no `finquantctl` yet (Makefile or thin shell). |
| **M3** | `finquantctl` CLI + VRAM preflight + `--confirm-full`. |
| **M4** | Docker image + Prefect agent on trx40; promotion gate + registry. |
| **M5** | Optional DVC integration for dataset tracks parallel to manifest hashes. |

**Non-goals for v0.1 design:** Kubernetes scheduler, multi-node training, automated Slack (unless webhook already available).

---

## 14. Completion checklist (design-only)

- [x] Stack: Prefect + MLflow + Docker (+ optional DVC / manifest hashing).
- [x] IDs: run, dataset version, config version, adapter version.
- [x] Flow: build → proof → train → eval → log → register → gated promotion.
- [x] Run folder contract under `/data/finquant-1/runs/<run_id>/`.
- [x] CLI surface: `submit`, `status`, `eval`, `promote`.
- [x] Safety: full-retrain guard, VRAM/Ollama guard.

---

## 15. References

- MLflow dataset tracking and lineage: [MLflow docs — ML Dataset Tracking](https://mlflow.org/docs/latest/ml/dataset/)
- TRL + PEFT/QLoRA (trainer remains underneath): [Hugging Face TRL — PEFT Integration](https://huggingface.co/docs/trl/peft_integration)

---

**Document version:** v0.1  
**Last updated:** 2026-04-29
