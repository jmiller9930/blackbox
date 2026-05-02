#!/usr/bin/env python3
"""
FinQuant agent lab — host smoke check.

PRIMARY: run on lab host (trx40), repo at /home/vanayr/blackbox.

  cd /home/vanayr/blackbox && python3 test_finquant_lab_smoke.py

Optional override:

  BLACKBOX_ROOT=/path/to/blackbox python3 test_finquant_lab_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("BLACKBOX_ROOT", "/home/vanayr/blackbox")).resolve()
LAB = ROOT / "finquant" / "unified" / "agent_lab"


def main() -> None:
    assert ROOT.is_dir(), f"BLACKBOX_ROOT does not exist or is not a directory: {ROOT}"
    assert LAB.is_dir(), f"Expected agent lab at {LAB}"
    sys.path.insert(0, str(LAB))

    from run_ab_comparison import discover_cases

    pack = LAB / "cases" / "ab_memory_replay_pack"
    assert pack.is_dir(), f"Missing proof pack: {pack}"

    cases = discover_cases(str(pack))
    assert len(cases) == 2, f"Expected 2 cases, got {cases!r}"

    print("OK — BLACKBOX_ROOT:", ROOT)
    print("OK — proof cases:", [Path(p).name for p in cases])


if __name__ == "__main__":
    main()
