"""
Operational driver: pattern/hypothesis context → paired outcomes → commit_outcome → SPRT → persistence.

Forward-only: ``market_event_ids`` must be ordered; duplicate ids are idempotent (manifest policy).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.anna_training.store import utc_now_iso

from .calibration_factory import validate_calibration_for_run
from .calibration_report import CalibrationReport
from .decision_state import commit_outcome, export_decision_snapshot
from .hypothesis import hypothesis_hash
from .ledger_pairs import fetch_paired_trades_for_event
from .mae_v1 import MAE_PROTOCOL_ID
from .pair_evaluation import build_outcome_record
from .pattern_spec import pattern_spec_hash
from .scaling_policy import execution_tier, max_scale_bound
from .sequential_persistence import ensure_strategy_registered, persist_sequential_decision_run


def _shadow_comparison(sprt_decision: str) -> str:
    if sprt_decision == "PROMOTE":
        return "above"
    if sprt_decision == "KILL":
        return "below"
    return "match"


def _write_hypothesis_bundle(
    test_dir: Path,
    *,
    test_id: str,
    hypothesis: dict[str, Any] | None,
    pattern_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    """Persist hypothesis/pattern hashes once (audit)."""
    test_dir.mkdir(parents=True, exist_ok=True)
    hsh: str | None = None
    psh: str | None = None
    if hypothesis:
        hsh = hypothesis_hash(hypothesis)
    if pattern_spec:
        psh = pattern_spec_hash(pattern_spec)
    bundle = {
        "schema": "hypothesis_bundle_v1",
        "test_id": test_id,
        "written_at_utc": utc_now_iso(),
        "hypothesis_hash": hsh,
        "pattern_spec_hash": psh,
        "hypothesis": hypothesis,
        "pattern_spec": pattern_spec,
    }
    (test_dir / "hypothesis_bundle.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"hypothesis_hash": hsh, "pattern_spec_hash": psh}


def run_sequential_learning_driver(
    *,
    test_id: str,
    strategy_id: str,
    calibration: CalibrationReport,
    market_event_ids: list[str],
    ledger_db_path: Path | None = None,
    market_db_path: Path | None = None,
    artifacts_dir: Path | None = None,
    hypothesis: dict[str, Any] | None = None,
    pattern_spec: dict[str, Any] | None = None,
    scaling_protocol: dict[str, Any] | None = None,
    write_hypothesis_bundle: bool = True,
) -> dict[str, Any]:
    """
    Process each ``market_event_id`` in order (forward-only).

    Persists SPRT decisions to ``anna_sequential_decision_runs`` when a batch evaluation fires.
    Shadow execution tier is always computed (inspectable JSON) — does not execute trades.
    """
    validate_calibration_for_run(calibration)

    ensure_strategy_registered(strategy_id, db_path=ledger_db_path)

    base_artifacts = artifacts_dir or (Path(__file__).resolve().parents[3] / "data" / "sequential_engine")
    test_dir = base_artifacts / test_id
    if write_hypothesis_bundle and (hypothesis or pattern_spec):
        hashes = _write_hypothesis_bundle(test_dir, test_id=test_id, hypothesis=hypothesis, pattern_spec=pattern_spec)
    else:
        hashes = {"hypothesis_hash": hypothesis_hash(hypothesis) if hypothesis else None, "pattern_spec_hash": pattern_spec_hash(pattern_spec) if pattern_spec else None}

    scaling_protocol = dict(scaling_protocol or {})
    eps = float(calibration.epsilon)

    event_results: list[dict[str, Any]] = []
    last_sprt: dict[str, Any] | None = None

    for mid in market_event_ids:
        mid = (mid or "").strip()
        if not mid:
            continue
        base, cand = fetch_paired_trades_for_event(mid, candidate_strategy_id=strategy_id, db_path=ledger_db_path)
        rec = build_outcome_record(
            test_id=test_id,
            market_event_id=mid,
            baseline_row=base,
            candidate_row=cand,
            epsilon=eps,
            mae_protocol_id=MAE_PROTOCOL_ID,
            baseline_trade_id=(base or {}).get("trade_id"),
            candidate_trade_id=(cand or {}).get("trade_id"),
            market_db_path=market_db_path,
            ledger_db_path=ledger_db_path,
        )
        if hashes.get("hypothesis_hash"):
            rec["hypothesis_hash"] = hashes["hypothesis_hash"]
        if hashes.get("pattern_spec_hash"):
            rec["pattern_spec_hash"] = hashes["pattern_spec_hash"]

        out = commit_outcome(
            test_id=test_id,
            record=rec,
            calibration=calibration,
            artifacts_dir=artifacts_dir,
        )
        sprt_advance = out.get("sprt_advance")
        row: dict[str, Any] = {
            "market_event_id": mid,
            "append": out.get("append"),
            "sprt_advance": sprt_advance,
        }

        if sprt_advance and sprt_advance.get("evaluated"):
            d = str(sprt_advance.get("decision") or "CONTINUE")
            wilson = sprt_advance.get("wilson")
            eligible_n = int(sprt_advance.get("sprt_eligible_n", 0))
            win_n = int(wilson.get("wins", 0)) if isinstance(wilson, dict) else 0

            snap = export_decision_snapshot(test_id, artifacts_dir=artifacts_dir)
            sprt_block = dict((snap.get("sprt") or {})) if isinstance(snap, dict) else {}

            tier = execution_tier(
                sprt_decision=d,
                baseline_comparison=_shadow_comparison(d),
                protocol=scaling_protocol,
            )
            shadow = {
                "tier": tier,
                "max_scale_bound": max_scale_bound(scaling_protocol),
                "mode": "shadow",
                "sprt_decision": d,
                "baseline_comparison": _shadow_comparison(d),
            }

            persist_sequential_decision_run(
                test_id=test_id,
                strategy_id=strategy_id,
                sprt_decision=d,
                eligible_n=eligible_n,
                win_n=win_n,
                wilson=wilson if isinstance(wilson, dict) else None,
                sprt_snapshot=sprt_block,
                shadow_tier=shadow,
                hypothesis_hash=hashes.get("hypothesis_hash"),
                pattern_spec_hash=hashes.get("pattern_spec_hash"),
                manifest_content_hash=rec.get("content_hash"),
                db_path=ledger_db_path,
            )
            last_sprt = {"decision": d, "shadow": shadow, "wilson": wilson}

        event_results.append(row)

    return {
        "ok": True,
        "test_id": test_id,
        "strategy_id": strategy_id,
        "events_processed": len(event_results),
        "hypothesis_bundle": hashes,
        "results": event_results,
        "last_sprt": last_sprt,
        "snapshot": export_decision_snapshot(test_id, artifacts_dir=artifacts_dir),
    }
