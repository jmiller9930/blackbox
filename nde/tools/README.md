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
