#!/usr/bin/env python3
"""
Decision Context Recall — proof (v1 fusion bias + v2 signal/module bias):

  1) Append context memory records (contrasting families + optional intersection-disable pair).
  2) Run manifest replay with recall enabled and optional v2 signal bias.
  3) Emit stats, sample recall blocks (including v2 proof keys when enabled), and checksum.

  Requires market_bars_5m data (same as replay). If unavailable, exits with a clear error.

  PYTHONPATH=. python3 scripts/prove_decision_context_recall_v1.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")

from renaissance_v4.game_theory.context_signature_memory import append_context_memory_record  # noqa: E402
from renaissance_v4.research.replay_runner import run_manifest_replay  # noqa: E402


def _sample_pattern_context() -> dict:
    return {
        "schema": "pattern_context_v1",
        "bars_processed": 200,
        "dominant_regime": "range",
        "dominant_volatility_bucket": "neutral",
        "structure_tag_shares": {
            "range_like": 0.5,
            "trend_like": 0.1,
            "breakout_like": 0.05,
            "vol_compressed": 0.2,
            "vol_expanding": 0.15,
        },
        "high_conflict_bars": 20,
        "aligned_directional_bars": 10,
        "countertrend_directional_bars": 5,
    }


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dcr_proof_"))
    mem = tmp / "context_signature_memory.jsonl"
    manifest_path = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"

    append_context_memory_record(
        pattern_context_v1=_sample_pattern_context(),
        source_run_id="prior_range_neutral",
        source_artifact_paths=[str(manifest_path.resolve())],
        effective_apply={
            "fusion_min_score": 0.32,
            "fusion_max_conflict_score": 0.4,
        },
        outcome_summary={
            "expectancy": 0.25,
            "max_drawdown": 15.0,
            "win_rate": 0.48,
            "total_trades": 20,
            "cumulative_pnl": 2.0,
        },
        optimizer_reason_codes=["PROOF_SEED_A"],
        memory_path=mem,
        record_id="dcr_proof_seed_range",
    )
    # Second record: contrasting volatility_compression + compressed vol — different family.
    append_context_memory_record(
        pattern_context_v1={
            "schema": "pattern_context_v1",
            "bars_processed": 120,
            "dominant_regime": "volatility_compression",
            "dominant_volatility_bucket": "compressed",
            "structure_tag_shares": {
                "range_like": 0.9,
                "trend_like": 0.0,
                "breakout_like": 0.0,
                "vol_compressed": 0.95,
                "vol_expanding": 0.0,
            },
            "high_conflict_bars": 0,
            "aligned_directional_bars": 0,
            "countertrend_directional_bars": 0,
        },
        source_run_id="prior_vol_compression",
        source_artifact_paths=[str(manifest_path.resolve())],
        effective_apply={
            "fusion_min_score": 0.33,
            "fusion_max_conflict_score": 0.42,
        },
        outcome_summary={
            "expectancy": 0.3,
            "max_drawdown": 12.0,
            "win_rate": 0.5,
            "total_trades": 10,
            "cumulative_pnl": 1.0,
        },
        optimizer_reason_codes=["PROOF_SEED_B"],
        memory_path=mem,
        record_id="dcr_proof_seed_vol",
    )
    # Pair with identical pattern context so both can match the same bar: intersection
    # of disabled_signal_modules across matches (both list mean_reversion_fade).
    same_as_range = _sample_pattern_context()
    append_context_memory_record(
        pattern_context_v1=same_as_range,
        source_run_id="prior_range_neutral_dup_intersection_a",
        source_artifact_paths=[str(manifest_path.resolve())],
        effective_apply={
            "fusion_min_score": 0.31,
            "disabled_signal_modules": ["mean_reversion_fade"],
        },
        outcome_summary={
            "expectancy": 0.25,
            "max_drawdown": 15.0,
            "win_rate": 0.48,
            "total_trades": 20,
            "cumulative_pnl": 2.0,
        },
        optimizer_reason_codes=["PROOF_SEED_INTERSECTION_A"],
        memory_path=mem,
        record_id="dcr_proof_seed_range_inter_a",
    )
    append_context_memory_record(
        pattern_context_v1=same_as_range,
        source_run_id="prior_range_neutral_dup_intersection_b",
        source_artifact_paths=[str(manifest_path.resolve())],
        effective_apply={
            "fusion_min_score": 0.315,
            "disabled_signal_modules": ["mean_reversion_fade"],
        },
        outcome_summary={
            "expectancy": 0.26,
            "max_drawdown": 14.0,
            "win_rate": 0.49,
            "total_trades": 21,
            "cumulative_pnl": 2.1,
        },
        optimizer_reason_codes=["PROOF_SEED_INTERSECTION_B"],
        memory_path=mem,
        record_id="dcr_proof_seed_range_inter_b",
    )

    try:
        raw = run_manifest_replay(
            manifest_path,
            emit_baseline_artifacts=False,
            verbose=False,
            decision_context_recall_enabled=True,
            decision_context_recall_apply_bias=True,
            decision_context_recall_apply_signal_bias_v2=True,
            decision_context_recall_memory_path=mem,
            decision_context_recall_max_samples=5,
        )
    except RuntimeError as e:
        print(json.dumps({"ok": False, "error": str(e), "hint": "Requires SQLite market_bars_5m with >= 50 rows"}, indent=2))
        return 1

    samples = raw.get("decision_context_recall_samples") or []
    v2_samples = [s for s in samples if s.get("schema") == "decision_context_recall_v2"]

    report = {
        "directive": "prove_decision_context_recall_v1_v2",
        "ok": True,
        "memory_path": str(mem),
        "validation_checksum": raw.get("validation_checksum"),
        "decision_context_recall_stats": raw.get("decision_context_recall_stats"),
        "decision_context_recall_samples": samples,
        "notes": {
            "v2_schema_samples_in_batch": len(v2_samples),
            "first_sample_keys": sorted(samples[0].keys()) if samples else [],
        },
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
