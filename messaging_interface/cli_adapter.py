"""
CLI adapter — primary validation surface (Directive 4.6.3.3).

  echo "test question" | python -m messaging_interface.cli_adapter

Run from repository root (blackbox/). Prints JSON normalized output to stdout.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    from messaging_interface.normalized import normalized_from_payload
    from messaging_interface.pipeline import run_dispatch_pipeline

    text = sys.stdin.read()
    t = text.strip()
    if not t:
        print(json.dumps({"error": "empty stdin"}, indent=2), file=sys.stderr)
        return 2
    payload = run_dispatch_pipeline(t, display_name=None)
    norm = normalized_from_payload(payload)
    print(json.dumps(norm, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
