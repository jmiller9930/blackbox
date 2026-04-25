"""
replay_runner.py

Purpose:
Run a deterministic bar-by-bar replay over historical 5-minute bars.

Usage:
Run after Phases 1 through 7 are installed to validate the full pipeline including learning ledger and scorecards.

Version:
v7.7

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
- v7.5 Decision Context Recall v2: bounded per-signal contribution multipliers + optional memory-driven module suppression (opt-in).
- v7.6 ``replay_attempt_aggregates_v1`` + optional DCR drill-down sample rings (operator harness).
- v7.7 ``signal_behavior_proof_v1``: per-signal bar counters, suppression histograms, fusion-vs-risk sanity,
  closed-trade attribution tallies, and capped raw trade-entry rows (for operator evidence exports).
"""

from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from collections.abc import Callable
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
from renaissance_v4.manifest.validate import load_manifest_file, validate_manifest_against_catalog
from renaissance_v4.registry import default_catalog_path
from renaissance_v4.registry.load import load_catalog
from renaissance_v4.research.baseline_report import maybe_export_outcomes_full, write_baseline_report
from renaissance_v4.research.determinism import deterministic_decision_id, validation_checksum
from renaissance_v4.research.execution_learning_bridge import record_closed_trade_to_ledger
from renaissance_v4.research.learning_ledger import LearningLedger
from renaissance_v4.research.signal_scorecard import build_signal_scorecards
from renaissance_v4.game_theory.evaluation_window_runtime import (
    parse_bar_open_time_unix,
    slice_rows_for_calendar_months,
)
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50

_RV4_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _RV4_ROOT.parent

_DEFAULT_MANIFEST = _RV4_ROOT / "configs" / "manifests" / "baseline_v1_recipe.json"


