#!/usr/bin/env python3
"""
Operator Test Harness v1 — end-to-end structured artifact:

  * Control replay (embedded in candidate search) with attempt aggregates + drill-down samples
  * Context-conditioned candidate search proof (ranking, winner, Groundhog **recommendation** only)

  Requires SQLite ``market_bars_5m`` (>= 50 rows). Seeds a temp context memory file so recall can match.

  PYTHONPATH=. python3 scripts/prove_operator_test_harness_v1.py
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
from renaissance_v4.game_theory.operator_test_harness_v1 import run_operator_test_harness_v1  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="oth_proof_"))
    mem = tmp / "context_signature_memory.jsonl"
    manifest_path = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"

    append_context_memory_record(
        pattern_context_v1={
            "schema": "pattern_context_v1",
            "bars_processed": 200,
            "dominant_regime": "range",
            "dominant_volatility_bucket": "neutral",
            "structure_tag_shares": {
                "range_like": 0.45,
                "trend_like": 0.12,
                "breakout_like": 0.05,
                "vol_compressed": 0.3,
                "vol_expanding": 0.1,
            },
            "high_conflict_bars": 10,
            "aligned_directional_bars": 8,
            "countertrend_directional_bars": 4,
        },
        source_run_id="oth_proof_seed",
        source_artifact_paths=[str(manifest_path.resolve())],
        effective_apply={"fusion_min_score": 0.34, "fusion_max_conflict_score": 0.43},
        outcome_summary={
            "expectancy": 0.2,
            "max_drawdown": 10.0,
            "win_rate": 0.5,
            "total_trades": 15,
            "cumulative_pnl": 1.5,
        },
        optimizer_reason_codes=["OTH_PROOF_SEED"],
        memory_path=mem,
        record_id="oth_proof_record_1",
    )

    context_signature_v1 = {
        "schema": "context_signature_v1",
        "version": 1,
        "dominant_regime": "range",
        "dominant_volatility_bucket": "neutral",
        "range_like_share": 0.4,
        "trend_like_share": 0.1,
        "breakout_like_share": 0.05,
        "vol_compressed_share": 0.32,
        "vol_expanding_share": 0.08,
        "high_conflict_share": 0.06,
        "aligned_directional_share": 0.05,
        "countertrend_directional_share": 0.02,
    }

    try:
        out = run_operator_test_harness_v1(
            manifest_path,
            test_run_id="prove_operator_test_harness_v1",
            source_preset_or_manifest=str(manifest_path),
            control_apply={},
            context_signature_v1=context_signature_v1,
            memory_prior_apply={"fusion_min_score": 0.33, "fusion_max_conflict_score": 0.42},
            source_run_id="prove_oth_v1",
            decision_context_recall_enabled=True,
            decision_context_recall_apply_bias=True,
            decision_context_recall_apply_signal_bias_v2=True,
            decision_context_recall_memory_path=mem,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 1

    harness = out["operator_test_harness_v1"]
    print(json.dumps({"ok": True, "operator_test_harness_v1": harness}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
