#!/usr/bin/env python3
"""
Phase 1 — Dataset proof (must pass before FinQuant-1 training).

Validates staging JSONL + build report, then writes:
  {FINQUANT_BASE}/reports/dataset_proof_report.md

Exit code 0 only if acceptance criteria pass.

Usage (trx40):
  export FINQUANT_BASE=/data/finquant-1
  python3 finquant/scripts/dataset_proof.py

Optional:
  python3 finquant/scripts/dataset_proof.py --base /data/finquant-1
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path


def default_base() -> Path:
    env = (os.environ.get("FINQUANT_BASE") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


REQUIRED_LINES = 1500
MIN_ADVERSARIAL = 750
STAGING_REL = Path("datasets/staging/finquant_staging_v0.1.jsonl")
BUILD_REPORT_REL = Path("reports/source_to_training_build_report_v0.1.md")


def count_records_and_adversarial(path: Path) -> tuple[int, int]:
    n = 0
    adv = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n += 1
            obj = json.loads(line)
            if obj.get("adversarial") is True:
                adv += 1
    return n, adv


def build_report_has_twenty_samples(build_report: Path) -> bool:
    text = build_report.read_text(encoding="utf-8")
    if "Twenty sample records" not in text and "Twenty sample" not in text:
        return False
    blocks = text.count("### Sample ")
    return blocks >= 20


def main() -> None:
    ap = argparse.ArgumentParser(description="FinQuant-1 Phase 1 dataset proof")
    ap.add_argument("--base", type=Path, default=None, help="FINQUANT_BASE (default: env FINQUANT_BASE or repo finquant/)")
    args = ap.parse_args()
    base = (args.base or default_base()).resolve()

    staging = base / STAGING_REL
    build_report = base / BUILD_REPORT_REL
    out_report = base / "reports" / "dataset_proof_report.md"

    checks: list[tuple[str, bool, str]] = []
    n_lines = adv_n = 0

    checks.append(("staging_file_exists", staging.is_file(), str(staging)))
    if staging.is_file():
        n_lines, adv_n = count_records_and_adversarial(staging)

    checks.append(("record_count_1500", n_lines == REQUIRED_LINES, f"got {n_lines}"))
    checks.append(("adversarial_ge_750", adv_n >= MIN_ADVERSARIAL, f"got {adv_n}"))
    checks.append(("build_report_exists", build_report.is_file(), str(build_report)))
    if build_report.is_file():
        checks.append(("build_report_has_20_samples", build_report_has_twenty_samples(build_report), "need 20 sample blocks"))

    passed = all(c[1] for c in checks)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    host = socket.gethostname()

    lines = [
        "# FinQuant-1 — dataset proof report",
        "",
        f"**Generated:** `{ts}` UTC",
        f"**Host:** `{host}`",
        f"**FINQUANT_BASE:** `{base}`",
        "",
        "## Acceptance",
        "",
        "| Criterion | Required | Actual | Pass |",
        "|-----------|----------|--------|------|",
        f"| Staging records | {REQUIRED_LINES} | {n_lines} | {'yes' if n_lines == REQUIRED_LINES else 'no'} |",
        f"| Adversarial rows | ≥ {MIN_ADVERSARIAL} | {adv_n} | {'yes' if adv_n >= MIN_ADVERSARIAL else 'no'} |",
        f"| Build report + 20 samples | yes | {'present' if build_report.is_file() else 'missing'} | "
        f"{'yes' if build_report.is_file() and build_report_has_twenty_samples(build_report) else 'no'} |",
        "",
        "## Checks",
        "",
        "| Check | Pass | Detail |",
        "|-------|------|--------|",
    ]
    for name, ok, detail in checks:
        lines.append(f"| `{name}` | {'yes' if ok else 'no'} | {detail} |")

    lines.extend(
        [
            "",
            "## Validation commands (reference)",
            "",
            "```bash",
            f"wc -l {staging}",
            f'grep -c \'\"adversarial\": true\' {staging}',
            "```",
            "",
            "## Phase gate",
            "",
            "**Dataset proof PASSED — OK to proceed to training setup (Phase 2).**"
            if passed
            else "**Dataset proof FAILED — do not start training.** Fix staging build and re-run.",
            "",
        ]
    )

    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text("\n".join(lines), encoding="utf-8")
    print(out_report)

    if not passed:
        print("DATASET PROOF FAILED — see report.", file=sys.stderr)
        sys.exit(1)
    print("DATASET PROOF PASSED")


if __name__ == "__main__":
    main()
