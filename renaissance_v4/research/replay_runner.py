"""
replay_runner.py

Purpose:
Run a deterministic bar-by-bar replay over historical 5-minute bars.

Usage:
Run after Phases 1 through 7 are installed to validate the full pipeline including learning ledger and scorecards.

Version:
v7.3

Change History:
- v1.0 Initial Phase 1 replay shell.
- v2.0 Added MarketState builder, feature engine, and regime classifier integration.
- v3.0 Added signal evaluation layer integration.
- v4.0 Added fusion engine integration and no-trade threshold logic.
- v5.0 Added risk governor integration and execution gating.
- v6.0 Added execution simulation and trade lifecycle hooks.
- v7.0 Added learning ledger, outcome records from closed trades, and signal scorecards.
- v7.1 Baseline v1: deterministic IDs, single execution→learning bridge, baseline report + checksum.
- v7.2 Authoritative replay driven by baseline strategy manifest (`configs/manifests/baseline_v1_recipe.json`).
- v7.3 `run_manifest_replay()` for programmatic / experiment flows; optional `--manifest` CLI (no env required).
- v7.4 Optional Decision Context Recall v1 (per-bar structured recall + bounded fusion bias; opt-in kwargs).
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from pathlib import Path
from typing import Any

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.performance_metrics import compute_excursion_mae_mfe
from renaissance_v4.core.fusion_engine import (
    MAX_CONFLICT_SCORE,
    MIN_FUSION_SCORE,
    fuse_signal_results,
    signal_family_bucket,
)
from renaissance_v4.core.pnl import compute_pnl
from renaissance_v4.core.regime_classifier import (
    VOLATILITY_COMPRESSION_THRESHOLD,
    VOLATILITY_EXPANSION_THRESHOLD,
)
from renaissance_v4.manifest.runtime import (
    build_execution_manager_from_manifest,
    build_signals_from_manifest,
    resolve_factor_fn,
    resolve_fusion,
    resolve_regime_fn,
    resolve_risk_fn,
)
from renaissance_v4.game_theory.decision_context_recall import (
    build_causal_partial_pattern_context_v1,
    build_decision_recall_trace_v1,
    compute_decision_fusion_bias,
    derive_decision_context_signature_for_matching,
    fusion_engine_supports_decision_recall,
)
from renaissance_v4.game_theory.context_signature_memory import (
    SignatureMatchParamsV1,
    canonical_signature_key,
    find_matching_records_v1,
    read_context_memory_records,
    select_best_outcome_record,
)
from renaissance_v4.manifest.validate import load_manifest_file, validate_manifest_against_catalog
from renaissance_v4.registry import default_catalog_path
from renaissance_v4.registry.load import load_catalog
from renaissance_v4.research.baseline_report import maybe_export_outcomes_full, write_baseline_report
from renaissance_v4.research.determinism import deterministic_decision_id, validation_checksum
from renaissance_v4.research.execution_learning_bridge import record_closed_trade_to_ledger
from renaissance_v4.research.learning_ledger import LearningLedger
from renaissance_v4.research.signal_scorecard import build_signal_scorecards
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50

_RV4_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _RV4_ROOT.parent

_DEFAULT_MANIFEST = _RV4_ROOT / "configs" / "manifests" / "baseline_v1_recipe.json"


def load_replay_manifest(explicit: Path | str | None = None) -> tuple[dict[str, Any], Path]:
    """
    Load and validate the strategy manifest for replay.

    Resolution order when ``explicit`` is None:
    1. Env ``RENAISSANCE_REPLAY_MANIFEST`` (absolute or cwd-relative)
    2. Default baseline recipe path

    When ``explicit`` is set, it is the authoritative path (CLI / experiment jobs — no env required).
    """
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            alt = _REPO_ROOT / path
            if alt.is_file():
                path = alt
    else:
        override = (os.environ.get("RENAISSANCE_REPLAY_MANIFEST") or "").strip()
        path = Path(override) if override else _DEFAULT_MANIFEST
        if not path.is_file():
            alt = _REPO_ROOT / path
            if alt.is_file():
                path = alt
    if not path.is_file():
        raise FileNotFoundError(f"[replay] manifest not found: {path}")
    manifest = load_manifest_file(path)
    errs = validate_manifest_against_catalog(manifest)
    if errs:
        raise RuntimeError("[replay] manifest validation failed: " + "; ".join(errs))
    return manifest, path.resolve()


def run_manifest_replay(
    manifest_path: Path | str | None = None,
    *,
    emit_baseline_artifacts: bool = True,
    verbose: bool = True,
    decision_context_recall_enabled: bool = False,
    decision_context_recall_apply_bias: bool = False,
    decision_context_recall_memory_path: Path | str | None = None,
    decision_context_recall_match_params: SignatureMatchParamsV1 | None = None,
    decision_context_recall_max_samples: int = 24,
) -> dict[str, Any]:
    """
    Execute one full deterministic replay using the manifest resolution rules in ``load_replay_manifest``.

    When ``emit_baseline_artifacts`` is False (experiment / multi-strategy runs), baseline markdown and
    full outcome exports are skipped so baseline reference files are not overwritten.

    When ``decision_context_recall_enabled`` is True, each decision may include structured recall from
    ``context_signature_memory`` JSONL (see :mod:`renaissance_v4.game_theory.decision_context_recall`).
    Optional ``decision_context_recall_apply_bias`` nudges fusion thresholds toward matching memory
    (bounded; ``fuse_signal_results`` manifests only).
    """
    connection = get_connection()
    rows = connection.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m
        ORDER BY open_time ASC
        """
    ).fetchall()

    dataset_bars = len(rows)
    if verbose:
        print(f"[replay] Loaded {dataset_bars} bars")

    if dataset_bars < MIN_ROWS_REQUIRED:
        raise RuntimeError(
            f"[replay] Need at least {MIN_ROWS_REQUIRED} bars, found {dataset_bars}"
        )

    manifest, resolved_manifest_path = load_replay_manifest(manifest_path)
    if verbose:
        print(
            f"[replay] manifest strategy_id={manifest.get('strategy_id')} "
            f"baseline_tag={manifest.get('baseline_tag')} path={resolved_manifest_path}"
        )

    signals = build_signals_from_manifest(manifest)
    factor_fn = resolve_factor_fn(manifest)
    regime_fn = resolve_regime_fn(manifest)
    fusion_fn = resolve_fusion(manifest)
    risk_fn = resolve_risk_fn(manifest)
    exec_manager = build_execution_manager_from_manifest(manifest)
    ledger = LearningLedger()
    processed = 0

    catalog = load_catalog(default_catalog_path())
    recall_fusion_ok = bool(
        decision_context_recall_enabled and fusion_engine_supports_decision_recall(manifest, catalog)
    )
    dcr_match_params = decision_context_recall_match_params or SignatureMatchParamsV1()
    memory_records_cache: list[dict[str, Any]] | None = None
    dcr_samples: list[dict[str, Any]] = []
    dcr_stats: dict[str, Any] = {
        "decision_context_recall_enabled": decision_context_recall_enabled,
        "decision_context_recall_apply_bias": decision_context_recall_apply_bias,
        "fusion_override_supported": recall_fusion_ok,
        "decisions_observed": 0,
        "recall_attempted": 0,
        "decisions_with_positive_match_count": 0,
        "decisions_with_bias_applied": 0,
    }

    fusion_no_trade_bars = 0
    fusion_directional_bars = 0
    risk_blocked_bars = 0
    entries_attempted = 0
    closes_recorded = 0

    regime_bar_counts: Counter[str] = Counter()
    fusion_direction_counts: Counter[str] = Counter()
    volatility_bucket_counts: Counter[str] = Counter()
    signal_family_active_bar_counts: Counter[str] = Counter()
    high_conflict_bars = 0
    aligned_directional_bars = 0
    countertrend_directional_bars = 0

    for index in range(MIN_ROWS_REQUIRED, len(rows) + 1):
        window = rows[:index]
        state = build_market_state(window)
        features = factor_fn(state)
        regime = regime_fn(features)

        signal_results = []
        for signal in signals:
            result = signal.evaluate(state, features, regime)
            signal_results.append(result)

        reg_b = regime_bar_counts.copy()
        vol_b = volatility_bucket_counts.copy()
        fdir_b = fusion_direction_counts.copy()
        hc_b = high_conflict_bars
        al_b = aligned_directional_bars
        ct_b = countertrend_directional_bars

        partial_pc: dict[str, Any] | None = None
        sig_current: dict[str, Any] | None = None
        sig_key: str | None = None
        matches: list[dict[str, Any]] = []
        match_summaries: list[dict[str, Any]] = []
        best_id: str | None = None
        best_summary: dict[str, Any] | None = None
        bias_applied = False
        bias_diff: list[dict[str, Any]] = []
        dcr_codes: list[str] = []

        if decision_context_recall_enabled and recall_fusion_ok:
            if memory_records_cache is None:
                memory_records_cache = read_context_memory_records(decision_context_recall_memory_path)
            partial_pc = build_causal_partial_pattern_context_v1(
                regime_bar_counts_before=reg_b,
                volatility_bucket_counts_before=vol_b,
                fusion_direction_counts_before=fdir_b,
                high_conflict_bars_before=hc_b,
                aligned_directional_bars_before=al_b,
                countertrend_directional_bars_before=ct_b,
                current_regime=regime,
                vol20=float(features.volatility_20),
            )
            sig_current = derive_decision_context_signature_for_matching(partial_pc)
            sig_key = canonical_signature_key(sig_current)
            matches = find_matching_records_v1(
                sig_current,
                memory_records_cache,
                params=dcr_match_params,
            )
            match_summaries = [
                {
                    "record_id": m.get("record_id"),
                    "signature_key": m.get("signature_key"),
                    "source_run_id": m.get("source_run_id"),
                }
                for m in matches
            ]
            best = select_best_outcome_record(matches) if matches else None
            if best is not None:
                best_id = str(best.get("record_id", ""))
                eff = best.get("effective_apply") if isinstance(best.get("effective_apply"), dict) else {}
                best_summary = {
                    "record_id": best_id,
                    "outcome_summary": best.get("outcome_summary"),
                    "effective_apply_keys": sorted(eff.keys()),
                }
            base_min = float(
                manifest.get("fusion_min_score") if manifest.get("fusion_min_score") is not None else MIN_FUSION_SCORE
            )
            base_mc = float(
                manifest.get("fusion_max_conflict_score")
                if manifest.get("fusion_max_conflict_score") is not None
                else MAX_CONFLICT_SCORE
            )
            fusion_min_u, fusion_mc_u, bias_diff, bias_codes, _bid = compute_decision_fusion_bias(
                matches,
                base_fusion_min=base_min,
                base_fusion_max_conflict=base_mc,
                apply_bias=decision_context_recall_apply_bias,
            )
            dcr_codes.extend(bias_codes)
            bias_applied = len(bias_diff) > 0
            fusion_result = fuse_signal_results(
                signal_results,
                min_fusion_score=fusion_min_u,
                max_conflict_score=fusion_mc_u,
                overlap_penalty_per_extra_signal=manifest.get("fusion_overlap_penalty_per_extra_signal"),
            )
        else:
            fusion_result = fusion_fn(signal_results)
            if decision_context_recall_enabled and not recall_fusion_ok:
                dcr_codes.append("DCR_V1_SKIPPED_UNSUPPORTED_FUSION_ENGINE")

        attempted = bool(decision_context_recall_enabled and recall_fusion_ok)
        recall_block = build_decision_recall_trace_v1(
            enabled=decision_context_recall_enabled,
            attempted=attempted,
            partial_pc=partial_pc,
            signature=sig_current,
            signature_key=sig_key,
            matches=matches,
            match_summaries=match_summaries,
            best_id=best_id,
            best_summary=best_summary,
            bias_applied=bias_applied,
            bias_diff=bias_diff,
            reason_codes=dcr_codes
            + (["DCR_V1_NO_MATCHING_SIGNATURES"] if attempted and not matches else []),
        )
        if decision_context_recall_enabled:
            dcr_stats["decisions_observed"] += 1
            if attempted:
                dcr_stats["recall_attempted"] += 1
            if matches:
                dcr_stats["decisions_with_positive_match_count"] += 1
            if bias_applied:
                dcr_stats["decisions_with_bias_applied"] += 1
            if len(dcr_samples) < int(decision_context_recall_max_samples):
                dcr_samples.append(recall_block)

        active_signal_names = [r.signal_name for r in signal_results if r.active]

        regime_bar_counts[regime] += 1
        fusion_direction_counts[fusion_result.direction] += 1

        vol20 = float(features.volatility_20)
        if vol20 <= VOLATILITY_COMPRESSION_THRESHOLD:
            volatility_bucket_counts["compressed"] += 1
        elif vol20 >= VOLATILITY_EXPANSION_THRESHOLD:
            volatility_bucket_counts["expanding"] += 1
        else:
            volatility_bucket_counts["neutral"] += 1

        if fusion_result.conflict_score >= MAX_CONFLICT_SCORE * 0.85:
            high_conflict_bars += 1

        if fusion_result.direction == "long" and regime == "trend_down":
            countertrend_directional_bars += 1
        elif fusion_result.direction == "short" and regime == "trend_up":
            countertrend_directional_bars += 1
        elif fusion_result.direction in {"long", "short"} and regime in {"trend_up", "trend_down"}:
            aligned_directional_bars += 1

        for r in signal_results:
            if r.active:
                signal_family_active_bar_counts[signal_family_bucket(r.signal_name)] += 1

        if fusion_result.direction == "no_trade":
            fusion_no_trade_bars += 1
        else:
            fusion_directional_bars += 1

        drawdown_proxy = 0.0

        risk_decision = risk_fn(
            fusion_result=fusion_result,
            features=features,
            regime=regime,
            drawdown_proxy=drawdown_proxy,
            active_signal_names=active_signal_names,
        )

        if not risk_decision.allowed:
            risk_blocked_bars += 1

        confidence_score = fusion_result.fusion_score
        edge_score = max(fusion_result.long_score, fusion_result.short_score)

        exit_this_bar: dict | None = None
        if exec_manager.current_trade and exec_manager.current_trade.open:
            exec_manager.record_bar_extremes(state.current_high, state.current_low)
            t = exec_manager.current_trade
            entry_price = t.entry_price
            trade_direction = t.direction
            trade_size = t.size
            exit_ev = exec_manager.evaluate_bar(state.current_high, state.current_low)
            if exit_ev:
                reason, exit_price = exit_ev
                bar_pnl = compute_pnl(entry_price, exit_price, trade_size, trade_direction)
                exec_manager.cumulative_pnl += bar_pnl
                closed = exec_manager.current_trade
                mae, mfe = compute_excursion_mae_mfe(closed)
                record_closed_trade_to_ledger(
                    ledger,
                    closed_trade=closed,
                    exit_time=state.timestamp,
                    exit_price=exit_price,
                    exit_reason=reason,
                    bar_pnl=bar_pnl,
                    mae=mae,
                    mfe=mfe,
                    regime=regime,
                )
                closes_recorded += 1
                if verbose:
                    print(
                        f"[execution] bar_pnl={bar_pnl:.6f} cumulative_pnl={exec_manager.cumulative_pnl:.6f}"
                    )
                exit_this_bar = {
                    "reason": reason,
                    "exit_price": exit_price,
                    "bar_pnl": bar_pnl,
                    "mae": mae,
                    "mfe": mfe,
                }

        flat = exec_manager.current_trade is None or not exec_manager.current_trade.open
        opened_this_bar = False
        if (
            flat
            and risk_decision.allowed
            and fusion_result.direction in {"long", "short"}
        ):
            exec_manager.open_trade(
                symbol=state.symbol,
                price=state.current_close,
                direction=fusion_result.direction,
                atr=features.atr_proxy_14,
                size=risk_decision.notional_fraction,
                entry_time=state.timestamp,
                contributing_signal_names=active_signal_names,
                size_tier=risk_decision.size_tier,
                notional_fraction=risk_decision.notional_fraction,
                bar_high=state.current_high,
                bar_low=state.current_low,
                entry_regime=regime,
            )
            opened_this_bar = True
            entries_attempted += 1

        position_open_after = (
            exec_manager.current_trade is not None and exec_manager.current_trade.open
        )

        decision = DecisionContract(
            decision_id=deterministic_decision_id(state.timestamp, index),
            symbol=state.symbol,
            timestamp=state.timestamp,
            market_regime=regime,
            direction=fusion_result.direction,
            fusion_score=fusion_result.fusion_score,
            confidence_score=confidence_score,
            edge_score=edge_score,
            risk_budget=risk_decision.notional_fraction,
            execution_allowed=risk_decision.allowed,
            reason_trace={
                "phase": "phase_7_learning_foundation",
                "decision_context_recall": recall_block,
                "regime": regime,
                "fusion": {
                    "direction": fusion_result.direction,
                    "long_score": fusion_result.long_score,
                    "short_score": fusion_result.short_score,
                    "gross_score": fusion_result.gross_score,
                    "conflict_score": fusion_result.conflict_score,
                    "overlap_penalty": fusion_result.overlap_penalty,
                    "threshold_passed": fusion_result.threshold_passed,
                },
                "risk": {
                    "allowed": risk_decision.allowed,
                    "size_tier": risk_decision.size_tier,
                    "notional_fraction": risk_decision.notional_fraction,
                    "compression_factor": risk_decision.compression_factor,
                    "veto_reasons": risk_decision.veto_reasons,
                    "debug_trace": risk_decision.debug_trace,
                },
                "execution": {
                    "exit_this_bar": exit_this_bar,
                    "opened_this_bar": opened_this_bar,
                    "cumulative_pnl": exec_manager.cumulative_pnl,
                    "position_open_after": position_open_after,
                },
                "learning": {
                    "outcomes_recorded": len(ledger.outcomes),
                    "learning_source": "closed_trades_only_via_execution_learning_bridge",
                },
                "contributing_signals": fusion_result.contributing_signals,
                "suppressed_signals": fusion_result.suppressed_signals,
            },
        )

        assert decision.timestamp == state.timestamp

        processed += 1

        if verbose and processed % 5000 == 0:
            print(
                "[replay] Progress "
                f"processed={processed} timestamp={decision.timestamp} "
                f"regime={decision.market_regime} direction={decision.direction} "
                f"risk_budget={decision.risk_budget:.2f} "
                f"execution_allowed={decision.execution_allowed} "
                f"cumulative_pnl={exec_manager.cumulative_pnl:.6f} "
                f"outcomes={len(ledger.outcomes)}"
            )

    summary = ledger.summary()
    scorecards = build_signal_scorecards(ledger.outcomes)

    vchk = validation_checksum(
        summary,
        exec_manager.cumulative_pnl,
        len(ledger.outcomes),
    )
    if verbose:
        print(f"[VALIDATION_CHECKSUM] {vchk}")

    sanity = {
        "fusion_no_trade_bars": fusion_no_trade_bars,
        "fusion_directional_bars": fusion_directional_bars,
        "risk_blocked_bars": risk_blocked_bars,
        "entries_attempted": entries_attempted,
        "closes_recorded": closes_recorded,
    }

    if emit_baseline_artifacts:
        write_baseline_report(
            None,
            dataset_bars=dataset_bars,
            summary=summary,
            scorecards=scorecards,
            cumulative_pnl=exec_manager.cumulative_pnl,
            validation_checksum=vchk,
            sanity=sanity,
            outcomes=ledger.outcomes,
        )
        maybe_export_outcomes_full(ledger.outcomes)

    if verbose:
        print(f"[replay] Final summary metrics: {summary}")
        print(f"[replay] Final signal scorecards: {scorecards}")
        print("[replay] Phase 7 replay completed successfully")

    outcomes: list[OutcomeRecord] = list(ledger.outcomes)

    def _dominant(c: Counter[str]) -> str | None:
        if not c:
            return None
        return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    rc = dict(regime_bar_counts)
    bp = float(processed) if processed else 1.0
    range_like = int(rc.get("range", 0)) + int(rc.get("volatility_compression", 0))
    trend_like = int(rc.get("trend_up", 0)) + int(rc.get("trend_down", 0))
    breakout_like = int(rc.get("volatility_expansion", 0))

    pattern_context_v1: dict[str, Any] = {
        "schema": "pattern_context_v1",
        "bars_processed": processed,
        "regime_bar_counts": {k: int(regime_bar_counts[k]) for k in sorted(regime_bar_counts)},
        "fusion_direction_counts": {
            k: int(fusion_direction_counts[k]) for k in sorted(fusion_direction_counts)
        },
        "volatility_bucket_counts": {
            k: int(volatility_bucket_counts[k]) for k in sorted(volatility_bucket_counts)
        },
        "signal_family_active_bar_counts": {
            k: int(signal_family_active_bar_counts[k]) for k in sorted(signal_family_active_bar_counts)
        },
        "high_conflict_bars": int(high_conflict_bars),
        "aligned_directional_bars": int(aligned_directional_bars),
        "countertrend_directional_bars": int(countertrend_directional_bars),
        "dominant_regime": _dominant(regime_bar_counts),
        "dominant_volatility_bucket": _dominant(volatility_bucket_counts),
        "structure_tag_shares": {
            "range_like": round(range_like / bp, 6),
            "trend_like": round(trend_like / bp, 6),
            "breakout_like": round(breakout_like / bp, 6),
            "vol_compressed": round(
                float(volatility_bucket_counts.get("compressed", 0)) / bp,
                6,
            ),
            "vol_expanding": round(
                float(volatility_bucket_counts.get("expanding", 0)) / bp,
                6,
            ),
        },
    }

    out: dict[str, Any] = {
        "manifest": manifest,
        "manifest_path": str(resolved_manifest_path),
        "dataset_bars": dataset_bars,
        "outcomes": outcomes,
        "validation_checksum": vchk,
        "summary": summary,
        "scorecards": scorecards,
        "cumulative_pnl": exec_manager.cumulative_pnl,
        "sanity": sanity,
        "pattern_context_v1": pattern_context_v1,
    }
    if decision_context_recall_enabled:
        out["decision_context_recall_stats"] = dcr_stats
        out["decision_context_recall_samples"] = dcr_samples
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="RenaissanceV4 deterministic manifest-driven replay")
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Strategy manifest JSON (repo-relative or absolute). Overrides RENAISSANCE_REPLAY_MANIFEST when set.",
    )
    args = parser.parse_args()
    manifest_arg: Path | str | None = args.manifest
    run_manifest_replay(
        manifest_path=manifest_arg,
        emit_baseline_artifacts=True,
        verbose=True,
    )


if __name__ == "__main__":
    main()