def _compute_student_lane_entry_v1(
    *,
    flat: bool,
    risk_decision_allowed: bool,
    fusion_result_direction: str,
    has_directional_signal: bool,
    signal_results: list[Any],
    student_execution_intent_v1: dict[str, Any] | None,
    student_full_control_lane_v1: bool,
) -> tuple[bool, str | None, str | None]:
    """
    ``(should_open, entry_direction, path_tag)`` for GT-024C (baseline-gated) vs GT-024D (full control).

    **024C:** When fusion is long/short and risk allows, optionally override direction / suppress
    with ``student_execution_intent_v1`` (enter_* / no_trade).

    **024D (fusion veto path):** When ``student_full_control_lane_v1`` and fusion is ``no_trade`` but
    at least one active signal points **long** or **short** and matches the intent's enter direction,
    allow opening **despite** fusion no_trade — still requires flat and risk. Does not open when
    no signal aligns (no "naked" student entry without a directional signal).
    """
    should_open_baseline = (
        flat
        and risk_decision_allowed
        and fusion_result_direction in {"long", "short"}
    )
    if should_open_baseline:
        entry_dir: str | None = str(fusion_result_direction)
        if student_execution_intent_v1 is not None:
            act = str((student_execution_intent_v1 or {}).get("action") or "").strip()
            if act == "no_trade":
                entry_dir = None
            elif act == "enter_long":
                entry_dir = "long"
            elif act == "enter_short":
                entry_dir = "short"
            else:
                entry_dir = None
        if entry_dir in {"long", "short"}:
            return True, entry_dir, "baseline_024c"
        return False, None, None

    if not student_full_control_lane_v1 or not student_execution_intent_v1:
        return False, None, None
    if not (flat and risk_decision_allowed):
        return False, None, None
    if fusion_result_direction != "no_trade":
        return False, None, None
    act = str((student_execution_intent_v1 or {}).get("action") or "").strip()
    if act == "enter_long":
        int_dir = "long"
    elif act == "enter_short":
        int_dir = "short"
    else:
        return False, None, None
    if not has_directional_signal:
        return False, None, None
    if not any(
        getattr(r, "active", False) and getattr(r, "direction", None) == int_dir
        for r in signal_results
    ):
        return False, None, None
    return True, int_dir, "full_control_024d_fusion_veto"


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
    bar_window_calendar_months: int | None = None,
    candle_timeframe_minutes: int | None = None,
    decision_context_recall_enabled: bool = False,
    decision_context_recall_apply_bias: bool = False,
    decision_context_recall_apply_signal_bias_v2: bool = False,
    decision_context_recall_memory_path: Path | str | None = None,
    decision_context_recall_match_params: Any = None,
    decision_context_recall_max_samples: int = 24,
    decision_context_recall_drill_matched_max: int = 0,
    decision_context_recall_drill_bias_max: int = 0,
    decision_context_recall_drill_trade_entry_max: int = 0,
    live_telemetry_callback: Callable[[dict[str, Any]], None] | None = None,
    student_execution_intent_v1: dict[str, Any] | None = None,
    student_full_control_lane_v1: bool = False,
) -> dict[str, Any]:
    """
    Execute one full deterministic replay using the manifest resolution rules in ``load_replay_manifest``.

    When ``emit_baseline_artifacts`` is False (experiment / multi-strategy runs), baseline markdown and
    full outcome exports are skipped so baseline reference files are not overwritten.

    When ``bar_window_calendar_months`` is a positive integer, replay uses only the last ~N calendar
    months of bars (approximate day cutoff from the last bar). When ``None`` or non-positive, the
    full ``market_bars_5m`` series is used.

    When ``candle_timeframe_minutes`` is greater than 5 and a multiple of 5, bars are rolled up from
    the 5m base table into synthetic OHLCV rows at that cadence before the replay loop.

    When ``decision_context_recall_enabled`` is True, each decision may include structured recall from
    ``context_signature_memory`` JSONL (see :mod:`renaissance_v4.game_theory.decision_context_recall`).
    Optional ``decision_context_recall_apply_bias`` nudges fusion thresholds toward matching memory
    (bounded; ``fuse_signal_results`` manifests only).

    Optional ``decision_context_recall_apply_signal_bias_v2`` applies bounded per-signal contribution
    multipliers and optional intersection-based module suppression from memory (still manifest-scoped).

    When ``student_execution_intent_v1`` is set (GT_DIRECTIVE_024C Student-controlled lane), entry
    direction for **bars where fusion is directional and risk allows a baseline entry** is taken from
    the intent: ``enter_long`` / ``enter_short`` / ``no_trade`` (suppresses that would-be entry). When
    ``None`` (default), behavior matches historical manifest-only control. Callers should keep DCR
    off when using Student intent; Student lane is invoked only from orchestration, not the default
    single-replay path.

    When ``student_full_control_lane_v1`` is True (GT_DIRECTIVE_024D), the replay may also open when
    fusion is ``no_trade`` if ``student_execution_intent_v1`` says ``enter_long``/``enter_short`` and
    an active **signal** matches that direction (fusion veto path). Risk and flat gating still apply;
    024C baseline-gated behavior takes precedence on bars where fusion is already directional.

    When drill-down maxima are > 0, the replay keeps the **last** N windows matching each category
    (matched memory, fusion/signal bias applied, trade opened) for operator harness inspection.
    """
    connection = get_connection()
    rows = connection.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m
        ORDER BY open_time ASC
        """
    ).fetchall()

    n_full = len(rows)
    replay_data_audit: dict[str, Any]
    if bar_window_calendar_months is not None and int(bar_window_calendar_months) > 0:
        rows, replay_data_audit = slice_rows_for_calendar_months(
            list(rows),
            int(bar_window_calendar_months),
            min_rows_required=MIN_ROWS_REQUIRED,
        )
        replay_data_audit["dataset_bars_before_window"] = n_full
    else:
        replay_data_audit = {
            "schema": "pattern_game_bar_window_v1",
            "dataset_bars_before_window": n_full,
            "dataset_bars_after_window": n_full,
            "bar_window_calendar_months_requested": None,
            "slicing_applied": False,
            "bar_window_open_time_start": parse_bar_open_time_unix(rows[0]) if rows else None,
            "bar_window_open_time_end": parse_bar_open_time_unix(rows[-1]) if rows else None,
            "note": "Full dataset — no calendar-month window slice.",
        }

    dataset_bars = len(rows)
    if verbose:
        print(f"[replay] Loaded {dataset_bars} bars (full DB had {n_full})")

    rollup_audit: dict[str, Any] | None = None
    ctf: int | None = None
    if candle_timeframe_minutes is not None:
        try:
            ctf = int(candle_timeframe_minutes)
        except (TypeError, ValueError):
            ctf = None
    if ctf is not None and ctf > 5 and ctf % 5 == 0:
        from renaissance_v4.game_theory.candle_timeframe_runtime import rollup_5m_rows_to_candle_timeframe

        rows, rollup_audit = rollup_5m_rows_to_candle_timeframe(
            list(rows),
            target_minutes=ctf,
        )
        dataset_bars = len(rows)
        if isinstance(replay_data_audit, dict) and rollup_audit:
            replay_data_audit = {**replay_data_audit, "candle_timeframe_rollup_v1": rollup_audit}
        if verbose:
            print(
                f"[replay] Candle rollup {ctf}m → {dataset_bars} bars "
                f"(after calendar-window slice; rollup_applied={rollup_audit.get('rollup_applied')})"
            )

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

    # Lazy-import DCR + context memory so ``import renaissance_v4.research.replay_runner`` does not
    # execute ``renaissance_v4.game_theory.__init__`` (which imports pattern_game → replay_runner).
    from renaissance_v4.game_theory.context_signature_memory import (
        SignatureMatchParamsV1,
        canonical_signature_key,
        find_matching_records_v1,
        read_context_memory_records,
        select_best_outcome_record,
    )
    from renaissance_v4.game_theory.decision_context_recall import (
        build_causal_partial_pattern_context_v1,
        build_decision_recall_trace_v1,
        compute_decision_fusion_bias,
        compute_decision_signal_module_bias_v2,
        derive_decision_context_signature_for_matching,
        fusion_engine_supports_decision_recall,
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
    recall_match_records_total = 0
    recall_no_effect_windows = 0
    recall_skipped_unsupported_total = 0
    dcr_drill_matched: list[dict[str, Any]] = []
    dcr_drill_bias: list[dict[str, Any]] = []
    dcr_drill_trade_entries: list[dict[str, Any]] = []
    dm_max = int(decision_context_recall_drill_matched_max)
    db_max = int(decision_context_recall_drill_bias_max)
    dt_max = int(decision_context_recall_drill_trade_entry_max)
    dcr_stats: dict[str, Any] = {
        "decision_context_recall_enabled": decision_context_recall_enabled,
        "decision_context_recall_apply_bias": decision_context_recall_apply_bias,
        "decision_context_recall_apply_signal_bias_v2": decision_context_recall_apply_signal_bias_v2,
        "fusion_override_supported": recall_fusion_ok,
        "decisions_observed": 0,
        "recall_attempted": 0,
        "decisions_with_positive_match_count": 0,
        "decisions_with_bias_applied": 0,
        "decisions_with_signal_bias_applied": 0,
        "suppressed_module_slots_total": 0,
    }

    fusion_no_trade_bars = 0
    fusion_directional_bars = 0
    risk_blocked_bars = 0
    entries_attempted = 0
    closes_recorded = 0
    student_full_control_024d_fusion_veto_entries = 0

    regime_bar_counts: Counter[str] = Counter()
    fusion_direction_counts: Counter[str] = Counter()
    volatility_bucket_counts: Counter[str] = Counter()
    signal_family_active_bar_counts: Counter[str] = Counter()
    high_conflict_bars = 0
    aligned_directional_bars = 0
    countertrend_directional_bars = 0

    SIGNAL_TRACE_MAX = int(os.environ.get("PATTERN_GAME_SIGNAL_TRACE_MAX", "40"))
    signal_active_bar_counts: Counter[str] = Counter()
    signal_directional_active_bar_counts: Counter[str] = Counter()
    signal_suppression_hists: defaultdict[str, Counter[str]] = defaultdict(Counter)
    trade_entry_signal_proof_samples: list[dict[str, Any]] = []
    fusion_rejected_bars_with_directional_signal = 0
    directional_signal_instances_total = 0
    inactive_suppression_events_total = 0

    for index in range(MIN_ROWS_REQUIRED, len(rows) + 1):
        window = rows[:index]
        state = build_market_state(window)
        features = factor_fn(state)
        regime = regime_fn(features)

        signal_results = []
        for signal in signals:
            result = signal.evaluate(state, features, regime)
            signal_results.append(result)

        for r in signal_results:
            if r.active:
                signal_active_bar_counts[r.signal_name] += 1
            if r.active and r.direction in {"long", "short"}:
                signal_directional_active_bar_counts[r.signal_name] += 1
            if not r.active and r.suppression_reason:
                signal_suppression_hists[r.signal_name][str(r.suppression_reason)] += 1

        directional_signal_instances_total += sum(
            1 for r in signal_results if r.active and r.direction in {"long", "short"}
        )
        inactive_suppression_events_total += sum(
            1 for r in signal_results if (not r.active) and r.suppression_reason
        )

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

        sig_bias_applied = False
        sig_bias_diff: list[dict[str, Any]] = []
        sig_suppressed: list[str] = []
        sig_favored: list[dict[str, Any]] = []
        sig_reason_codes: list[str] = []
        mem_just_sig: list[dict[str, Any]] = []
        pcm: dict[str, float] | None = None

        if decision_context_recall_enabled and recall_fusion_ok:
            if memory_records_cache is None:
                memory_records_cache = read_context_memory_records(decision_context_recall_memory_path)
                dcr_stats["memory_records_loaded_count"] = len(memory_records_cache)
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

            disabled_m = set(manifest.get("disabled_signal_modules") or [])
            manifest_signal_modules = [
                s for s in (manifest.get("signal_modules") or []) if s not in disabled_m
            ]
            if decision_context_recall_apply_signal_bias_v2:
                (
                    _per_mult,
                    sig_bias_applied,
                    sig_bias_diff,
                    sig_suppressed,
                    sig_favored,
                    sig_reason_codes,
                    mem_just_sig,
                ) = compute_decision_signal_module_bias_v2(
                    signature=sig_current,
                    matches=matches,
                    manifest_signal_modules=manifest_signal_modules,
                    apply_signal_bias=True,
                )
                if sig_bias_applied:
                    pcm = _per_mult

            fusion_result = fuse_signal_results(
                signal_results,
                min_fusion_score=fusion_min_u,
                max_conflict_score=fusion_mc_u,
                overlap_penalty_per_extra_signal=manifest.get("fusion_overlap_penalty_per_extra_signal"),
                per_signal_contribution_multiplier=pcm,
            )
        else:
            fusion_result = fusion_fn(signal_results)
            if decision_context_recall_enabled and not recall_fusion_ok:
                dcr_codes.append("DCR_V1_SKIPPED_UNSUPPORTED_FUSION_ENGINE")

        attempted = bool(decision_context_recall_enabled and recall_fusion_ok)
        if decision_context_recall_enabled and not recall_fusion_ok:
            recall_skipped_unsupported_total += 1
        signal_bias_v2_trace = bool(
            attempted and decision_context_recall_apply_signal_bias_v2
        )
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
            signal_bias_v2_enabled=signal_bias_v2_trace,
            decision_context_signal_bias_applied=sig_bias_applied,
            decision_context_signal_bias_diff=sig_bias_diff,
            decision_context_signal_reason_codes=sig_reason_codes,
            decision_context_suppressed_modules=sig_suppressed,
            decision_context_favored_signal_families=sig_favored,
            memory_justification_signal_bias=mem_just_sig,
        )
        if attempted:
            recall_match_records_total += len(matches)
            effective_recall = bias_applied or (signal_bias_v2_trace and sig_bias_applied)
            if not effective_recall:
                recall_no_effect_windows += 1
            if matches and dm_max > 0:
                dcr_drill_matched.append(
                    {
                        "timestamp": state.timestamp,
                        "decision_context_signature_key_current": sig_key,
                        "context_memory_match_count_for_decision": len(matches),
                        "best_context_match_id": best_id,
                        "decision_context_recall_bias_applied": bias_applied,
                        "decision_context_signal_bias_applied": sig_bias_applied
                        if signal_bias_v2_trace
                        else False,
                    }
                )
                dcr_drill_matched = dcr_drill_matched[-dm_max:]
            if (
                (bias_applied or (signal_bias_v2_trace and sig_bias_applied))
                and db_max > 0
            ):
                dcr_drill_bias.append(
                    {
                        "timestamp": state.timestamp,
                        "decision_context_signature_key_current": sig_key,
                        "decision_context_recall_bias_applied": bias_applied,
                        "decision_context_recall_bias_diff": bias_diff,
                        "decision_context_signal_bias_applied": sig_bias_applied
                        if signal_bias_v2_trace
                        else False,
                        "decision_context_signal_bias_diff": sig_bias_diff
                        if signal_bias_v2_trace
                        else [],
                    }
                )
                dcr_drill_bias = dcr_drill_bias[-db_max:]
        if decision_context_recall_enabled:
            dcr_stats["decisions_observed"] += 1
            if attempted:
                dcr_stats["recall_attempted"] += 1
            if matches:
                dcr_stats["decisions_with_positive_match_count"] += 1
            if bias_applied:
                dcr_stats["decisions_with_bias_applied"] += 1
            if signal_bias_v2_trace and sig_bias_applied:
                dcr_stats["decisions_with_signal_bias_applied"] += 1
            if signal_bias_v2_trace and sig_suppressed:
                dcr_stats["suppressed_module_slots_total"] = int(
                    dcr_stats.get("suppressed_module_slots_total", 0)
                ) + len(sig_suppressed)
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

        has_directional_signal = any(
            r.active and r.direction in {"long", "short"} for r in signal_results
        )
        if has_directional_signal and fusion_result.direction == "no_trade":
            fusion_rejected_bars_with_directional_signal += 1

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
        should_open, entry_direction, entry_path_v1 = _compute_student_lane_entry_v1(
            flat=flat,
            risk_decision_allowed=risk_decision.allowed,
            fusion_result_direction=str(fusion_result.direction or ""),
            has_directional_signal=has_directional_signal,
            signal_results=signal_results,
            student_execution_intent_v1=student_execution_intent_v1
            if isinstance(student_execution_intent_v1, dict)
            else None,
            student_full_control_lane_v1=bool(student_full_control_lane_v1),
        )
        if should_open and entry_path_v1 == "full_control_024d_fusion_veto":
            student_full_control_024d_fusion_veto_entries += 1
        if should_open and entry_direction in {"long", "short"}:
            exec_manager.open_trade(
                symbol=state.symbol,
                price=state.current_close,
                direction=entry_direction,
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
            if len(trade_entry_signal_proof_samples) < SIGNAL_TRACE_MAX:
                trade_entry_signal_proof_samples.append(
                    {
                        "bar_index_1based": index,
                        "timestamp": state.timestamp,
                        "student_lane_entry_path_v1": entry_path_v1,
                        "entry_close": state.current_close,
                        "fusion_direction": fusion_result.direction,
                        "fusion_threshold_passed": fusion_result.threshold_passed,
                        "fusion_scores": {
                            "long_score": fusion_result.long_score,
                            "short_score": fusion_result.short_score,
                            "gross_score": fusion_result.gross_score,
                            "fusion_score": fusion_result.fusion_score,
                            "conflict_score": fusion_result.conflict_score,
                            "overlap_penalty": fusion_result.overlap_penalty,
                        },
                        "fusion_contributing_signals": list(fusion_result.contributing_signals),
                        "fusion_suppressed_signals": list(fusion_result.suppressed_signals),
                        "active_signal_names_copied_to_trade": list(active_signal_names),
                        "risk": {
                            "allowed": risk_decision.allowed,
                            "veto_reasons": list(risk_decision.veto_reasons),
                        },
                        "atr_proxy_14_at_entry": float(features.atr_proxy_14),
                        "signal_rows": [
                            {
                                "signal_name": r.signal_name,
                                "active": r.active,
                                "direction": r.direction,
                                "confidence": r.confidence,
                                "expected_edge": r.expected_edge,
                                "regime_fit": r.regime_fit,
                                "stability_score": r.stability_score,
                                "suppression_reason": r.suppression_reason,
                                "evidence_trace": dict(r.evidence_trace),
                            }
                            for r in signal_results
                        ],
                    }
                )
            if dt_max > 0:
                dcr_drill_trade_entries.append(
                    {
                        "timestamp": state.timestamp,
                        "direction": fusion_result.direction,
                        "decision_context_signature_key_current": sig_key,
                        "decision_context_recall_bias_applied": bias_applied,
                        "decision_context_signal_bias_applied": sig_bias_applied
                        if signal_bias_v2_trace
                        else False,
                        "context_memory_match_count_for_decision": len(matches)
                        if attempted
                        else 0,
                    }
                )
                dcr_drill_trade_entries = dcr_drill_trade_entries[-dt_max:]

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
                    "per_signal_contribution_multiplier": dict(pcm) if pcm is not None else {},
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

        if live_telemetry_callback is not None:
            live_telemetry_callback(
                {
                    "decision_windows_processed": processed,
                    "bars_processed": processed,
                    "dataset_bars": dataset_bars,
                    "trades_closed_so_far": len(ledger.outcomes),
                    "entries_attempted_so_far": int(entries_attempted),
                    "closes_recorded_so_far": int(closes_recorded),
                    "recall_match_windows_so_far": int(
                        dcr_stats.get("decisions_with_positive_match_count") or 0
                    ),
                    "recall_bias_applied_so_far": int(dcr_stats.get("decisions_with_bias_applied") or 0),
                    "signal_bias_applied_so_far": int(
                        dcr_stats.get("decisions_with_signal_bias_applied") or 0
                    ),
                    "recall_match_records_so_far": int(recall_match_records_total),
                }
            )

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

    outcomes: list[OutcomeRecord] = list(ledger.outcomes)
    disabled_m_final = set(manifest.get("disabled_signal_modules") or [])
    declared_modules = [str(x) for x in (manifest.get("signal_modules") or []) if str(x) not in disabled_m_final]
    trade_by_signal = Counter()
    for o in outcomes:
        for nm in o.contributing_signals or []:
            trade_by_signal[str(nm)] += 1
    evaluated_per_signal = {str(s.signal_name): int(processed) for s in signals}
    dead_signal_rows: list[dict[str, Any]] = []
    for name in declared_modules:
        tc = int(trade_by_signal.get(name, 0))
        dir_bars = int(signal_directional_active_bar_counts.get(name, 0))
        active_bars = int(signal_active_bar_counts.get(name, 0))
        if tc == 0:
            if dir_bars == 0 and active_bars == 0:
                reason = "never_active_any_bar_in_replay_window"
            elif dir_bars == 0:
                reason = "was_active_but_never_directional_long_short"
            else:
                reason = (
                    "had_directional_active_bars_but_zero_closed_trade_attribution "
                    "(see attribution_semantics — fusion may still block entries after this bar)"
                )
            dead_signal_rows.append(
                {
                    "signal": name,
                    "closed_trade_attribution_count": 0,
                    "directional_active_bars": dir_bars,
                    "active_any_bar": active_bars,
                    "analysis": reason,
                }
            )

    def _dominant_trade(c: Counter[str]) -> str | None:
        if not c:
            return None
        return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    scorecard_trade_totals = {
        k: int(v.get("total_trades", 0) or 0) for k, v in (scorecards or {}).items() if isinstance(v, dict)
    }
    _directive_signal_names = (
        "trend_continuation",
        "pullback_continuation",
        "breakout_continuation",
        "mean_reversion_fade",
    )
    directive_per_signal_evaluated_vs_trades_v1 = {
        nm: {
            "evaluated_bars_signal_module_ran": int(processed),
            "active_any_direction_bars": int(signal_active_bar_counts.get(nm, 0)),
            "directional_active_bars": int(signal_directional_active_bar_counts.get(nm, 0)),
            "closed_trade_attribution_count": int(trade_by_signal.get(nm, 0)),
        }
        for nm in _directive_signal_names
    }
    signal_behavior_proof_v1: dict[str, Any] = {
        "schema": "signal_behavior_proof_v1",
        "manifest_signal_modules_declared": declared_modules,
        "manifest_disabled_signal_modules": sorted(str(x) for x in disabled_m_final),
        "per_signal_evaluated_bars_total": evaluated_per_signal,
        "per_signal_active_bars_total": dict(sorted(signal_active_bar_counts.items())),
        "per_signal_directional_active_bars_total": dict(sorted(signal_directional_active_bar_counts.items())),
        "per_signal_closed_trade_attribution_count": dict(sorted(trade_by_signal.items())),
        "ledger_scorecard_total_trades_by_signal": scorecard_trade_totals,
        "dominant_closed_trade_attributing_signal": _dominant_trade(trade_by_signal),
        "attribution_semantics": (
            "per_signal_closed_trade_attribution_count counts each OutcomeRecord.contributing_signals entry "
            "(replay_runner copies all signal_names with active=True on the **entry bar** into the trade; "
            "it is NOT the fusion-only short list). Fusion picks direction; see fusion_contributing_signals "
            "inside trade_entry_raw_samples."
        ),
        "fusion_bars": {
            "fusion_no_trade_bars": int(fusion_no_trade_bars),
            "fusion_directional_output_bars": int(fusion_directional_bars),
            "bars_with_directional_signal_but_fusion_no_trade": int(
                fusion_rejected_bars_with_directional_signal
            ),
            "risk_blocked_bars": int(risk_blocked_bars),
            "trade_entries_attempted": int(entries_attempted),
            "trade_exits_recorded": int(closes_recorded),
        },
        "fusion_signal_level_rollup_v1": {
            "bars_processed_after_warmup": int(processed),
            "directional_signal_instances_total_across_bars": int(directional_signal_instances_total),
            "inactive_with_suppression_reason_events_total": int(inactive_suppression_events_total),
            "fusion_emitted_long_short_bars": int(fusion_directional_bars),
            "fusion_emitted_no_trade_bars": int(fusion_no_trade_bars),
            "bars_fusion_no_trade_while_any_signal_directional": int(
                fusion_rejected_bars_with_directional_signal
            ),
            "trade_open_events_total": int(entries_attempted),
            "closed_trades_recorded_total": int(closes_recorded),
        },
        "directive_per_signal_evaluated_vs_trades_v1": directive_per_signal_evaluated_vs_trades_v1,
        "suppression_reason_histograms_top": {
            k: dict(v.most_common(20)) for k, v in sorted(signal_suppression_hists.items())
        },
        "dead_signals_zero_closed_trade_attribution": dead_signal_rows,
        "trade_entry_raw_samples": trade_entry_signal_proof_samples,
        "trade_entry_raw_samples_max": SIGNAL_TRACE_MAX,
        "atr_usage_code_references_v1": {
            "feature_atr_proxy_14": "renaissance_v4/core/feature_engine.py → FeatureSet.atr_proxy_14",
            "execution_stop_target": (
                "renaissance_v4/research/replay_runner.py passes features.atr_proxy_14 into "
                "ExecutionManager.open_trade; renaissance_v4/core/execution_manager.py sets stop_loss / "
                "take_profit from atr × atr_stop_mult / atr_target_mult (manifest or defaults)."
            ),
            "signals_use_atr_proxy_14": False,
            "signals_note": (
                "Signal modules in renaissance_v4/signals/*.py use FeatureSet fields such as volatility_20; "
                "they do not reference atr_proxy_14 (repo grep)."
            ),
        },
    }

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

    ra = dict(dcr_stats) if decision_context_recall_enabled else {}
    recall_attempts = int(ra.get("recall_attempted") or 0)
    recall_rate = (
        (recall_attempts / float(processed)) if processed and decision_context_recall_enabled else 0.0
    )
    # GT_DIRECTIVE_026TF — explicit replay bar width + post-rollup size for trace alignment.
    _ctf_eff: int = 5
    if ctf is not None and ctf > 5 and ctf % 5 == 0:
        _ctf_eff = int(ctf)
    out: dict[str, Any] = {
        "manifest": manifest,
        "manifest_path": str(resolved_manifest_path),
        "dataset_bars": dataset_bars,
        "replay_timeframe_minutes": int(_ctf_eff),
        "dataset_bars_after_rollup": int(dataset_bars),
        "outcomes": outcomes,
        "validation_checksum": vchk,
        "summary": summary,
        "scorecards": scorecards,
        "cumulative_pnl": exec_manager.cumulative_pnl,
        "sanity": sanity,
        "pattern_context_v1": pattern_context_v1,
        "replay_attempt_aggregates_v1": {
            "bars_processed": int(processed),
            "decision_windows_total": int(processed),
            "recall_attempts_total": recall_attempts,
            "recall_match_windows_total": int(ra.get("decisions_with_positive_match_count") or 0),
            "recall_match_records_total": int(recall_match_records_total),
            "recall_bias_applied_total": int(ra.get("decisions_with_bias_applied") or 0),
            "recall_signal_bias_applied_total": int(ra.get("decisions_with_signal_bias_applied") or 0),
            "recall_no_effect_windows_total": int(recall_no_effect_windows),
            "recall_skipped_unsupported_fusion_total": int(recall_skipped_unsupported_total),
            "recall_utilization_rate": round(recall_rate, 8),
            "actionable_signal_windows_total": int(fusion_directional_bars),
            "no_trade_windows_total": int(fusion_no_trade_bars),
            "trade_entries_total": int(entries_attempted),
            "trade_exits_total": int(closes_recorded),
            "risk_blocked_bars_total": int(risk_blocked_bars),
            "suppressed_module_slots_total": int(ra.get("suppressed_module_slots_total") or 0),
            "memory_records_loaded_count": int(ra.get("memory_records_loaded_count") or 0),
        },
        "decision_context_recall_drill_down_v1": {
            "matched_samples": list(dcr_drill_matched),
            "bias_applied_samples": list(dcr_drill_bias),
            "trade_entry_samples": list(dcr_drill_trade_entries),
        },
        "signal_behavior_proof_v1": signal_behavior_proof_v1,
        "student_full_control_replay_audit_v1": {
            "schema": "student_full_control_replay_audit_v1",
            "student_full_control_lane_requested_v1": bool(student_full_control_lane_v1),
            "student_full_control_024d_fusion_veto_entry_events_v1": int(
                student_full_control_024d_fusion_veto_entries
            ),
            "note_v1": (
                "Entries with path full_control_024d_fusion_veto open when fusion is no_trade but a "
                "directional signal aligns with student_execution_intent_v1; flat and risk still required."
            ),
        },
    }
    if decision_context_recall_enabled:
        out["decision_context_recall_stats"] = dcr_stats
        out["decision_context_recall_samples"] = dcr_samples
    out["replay_data_audit"] = replay_data_audit
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
