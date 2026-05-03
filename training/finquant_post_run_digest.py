#!/usr/bin/env python3
"""After train+exam: print artifact paths, newest reports, and normative next steps (operator-facing)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


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

    if adapter.is_dir():
        n = sum(1 for _ in adapter.rglob("*") if _.is_file())
        print(f"adapter_files={n}", flush=True)
    else:
        print("WARN: adapter directory missing or not a directory", flush=True)

    if reports.is_dir():
        mds = sorted(reports.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        print("\nRecent reports (.md, newest first):", flush=True)
        for p in mds[:8]:
            print(f"  {p.name}", flush=True)
        if not mds:
            print("  (none)", flush=True)
    else:
        print("\nWARN: reports/ missing — training may not have written reports yet.", flush=True)

    print(
        "\nNext steps:\n"
        "  1) Read the newest training + eval reports under reports_dir.\n"
        "  2) For a stronger model: grow a validated JSONL corpus, place it under FINQUANT_BASE/datasets/, "
        "then rerun full train pointing --dataset at that file (or copy seed there).\n"
        "  3) Quant exam certification (separate from verifier battery): "
        "docs/architect/finquant_quant_exam_architect_spec_v1.md — wire when directed.\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
