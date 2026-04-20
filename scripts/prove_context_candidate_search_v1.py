#!/usr/bin/env python3
"""
Context-Conditioned Candidate Search v1 — operator proof:

  * Seed a deterministic ``context_signature_v1`` (compressed/range-like family).
  * Run control + bounded candidate batch via :func:`run_context_candidate_search_v1`.
  * Print raw ``context_candidate_search_proof`` JSON (machine-readable).

  Requires SQLite ``market_bars_5m`` with at least 50 rows (same as replay).

  PYTHONPATH=. python3 scripts/prove_context_candidate_search_v1.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")

from renaissance_v4.game_theory.context_candidate_search import (  # noqa: E402
    run_context_candidate_search_v1,
)
from renaissance_v4.game_theory.pml_proof_stdio import (  # noqa: E402
    add_proof_stdio_flags,
    begin_pml_proof_stdio,
    proof_json_out,
    raw_stdout_selected,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_proof_stdio_flags(ap)
    args = ap.parse_args()
    begin_pml_proof_stdio("prove_context_candidate_search_v1", raw_stdout=raw_stdout_selected(args))

    manifest_path = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    # Seeded signature: compressed + range-like shares → compressed_range family.
    context_signature_v1 = {
        "schema": "context_signature_v1",
        "version": 1,
        "dominant_regime": "range",
        "dominant_volatility_bucket": "compressed",
        "range_like_share": 0.42,
        "trend_like_share": 0.08,
        "breakout_like_share": 0.05,
        "vol_compressed_share": 0.35,
        "vol_expanding_share": 0.05,
        "high_conflict_share": 0.08,
        "aligned_directional_share": 0.04,
        "countertrend_directional_share": 0.02,
    }
    memory_prior = {
        "fusion_min_score": 0.33,
        "fusion_max_conflict_score": 0.4,
    }
    try:
        out = run_context_candidate_search_v1(
            manifest_path,
            control_apply={},
            context_signature_v1=context_signature_v1,
            memory_prior_apply=memory_prior,
            source_run_id="prove_ccs_v1_seeded",
            parent_reference_id="prove_manifest_baseline",
        )
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        proof_json_out({"ok": False, "error": str(e)})
        return 1

    proof = out["context_candidate_search_proof"]
    report = {
        "directive": "prove_context_candidate_search_v1",
        "ok": True,
        "context_candidate_search_proof": proof,
        "selected_candidate_id": proof.get("selected_candidate_id"),
        "operator_summary": proof.get("operator_summary"),
        "ranking_order": proof.get("ranking_order"),
    }
    proof_json_out(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
