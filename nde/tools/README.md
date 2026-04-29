# NDE tools

## `nde_source_processor.py`

Universal **source → extracted → concepts → staging JSONL → report** driver for any domain under `/data/NDE/<domain>/`.

Requires **PyYAML** (`pip install pyyaml`). Optional **pypdf** for PDF text extraction.

Deploy: `bash scripts/install_nde_data_layout.sh /data/NDE` copies tools + layout.

**Production:** create the venv once (PEP 668–safe on managed hosts):

```bash
bash /data/NDE/tools/setup_env.sh
```

**Canonical run** (uses `/data/NDE/.venv` if present; otherwise runs `setup_env.sh`):

```bash
/data/NDE/tools/run_processor.sh \
  --domain secops \
  --input /data/NDE/secops/sources/raw/ \
  --output /data/NDE/secops/datasets/staging/secops_v0.1.jsonl
```

Direct Python (same interpreter after venv exists):

```bash
/data/NDE/.venv/bin/python /data/NDE/tools/nde_source_processor.py \
  --domain secops \
  --input /data/NDE/secops/sources/raw/ \
  --output /data/NDE/secops/datasets/staging/secops_v0.1.jsonl
```

Configs: `nde_factory/layout/secops/domain_config.yaml`, `nde_factory/layout/finquant/domain_config.yaml`.

## CI — LangGraph orchestration guard

From repo root:

```bash
python3 nde/tools/check_langgraph_enforcement.py
```

Fails if `.py` / `.sh` under `nde/`, `nde_factory/layout/`, or `scripts/install_nde_data_layout.sh` combines multi-step pipeline signals (process + train + eval) without **`nde_graph_runner.py`** / **`run_graph.sh`** / **`langgraph`** imports. Exceptions: **`nde/tools/langgraph_enforcement_allowlist.json`** (architect-approved patterns only).

## LangGraph orchestration (`nde_graph_runner.py`)

**LangGraph** drives durable checkpoints (SQLite per run), explicit routing, and resume after interruption — **not** “Lang chart.” **LangChain** is optional for tools/models elsewhere; this runner stays dependency-light.

Deploy: `nde_graph_runner.py` + `run_graph.sh` (installed under `/data/NDE/tools/` with `install_nde_data_layout.sh`). Install graph deps: `pip install -r nde/tools/requirements.txt` into `/data/NDE/.venv`.

```bash
/data/NDE/tools/run_graph.sh --domain secops --mode smoke
/data/NDE/tools/run_graph.sh --domain finquant --mode smoke
/data/NDE/tools/run_graph.sh --domain secops --mode full --require-approval
```

- **`--mode smoke`:** smoke train path only (no full training unless you override training subprocess separately).
- **`--mode full --require-approval`:** requires `runs/<run_id>/APPROVED` on disk before the train step runs full QLoRA (via existing `finquant/training/train_qlora.py`).
- **`--dry-run` / `--skip-train`:** graph proof without subprocess processor/train.

Run artifacts: `/data/NDE/<domain>/runs/<run_id>/state.json`, `checkpoints.sqlite`, per-node `runs/.../nodes/<node>/node_status.json` + logs.

Resume (after an interrupted run with the same `run_id`):

```bash
/data/NDE/tools/run_graph.sh --domain secops --mode smoke --run-id <same> --resume
```

### SecOps CMMC build (v0.3, authoritative PDF drops)

Official **CMMC Model / Assessment Guide** PDFs and **CIS Controls v8 / v8.1** PDF often **cannot** be fetched unattended (`curl`/`wget` may get **403** on DoD Akamai; CIS download pages may return **HTML** instead of the PDF). Use a **browser download**, then copy onto the host:

```bash
# Example: after saving PDFs locally
scp CMMC_ModelOverview_v2.pdf CMMC_AssessmentGuide_L1_v2.pdf CIS_Controls_v8.1.pdf \
  USER@HOST:/data/NDE/secops/sources/raw/
```

Then (no processor code changes):

```bash
/data/NDE/tools/run_processor.sh \
  --domain secops \
  --config /data/NDE/secops/domain_config_cmmc_v0.3.yaml \
  --input /data/NDE/secops/sources/raw/ \
  --output /data/NDE/secops/datasets/staging/secops_cmmc_v0.3_from_sources.jsonl
```
