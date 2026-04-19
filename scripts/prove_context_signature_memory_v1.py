#!/usr/bin/env python3
"""
Context Signature Memory v1 — proof script:

  1) Append two memory records (two prior \"scenarios\") with structured signatures + outcomes.
  2) Run optimize_bundle_v3 for a third metrics payload with similar context + worse outcome.
  3) Print current signature, matches, bias proof fields, bundle apply, and (optional) pattern game run2.

  PYTHONPATH=. python3 scripts/prove_context_signature_memory_v1.py
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

from renaissance_v4.game_theory.bundle_optimizer import (  # noqa: E402
    optimize_bundle_v3,
    write_bundle_and_proof,
)
from renaissance_v4.game_theory.context_signature_memory import (  # noqa: E402
    SignatureMatchParamsV1,
    append_context_memory_record,
    derive_context_signature_v1,
    read_context_memory_records,
)


def _pc_a() -> dict:
    return {
        "schema": "pattern_context_v1",
        "bars_processed": 120,
        "dominant_regime": "range",
        "dominant_volatility_bucket": "neutral",
        "structure_tag_shares": {
            "range_like": 0.48,
            "trend_like": 0.12,
            "breakout_like": 0.06,
            "vol_compressed": 0.22,
            "vol_expanding": 0.12,
        },
        "high_conflict_bars": 12,
        "aligned_directional_bars": 6,
        "countertrend_directional_bars": 4,
    }


def _pc_b() -> dict:
    p = dict(_pc_a())
    p["bars_processed"] = 130
    p["structure_tag_shares"] = {
        "range_like": 0.46,
        "trend_like": 0.13,
        "breakout_like": 0.06,
        "vol_compressed": 0.21,
        "vol_expanding": 0.14,
    }
    p["high_conflict_bars"] = 11
    return p


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ctx_sig_mem_proof_"))
    mem = tmp / "context_signature_memory.jsonl"
    bundle_path = tmp / "bundle_v3.json"
    proof_path = tmp / "proof_v3.json"

    mods = ["mean_reversion_fade", "trend_continuation", "breakout_expansion"]

    r1 = append_context_memory_record(
        pattern_context_v1=_pc_a(),
        source_run_id="scenario_a",
        source_artifact_paths=[str(_REPO / "renaissance_v4/configs/manifests/baseline_v1_recipe.json")],
        effective_apply={"fusion_min_score": 0.28, "fusion_max_conflict_score": 0.38},
        outcome_summary={
            "expectancy": 0.35,
            "max_drawdown": 12.0,
            "win_rate": 0.52,
            "total_trades": 12,
            "cumulative_pnl": 3.0,
        },
        optimizer_reason_codes=["V1_NO_TRADES_RELAX_FUSION", "P2_LOWVOL_RANGE_EXTRA_RELAX_MR_STRETCH"],
        memory_path=mem,
        record_id="scenario_a_record",
    )
    r2 = append_context_memory_record(
        pattern_context_v1=_pc_b(),
        source_run_id="scenario_b",
        source_artifact_paths=[str(_REPO / "renaissance_v4/configs/manifests/baseline_v1_recipe.json")],
        effective_apply={"fusion_min_score": 0.26, "mean_reversion_fade_stretch_threshold": 0.0025},
        outcome_summary={
            "expectancy": 0.42,
            "max_drawdown": 9.0,
            "win_rate": 0.55,
            "total_trades": 15,
            "cumulative_pnl": 4.5,
        },
        optimizer_reason_codes=["V1_HIGH_DRAWDOWN_TIGHTEN_FUSION"],
        memory_path=mem,
        record_id="scenario_b_record",
    )

    pc_current = _pc_a()
    pc_current["structure_tag_shares"] = {
        "range_like": 0.49,
        "trend_like": 0.11,
        "breakout_like": 0.05,
        "vol_compressed": 0.23,
        "vol_expanding": 0.12,
    }

    metrics = {
        "source_run_id": "scenario_c_current_run",
        "total_trades": 3,
        "max_drawdown": 55.0,
        "win_rate": 0.25,
        "expectancy": -0.35,
        "cumulative_pnl": -5.0,
        "fusion_no_trade_bars": 40,
        "fusion_directional_bars": 50,
        "entries_attempted": 3,
        "closes_recorded": 3,
        "risk_blocked_bars": 0,
        "dataset_bars": 200,
        "scorecards": {},
        "pattern_context_v1": pc_current,
    }

    bundle, proof = optimize_bundle_v3(
        metrics,
        manifest_signal_modules=mods,
        source_artifact_paths=[str(_REPO / "renaissance_v4/configs/manifests/baseline_v1_recipe.json")],
        context_memory_path=mem,
        signature_match_params=SignatureMatchParamsV1(structure_share_abs_tol=0.15),
    )
    _bp, _pp, proof_out = write_bundle_and_proof(
        bundle,
        proof,
        bundle_path=bundle_path,
        proof_path=proof_path,
    )

    store_count = len(read_context_memory_records(mem))

    report = {
        "directive": "prove_context_signature_memory_v1",
        "memory_store_path": str(mem),
        "memory_record_count": store_count,
        "records_appended": [r1["record_id"], r2["record_id"]],
        "current_context_signature": derive_context_signature_v1(pc_current),
        "optimizer_proof_v3": {
            "context_signature_key_current": proof_out.get("context_signature_key_current"),
            "context_memory_match_count": proof_out.get("context_memory_match_count"),
            "context_memory_matches": proof_out.get("context_memory_matches"),
            "context_memory_bias_applied": proof_out.get("context_memory_bias_applied"),
            "context_memory_bias_diff": proof_out.get("context_memory_bias_diff"),
            "context_memory_reason_codes": proof_out.get("context_memory_reason_codes"),
        },
        "generated_bundle_apply": bundle.get("apply"),
        "paths": {"bundle_path": str(bundle_path), "proof_path": str(proof_path), "tmpdir": str(tmp)},
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
