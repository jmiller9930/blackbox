# FinQuant Control Plane — M1 completion report

**Canonical copy (repo):** `finquant/reports/control_plane_m1_report.md`  
**Runtime mirror (operator):** `/data/finquant-1/reports/control_plane_m1_report.md`

M1 implements **`finquant/control/finquantctl.py`** only (submit / status / list). Prefect, MLflow, DVC, promotion automation, and retraining loops are **out of scope**.

## Engineering acceptance

| Criterion | Met | Evidence / notes |
|-----------|-----|------------------|
| CLI exists (`submit`, `status`, `list`) | | |
| `submit` creates `/data/finquant-1/runs/<run_id>/` | | |
| Artifacts: `submit.json`, `resolved_config.yaml`, `run_state.json`, `logs/` | | |
| Default submit is **dry registration** (no training subprocess) | | |
| `--execute` records intent; **M1 does not spawn `train_qlora.py`** (later milestone) | | |
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
