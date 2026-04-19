"""
Bundle Optimizer v1 / v2 / v3 — deterministic, rule-based proposals for the next run's memory bundle.

Reads **structured** metrics only (no narrative, no LLM). Emits a schema-valid
``pattern_game_memory_bundle_v1`` document with **whitelisted** ``apply`` keys and a
parallel **optimizer proof** record for audit.

v2 adds :func:`optimize_bundle_v2`, which layers **pattern-context** rules on top of v1
when ``pattern_context_v1`` is present on the run (from replay: ``pattern_context_v1``).

v3 adds :func:`optimize_bundle_v3`, which may bias the v2 proposal using append-only
:mod:`renaissance_v4.game_theory.context_signature_memory` (deterministic signature match + outcome gates).

See :func:`optimize_bundle_v1`, :func:`optimize_bundle_v2`, :func:`optimize_bundle_v3`, and
:func:`extract_metrics_from_pattern_game_run`.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from renaissance_v4.core.fusion_engine import (
    MAX_CONFLICT_SCORE,
    MIN_FUSION_SCORE,
    OVERLAP_PENALTY_PER_EXTRA_SIGNAL,
)
from renaissance_v4.game_theory.context_signature_memory import (
    ContextSignatureMemoryError,
    SignatureMatchParamsV1,
    apply_context_memory_bias_v1,
    canonical_signature_key,
    default_memory_path,
    derive_context_signature_v1,
    eligible_bias_records,
    find_matching_records_v1,
    read_context_memory_records,
)
from renaissance_v4.game_theory.memory_bundle import MEMORY_BUNDLE_SCHEMA, load_memory_bundle

# Defaults when manifest did not override (same module baselines as fusion_engine / signals).
_DEFAULT_FUSION_MIN = float(MIN_FUSION_SCORE)
_DEFAULT_FUSION_MAX_CONFLICT = float(MAX_CONFLICT_SCORE)
_DEFAULT_MR_MIN_CONF = 0.53
_DEFAULT_STRETCH = 0.003


class BundleOptimizerError(ValueError):
    """Invalid or missing structured input for the optimizer."""


def extract_metrics_from_pattern_game_run(run: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a :func:`renaissance_v4.game_theory.pattern_game.run_pattern_game` return dict
    into optimizer input fields. Fails closed if required structure is missing.
    """
    if not isinstance(run, dict):
        raise BundleOptimizerError("run must be a dict")
    summary = run.get("summary")
    sanity = run.get("sanity")
    if not isinstance(summary, dict):
        raise BundleOptimizerError("run.summary must be a dict")
    if not isinstance(sanity, dict):
        raise BundleOptimizerError("run.sanity must be a dict")
    sc = run.get("scorecards")
    if sc is not None and not isinstance(sc, dict):
        raise BundleOptimizerError("run.scorecards must be a dict or omitted")

    rid = str(run.get("source_run_id") or run.get("validation_checksum") or "")[:32] or "unknown"
    out: dict[str, Any] = {
        "source_run_id": rid,
        "total_trades": int(summary.get("total_trades") or 0),
        "max_drawdown": float(summary.get("max_drawdown") or 0.0),
        "win_rate": float(summary.get("win_rate") or 0.0),
        "expectancy": float(summary.get("expectancy") or 0.0),
        "cumulative_pnl": float(run.get("cumulative_pnl") or 0.0),
        "fusion_no_trade_bars": int(sanity.get("fusion_no_trade_bars") or 0),
        "fusion_directional_bars": int(sanity.get("fusion_directional_bars") or 0),
        "entries_attempted": int(sanity.get("entries_attempted") or 0),
        "closes_recorded": int(sanity.get("closes_recorded") or 0),
        "risk_blocked_bars": int(sanity.get("risk_blocked_bars") or 0),
        "dataset_bars": int(run.get("dataset_bars") or 0),
        "scorecards": sc if isinstance(sc, dict) else {},
        "memory_bundle_proof": run.get("memory_bundle_proof") if isinstance(run.get("memory_bundle_proof"), dict) else None,
    }
    pc = run.get("pattern_context_v1")
    if pc is not None:
        if not isinstance(pc, dict):
            raise BundleOptimizerError("run.pattern_context_v1 must be a dict or omitted")
        if pc.get("schema") != "pattern_context_v1":
            raise BundleOptimizerError("run.pattern_context_v1.schema must be 'pattern_context_v1'")
        out["pattern_context_v1"] = pc
    return out


