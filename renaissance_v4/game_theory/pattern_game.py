"""
pattern_game.py

Official pattern-game runner: validate manifest → deterministic replay → binary WIN/LOSS (Referee only).

See GAME_SPEC_INDICATOR_PATTERN_V1.md in this folder. Scores are never injected; they come from replay outcomes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.manifest.validate import load_manifest_file, validate_manifest_against_catalog
from renaissance_v4.research.replay_runner import run_manifest_replay
from renaissance_v4.game_theory.run_memory import append_run_memory, build_run_memory_record

# Frozen label rule (breakeven counts as LOSS).
OUTCOME_RULE_V1 = "outcome_rule_v1_pnl_strict"

# Spec targets (metadata for operators; full dollar-risk parity with risk governor is follow-up).
PATTERN_GAME_STARTING_EQUITY_USD_SPEC = 1000.0
PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC = 0.02


def _default_manifest_path() -> Path:
    """Baseline recipe next to ``renaissance_v4/configs`` (this package lives under ``renaissance_v4/``)."""
    return Path(__file__).resolve().parent.parent / "configs" / "manifests" / "baseline_v1_recipe.json"


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


def json_summary(out: dict[str, Any]) -> dict[str, Any]:
    """JSON-serializable summary for CLI / web UI (no raw OutcomeRecord list)."""
    b = out.get("binary_scorecard") or {}
    sm = out.get("summary") if isinstance(out.get("summary"), dict) else {}
    # Referee binary card is win/loss counts; portfolio economics live in ``summary`` (ledger metrics).
    row: dict[str, Any] = {
        "outcome_rule_version": b.get("outcome_rule_version"),
        "wins": b.get("wins"),
        "losses": b.get("losses"),
        "trades": b.get("trades"),
        "win_rate": round(float(b.get("win_rate", 0.0)), 6),
        "validation_checksum": out.get("validation_checksum"),
        "cumulative_pnl": out.get("cumulative_pnl"),
        "dataset_bars": out.get("dataset_bars"),
        "manifest_path": out.get("manifest_path"),
        "summary": out.get("summary"),
        "pattern_game_meta": out.get("pattern_game_meta"),
    }
    if sm:
        row["expectancy"] = round(float(sm.get("expectancy", 0.0)), 6)
        row["average_pnl"] = round(float(sm.get("average_pnl", 0.0)), 6)
        row["max_drawdown"] = round(float(sm.get("max_drawdown", 0.0)), 6)
        row["note"] = (
            "win_rate is the binary Referee scorecard; expectancy/average_pnl/max_drawdown "
            "are portfolio metrics from the same run — do not judge economics from win_rate alone."
        )
    return row


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


def _default_run_memory_path() -> Path:
    return Path(__file__).resolve().parent / "run_memory.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Renaissance pattern game — validate → replay → binary scorecard")
    parser.add_argument(
        "--manifest",
        type=str,
        default=str(_default_manifest_path()),
        help="Strategy manifest JSON path",
    )
    parser.add_argument("--atr-stop-mult", type=float, default=None, help="Override ATR stop multiple (0.5–6)")
    parser.add_argument("--atr-target-mult", type=float, default=None, help="Override ATR target multiple (0.5–6)")
    parser.add_argument(
        "--emit-baseline-artifacts",
        action="store_true",
        help="Also write baseline report / outcomes export (default off for game runs)",
    )
    parser.add_argument(
        "--memory-log",
        type=str,
        default=None,
        help="Append structured run_memory JSONL (use 'default' for game_theory/run_memory.jsonl)",
    )
    parser.add_argument(
        "--hypothesis",
        type=str,
        default=None,
        help="Testable statement for this run (or set PATTERN_GAME_HYPOTHESIS)",
    )
    parser.add_argument(
        "--indicator-context",
        type=str,
        default=None,
        help="Path to JSON: structured indicator context (direction, regime, transitions — not raw numbers alone)",
    )
    parser.add_argument(
        "--indicator-context-json",
        type=str,
        default=None,
        help="Inline JSON object for indicator context (alternative to --indicator-context file)",
    )
    parser.add_argument("--prior-run-id", type=str, default=None, help="Link to prior run_memory run_id")
    parser.add_argument(
        "--require-hypothesis",
        action="store_true",
        help="Exit if hypothesis is empty (or set PATTERN_GAME_REQUIRE_HYPOTHESIS=1)",
    )
    args = parser.parse_args()
    hyp = (args.hypothesis or os.environ.get("PATTERN_GAME_HYPOTHESIS") or "").strip()
    ctx: dict[str, Any] | None = None
    if args.indicator_context:
        ctx = json.loads(Path(args.indicator_context).expanduser().read_text(encoding="utf-8"))
        if not isinstance(ctx, dict):
            raise SystemExit("--indicator-context must be a JSON object")
    elif args.indicator_context_json:
        ctx = json.loads(args.indicator_context_json)
        if not isinstance(ctx, dict):
            raise SystemExit("--indicator-context-json must be a JSON object")
    req = args.require_hypothesis or os.environ.get("PATTERN_GAME_REQUIRE_HYPOTHESIS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if req and not hyp:
        raise SystemExit("Hypothesis required: pass --hypothesis or set PATTERN_GAME_HYPOTHESIS")

    out = run_pattern_game(
        args.manifest,
        atr_stop_mult=args.atr_stop_mult,
        atr_target_mult=args.atr_target_mult,
        emit_baseline_artifacts=args.emit_baseline_artifacts,
        verbose=True,
    )
    summ = json_summary(out)
    print(json.dumps(summ, indent=2))

    mem_arg = args.memory_log
    if mem_arg is not None:
        mem_path = _default_run_memory_path() if mem_arg in ("default", "1") else Path(mem_arg).expanduser()
        scenario_echo = None
        if hyp or ctx:
            scenario_echo = {
                "agent_explanation": {
                    "hypothesis": hyp,
                    "indicator_context": ctx or {},
                }
            }
        rec = build_run_memory_record(
            source="pattern_game_cli",
            manifest_path=args.manifest,
            json_summary_row=summ,
            scenario=scenario_echo,
            hypothesis_cli=hyp if hyp else None,
            indicator_context=ctx,
            prior_run_id=args.prior_run_id,
            atr_stop_mult=args.atr_stop_mult,
            atr_target_mult=args.atr_target_mult,
        )
        append_run_memory(mem_path, rec)
        print(f"[run_memory] appended run_id={rec['run_id']} → {mem_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
