"""
Phase 1 walk-forward report — historical splits only (no training).

Splits rows by ``created_at_utc`` from the ledger query order (chronological).
Default: 3 folds by time (train on earlier, "test" is last segment — report only counts/balance).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.anna_training.learning_layer.dataset_builder import build_phase1_dataset


@dataclass
class WalkForwardReport:
    schema_version: str
    total_rows: int
    label_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    split_boundaries: list[dict[str, Any]] = field(default_factory=list)
    quality_counts: dict[str, int] = field(default_factory=dict)
    inventory: dict[str, Any] = field(default_factory=dict)
    phase2_blockers: list[str] = field(default_factory=list)


def _count_labels(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    keys = ("trade_success", "stopped_early", "beats_baseline", "whipsaw_flag")
    out: dict[str, dict[str, int]] = {k: {"true": 0, "false": 0} for k in keys}
    for r in rows:
        for k in keys:
            v = bool(r.get(k))
            out[k]["true" if v else "false"] += 1
    return out


def _quality_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    qc: dict[str, int] = {}
    for r in rows:
        q = str(r.get("row_quality") or "unknown")
        qc[q] = qc.get(q, 0) + 1
    return qc


def _time_splits(n_rows: int, *, n_folds: int = 3) -> list[dict[str, Any]]:
    """Index ranges only (Phase 1 has no timestamp column in row dict unless we add it)."""
    if n_rows <= 0 or n_folds < 2:
        return []
    base = n_rows // n_folds
    rem = n_rows % n_folds
    splits: list[dict[str, Any]] = []
    start = 0
    for i in range(n_folds):
        sz = base + (1 if i < rem else 0)
        end = start + sz
        splits.append(
            {
                "fold_index": i,
                "row_index_start": start,
                "row_index_end_exclusive": end,
                "row_count": sz,
            }
        )
        start = end
    return splits


def generate_walk_forward_report(
    *,
    ledger_db_path: Any = None,
    market_db_path: Any = None,
    signal_mode: str = "sean_jupiter_v1",
    n_folds: int = 3,
) -> WalkForwardReport:
    rows, inv = build_phase1_dataset(
        ledger_db_path=ledger_db_path,
        market_db_path=market_db_path,
        signal_mode=signal_mode,
    )
    from modules.anna_training.learning_layer.schema import LEARNING_DATASET_SCHEMA_VERSION

    blockers: list[str] = []
    if inv.get("error"):
        blockers.append(f"dataset_build_error:{inv['error']}")
    if not rows:
        blockers.append("zero_rows:lifecycle_trades_or_missing_dbs")

    qc = _quality_counts(rows)
    ok_n = qc.get("ok", 0)
    if ok_n == 0 and rows:
        blockers.append("no_rows_with_row_quality_ok")

    wf = WalkForwardReport(
        schema_version=LEARNING_DATASET_SCHEMA_VERSION,
        total_rows=len(rows),
        label_counts=_count_labels(rows),
        split_boundaries=_time_splits(len(rows), n_folds=n_folds),
        quality_counts=qc,
        inventory=inv,
        phase2_blockers=blockers,
    )
    return wf


def report_to_dict(r: WalkForwardReport) -> dict[str, Any]:
    return {
        "schema_version": r.schema_version,
        "total_rows": r.total_rows,
        "label_counts": r.label_counts,
        "split_boundaries": r.split_boundaries,
        "quality_counts": r.quality_counts,
        "inventory": r.inventory,
        "phase2_blockers": r.phase2_blockers,
    }
