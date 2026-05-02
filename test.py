#!/usr/bin/env python3
"""
FinQuant agent lab — one-shot launcher for lab host (trx40).

  cd /home/vanayr/blackbox
  python3 test.py              # Run A/B proof pack + operator report (stub)
  python3 test.py smoke        # Quick case discovery only
  python3 test.py llm          # Same as default but Qwen/Ollama config

Override repo root:

  BLACKBOX_ROOT=/path/to/blackbox python3 test.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("BLACKBOX_ROOT", "/home/vanayr/blackbox")).resolve()
LAB = ROOT / "finquant" / "unified" / "agent_lab"
PY = sys.executable


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def cmd_smoke() -> None:
    if not LAB.is_dir():
        die(f"Missing lab: {LAB}")
    sys.path.insert(0, str(LAB))
    from run_ab_comparison import discover_cases

    pack = LAB / "cases" / "ab_memory_replay_pack"
    if not pack.is_dir():
        die(f"Missing proof pack: {pack}")
    cases = discover_cases(str(pack))
    if len(cases) != 2:
        die(f"Expected 2 proof cases, got {len(cases)}: {cases!r}")
    print("OK — BLACKBOX_ROOT:", ROOT)
    print("OK — proof cases:", [Path(p).name for p in cases])


def cmd_train(*, use_llm: bool) -> None:
    """Multi-cycle training loop on a generated synthetic dataset."""
    if not ROOT.is_dir():
        die(f"BLACKBOX_ROOT not found: {ROOT}")
    if not LAB.is_dir():
        die(f"Missing lab: {LAB}")

    trainer = LAB / "training_loop.py"
    cfg = LAB / "configs" / ("default_lab_config.json" if use_llm else "stub_lab_config.json")
    out = LAB / "outputs"

    for label, p in (("training_loop.py", trainer), ("config", cfg)):
        if not p.exists():
            die(f"Missing {label}: {p}")

    print("[test.py] mode=", "llm" if use_llm else "stub", file=sys.stderr)
    r = subprocess.run(
        [
            PY,
            str(trainer),
            "--generate-synthetic",
            "--case-count", "60",
            "--cycles", "4",
            "--symbol", "SOL-PERP",
            "--config", str(cfg),
            "--output-dir", str(out),
        ],
        cwd=str(ROOT),
    )
    sys.exit(r.returncode)


def cmd_ab(*, use_llm: bool) -> None:
    if not ROOT.is_dir():
        die(f"BLACKBOX_ROOT not found: {ROOT}")
    if not LAB.is_dir():
        die(f"Missing lab: {LAB}")

    run_ab = LAB / "run_ab_comparison.py"
    report = LAB / "operator_report.py"
    cases = LAB / "cases" / "ab_memory_replay_pack"
    cfg = LAB / "configs" / ("default_lab_config.json" if use_llm else "stub_lab_config.json")
    out = LAB / "outputs"

    for label, p in (
        ("run_ab_comparison.py", run_ab),
        ("operator_report.py", report),
        ("cases/ab_memory_replay_pack", cases),
        ("config", cfg),
    ):
        if not p.exists():
            die(f"Missing {label}: {p}")

    print("[test.py] BLACKBOX_ROOT=", ROOT, file=sys.stderr)
    print("[test.py] mode=", "llm" if use_llm else "stub", file=sys.stderr)

    r1 = subprocess.run(
        [
            PY,
            str(run_ab),
            "--cases-dir",
            str(cases),
            "--config",
            str(cfg),
            "--output-dir",
            str(out),
            "--run-a-fraction",
            "1",
            "--run-b-mode",
            "replay_run_a",
        ],
        cwd=str(ROOT),
    )
    if r1.returncode != 0:
        sys.exit(r1.returncode)

    r2 = subprocess.run(
        [PY, str(report), "--latest", "--output-dir", str(out)],
        cwd=str(ROOT),
    )
    sys.exit(r2.returncode)


def main() -> None:
    arg = (sys.argv[1] if len(sys.argv) > 1 else "ab").strip().lower()
    if arg in ("smoke", "s"):
        cmd_smoke()
        return
    if arg in ("llm", "qwen"):
        cmd_ab(use_llm=True)
        return
    if arg in ("ab", "stub", "run", ""):
        cmd_ab(use_llm=False)
        return
    if arg in ("train", "training"):
        cmd_train(use_llm=False)
        return
    if arg in ("train-llm",):
        cmd_train(use_llm=True)
        return
    die(
        "Usage: python3 test.py [ab|stub|smoke|llm|train|train-llm]\n"
        "  ab|stub|run (default) — replay proof + operator report (stub)\n"
        "  llm|qwen      — same with default_lab_config.json (Ollama)\n"
        "  smoke         — only verify proof cases exist\n"
        "  train         — multi-cycle training loop on synthetic dataset (stub)\n"
        "  train-llm     — same with default_lab_config.json (Ollama)\n",
        2,
    )


if __name__ == "__main__":
    main()
