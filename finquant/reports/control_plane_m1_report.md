# FinQuant Control Plane — M1 completion report

**Canonical copy (repo):** `finquant/reports/control_plane_m1_report.md`  
**Runtime mirror (operator):** `/data/finquant-1/reports/control_plane_m1_report.md`

M1 implements **`finquant/control/finquantctl.py`** only (submit / status / list). Prefect, MLflow, DVC, promotion automation, and retraining loops are **out of scope**.

### M1 scope (accepted; commit `364f883` baseline)

- **Dry-only:** default `submit` registers a run folder and artifacts; **no training** is started.
- **`--execute`:** records intent in `submit.json` / `run_state.json` only; **must not** start `train_qlora.py`, spawn training/job subprocesses, modify active adapters, or interact with an active long-running training job.
- **M2+:** actual job launching after Phase 6 training and proof are complete.

## Engineering acceptance

| Criterion | Met | Evidence / notes |
|-----------|-----|------------------|
| CLI exists (`submit`, `status`, `list`) | | |
| `submit` creates `/data/finquant-1/runs/<run_id>/` | | |
| Artifacts: `submit.json`, `resolved_config.yaml`, `run_state.json`, `logs/` | | |
| Default submit is **dry registration** (no training subprocess) | | |
| `--execute` records intent only; **M1 does not** start `train_qlora.py` or training/job subprocesses | | |
| `status <run_id>` reads `run_state.json` | | |
| `list` shows recent runs | | |
| `--mode full` requires `--confirm-full` | | |
| VRAM guard: large Ollama footprint → `blocked_vram`; **no automatic Ollama kill** | | |
| Run ID format `YYYYMMDD_HHMMSS_<mode>_<short_hash>` (UTC) | | |

## Operator proof (host)

Fill with commands + outputs as needed.

| Check | Result |
|-------|--------|
| Training PID / workload unchanged after dry M1 usage (if training active) | |
| `FINQUANT_BASE=/data/finquant-1 python3 …/finquantctl.py submit … --mode smoke` → new run dir | |
| `status`, `list` | |
| Full without `--confirm-full` exits non-zero | |
| `run_state.json` → `vram_guard` sensible on GPU host | |
| No unexpected `train_qlora` child processes from `finquantctl` | |

## Submit log (append-only, UTC)

Stamps appended automatically by `finquantctl submit` when `reports/control_plane_m1_report.md` exists under `FINQUANT_BASE`. If the file is missing on first submit, the CLI creates a starter file with the same name.
