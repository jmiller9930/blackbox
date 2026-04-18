"""
pattern_game.py

Official pattern-game runner: validate manifest → deterministic replay → binary WIN/LOSS (Referee only).

See GAME_SPEC_INDICATOR_PATTERN_V1.md. Scores are never injected; they come from replay outcomes.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.manifest.validate import load_manifest_file, validate_manifest_against_catalog
from renaissance_v4.research.replay_runner import run_manifest_replay

# Frozen label rule (breakeven counts as LOSS).
OUTCOME_RULE_V1 = "outcome_rule_v1_pnl_strict"

# Spec targets (metadata for operators; full dollar-risk parity with risk governor is follow-up).
PATTERN_GAME_STARTING_EQUITY_USD_SPEC = 1000.0
PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC = 0.02


def score_binary_outcomes(outcomes: list[OutcomeRecord]) -> dict[str, Any]:
    """
    WIN if realized pnl > 0; LOSS if pnl <= 0 (including breakeven).
    """
    wins = 0
    losses = 0
    for o in outcomes:
        if o.pnl > 0.0:
            wins += 1
        else:
            losses += 1
    n = wins + losses
    return {
        "outcome_rule_version": OUTCOME_RULE_V1,
        "wins": wins,
        "losses": losses,
        "trades": n,
        "win_rate": (wins / n) if n else 0.0,
    }


def run_pattern_game(
    manifest_path: Path | str,
    *,
    atr_stop_mult: float | None = None,
    atr_target_mult: float | None = None,
    emit_baseline_artifacts: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Load manifest, optionally overlay ATR multiples, validate, run replay, attach binary scorecard.

    Writes a temporary manifest when ATR overrides are used so ``run_manifest_replay`` stays unchanged.
    """
    path = Path(manifest_path)
    manifest = load_manifest_file(path)
    if atr_stop_mult is not None:
        manifest["atr_stop_mult"] = float(atr_stop_mult)
    if atr_target_mult is not None:
        manifest["atr_target_mult"] = float(atr_target_mult)

    errs = validate_manifest_against_catalog(manifest)
    if errs:
        raise RuntimeError("[pattern_game] manifest validation failed: " + "; ".join(errs))

    tmp_path: str | None = None
    replay_arg: Path | str = path
    if atr_stop_mult is not None or atr_target_mult is not None:
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="pattern_game_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)
            replay_arg = tmp_path
        except Exception:
            if tmp_path and os.path.isfile(tmp_path):
                os.unlink(tmp_path)
            raise

    try:
        raw = run_manifest_replay(
            replay_arg,
            emit_baseline_artifacts=emit_baseline_artifacts,
            verbose=verbose,
        )
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.unlink(tmp_path)

    outcomes: list[OutcomeRecord] = list(raw.get("outcomes") or [])
    binary = score_binary_outcomes(outcomes)
    meta = {
        "starting_equity_usd_spec": PATTERN_GAME_STARTING_EQUITY_USD_SPEC,
        "risk_fraction_per_trade_spec": PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC,
        "note": "Equity/risk are spec targets; risk governor still uses tiered notional_fraction.",
    }
    return {
        **raw,
        "binary_scorecard": binary,
        "pattern_game_meta": meta,
        "manifest_effective": manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Renaissance pattern game — validate → replay → binary scorecard")
    parser.add_argument(
        "--manifest",
        type=str,
        default=str(
            Path(__file__).resolve().parent.parent / "configs" / "manifests" / "baseline_v1_recipe.json"
        ),
        help="Strategy manifest JSON path",
    )
    parser.add_argument("--atr-stop-mult", type=float, default=None, help="Override ATR stop multiple (0.5–6)")
    parser.add_argument("--atr-target-mult", type=float, default=None, help="Override ATR target multiple (0.5–6)")
    parser.add_argument(
        "--emit-baseline-artifacts",
        action="store_true",
        help="Also write baseline report / outcomes export (default off for game runs)",
    )
    args = parser.parse_args()
    out = run_pattern_game(
        args.manifest,
        atr_stop_mult=args.atr_stop_mult,
        atr_target_mult=args.atr_target_mult,
        emit_baseline_artifacts=args.emit_baseline_artifacts,
        verbose=True,
    )
    # Human-readable one screen
    b = out["binary_scorecard"]
    print(
        json.dumps(
            {
                "outcome_rule_version": b["outcome_rule_version"],
                "wins": b["wins"],
                "losses": b["losses"],
                "trades": b["trades"],
                "win_rate": round(b["win_rate"], 6),
                "validation_checksum": out.get("validation_checksum"),
                "cumulative_pnl": out.get("cumulative_pnl"),
                "pattern_game_meta": out.get("pattern_game_meta"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
