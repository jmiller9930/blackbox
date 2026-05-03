#!/usr/bin/env python3
"""After train+exam: print artifact paths, newest reports, and normative next steps (operator-facing)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def _adapter_has_weights(adapter: Path) -> bool:
    if not adapter.is_dir():
        return False
    markers = ("adapter_model.safetensors", "adapter_config.json", "pytorch_model.bin")
    for p in adapter.rglob("*"):
        if p.is_file() and p.name in markers:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="FinQuant post-run artifact digest")
    ap.add_argument("--base", type=Path, default=None, help="FINQUANT_BASE (default: env FINQUANT_BASE)")
    ap.add_argument(
        "--adapter",
        type=str,
        default="adapters/finquant-1-qwen7b-v0.1",
        help="Adapter dir relative to FINQUANT_BASE unless absolute",
    )
    args = ap.parse_args()

    if args.base is not None:
        base = args.base.expanduser().resolve()
    else:
        env = (os.environ.get("FINQUANT_BASE") or "").strip()
        base = Path(env).expanduser().resolve() if env else Path("/data/NDE/finquant/agentic_v05").resolve()

    raw_ad = Path(args.adapter)
    adapter = raw_ad.expanduser().resolve() if raw_ad.is_absolute() else (base / raw_ad).resolve()
    reports = base / "reports"

    print("\n=== FINQUANT POST-RUN DIGEST ===\n", flush=True)
    print(f"FINQUANT_BASE={base}", flush=True)
    print(f"adapter_path={adapter}", flush=True)
    print(f"reports_dir={reports}", flush=True)

    adapter_file_count = 0
    if adapter.is_dir():
        adapter_file_count = sum(1 for _ in adapter.rglob("*") if _.is_file())
        print(f"adapter_files={adapter_file_count}", flush=True)
        if adapter_file_count == 0:
            print(
                "WARN: adapter directory is empty — full/smoke training did not reach save_model(), "
                "or output_dir pointed elsewhere. Remove this empty dir or rerun train.",
                flush=True,
            )
        elif not _adapter_has_weights(adapter):
            print(
                "WARN: no adapter_model.safetensors / adapter_config.json found under adapter_path "
                "(unexpected layout — verify train completed).",
                flush=True,
            )
    else:
        print("WARN: adapter directory missing or not a directory", flush=True)

    full_report = reports / "full_training_report_v0.1.md"
    if reports.is_dir():
        mds = sorted(reports.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        print("\nRecent reports (.md, newest first):", flush=True)
        for p in mds[:8]:
            print(f"  {p.name}", flush=True)
        if not mds:
            print("  (none)", flush=True)
        prod_adapter = "finquant-1-qwen7b-v0.1" in str(adapter) and "-smoke" not in str(adapter.name)
        has_smoke_names = any(p.name.startswith("smoke_") for p in mds[:5])
        if prod_adapter and not full_report.is_file() and has_smoke_names:
            print(
                "\nWARN: Expecting full-training artifact full_training_report_v0.1.md for production adapter, "
                "but only smoke_* reports showed up (or full report missing). "
                "Likely only smoke completed here, or full run failed before the report write.",
                flush=True,
            )
    else:
        print("\nWARN: reports/ missing — training may not have written reports yet.", flush=True)

    print(
        "\nNext steps:\n"
        "  1) Read reports under reports_dir. If WARN appeared above, inspect tmux/train logs and rerun "
        "full training until adapter_files>0 and full_training_report_v0.1.md exists.\n"
        "  2) For a stronger model: grow a validated JSONL corpus under FINQUANT_BASE/datasets/, "
        "then rerun full train with --dataset on that file.\n"
        "  3) Quant exam certification (separate from verifier battery): "
        "docs/architect/finquant_quant_exam_architect_spec_v1.md — wire when directed.\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
