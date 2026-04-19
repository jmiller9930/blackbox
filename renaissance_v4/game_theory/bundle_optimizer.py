"""
Bundle Optimizer v1 — deterministic, rule-based proposals for the next run's memory bundle.

Reads **structured** metrics only (no narrative, no LLM). Emits a schema-valid
``pattern_game_memory_bundle_v1`` document with **whitelisted** ``apply`` keys and a
parallel **optimizer proof** record for audit.

See :func:`optimize_bundle_v1` and :func:`extract_metrics_from_pattern_game_run`.
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
    return {
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
