#!/usr/bin/env python3
"""
Unified FinQuant RTX 40 launcher alias.

From trx40 (SSH / tmux), repo root:

  python3 training/test.py --help

Delegates to run_finquant_rtx40_event.py.

Training JSONL: `--corpus PATH` or `--dataset PATH` (same flag to train_qlora).

Smoke (default): `--train smoke`. Production full train: `--train full --confirm-production-train`.
"""
from __future__ import annotations

import sys
from pathlib import Path

_training_dir = Path(__file__).resolve().parent
if str(_training_dir) not in sys.path:
    sys.path.insert(0, str(_training_dir))

from run_finquant_rtx40_event import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
