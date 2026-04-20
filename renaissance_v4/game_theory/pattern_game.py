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
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.manifest.validate import load_manifest_file, validate_manifest_against_catalog
from renaissance_v4.research.replay_runner import run_manifest_replay
from renaissance_v4.game_theory.groundhog_memory import resolve_memory_bundle_for_scenario
from renaissance_v4.game_theory.memory_bundle import (
    apply_memory_bundle_to_manifest,
    build_memory_bundle_proof,
    memory_bundle_required_and_missing,
)
from renaissance_v4.game_theory.learning_run_audit import build_per_scenario_learning_run_audit_v1
from renaissance_v4.game_theory.run_memory import append_run_memory, build_run_memory_record
from renaissance_v4.game_theory.memory_paths import default_logs_root, default_run_memory_jsonl
from renaissance_v4.game_theory.run_session_log import write_run_session_folder

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


def json_summary(out: dict[str, Any], scenario: dict[str, Any] | None = None) -> dict[str, Any]:
    """JSON-serializable summary for CLI / web UI (no raw OutcomeRecord list)."""
    b = out.get("binary_scorecard") or {}
    sm = out.get("summary") if isinstance(out.get("summary"), dict) else {}
    # Referee binary card is win/loss counts; portfolio economics live in ``summary`` (ledger metrics).
    trades_card = int(b.get("trades") or 0)
    wr_val = round(float(b.get("win_rate", 0.0)), 6) if trades_card > 0 else None
    row: dict[str, Any] = {
        "outcome_rule_version": b.get("outcome_rule_version"),
        "wins": b.get("wins"),
        "losses": b.get("losses"),
        "trades": b.get("trades"),
        "win_rate": wr_val,
        "validation_checksum": out.get("validation_checksum"),
        "cumulative_pnl": out.get("cumulative_pnl"),
        "dataset_bars": out.get("dataset_bars"),
        "manifest_path": out.get("manifest_path"),
        "summary": out.get("summary"),
        "pattern_game_meta": out.get("pattern_game_meta"),
        "replay_data_audit": out.get("replay_data_audit"),
    }
    if sm:
        row["expectancy"] = round(float(sm.get("expectancy", 0.0)), 6)
        row["average_pnl"] = round(float(sm.get("average_pnl", 0.0)), 6)
        row["max_drawdown"] = round(float(sm.get("max_drawdown", 0.0)), 6)
        row["note"] = (
            "win_rate is the binary Referee scorecard; expectancy/average_pnl/max_drawdown "
            "are portfolio metrics from the same run — do not judge economics from win_rate alone."
        )
    learn = build_per_scenario_learning_run_audit_v1(out, scenario)
    row["learning_run_audit_v1"] = learn
    row["operator_learning_status_line_v1"] = learn.get("operator_learning_status_line_v1")
    sb = out.get("signal_behavior_proof_v1")
    if isinstance(sb, dict):
        row["signal_behavior_proof_v1"] = sb
    return row


class PreparedReplayManifest(NamedTuple):
    """Effective manifest path for ``run_manifest_replay`` / candidate search (temp JSON when needed)."""

    replay_path: Path
    cleanup: Callable[[], None]
    manifest_effective: dict[str, Any]
    memory_bundle_audit: dict[str, Any] | None
    mb_path_for_proof: str | None
    manifest_atr_on_disk: dict[str, Any]
    manifest_atr_after_bundle_merge: dict[str, Any]
    manifest_atr_effective: dict[str, Any]


