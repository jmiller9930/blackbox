#!/usr/bin/env python3
"""Single entry for Anna 12th-grade training: readiness + gates + start.

Equivalent to: python3 scripts/runtime/anna_training_cli.py school [args...]
Run from repo root (or anywhere; repo root is detected).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    cli = _REPO / "scripts/runtime/anna_training_cli.py"
    spec = importlib.util.spec_from_file_location("anna_training_cli", cli)
    if spec is None or spec.loader is None:
        print(f"Cannot load {cli}", file=sys.stderr)
        return 2
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    argv = ["school", *sys.argv[1:]]
    return int(mod.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
