#!/usr/bin/env python3
"""
Phase 1 directive: two-run proof — control vs bundle touching fusion + signal + policy.

Run A: baseline manifest, no bundle, Groundhog off.
Run B: temp bundle with fusion_min_score, mean_reversion_fade_min_confidence,
       disabled_signal_modules (three trend/breakout signals off).

Outputs JSON: effective manifest diff, memory_bundle_proof buckets, outcomes, sanity counters.

  PYTHONPATH=. python3 scripts/prove_memory_bundle_decision_phase1.py 2>/dev/null
"""

from __future__ import annotations

import argparse
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

from renaissance_v4.game_theory.memory_bundle import MEMORY_BUNDLE_SCHEMA  # noqa: E402
from renaissance_v4.game_theory.pattern_game import run_pattern_game  # noqa: E402
from renaissance_v4.game_theory.pml_proof_stdio import (  # noqa: E402
    add_proof_stdio_flags,
    begin_pml_proof_stdio,
    proof_json_out,
    raw_stdout_selected,
)


def _subset(m: dict, keys: list[str]) -> dict:
    return {k: m.get(k) for k in keys}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_proof_stdio_flags(ap)
    args = ap.parse_args()
    begin_pml_proof_stdio("prove_memory_bundle_decision_phase1", raw_stdout=raw_stdout_selected(args))

    manifest = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    fd, bundle_path = tempfile.mkstemp(suffix=".json", prefix="phase1_bundle_")
    os.close(fd)
    bp = Path(bundle_path)
    bp.write_text(
        json.dumps(
            {
                "schema": MEMORY_BUNDLE_SCHEMA,
                "from_run_id": "prove_memory_bundle_decision_phase1",
                "note": "Phase 1 — fusion + signal + policy keys",
                "apply": {
                    "fusion_min_score": 0.05,
                    "mean_reversion_fade_min_confidence": 0.35,
                    "mean_reversion_fade_stretch_threshold": 0.0008,
                    "disabled_signal_modules": [
                        "trend_continuation",
                        "pullback_continuation",
                        "breakout_expansion",
                    ],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    keys_interest = [
        "fusion_min_score",
        "mean_reversion_fade_min_confidence",
        "mean_reversion_fade_stretch_threshold",
        "disabled_signal_modules",
        "atr_stop_mult",
        "atr_target_mult",
    ]

    buf_a = io.StringIO()
    with contextlib.redirect_stdout(buf_a):
        run_a = run_pattern_game(
            manifest,
            memory_bundle_path=None,
            use_groundhog_auto_resolve=False,
            emit_baseline_artifacts=False,
            verbose=False,
        )

    buf_b = io.StringIO()
    with contextlib.redirect_stdout(buf_b):
        run_b = run_pattern_game(
            manifest,
            memory_bundle_path=str(bp.resolve()),
            use_groundhog_auto_resolve=False,
            emit_baseline_artifacts=False,
            verbose=False,
        )

    me_a = run_a.get("manifest_effective") or {}
    me_b = run_b.get("manifest_effective") or {}
    proof_b = run_b.get("memory_bundle_proof") or {}

    report = {
        "directive": "memory_bundle_decision_phase1",
        "run_a_control": {
            "manifest_subset": _subset(me_a, keys_interest),
            "cumulative_pnl": run_a.get("cumulative_pnl"),
            "trade_count": len(run_a.get("outcomes") or []),
            "validation_checksum": run_a.get("validation_checksum"),
            "sanity": run_a.get("sanity"),
            "summary": run_a.get("summary"),
        },
        "run_b_treatment": {
            "bundle_path": str(bp.resolve()),
            "manifest_subset": _subset(me_b, keys_interest),
            "memory_bundle_proof": proof_b,
            "cumulative_pnl": run_b.get("cumulative_pnl"),
            "trade_count": len(run_b.get("outcomes") or []),
            "validation_checksum": run_b.get("validation_checksum"),
            "sanity": run_b.get("sanity"),
            "summary": run_b.get("summary"),
        },
        "diff": {
            "manifest_effective_delta": {
                k: {"run_a": me_a.get(k), "run_b": me_b.get(k)}
                for k in keys_interest
                if me_a.get(k) != me_b.get(k)
            },
            "trade_count_delta": len(run_b.get("outcomes") or []) - len(run_a.get("outcomes") or []),
            "pnl_delta": (float(run_b.get("cumulative_pnl") or 0.0))
            - (float(run_a.get("cumulative_pnl") or 0.0)),
            "checksum_equal": run_a.get("validation_checksum") == run_b.get("validation_checksum"),
            "if_no_trades_note": (
                "If trade_count is 0 for both: the bundled SQLite tape may still yield fusion=no_trade "
                "for all bars (e.g. mean_reversion regime gating). Decision-level changes are still present "
                "in manifest (fusion_min_score, signal floors, disabled modules) and in fusion_engine "
                "debug_trace min_fusion_score; use a longer tape or different date slice where "
                "volatility_compression/range produces stretch signals."
            ),
        },
    }

    proof_json_out(report)
    bp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
