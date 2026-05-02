#!/usr/bin/env python3
"""
Unified FinQuant RTX 40 launcher alias.

From trx40 (SSH / tmux), repo root:

  python3 training/test.py --help

Delegates to run_finquant_rtx40_event.py.

Smoke (default): `--train smoke`. Production full train: `--train full --confirm-production-train`.
"""
from __future__ import annotations

from run_finquant_rtx40_event import main

if __name__ == "__main__":
    raise SystemExit(main())
