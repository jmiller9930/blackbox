"""
Operator Test Harness v1 — single structured artifact combining control replay aggregates,
context-recall utilization, context-conditioned candidate search proof, and Groundhog
commit **recommendations** (no automatic writes).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.context_candidate_search import run_context_candidate_search_v1
from renaissance_v4.game_theory.memory_bundle import BUNDLE_APPLY_WHITELIST
from renaissance_v4.game_theory.pattern_outcome_quality_v1 import (
    DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY,
)

OPERATOR_TEST_HARNESS_SCHEMA = "operator_test_harness_v1"


def _git_revision(repo_root: Path | None = None) -> str | None:
    try:
        # .../renaissance_v4/game_theory/this_file.py -> repo root is parents[2]
        cwd = repo_root or Path(__file__).resolve().parents[2]
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()[:40] or None
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return None


def _fmt_apply_diff_for_summary(apply_diff: list[dict[str, Any]] | None) -> str:
    if not apply_diff:
        return "none"
    parts: list[str] = []
    for row in apply_diff[:12]:
        k = row.get("key")
        parts.append(f"{k}: {row.get('old')} -> {row.get('new')}")
    return "; ".join(parts)


def build_groundhog_commit_block_v1(
    *,
    selected_candidate_id: str | None,
    winner_apply_effective: dict[str, Any] | None,
    search_reason_codes: list[str],
) -> dict[str, Any]:
    """Recommendation only — does not write ``groundhog_memory_bundle.json``."""
    win = bool(selected_candidate_id)
    apply_clean = {k: v for k, v in (winner_apply_effective or {}).items() if k in BUNDLE_APPLY_WHITELIST}
    codes: list[str] = []
    no_commit: str | None = None
    if win:
        codes.append("GTH_V1_COMMIT_WOULD_PROMOTE_WINNER_APPLY")
        if "CCS_V1_SELECTED_STRICTLY_BEATS_CONTROL" in search_reason_codes:
            codes.append("CCS_V1_SELECTED_STRICTLY_BEATS_CONTROL")
    else:
        codes.append("GTH_V1_NO_COMMIT")
        if "CCS_V1_NONE_BEAT_CONTROL" in search_reason_codes:
            no_commit = "CCS_V1_NONE_BEAT_CONTROL"
        else:
            no_commit = "GTH_V1_NO_WINNER"
    return {
        "groundhog_commit_candidate": win,
        "groundhog_commit_apply": apply_clean if win else {},
        "groundhog_commit_reason_codes": codes,
        "no_commit_reason": None if win else no_commit,
    }


def build_operator_summary_block_v1(
    *,
    context_family: str | None,
    decision_windows_total: int,
    recall_utilization_rate: float,
    trade_count: int,
    selected_candidate_id: str | None,
    winner_vs_control: dict[str, Any] | None,
    winner_apply_diff: list[dict[str, Any]] | None,
    groundhog_commit_candidate: bool,
    control_outcome_quality_v1: dict[str, Any] | None,
    winner_outcome_quality_delta_v1: dict[str, Any] | None,
) -> dict[str, str]:
    """Human-readable lines derived only from structured inputs (no LLM)."""
    sel = selected_candidate_id or "none"
    ev_d = winner_vs_control.get("expectancy_delta") if winner_vs_control else None
    dd_d = winner_vs_control.get("max_drawdown_delta") if winner_vs_control else None
    coq = control_outcome_quality_v1 or {}
    woq = winner_outcome_quality_delta_v1 or {}
    return {
        "context_family": str(context_family or "unknown"),
        "total_decision_attempts": str(int(decision_windows_total)),
        "recall_usage_rate": f"{float(recall_utilization_rate):.6f}",
        "trade_count": str(int(trade_count)),
        "winner_or_none": sel,
        "key_parameter_changes": _fmt_apply_diff_for_summary(winner_apply_diff),
        "expectancy_delta_vs_control": "n/a" if ev_d is None else str(ev_d),
        "max_drawdown_delta_vs_control": "n/a" if dd_d is None else str(dd_d),
        "expectancy_per_trade_control": str(coq.get("expectancy_per_trade", "n/a")),
        "exit_efficiency_control": str(coq.get("exit_efficiency", "n/a")),
        "win_loss_size_ratio_control": str(coq.get("win_loss_size_ratio", "n/a")),
        "expectancy_per_trade_delta_vs_control": str(woq.get("expectancy_per_trade_delta", "n/a")),
        "exit_efficiency_delta_vs_control": str(woq.get("exit_efficiency_delta", "n/a")),
        "groundhog_update_recommended": "yes" if groundhog_commit_candidate else "no",
    }


def run_operator_test_harness_v1(
    manifest_path: Path | str,
    *,
    test_run_id: str | None = None,
    source_preset_or_manifest: str | None = None,
    control_apply: dict[str, Any] | None = None,
    context_signature_v1: dict[str, Any] | None = None,
    pattern_context_v1: dict[str, Any] | None = None,
    memory_prior_apply: dict[str, Any] | None = None,
    source_run_id: str = "operator_harness_v1",
    decision_context_recall_enabled: bool = True,
    decision_context_recall_apply_bias: bool = True,
    decision_context_recall_apply_signal_bias_v2: bool = False,
    decision_context_recall_memory_path: Path | str | None = None,
    decision_context_recall_max_samples: int = 24,
    decision_context_recall_drill_matched_max: int = 8,
    decision_context_recall_drill_bias_max: int = 8,
    decision_context_recall_drill_trade_entry_max: int = 5,
    repo_root_for_git: Path | None = None,
    goal_v2: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run control replay (with drill-down caps) embedded in candidate search, emit one harness dict.

    This calls :func:`run_context_candidate_search_v1` once; the **control** replay inside it
    supplies attempt aggregates and drill-down samples for the operator.
    """
    mp = Path(manifest_path).resolve()
    preset = source_preset_or_manifest or str(mp)
    rid = test_run_id or hashlib.sha256(
        json.dumps(
            {"manifest": str(mp), "sig": context_signature_v1 is not None},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]

    goal_effective = goal_v2 if goal_v2 is not None else dict(DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY)

    search_out = run_context_candidate_search_v1(
        mp,
        control_apply=control_apply,
        context_signature_v1=context_signature_v1,
        pattern_context_v1=pattern_context_v1,
        memory_prior_apply=memory_prior_apply,
        source_run_id=source_run_id,
        parent_reference_id="operator_harness_control",
        decision_context_recall_enabled=decision_context_recall_enabled,
        decision_context_recall_apply_bias=decision_context_recall_apply_bias,
        decision_context_recall_apply_signal_bias_v2=decision_context_recall_apply_signal_bias_v2,
        decision_context_recall_memory_path=decision_context_recall_memory_path,
        decision_context_recall_max_samples=decision_context_recall_max_samples,
        decision_context_recall_drill_matched_max=decision_context_recall_drill_matched_max,
        decision_context_recall_drill_bias_max=decision_context_recall_drill_bias_max,
        decision_context_recall_drill_trade_entry_max=decision_context_recall_drill_trade_entry_max,
        goal_v2=goal_effective,
    )
    proof = search_out["context_candidate_search_proof"]
    control_replay = search_out["control_replay"]
    agg = control_replay.get("replay_attempt_aggregates_v1") or {}
    dcr_stats = control_replay.get("decision_context_recall_stats") or {}

    selected = proof.get("selected_candidate_id")
    winner_apply_diff: list[dict[str, Any]] | None = None
    winner_apply_eff: dict[str, Any] | None = None
    winner_oq_delta: dict[str, Any] | None = None
    if selected:
        for row in proof.get("candidate_summaries") or []:
            if row.get("candidate_id") == selected:
                winner_apply_diff = list(row.get("apply_diff_from_control") or [])
                winner_apply_eff = dict(row.get("apply_effective_snapshot") or {})
                winner_oq_delta = dict(row.get("vs_control_outcome_quality_v1") or {})
                break

    gh = build_groundhog_commit_block_v1(
        selected_candidate_id=str(selected) if selected else None,
        winner_apply_effective=winner_apply_eff,
        search_reason_codes=list(proof.get("reason_codes") or []),
    )

    cm = proof.get("control_metrics") if isinstance(proof.get("control_metrics"), dict) else {}
    coq_ctrl = cm.get("outcome_quality_v1") if isinstance(cm.get("outcome_quality_v1"), dict) else {}

    summary_block = build_operator_summary_block_v1(
        context_family=proof.get("source_context_family"),
        decision_windows_total=int(agg.get("decision_windows_total") or 0),
        recall_utilization_rate=float(agg.get("recall_utilization_rate") or 0.0),
        trade_count=int(cm.get("trade_count") or 0),
        selected_candidate_id=str(selected) if selected else None,
        winner_vs_control=proof.get("winner_vs_control") if isinstance(proof.get("winner_vs_control"), dict) else None,
        winner_apply_diff=winner_apply_diff,
        groundhog_commit_candidate=bool(gh["groundhog_commit_candidate"]),
        control_outcome_quality_v1=coq_ctrl,
        winner_outcome_quality_delta_v1=winner_oq_delta,
    )

    recall_block = {
        "decision_context_recall_enabled_flag": decision_context_recall_enabled,
        "decision_context_recall_apply_bias_flag": decision_context_recall_apply_bias,
        "decision_context_recall_apply_signal_bias_v2_flag": decision_context_recall_apply_signal_bias_v2,
        "recall_attempts_total": int(agg.get("recall_attempts_total") or 0),
        "recall_match_windows_total": int(agg.get("recall_match_windows_total") or 0),
        "recall_match_records_total": int(agg.get("recall_match_records_total") or 0),
        "recall_fusion_bias_applied_total": int(agg.get("recall_bias_applied_total") or 0),
        "recall_signal_bias_applied_total": int(agg.get("recall_signal_bias_applied_total") or 0),
        "recall_no_effect_windows_total": int(agg.get("recall_no_effect_windows_total") or 0),
        "recall_skipped_unsupported_fusion_total": int(agg.get("recall_skipped_unsupported_fusion_total") or 0),
        "recall_utilization_rate": float(agg.get("recall_utilization_rate") or 0.0),
        "decision_context_recall_stats": dcr_stats,
    }

    cons = goal_effective.get("constraints") or {}
    min_tc = cons.get("minimum_trade_count")
    max_dd_thr = cons.get("maximum_drawdown_threshold")
    cm_dd = float(cm.get("max_drawdown") or 0.0)
    tc = int(cm.get("trade_count") or 0)
    goal_constraints_check_v1 = {
        "minimum_trade_count_met": True if min_tc is None else (tc >= int(min_tc)),
        "maximum_drawdown_threshold_met": True
        if max_dd_thr is None
        else (cm_dd <= float(max_dd_thr) + 1e-12),
        "minimum_trade_count_required": min_tc,
        "maximum_drawdown_threshold": max_dd_thr,
    }

    harness: dict[str, Any] = {
        "schema": OPERATOR_TEST_HARNESS_SCHEMA,
        "version": 1,
        "goal_v2": goal_effective,
        "test_run_id": rid,
        "reproducibility_v1": {
            "source_preset_or_manifest": preset,
            "context_signature_v1": proof.get("source_context_signature_v1"),
            "search_batch_id": proof.get("search_batch_id"),
            "git_revision": _git_revision(repo_root_for_git),
            "flags": {
                "decision_context_recall_enabled": decision_context_recall_enabled,
                "decision_context_recall_apply_bias": decision_context_recall_apply_bias,
                "decision_context_recall_apply_signal_bias_v2": decision_context_recall_apply_signal_bias_v2,
            },
        },
        "control_replay_validation_checksum": control_replay.get("validation_checksum"),
        "replay_attempt_aggregates_v1": agg,
        "decision_context_recall_drill_down_v1": control_replay.get("decision_context_recall_drill_down_v1")
        or {},
        "context_recall_utilization_v1": recall_block,
        "context_candidate_search_proof": proof,
        "control_outcome_quality_v1": coq_ctrl,
        "winner_outcome_quality_delta_v1": winner_oq_delta,
        "goal_constraints_check_v1": goal_constraints_check_v1,
        "groundhog_commit_recommendation_v1": gh,
        "operator_summary_block_v1": summary_block,
        "operator_summary_text_v1": " | ".join(f"{k}={v}" for k, v in sorted(summary_block.items())),
    }
    return {
        "operator_test_harness_v1": harness,
        "context_candidate_search_raw": search_out,
    }


__all__ = [
    "OPERATOR_TEST_HARNESS_SCHEMA",
    "DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY",
    "build_groundhog_commit_block_v1",
    "build_operator_summary_block_v1",
    "run_operator_test_harness_v1",
]
