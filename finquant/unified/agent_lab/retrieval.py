"""
FinQuant Unified Agent Lab — Retrieval.

Reads shared learning records JSONL and filters retrieval eligibility.

MANDATORY RULE: records with retrieval_enabled_v1=false must NEVER be returned.
This is critical — storing rejected/early records must not contaminate future agent reasoning.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any


def retrieve_eligible(
    shared_store_path: str | Path | None,
    case: dict[str, Any],
    config: dict[str, Any],
    max_records: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return (eligible_records, retrieval_trace_entries).

    Only records where retrieval_enabled_v1=True and symbol matches are returned.
    All filtered-out records are captured in the trace for auditability.
    """
    if not shared_store_path or not config.get("retrieval_enabled_default_v1", False):
        return [], [_trace_entry(reason="retrieval_disabled_by_config")]

    store_path = Path(shared_store_path)
    if not store_path.exists():
        return [], [_trace_entry(reason="shared_store_not_found", path=str(store_path))]

    eligible: list[dict] = []
    trace: list[dict] = []
    symbol = case.get("symbol", "")

    with open(store_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                trace.append(_trace_entry(reason="parse_error"))
                continue

            if not rec.get("retrieval_enabled_v1", False):
                trace.append(_trace_entry(
                    reason="retrieval_disabled",
                    record_id=rec.get("record_id"),
                ))
                continue

            if rec.get("symbol") != symbol:
                trace.append(_trace_entry(
                    reason="symbol_mismatch",
                    record_id=rec.get("record_id"),
                    detail=f"wanted={symbol} got={rec.get('symbol')}",
                ))
                continue

            eligible.append(rec)
            trace.append(_trace_entry(
                reason="retrieved",
                record_id=rec.get("record_id"),
            ))

            if len(eligible) >= max_records:
                break

    return eligible, trace


def _trace_entry(
    reason: str,
    record_id: str | None = None,
    path: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"reason": reason}
    if record_id:
        entry["record_id"] = record_id
    if path:
        entry["path"] = path
    if detail:
        entry["detail"] = detail
    return entry
