#!/usr/bin/env python3
"""CLI wrapper for GT055 walk-forward analysis (see module docstring)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from renaissance_v4.game_theory.analyze_gt055_walk_forward_v1 import main_cli

if __name__ == "__main__":
    raise SystemExit(main_cli())