def prepare_effective_manifest_for_replay(
    manifest_path: Path | str,
    *,
    atr_stop_mult: float | None = None,
    atr_target_mult: float | None = None,
    memory_bundle_path: str | None = None,
    use_groundhog_auto_resolve: bool = True,
) -> PreparedReplayManifest:
    """
    Load + validate manifest with the same bundle/ATR rules as :func:`run_pattern_game`, without replay.

    Caller must invoke ``cleanup()`` after replay (or candidate search) finishes when a temp file
    was used.
    """
    path = Path(manifest_path)
    manifest = load_manifest_file(path)
    manifest_atr_on_disk = {k: manifest.get(k) for k in ("atr_stop_mult", "atr_target_mult")}

    mb_resolved: str | Path | None = memory_bundle_path
    if mb_resolved is None and use_groundhog_auto_resolve:
        mb_resolved = resolve_memory_bundle_for_scenario(None, explicit_path=None)
    mb_path_for_proof: str | None = None
    if mb_resolved:
        ms = str(mb_resolved).strip()
        if ms:
            mb_path_for_proof = str(Path(ms).expanduser().resolve())

    mb_audit = apply_memory_bundle_to_manifest(manifest, mb_resolved)
    manifest_atr_after_bundle_merge = {k: manifest.get(k) for k in ("atr_stop_mult", "atr_target_mult")}
    if atr_stop_mult is not None:
        manifest["atr_stop_mult"] = float(atr_stop_mult)
    if atr_target_mult is not None:
        manifest["atr_target_mult"] = float(atr_target_mult)
    manifest_atr_effective = {k: manifest.get(k) for k in ("atr_stop_mult", "atr_target_mult")}

    errs = validate_manifest_against_catalog(manifest)
    if errs:
        raise RuntimeError("[pattern_game] manifest validation failed: " + "; ".join(errs))

    tmp_path: str | None = None
    needs_temp = mb_audit is not None or atr_stop_mult is not None or atr_target_mult is not None
    if needs_temp:
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="pattern_game_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)
        except Exception:
            if tmp_path and os.path.isfile(tmp_path):
                os.unlink(tmp_path)
            raise
        replay_path = Path(tmp_path)
    else:
        replay_path = path.resolve()

    def cleanup() -> None:
        if tmp_path and os.path.isfile(tmp_path):
            os.unlink(tmp_path)

    return PreparedReplayManifest(
        replay_path=replay_path,
        cleanup=cleanup,
        manifest_effective=manifest,
        memory_bundle_audit=mb_audit,
        mb_path_for_proof=mb_path_for_proof,
        manifest_atr_on_disk=manifest_atr_on_disk,
        manifest_atr_after_bundle_merge=manifest_atr_after_bundle_merge,
        manifest_atr_effective=manifest_atr_effective,
    )


