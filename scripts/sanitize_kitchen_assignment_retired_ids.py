#!/usr/bin/env python3
"""
One-shot: clear Kitchen assignment rows whose active_runtime_policy_id is not in
kitchen_policy_registry_v1 (same logic as GET sanitize).

Usage:
  python3 scripts/sanitize_kitchen_assignment_retired_ids.py
  python3 scripts/sanitize_kitchen_assignment_retired_ids.py /path/to/blackbox/repo
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else _ROOT
    from renaissance_v4.kitchen_runtime_assignment import sanitize_assignment_store_retired_policy_ids

    out = sanitize_assignment_store_retired_policy_ids(root)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
