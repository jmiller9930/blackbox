#!/usr/bin/env python3
"""
Bundle Optimizer v1 — end-to-end proof:

  1) Run pattern game (control, no bundle)
  2) Extract structured metrics → optimize_bundle_v1 → write bundle + proof JSON
  3) Run pattern game with generated bundle
  4) Emit comparison JSON (source metrics, bundle apply, run2 memory_bundle_proof, outcomes)

  PYTHONPATH=. python3 scripts/prove_bundle_optimizer_v1.py 2>/dev/null
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")

from renaissance_v4.game_theory.bundle_optimizer import (  # noqa: E402
    extract_metrics_from_pattern_game_run,
    optimize_bundle_v1,
    write_bundle_and_proof,
)
from renaissance_v4.game_theory.pattern_game import run_pattern_game  # noqa: E402
from renaissance_v4.manifest.validate import load_manifest_file  # noqa: E402


def main() -> int:
    manifest_path = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    manifest = load_manifest_file(manifest_path)
    mods = list(manifest.get("signal_modules") or [])

    tmp = Path(tempfile.mkdtemp(prefix="bundle_opt_proof_"))
    bundle_path = tmp / "optimizer_bundle.json"
    proof_path = tmp / "optimizer_proof.json"

    buf1 = io.StringIO()
    with contextlib.redirect_stdout(buf1):
        run1 = run_pattern_game(
            manifest_path,
            memory_bundle_path=None,
            use_groundhog_auto_resolve=False,
            emit_baseline_artifacts=False,
            verbose=False,
        )

    run1["source_run_id"] = run1.get("validation_checksum") or "run1"
    metrics = extract_metrics_from_pattern_game_run(run1)
    prior = {}
    aud = run1.get("memory_bundle_audit")
    if isinstance(aud, dict) and aud.get("apply_snapshot"):
        prior = dict(aud["apply_snapshot"])

    bundle_doc, proof = optimize_bundle_v1(
        metrics,
        prior_apply=prior or None,
        manifest_signal_modules=mods,
        source_artifact_paths=[str(manifest_path.resolve())],
    )
    _bp, _pp, proof_out = write_bundle_and_proof(
        bundle_doc,
        proof,
        bundle_path=bundle_path,
        proof_path=proof_path,
    )

    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        run2 = run_pattern_game(
            manifest_path,
            memory_bundle_path=str(bundle_path.resolve()),
            use_groundhog_auto_resolve=False,
            emit_baseline_artifacts=False,
            verbose=False,
        )

    report = {
        "directive": "prove_bundle_optimizer_v1",
        "run1_source": {
            "cumulative_pnl": run1.get("cumulative_pnl"),
            "trade_count": len(run1.get("outcomes") or []),
            "validation_checksum": run1.get("validation_checksum"),
            "sanity": run1.get("sanity"),
            "summary": run1.get("summary"),
        },
        "optimizer_proof": proof_out,
        "generated_bundle_apply": bundle_doc.get("apply"),
        "run2_with_bundle": {
            "memory_bundle_proof": run2.get("memory_bundle_proof"),
            "cumulative_pnl": run2.get("cumulative_pnl"),
            "trade_count": len(run2.get("outcomes") or []),
            "validation_checksum": run2.get("validation_checksum"),
            "sanity": run2.get("sanity"),
            "summary": run2.get("summary"),
        },
        "comparison": {
            "pnl_delta": float(run2.get("cumulative_pnl") or 0.0)
            - float(run1.get("cumulative_pnl") or 0.0),
            "trade_count_delta": len(run2.get("outcomes") or []) - len(run1.get("outcomes") or []),
            "checksum_equal": run1.get("validation_checksum") == run2.get("validation_checksum"),
        },
        "paths": {
            "bundle_path": str(bundle_path),
            "proof_path": str(proof_path),
        },
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