def run_pattern_game(
    manifest_path: Path | str,
    *,
    atr_stop_mult: float | None = None,
    atr_target_mult: float | None = None,
    memory_bundle_path: str | None = None,
    use_groundhog_auto_resolve: bool = True,
    emit_baseline_artifacts: bool = False,
    verbose: bool = True,
    bar_window_calendar_months: int | None = None,
    live_telemetry_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Load manifest, optional **memory bundle** merge, optional ATR overlays, validate, replay.

    Memory bundle (opt-in) merges whitelisted keys into the manifest **before** replay so promoted
    parameters can affect behavior; see ``memory_bundle.py``. CLI ATR overrides win over bundle.
    Writes a temp manifest when the effective manifest differs from the file on disk.

    When ``use_groundhog_auto_resolve`` is False and ``memory_bundle_path`` is None, the canonical
    Groundhog bundle is not resolved (control runs for E2E proof).
    """
    prep = prepare_effective_manifest_for_replay(
        manifest_path,
        atr_stop_mult=atr_stop_mult,
        atr_target_mult=atr_target_mult,
        memory_bundle_path=memory_bundle_path,
        use_groundhog_auto_resolve=use_groundhog_auto_resolve,
    )
    try:
        raw = run_manifest_replay(
            prep.replay_path,
            emit_baseline_artifacts=emit_baseline_artifacts,
            verbose=verbose,
            bar_window_calendar_months=bar_window_calendar_months,
            live_telemetry_callback=live_telemetry_callback,
        )
    finally:
        prep.cleanup()

    outcomes: list[OutcomeRecord] = list(raw.get("outcomes") or [])
    binary = score_binary_outcomes(outcomes)
    proof_core = build_memory_bundle_proof(
        resolved_bundle_path=prep.mb_path_for_proof,
        apply_audit=prep.memory_bundle_audit,
    )
    needs_temp = (
        prep.memory_bundle_audit is not None
        or atr_stop_mult is not None
        or atr_target_mult is not None
    )
    memory_bundle_proof = {
        **proof_core,
        "manifest_atr_on_disk": prep.manifest_atr_on_disk,
        "manifest_atr_after_bundle_merge": prep.manifest_atr_after_bundle_merge,
        "manifest_atr_effective": prep.manifest_atr_effective,
        "replay_manifest_source": "temp_effective_json" if needs_temp else "disk_manifest_file",
        "run_manifest_replay_module": "renaissance_v4.research.replay_runner",
        "run_manifest_replay_function": "run_manifest_replay",
        "execution_pipeline_note": (
            "Signals/regime/fusion/risk/execution managers are built from the effective manifest dict "
            "inside run_manifest_replay via renaissance_v4.manifest.runtime (build_signals_from_manifest, "
            "build_execution_manager_from_manifest, etc.)."
        ),
    }
    meta = {
        "starting_equity_usd_spec": PATTERN_GAME_STARTING_EQUITY_USD_SPEC,
        "risk_fraction_per_trade_spec": PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC,
        "note": "Equity/risk are spec targets; risk governor still uses tiered notional_fraction.",
        "memory_bundle_audit": prep.memory_bundle_audit,
        "memory_bundle_proof": memory_bundle_proof,
    }
    return {
        **raw,
        "binary_scorecard": binary,
        "pattern_game_meta": meta,
        "manifest_effective": prep.manifest_effective,
        "memory_bundle_audit": prep.memory_bundle_audit,
        "memory_bundle_proof": memory_bundle_proof,
    }


def _default_run_memory_path() -> Path:
    return default_run_memory_jsonl()


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
        "--memory-bundle",
        type=str,
        default=None,
        help="JSON file: promoted parameters merged into manifest before replay (see memory_bundle.py); or PATTERN_GAME_MEMORY_BUNDLE",
    )
    parser.add_argument(
        "--require-hypothesis",
        action="store_true",
        help="Exit if hypothesis is empty (or set PATTERN_GAME_REQUIRE_HYPOTHESIS=1)",
    )
    parser.add_argument(
        "--no-session-log",
        action="store_true",
        help="Skip creating logs/run_<UTC>_<id>/ with HUMAN_READABLE.md (default: session log ON)",
    )
    parser.add_argument(
        "--session-logs-root",
        type=str,
        default=None,
        help="Directory for session folders (default: game_theory/logs; or PATTERN_GAME_SESSION_LOGS_ROOT)",
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

    mb_path = args.memory_bundle or os.environ.get("PATTERN_GAME_MEMORY_BUNDLE", "").strip() or None
    if memory_bundle_required_and_missing(mb_path):
        raise SystemExit(
            "Memory bundle required: set PATTERN_GAME_REQUIRE_MEMORY_BUNDLE=1 and pass "
            "--memory-bundle or PATTERN_GAME_MEMORY_BUNDLE"
        )

    out = run_pattern_game(
        args.manifest,
        atr_stop_mult=args.atr_stop_mult,
        atr_target_mult=args.atr_target_mult,
        memory_bundle_path=mb_path,
        emit_baseline_artifacts=args.emit_baseline_artifacts,
        verbose=True,
    )
    summ = json_summary(out)
    print(json.dumps(summ, indent=2))

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
        memory_bundle_audit=out.get("memory_bundle_audit"),
    )

    mem_arg = args.memory_log
    if mem_arg is not None:
        mem_path = _default_run_memory_path() if mem_arg in ("default", "1") else Path(mem_arg).expanduser()
        append_run_memory(mem_path, rec)
        print(f"[run_memory] appended run_id={rec['run_id']} → {mem_path}", file=sys.stderr)

    session_on = not args.no_session_log and os.environ.get("PATTERN_GAME_NO_SESSION_LOG", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )
    if session_on:
        root = args.session_logs_root or os.environ.get("PATTERN_GAME_SESSION_LOGS_ROOT")
        log_root = Path(root).expanduser() if root else default_logs_root()
        session_dir = write_run_session_folder(rec, logs_root=log_root)
        print(
            f"[session_log] run_id={rec['run_id']} → folder={session_dir} (open HUMAN_READABLE.md)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