def _effective_fusion_min(prior_apply: dict[str, Any] | None) -> float:
    if prior_apply and prior_apply.get("fusion_min_score") is not None:
        return float(prior_apply["fusion_min_score"])
    return _DEFAULT_FUSION_MIN


def _pick_signals_to_disable(
    scorecards: dict[str, Any],
    *,
    manifest_modules: list[str],
    min_trades: int = 3,
    expectancy_floor: float = -0.25,
) -> list[str]:
    """Disable signal ids with enough trades and strongly negative expectancy."""
    out: list[str] = []
    for sid, row in scorecards.items():
        if sid not in manifest_modules:
            continue
        if not isinstance(row, dict):
            continue
        tt = int(row.get("total_trades") or 0)
        ex = float(row.get("expectancy") or 0.0)
        if tt >= min_trades and ex < expectancy_floor:
            out.append(sid)
    return sorted(set(out))


def optimize_bundle_v1(
    metrics: dict[str, Any],
    *,
    prior_apply: dict[str, Any] | None = None,
    manifest_signal_modules: list[str] | None = None,
    optimizer_run_id: str | None = None,
    source_artifact_paths: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Apply deterministic v1 rules; return ``(bundle_document, optimizer_proof)``.

    * ``prior_apply`` — last merged apply block (e.g. from a previous bundle), for old→new diffs.
    * ``manifest_signal_modules`` — active catalog signal ids from the manifest (for disable policy).
    """
    required = (
        "source_run_id",
        "total_trades",
        "fusion_no_trade_bars",
        "fusion_directional_bars",
        "closes_recorded",
    )
    for k in required:
        if k not in metrics:
            raise BundleOptimizerError(f"metrics missing required key: {k}")

    mods = list(manifest_signal_modules or [])
    prior = dict(prior_apply) if prior_apply else {}
    apply_out: dict[str, Any] = {}
    triggered: list[dict[str, Any]] = []
    apply_diff: list[dict[str, Any]] = []

    def _record(key: str, new_val: Any, reason_code: str, old_val: Any | None) -> None:
        apply_out[key] = new_val
        apply_diff.append(
            {
                "key": key,
                "old": old_val,
                "new": new_val,
                "reason_code": reason_code,
            }
        )
        triggered.append(
            {"reason_code": reason_code, "key": key, "old": old_val, "new": new_val}
        )

    closes = int(metrics["closes_recorded"])
    fn = int(metrics["fusion_no_trade_bars"])
    fd = int(metrics["fusion_directional_bars"])
    total_trades = int(metrics["total_trades"])
    dd = float(metrics.get("max_drawdown") or 0.0)
    win_rate = float(metrics.get("win_rate") or 0.0)

    eff_fusion = _effective_fusion_min(prior)

    # Rule 1: No completed trades — fusion likely too strict; relax fusion gate and MR floor.
    # Require enough bars where fusion abstained to avoid noisy tiny replays.
    if closes == 0 and total_trades == 0 and fn >= 10:
        new_f = max(0.05, round(eff_fusion - 0.06, 4))
        if new_f != eff_fusion:
            _record("fusion_min_score", new_f, "V1_NO_TRADES_RELAX_FUSION", eff_fusion)
        old_mr = prior.get("mean_reversion_fade_min_confidence")
        base_mr = float(old_mr) if old_mr is not None else _DEFAULT_MR_MIN_CONF
        new_mr = max(0.35, round(base_mr - 0.08, 4))
        if new_mr != base_mr:
            _record(
                "mean_reversion_fade_min_confidence",
                new_mr,
                "V1_NO_TRADES_RELAX_MR_CONF",
                base_mr,
            )
        old_st = prior.get("mean_reversion_fade_stretch_threshold")
        base_st = float(old_st) if old_st is not None else _DEFAULT_STRETCH
        new_st = max(0.0005, round(base_st * 0.85, 6))
        if new_st != base_st:
            _record(
                "mean_reversion_fade_stretch_threshold",
                new_st,
                "V1_NO_TRADES_RELAX_STRETCH",
                base_st,
            )

    # Rule 2: Trades occurred but drawdown large — tighten gate slightly.
    elif closes >= 1 and dd > 40.0:
        new_f = min(0.55, round(eff_fusion + 0.05, 4))
        if new_f != eff_fusion:
            _record("fusion_min_score", new_f, "V1_HIGH_DRAWDOWN_TIGHTEN_FUSION", eff_fusion)
        old_atr_s = prior.get("atr_stop_mult")
        base_s = float(old_atr_s) if old_atr_s is not None else 2.0
        new_s = min(6.0, round(base_s + 0.15, 3))
        if new_s != base_s:
            _record("atr_stop_mult", new_s, "V1_HIGH_DRAWDOWN_WIDEN_STOP_ATR", base_s)

    # Rule 3: Many fusion directional bars but poor win rate — tighten conflict cap.
    elif total_trades >= 4 and win_rate < 0.35 and fd > fn:
        old_mc = prior.get("fusion_max_conflict_score")
        base_mc = float(old_mc) if old_mc is not None else _DEFAULT_FUSION_MAX_CONFLICT
        new_mc = max(0.15, round(base_mc - 0.05, 4))
        if new_mc != base_mc:
            _record(
                "fusion_max_conflict_score",
                new_mc,
                "V1_LOW_WINRATE_TIGHTEN_CONFLICT_CAP",
                base_mc,
            )

    # Rule 4: Underperforming signal families (structured scorecards only).
    scorecards = metrics.get("scorecards") or {}
    if mods and isinstance(scorecards, dict):
        to_disable = _pick_signals_to_disable(scorecards, manifest_modules=mods)
        already = list(prior.get("disabled_signal_modules") or [])
        merged = sorted(set(already) | set(to_disable))
        # Must leave ≥1 enabled signal.
        remaining = [m for m in mods if m not in merged]
        if to_disable and len(remaining) >= 1:
            _record(
                "disabled_signal_modules",
                merged,
                "V1_SIGNAL_EXPECTANCY_DISABLE",
                already if already else None,
            )
        elif to_disable and len(remaining) < 1:
            triggered.append(
                {
                    "reason_code": "V1_SIGNAL_EXPECTANCY_DISABLE_SKIPPED",
                    "detail": "would leave zero signals; not applied",
                    "candidates": to_disable,
                }
            )

    opt_id = optimizer_run_id or uuid.uuid4().hex[:16]
    bundle_doc: dict[str, Any] = {
        "schema": MEMORY_BUNDLE_SCHEMA,
        "from_run_id": str(metrics["source_run_id"]),
        "note": f"bundle_optimizer_v1 run={opt_id} deterministic rules; not learning.",
        "apply": apply_out,
    }

    proof: dict[str, Any] = {
        "schema": "bundle_optimizer_proof_v1",
        "optimizer_run_id": opt_id,
        "source_run_id": metrics["source_run_id"],
        "source_artifact_paths": list(source_artifact_paths or []),
        "source_metrics_used": {k: metrics[k] for k in sorted(metrics.keys()) if k != "scorecards"},
        "source_scorecard_keys": sorted((metrics.get("scorecards") or {}).keys()),
        "triggered_rules": triggered,
        "apply_diff": apply_diff,
        "reason_codes": [x["reason_code"] for x in apply_diff],
        "bundle_output_apply": apply_out,
        "no_changes": len(apply_out) == 0,
    }
    if len(apply_out) == 0:
        proof["no_changes_reason"] = (
            "V1_NO_RULES_TRIGGERED — inputs did not satisfy any v1 threshold; "
            "see source_metrics_used and triggered_rules."
        )

    return bundle_doc, proof


def _merge_apply(prior: dict[str, Any] | None, delta: dict[str, Any]) -> dict[str, Any]:
    out = dict(prior or {})
    out.update(delta)
    return out


def _effective_fusion_max_conflict(prior_apply: dict[str, Any] | None) -> float:
    if prior_apply and prior_apply.get("fusion_max_conflict_score") is not None:
        return float(prior_apply["fusion_max_conflict_score"])
    return _DEFAULT_FUSION_MAX_CONFLICT


def _apply_pattern_rules_v2(
    metrics: dict[str, Any],
    effective_apply: dict[str, Any],
    *,
    manifest_signal_modules: list[str] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], list[str]]:
    """
    Deterministic pattern-context layer. Returns
    ``(pattern_apply_delta, pattern_apply_diff, pattern_rules_triggered, pattern_context_used, pattern_reason_codes)``.
    """
    pc = metrics.get("pattern_context_v1")
    mods = list(manifest_signal_modules or [])
    pattern_apply: dict[str, Any] = {}
    apply_diff: list[dict[str, Any]] = []
    triggered: list[dict[str, Any]] = []
    reason_codes: list[str] = []

    if not isinstance(pc, dict) or pc.get("schema") != "pattern_context_v1":
        return (
            {},
            [],
            [],
            {"pattern_context_available": False},
            [],
        )

    bars = int(pc.get("bars_processed") or 0)
    tags = pc.get("structure_tag_shares") if isinstance(pc.get("structure_tag_shares"), dict) else {}
    range_like = float(tags.get("range_like") or 0.0)
    vol_c = float(tags.get("vol_compressed") or 0.0)
    brk_like = float(tags.get("breakout_like") or 0.0)
    vol_ex = float(tags.get("vol_expanding") or 0.0)
    hc = int(pc.get("high_conflict_bars") or 0)
    hc_share = float(hc) / float(bars) if bars else 0.0
    ct = int(pc.get("countertrend_directional_bars") or 0)
    al = int(pc.get("aligned_directional_bars") or 0)

    closes = int(metrics["closes_recorded"])
    total_trades = int(metrics["total_trades"])
    win_rate = float(metrics.get("win_rate") or 0.0)
    fn = int(metrics.get("fusion_no_trade_bars") or 0)

    context_used: dict[str, Any] = {
        "bars_processed": bars,
        "structure_tag_shares": {
            "range_like": range_like,
            "vol_compressed": vol_c,
            "breakout_like": brk_like,
            "vol_expanding": vol_ex,
        },
        "high_conflict_share": round(hc_share, 6),
        "countertrend_directional_bars": ct,
        "aligned_directional_bars": al,
    }

    def _rec(key: str, new_val: Any, reason_code: str, old_val: Any | None) -> None:
        pattern_apply[key] = new_val
        apply_diff.append(
            {"key": key, "old": old_val, "new": new_val, "reason_code": reason_code, "layer": "pattern_v2"}
        )
        triggered.append(
            {"reason_code": reason_code, "key": key, "old": old_val, "new": new_val, "layer": "pattern_v2"}
        )
        reason_codes.append(reason_code)

    # P2: No completed trades while range-like + compressed-vol structure dominates — extra MR stretch only.
    if (
        closes == 0
        and total_trades == 0
        and bars >= 50
        and range_like >= 0.40
        and vol_c >= 0.30
        and "mean_reversion_fade" in mods
    ):
        old_st = effective_apply.get("mean_reversion_fade_stretch_threshold")
        base_st = float(old_st) if old_st is not None else _DEFAULT_STRETCH
        new_st = max(0.0005, round(base_st * 0.94, 6))
        if new_st != base_st:
            _rec(
                "mean_reversion_fade_stretch_threshold",
                new_st,
                "P2_LOWVOL_RANGE_EXTRA_RELAX_MR_STRETCH",
                base_st,
            )

    # P2: High conflict share with poor win rate — tighten conflict cap.
    if total_trades >= 3 and win_rate < 0.40 and hc_share >= 0.22:
        old_mc = effective_apply.get("fusion_max_conflict_score")
        base_mc = float(old_mc) if old_mc is not None else _effective_fusion_max_conflict(effective_apply)
        new_mc = max(0.12, round(base_mc - 0.04, 4))
        if new_mc != base_mc:
            _rec("fusion_max_conflict_score", new_mc, "P2_HIGH_CONFLICT_SHARE_TIGHTEN_CONFLICT_CAP", base_mc)

    # P2: Directional decisions skew countertrend vs trend alignment — tighten fusion floor.
    ct_skew = (al > 0 and ct > al * 1.25) or (al == 0 and ct >= 8)
    if total_trades >= 2 and win_rate < 0.45 and ct_skew:
        eff_f = _effective_fusion_min(effective_apply)
        new_f = min(0.52, round(eff_f + 0.025, 4))
        if new_f != eff_f:
            _rec("fusion_min_score", new_f, "P2_COUNTERTREND_DOMINANT_TIGHTEN_FUSION_MIN", eff_f)

    # P2: Breakout hypothesis underperforms in expansion-heavy structure — disable module if safe.
    sc = metrics.get("scorecards") or {}
    br = sc.get("breakout_expansion") if isinstance(sc.get("breakout_expansion"), dict) else {}
    br_tt = int(br.get("total_trades") or 0)
    br_ex = float(br.get("expectancy") or 0.0)
    if (
        "breakout_expansion" in mods
        and br_tt >= 2
        and br_ex < -0.15
        and (brk_like >= 0.20 or vol_ex >= 0.26)
    ):
        already = list(effective_apply.get("disabled_signal_modules") or [])
        if "breakout_expansion" not in already:
            merged = sorted(set(already) | {"breakout_expansion"})
            remaining = [m for m in mods if m not in merged]
            if len(remaining) >= 1:
                _rec(
                    "disabled_signal_modules",
                    merged,
                    "P2_BREAKOUT_UNDERPERF_EXPANSION_CONTEXT_DISABLE",
                    already if already else None,
                )

    return pattern_apply, apply_diff, triggered, context_used, reason_codes


def optimize_bundle_v2(
    metrics: dict[str, Any],
    *,
    prior_apply: dict[str, Any] | None = None,
    manifest_signal_modules: list[str] | None = None,
    optimizer_run_id: str | None = None,
    source_artifact_paths: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run v1 rules, then deterministic pattern-context rules (v2) on merged effective apply.

    Requires the same ``metrics`` keys as v1. Optional ``pattern_context_v1`` on ``metrics`` enables
    pattern rules; if absent, behavior matches v1 (pattern proof fields show no context).
    """
    bundle_v1, proof_v1 = optimize_bundle_v1(
        metrics,
        prior_apply=prior_apply,
        manifest_signal_modules=manifest_signal_modules,
        optimizer_run_id=optimizer_run_id,
        source_artifact_paths=source_artifact_paths,
    )
    opt_id = str(proof_v1["optimizer_run_id"])
    v1_apply = dict(bundle_v1.get("apply") or {})
    effective = _merge_apply(prior_apply, v1_apply)

    p_apply, p_diff, p_trig, p_used, p_codes = _apply_pattern_rules_v2(
        metrics,
        effective,
        manifest_signal_modules=manifest_signal_modules,
    )

    final_apply = {**v1_apply, **p_apply}

    bundle_doc: dict[str, Any] = {
        **bundle_v1,
        "apply": final_apply,
        "note": f"bundle_optimizer_v2 run={opt_id} v1+pattern deterministic rules; not learning.",
    }

    v1_codes = list(proof_v1.get("reason_codes") or [])
    combined_codes = v1_codes + p_codes
    combined_diff = list(proof_v1.get("apply_diff") or []) + p_diff
    combined_trig = list(proof_v1.get("triggered_rules") or []) + p_trig

    proof_v2: dict[str, Any] = {
        "schema": "bundle_optimizer_proof_v2",
        "optimizer_run_id": opt_id,
        "source_run_id": metrics["source_run_id"],
        "source_artifact_paths": list(source_artifact_paths or []),
        "v1_proof": proof_v1,
        "pattern_context_used": p_used,
        "pattern_rules_triggered": p_trig,
        "pattern_reason_codes": p_codes,
        "pattern_apply_diff": p_diff,
        "source_metrics_used": {
            k: metrics[k]
            for k in sorted(metrics.keys())
            if k not in ("scorecards", "pattern_context_v1")
        },
        "pattern_context_v1_summary": {
            "schema": (metrics.get("pattern_context_v1") or {}).get("schema"),
            "bars_processed": (metrics.get("pattern_context_v1") or {}).get("bars_processed"),
            "dominant_regime": (metrics.get("pattern_context_v1") or {}).get("dominant_regime"),
            "dominant_volatility_bucket": (metrics.get("pattern_context_v1") or {}).get(
                "dominant_volatility_bucket"
            ),
        }
        if metrics.get("pattern_context_v1")
        else None,
        "source_scorecard_keys": sorted((metrics.get("scorecards") or {}).keys()),
        "triggered_rules": combined_trig,
        "apply_diff": combined_diff,
        "reason_codes": combined_codes,
        "bundle_output_apply": final_apply,
        "no_changes": len(final_apply) == 0,
    }
    if len(final_apply) == 0:
        proof_v2["no_changes_reason"] = proof_v1.get(
            "no_changes_reason",
            "V2_NO_APPLY — v1 and pattern produced empty apply.",
        )
    return bundle_doc, proof_v2


def optimize_bundle_v3(
    metrics: dict[str, Any],
    *,
    prior_apply: dict[str, Any] | None = None,
    manifest_signal_modules: list[str] | None = None,
    optimizer_run_id: str | None = None,
    source_artifact_paths: list[str] | None = None,
    context_memory_path: Path | str | None = None,
    signature_match_params: SignatureMatchParamsV1 | None = None,
    skip_context_memory_bias: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run v2, then optionally apply Context Signature Memory v1 bias from the JSONL store.

    * ``context_memory_path`` — append-only JSONL (default: ``state/context_signature_memory.jsonl`` package path).
    * ``skip_context_memory_bias`` — force v2-only output (proof records skip reason).
    """
    bundle_v2, proof_v2 = optimize_bundle_v2(
        metrics,
        prior_apply=prior_apply,
        manifest_signal_modules=manifest_signal_modules,
        optimizer_run_id=optimizer_run_id,
        source_artifact_paths=source_artifact_paths,
    )
    opt_id = str(proof_v2["optimizer_run_id"])
    v2_apply = dict(bundle_v2.get("apply") or {})

    cm_reason_codes: list[str] = []
    bias_diff: list[dict[str, Any]] = []
    sig_current: dict[str, Any] | None = None
    matches_out: list[dict[str, Any]] = []
    match_count = 0
    bias_applied = False
    mem_delta: dict[str, Any] = {}
    mem_path = Path(context_memory_path).expanduser().resolve() if context_memory_path else default_memory_path()

    if skip_context_memory_bias:
        cm_reason_codes.append("CM3_SKIPPED_FLAG_SKIP_CONTEXT_MEMORY_BIAS")
    else:
        pc = metrics.get("pattern_context_v1")
        if not isinstance(pc, dict) or pc.get("schema") != "pattern_context_v1":
            cm_reason_codes.append("CM3_SKIPPED_NO_PATTERN_CONTEXT_V1")
        else:
            try:
                sig_current = derive_context_signature_v1(pc)
            except ContextSignatureMemoryError as e:
                raise BundleOptimizerError(str(e)) from e
            try:
                records = read_context_memory_records(mem_path)
            except ContextSignatureMemoryError as e:
                raise BundleOptimizerError(str(e)) from e
            params = signature_match_params or SignatureMatchParamsV1()
            matches = find_matching_records_v1(sig_current, records, params=params)
            match_count = len(matches)
            for rec in matches:
                matches_out.append(
                    {
                        "record_id": rec.get("record_id"),
                        "signature_key": rec.get("signature_key"),
                        "source_run_id": rec.get("source_run_id"),
                        "outcome_summary": rec.get("outcome_summary"),
                    }
                )
            if match_count == 0:
                cm_reason_codes.append("CM3_NO_MATCHING_SIGNATURES_IN_STORE")
            else:
                current_outcome = {
                    "expectancy": float(metrics.get("expectancy") or 0.0),
                    "max_drawdown": float(metrics.get("max_drawdown") or 0.0),
                    "win_rate": float(metrics.get("win_rate") or 0.0),
                    "total_trades": int(metrics.get("total_trades") or 0),
                    "cumulative_pnl": float(metrics.get("cumulative_pnl") or 0.0),
                }
                try:
                    eligible = eligible_bias_records(matches, current_outcome)
                except ContextSignatureMemoryError as e:
                    raise BundleOptimizerError(str(e)) from e
                if not eligible:
                    cm_reason_codes.append(
                        "CM3_MATCHES_FOUND_NO_STRICT_OUTCOME_BENEFIT — "
                        "no prior record has strictly higher expectancy and strictly lower max_drawdown than this run.",
                    )
                else:
                    mem_delta, mem_diff, bcodes = apply_context_memory_bias_v1(
                        v2_apply,
                        eligible_records=eligible,
                        manifest_signal_modules=manifest_signal_modules,
                    )
                    cm_reason_codes.extend(bcodes)
                    bias_diff = list(mem_diff)
                    if mem_delta:
                        bias_applied = True
                    else:
                        cm_reason_codes.append(
                            "CM3_ELIGIBLE_BUT_NO_BIAS_DELTA — v2 apply already at or within step of prior targets.",
                        )

    final_apply = {**v2_apply, **mem_delta}

    bundle_doc = {
        **bundle_v2,
        "apply": final_apply,
        "note": (
            f"bundle_optimizer_v3 run={opt_id} v2 + context signature memory bias; not learning."
        ),
    }

    sig_key: str | None = canonical_signature_key(sig_current) if sig_current is not None else None

    proof_v3: dict[str, Any] = {
        "schema": "bundle_optimizer_proof_v3",
        "optimizer_run_id": opt_id,
        "source_run_id": metrics["source_run_id"],
        "source_artifact_paths": list(source_artifact_paths or []),
        "v2_proof": proof_v2,
        "context_memory_path_resolved": str(mem_path),
        "context_signature_current": sig_current,
        "context_signature_key_current": sig_key,
        "context_memory_matches": matches_out,
        "context_memory_match_count": match_count,
        "context_memory_bias_applied": bias_applied,
        "context_memory_bias_diff": bias_diff,
        "context_memory_reason_codes": cm_reason_codes,
        "triggered_rules": list(proof_v2.get("triggered_rules") or []),
        "apply_diff": list(proof_v2.get("apply_diff") or []),
        "reason_codes": list(proof_v2.get("reason_codes") or []),
        "bundle_output_apply": final_apply,
        "no_changes": len(final_apply) == 0,
    }
    if len(final_apply) == 0:
        proof_v3["no_changes_reason"] = proof_v2.get(
            "no_changes_reason",
            "V3_NO_APPLY — v2 and context memory produced empty apply.",
        )

    return bundle_doc, proof_v3


def write_bundle_and_proof(
    bundle_doc: dict[str, Any],
    proof: dict[str, Any],
    *,
    bundle_path: Path | str,
    proof_path: Path | str,
) -> tuple[Path, Path, dict[str, Any]]:
    """Write JSON files; validate bundle loads via :func:`load_memory_bundle`. Proof includes output paths."""
    bp = Path(bundle_path).expanduser().resolve()
    pp = Path(proof_path).expanduser().resolve()
    bp.parent.mkdir(parents=True, exist_ok=True)
    pp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_text(json.dumps(bundle_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    proof_out = {
        **proof,
        "bundle_output_path": str(bp),
        "optimizer_proof_path": str(pp),
    }
    pp.write_text(json.dumps(proof_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    load_memory_bundle(bp)
    return bp, pp, proof_out


def load_metrics_json(path: Path | str) -> dict[str, Any]:
    """Load a JSON file containing a metrics dict or a full pattern-game run wrapper."""
    p = Path(path).expanduser().resolve()
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BundleOptimizerError("metrics JSON must be an object")
    if "summary" in raw and "sanity" in raw:
        return extract_metrics_from_pattern_game_run(raw)
    return raw
