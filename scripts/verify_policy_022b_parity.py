#!/usr/bin/env python3
"""
DV-ARCH-POLICY-GENERATOR-022-B — compare VALIDATION_CHECKSUM from replay_runner vs generated policy package.

Requires: PYTHONPATH=., Renaissance SQLite DB with market_bars_5m (same as replay).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    from renaissance_v4.research.replay_runner import run_manifest_replay

    from policies.generated.renaissance_baseline_v1.jupiter_4_renaissance_baseline_v1_policy import (
        baseline_manifest_path,
        replay_baseline_v1_checksum,
    )

    # Authoritative replay (same manifest, no baseline artifact writes)
    a = run_manifest_replay(
        manifest_path=baseline_manifest_path(),
        emit_baseline_artifacts=False,
        verbose=False,
    )["validation_checksum"]
    b = replay_baseline_v1_checksum()
    print(f"[manifest_replay]      {a}")
    print(f"[policy_package_replay] {b}")
    if a != b:
        print("PARITY_FAIL: checksum mismatch", file=sys.stderr)
        return 1
    print("PARITY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
