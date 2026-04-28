#!/usr/bin/env python3
"""
Print ``ollama_role_routing_snapshot_v1`` for operator proof.

Lab: set ``RUNTIME_LLM_API_GATEWAY_BASE_URL`` to the API Gateway base (not bare Ollama on .230).
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    repo_root = __file__.rsplit("/scripts/", 1)[0]
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from renaissance_v4.game_theory.ollama_role_routing_v1 import ollama_role_routing_snapshot_v1

    snap = ollama_role_routing_snapshot_v1()
    print(json.dumps(snap, indent=2))
    trx = "172.20.1.66"
    urls = json.dumps(snap)
    if trx in urls:
        print(f"\nWARNING: {trx} appears in snapshot — runtime routing must not target trx40.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
