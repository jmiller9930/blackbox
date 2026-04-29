# NDE tools

## `nde_source_processor.py`

Universal **source → extracted → concepts → staging JSONL → report** driver for any domain under `/data/NDE/<domain>/`.

Requires **PyYAML** (`pip install pyyaml`). Optional **pypdf** for PDF text extraction.

Deploy: copy to `/data/NDE/tools/` (see `scripts/install_nde_data_layout.sh`).

Example:

```bash
export NDE_ROOT=/data/NDE
python3 "$NDE_ROOT/tools/nde_source_processor.py" \
  --domain secops \
  --input "$NDE_ROOT/secops/sources/raw/" \
  --output "$NDE_ROOT/secops/datasets/staging/secops_v0.1.jsonl"
```

See `nde_factory/layout/secops/domain_config.yaml` for a SecOps template.
