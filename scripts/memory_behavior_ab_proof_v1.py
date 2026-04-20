#!/usr/bin/env python3
"""
memory_behavior_ab_proof_v1.py

Controlled A/B: same manifest + same bar window, Run A memory OFF vs Run B memory ON
(bundle and/or Decision Context Recall). Emits a single JSON proof document and exits
non-zero if the mandate acceptance gate fails.

Usage (from repo root)::

    PYTHONPATH=. python3 scripts/memory_behavior_ab_proof_v1.py \\
        --manifest renaissance_v4/configs/manifests/baseline_v1_recipe.json \\
        --months 12 \\
        --bundle renaissance_v4/game_theory/examples/memory_behavior_ab_bundle_fusion_strict.json

    PYTHONPATH=. python3 scripts/memory_behavior_ab_proof_v1.py --mode dcr \\
        --memory-jsonl renaissance_v4/game_theory/state/context_signature_memory.jsonl

Env: requires the same SQLite ``market_bars_5m`` as ``run_manifest_replay`` (see ``renaissance_v4.utils.db``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _repo_path(p: str | Path) -> Path:
    x = Path(p).expanduser()
    return x if x.is_file() else _REPO_ROOT / x


def _outcome_rows(out: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for o in out.get("outcomes") or []:
        if hasattr(o, "trade_id"):
            rows.append(
                {
                    "trade_id": str(o.trade_id),
                    "entry_time": int(o.entry_time),
                    "exit_time": int(o.exit_time),
                    "direction": str(o.direction),
                    "pnl": float(o.pnl),
                    "contributing_signals": list(o.contributing_signals or []),
                }
            )
        elif isinstance(o, dict):
            rows.append(
                {
                    "trade_id": str(o.get("trade_id", "")),
                    "entry_time": int(o.get("entry_time", 0)),
                    "exit_time": int(o.get("exit_time", 0)),
                    "direction": str(o.get("direction", "")),
                    "pnl": float(o.get("pnl", 0.0)),
                    "contributing_signals": list(o.get("contributing_signals") or []),
                }
            )
    rows.sort(key=lambda r: (r["entry_time"], r["trade_id"]))
    return rows


def _fusion_counts(out: dict[str, Any]) -> dict[str, int]:
    pc = out.get("pattern_context_v1") or {}
    raw = pc.get("fusion_direction_counts") or {}
    return {str(k): int(v) for k, v in raw.items()}


def _directional_fusion_bar_total(out: dict[str, Any]) -> int:
    fc = _fusion_counts(out)
    return int(fc.get("long", 0)) + int(fc.get("short", 0))


def _recall_bias_totals(out: dict[str, Any]) -> tuple[int, int]:
    ra = out.get("replay_attempt_aggregates_v1") or {}
    dcr = out.get("decision_context_recall_stats") or {}
    fusion_bias = int(ra.get("recall_bias_applied_total") or 0)
    if fusion_bias == 0 and isinstance(dcr, dict):
        fusion_bias = int(dcr.get("decisions_with_bias_applied") or 0)
    sig = int(ra.get("recall_signal_bias_applied_total") or 0)
    if sig == 0 and isinstance(dcr, dict):
        sig = int(dcr.get("decisions_with_signal_bias_applied") or 0)
    return fusion_bias, sig


def _run_a(
    manifest_path: Path,
    *,
    months: int | None,
) -> dict[str, Any]:
    from renaissance_v4.research.replay_runner import run_manifest_replay

    return run_manifest_replay(
        manifest_path,
        emit_baseline_artifacts=False,
        verbose=False,
        bar_window_calendar_months=months,
        decision_context_recall_enabled=False,
    )


def _run_b_bundle(
    manifest_path: Path,
    bundle_path: Path,
    *,
    months: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from renaissance_v4.game_theory.memory_bundle import build_memory_bundle_proof
    from renaissance_v4.game_theory.pattern_game import prepare_effective_manifest_for_replay
    from renaissance_v4.research.replay_runner import run_manifest_replay

    prep = prepare_effective_manifest_for_replay(
        manifest_path,
        memory_bundle_path=str(bundle_path),
        use_groundhog_auto_resolve=False,
    )
    try:
        out = run_manifest_replay(
            prep.replay_path,
            emit_baseline_artifacts=False,
            verbose=False,
            bar_window_calendar_months=months,
            decision_context_recall_enabled=False,
        )
    finally:
        prep.cleanup()
    proof = build_memory_bundle_proof(
        resolved_bundle_path=prep.mb_path_for_proof,
        apply_audit=prep.memory_bundle_audit,
    )
    return out, proof


def _run_b_dcr(
    manifest_path: Path,
    memory_jsonl: Path,
    *,
    months: int | None,
    signal_bias_v2: bool,
) -> dict[str, Any]:
    from renaissance_v4.research.replay_runner import run_manifest_replay

    return run_manifest_replay(
        manifest_path,
        emit_baseline_artifacts=False,
        verbose=False,
        bar_window_calendar_months=months,
        decision_context_recall_enabled=True,
        decision_context_recall_apply_bias=True,
        decision_context_recall_apply_signal_bias_v2=signal_bias_v2,
        decision_context_recall_memory_path=memory_jsonl,
        decision_context_recall_drill_matched_max=0,
        decision_context_recall_drill_bias_max=24,
        decision_context_recall_drill_trade_entry_max=0,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Memory A/B mandate proof (JSON to stdout)")
    ap.add_argument(
        "--manifest",
        type=str,
        default=str(_REPO_ROOT / "renaissance_v4/configs/manifests/baseline_v1_recipe.json"),
    )
    ap.add_argument("--months", type=int, default=12, help="Calendar month window (same for A and B)")
    ap.add_argument(
        "--mode",
        choices=("bundle", "dcr", "auto"),
        default="auto",
        help="auto: try bundle first; if gate1 fails for B, retry dcr",
    )
    ap.add_argument(
        "--bundle",
        type=str,
        default=str(
            _REPO_ROOT / "renaissance_v4/game_theory/examples/memory_behavior_ab_bundle_fusion_strict.json"
        ),
    )
    ap.add_argument(
        "--memory-jsonl",
        type=str,
        default=str(_REPO_ROOT / "renaissance_v4/game_theory/state/context_signature_memory.jsonl"),
    )
    ap.add_argument("--dcr-signal-bias-v2", action="store_true", help="Also enable recall signal bias v2 for run B (dcr)")
    args = ap.parse_args()

    manifest_path = _repo_path(args.manifest)
    if not manifest_path.is_file():
        print(json.dumps({"error": f"manifest not found: {manifest_path}"}), file=sys.stderr)
        return 2

    months = int(args.months) if int(args.months) > 0 else None

    proof: dict[str, Any] = {
        "schema": "memory_behavior_ab_proof_v1",
        "manifest_path": str(manifest_path),
        "bar_window_calendar_months": months,
        "run_a": {"label": "memory_off", "memory_bundle": False, "decision_context_recall": False},
        "run_b": {},
        "acceptance": {},
    }

    out_a = _run_a(manifest_path, months=months)
    rows_a = _outcome_rows(out_a)
    fusion_a = _fusion_counts(out_a)
    proof["run_a"]["trade_count"] = len(rows_a)
    proof["run_a"]["trade_ids"] = [r["trade_id"] for r in rows_a]
    proof["run_a"]["fusion_direction_counts"] = fusion_a
    proof["run_a"]["validation_checksum"] = out_a.get("validation_checksum")
    proof["run_a"]["replay_data_audit"] = out_a.get("replay_data_audit")
    m_a = out_a.get("manifest") or {}
    proof["run_a"]["manifest_fusion_min_score"] = m_a.get("fusion_min_score")

    modes_to_try: list[str]
    if args.mode == "bundle":
        modes_to_try = ["bundle"]
    elif args.mode == "dcr":
        modes_to_try = ["dcr"]
    else:
        modes_to_try = ["bundle", "dcr"]

    out_b: dict[str, Any] | None = None
    mb_proof: dict[str, Any] | None = None
    b_label = ""
    last_err: str | None = None

    for mode in modes_to_try:
        try:
            if mode == "bundle":
                bp = _repo_path(args.bundle)
                if not bp.is_file():
                    last_err = f"bundle not found: {bp}"
                    continue
                out_b, mb_proof = _run_b_bundle(manifest_path, bp, months=months)
                b_label = "memory_on_bundle"
            else:
                jp = _repo_path(args.memory_jsonl)
                if not jp.is_file():
                    last_err = f"memory jsonl not found: {jp}"
                    continue
                out_b = _run_b_dcr(
                    manifest_path,
                    jp,
                    months=months,
                    signal_bias_v2=bool(args.dcr_signal_bias_v2),
                )
                mb_proof = out_b.get("memory_bundle_proof")
                b_label = "memory_on_dcr"
            break
        except Exception as e:  # noqa: BLE001 — surface any replay failure in proof
            last_err = f"{mode}:{type(e).__name__}:{e}"
            out_b = None
            mb_proof = None
            continue

    if out_b is None:
        proof["error"] = last_err or "run_b_failed"
        print(json.dumps(proof, indent=2))
        return 3

    rows_b = _outcome_rows(out_b)
    fusion_b = _fusion_counts(out_b)
    ids_a = {r["trade_id"] for r in rows_a}
    ids_b = {r["trade_id"] for r in rows_b}
    only_a = sorted(ids_a - ids_b)
    only_b = sorted(ids_b - ids_a)
    fusion_delta = {k: fusion_b.get(k, 0) - fusion_a.get(k, 0) for k in sorted(set(fusion_a) | set(fusion_b))}
    dir_tot_a = _directional_fusion_bar_total(out_a)
    dir_tot_b = _directional_fusion_bar_total(out_b)
    ent_a = int((out_a.get("replay_attempt_aggregates_v1") or {}).get("trade_entries_total") or 0)
    ent_b = int((out_b.get("replay_attempt_aggregates_v1") or {}).get("trade_entries_total") or 0)
    vchk_a = str(out_a.get("validation_checksum") or "")
    vchk_b = str(out_b.get("validation_checksum") or "")

    fusion_bias_b, sig_bias_b = _recall_bias_totals(out_b)
    mb_applied = bool((mb_proof or {}).get("memory_bundle_applied"))
    keys_applied = list((mb_proof or {}).get("memory_keys_applied") or [])

    gate1 = mb_applied or fusion_bias_b > 0 or sig_bias_b > 0
    fusion_counts_changed = any(fusion_delta.get(k, 0) != 0 for k in fusion_delta)
    gate2 = (
        bool(only_a or only_b)
        or fusion_counts_changed
        or (dir_tot_a != dir_tot_b)
        or (ent_a != ent_b)
        or (gate1 and mb_applied and vchk_a != vchk_b)
    )

    proof["run_b"] = {
        "label": b_label,
        "trade_count": len(rows_b),
        "trade_ids": [r["trade_id"] for r in rows_b],
        "fusion_direction_counts": fusion_b,
        "validation_checksum": out_b.get("validation_checksum"),
        "memory_bundle_proof": mb_proof,
        "recall_bias_applied_total": fusion_bias_b,
        "recall_signal_bias_applied_total": sig_bias_b,
        "replay_data_audit": out_b.get("replay_data_audit"),
        "manifest_fusion_min_score": (out_b.get("manifest") or {}).get("fusion_min_score"),
        "sample_trades_only_in_b": [r for r in rows_b if r["trade_id"] in set(only_b)][:5],
        "sample_trades_only_in_a": [r for r in rows_a if r["trade_id"] in set(only_a)][:5],
    }

    proof["acceptance"] = {
        "gate_1_behavioral_memory": gate1,
        "gate_1_detail": {
            "memory_bundle_applied": mb_applied,
            "memory_keys_applied": keys_applied,
            "recall_bias_applied_total": fusion_bias_b,
            "recall_signal_bias_applied_total": sig_bias_b,
        },
        "gate_2_trade_or_fusion_diff": gate2,
        "gate_2_detail": {
            "directional_fusion_bars_run_a": dir_tot_a,
            "directional_fusion_bars_run_b": dir_tot_b,
            "trade_entries_total_run_a": ent_a,
            "trade_entries_total_run_b": ent_b,
            "validation_checksum_run_a": vchk_a,
            "validation_checksum_run_b": vchk_b,
            "fusion_direction_counts_changed": fusion_counts_changed,
        },
        "trade_ids_only_in_run_a": only_a,
        "trade_ids_only_in_run_b": only_b,
        "fusion_direction_counts_delta_b_minus_a": fusion_delta,
    }
    proof["mandate_passed"] = bool(gate1 and gate2)

    print(json.dumps(proof, indent=2))
    return 0 if proof["mandate_passed"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
