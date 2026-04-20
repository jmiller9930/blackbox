#!/usr/bin/env python3
"""
Directive: prove memory bundle resolution → manifest merge → run_manifest_replay → outcome delta.

Run from repo root with DB available (same as pattern game):

  PYTHONPATH=. python3 scripts/prove_memory_bundle_e2e.py

Run A (control): no bundle, no Groundhog auto-resolve.
Run B (treatment): explicit bundle JSON with atr_stop_mult / atr_target_mult differing from Run A effective manifest.

Outputs raw JSON with diffs — no narrative summary.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
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


def _git_rev() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=_REPO,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _outcome_block(raw: dict) -> dict:
    summ = raw.get("summary")
    if not isinstance(summ, dict):
        summ = {}
    return {
        "cumulative_pnl": raw.get("cumulative_pnl"),
        "trade_count": len(raw.get("outcomes") or []),
        "validation_checksum": raw.get("validation_checksum"),
        "summary_expectancy": summ.get("expectancy"),
        "summary_average_pnl": summ.get("average_pnl"),
        "summary_max_drawdown": summ.get("max_drawdown"),
        "binary_scorecard": raw.get("binary_scorecard"),
        "sanity": raw.get("sanity"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_proof_stdio_flags(ap)
    args = ap.parse_args()
    begin_pml_proof_stdio("prove_memory_bundle_e2e", raw_stdout=raw_stdout_selected(args))

    manifest = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not manifest.is_file():
        proof_json_out({"error": f"manifest not found: {manifest}"})
        return 1

    fd, bundle_path = tempfile.mkstemp(suffix=".json", prefix="proof_bundle_")
    os.close(fd)
    bundle_p = Path(bundle_path)
    bundle_doc = {
        "schema": MEMORY_BUNDLE_SCHEMA,
        "from_run_id": "prove_memory_bundle_e2e",
        "note": "E2E proof bundle — ATR geometry intentionally off baseline defaults.",
        "apply": {"atr_stop_mult": 2.25, "atr_target_mult": 4.5},
    }
    bundle_p.write_text(json.dumps(bundle_doc, indent=2) + "\n", encoding="utf-8")

    env_snapshot = {
        "PATTERN_GAME_GROUNDHOG_BUNDLE": os.environ.get("PATTERN_GAME_GROUNDHOG_BUNDLE", ""),
        "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED", ""),
    }

    common = {
        "manifest_path": str(manifest.resolve()),
        "git_rev": _git_rev(),
        "environment_subset": env_snapshot,
    }

    _quiet = io.StringIO()
    with contextlib.redirect_stdout(_quiet):
        run_a = run_pattern_game(
            manifest,
            memory_bundle_path=None,
            use_groundhog_auto_resolve=False,
            emit_baseline_artifacts=False,
            verbose=False,
        )

    _quiet2 = io.StringIO()
    with contextlib.redirect_stdout(_quiet2):
        run_b = run_pattern_game(
            manifest,
            memory_bundle_path=str(bundle_p.resolve()),
            use_groundhog_auto_resolve=False,
            emit_baseline_artifacts=False,
            verbose=False,
        )

    proof_a = run_a.get("memory_bundle_proof") or {}
    proof_b = run_b.get("memory_bundle_proof") or {}

    atr_diff = {
        "atr_stop_mult": {
            "run_a_effective": proof_a.get("manifest_atr_effective", {}).get("atr_stop_mult"),
            "run_b_effective": proof_b.get("manifest_atr_effective", {}).get("atr_stop_mult"),
        },
        "atr_target_mult": {
            "run_a_effective": proof_a.get("manifest_atr_effective", {}).get("atr_target_mult"),
            "run_b_effective": proof_b.get("manifest_atr_effective", {}).get("atr_target_mult"),
        },
    }

    outcome_a = _outcome_block(run_a)
    outcome_b = _outcome_block(run_b)

    chk_eq = outcome_a.get("validation_checksum") == outcome_b.get("validation_checksum")
    identical_note = None
    if chk_eq and (outcome_a.get("trade_count") == 0 and outcome_b.get("trade_count") == 0):
        identical_note = (
            "Manifest merge changed atr_stop_mult/atr_target_mult on disk (see diff.manifest_atr_effective), "
            "but both replays had entries_attempted=0 / closes_recorded=0. "
            "ATR multiples affect stop/target geometry inside ExecutionManager only after a position opens; "
            "with fusion=no_trade for all processed bars, no trade path executed, so PnL and validation_checksum "
            "can remain identical even though the effective manifest differed. "
            "Use a tape/manifest regime where directional trades occur to observe outcome divergence from ATR-only merge."
        )

    report = {
        "directive": "prove_memory_bundle_e2e",
        "common": common,
        "run_a_control": {
            "label": "no_bundle_no_groundhog_autoresolve",
            "memory_bundle_proof": proof_a,
            "outcome": outcome_a,
        },
        "run_b_treatment": {
            "label": "explicit_bundle_file",
            "bundle_file_path": str(bundle_p.resolve()),
            "memory_bundle_proof": proof_b,
            "outcome": outcome_b,
        },
        "diff": {
            "manifest_atr_effective": atr_diff,
            "cumulative_pnl_delta": (outcome_b.get("cumulative_pnl") or 0.0)
            - (outcome_a.get("cumulative_pnl") or 0.0),
            "trade_count_delta": (outcome_b.get("trade_count") or 0) - (outcome_a.get("trade_count") or 0),
            "validation_checksum_equal": chk_eq,
            "if_identical_outcome_explanation": identical_note,
        },
        "code_paths": {
            "merge": "renaissance_v4.game_theory.memory_bundle.apply_memory_bundle_to_manifest",
            "replay": "renaissance_v4.research.replay_runner.run_manifest_replay",
            "execution_build": "renaissance_v4.manifest.runtime (build_*_from_manifest inside replay)",
        },
    }

    proof_json_out(report)

    bundle_p.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
