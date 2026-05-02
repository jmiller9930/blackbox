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

_ENTRY_PRIO = {"ENTER_LONG": 0, "ENTER_SHORT": 1, "NO_TRADE": 2}


def retrieve_eligible(
    shared_store_path: str | Path | None,
    case: dict[str, Any],
    config: dict[str, Any],
    max_records: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return (eligible_records, retrieval_trace_entries).

    Only records where retrieval_enabled_v1=True and symbol matches are returned.
    Selection prefers directional lessons (ENTER_LONG / ENTER_SHORT) over NO_TRADE,
    then more recent lines — so a replay tail of NO_TRADE rows cannot hide prior
    promoted trend lessons.

    All filtered-out records are captured in the trace for auditability.
    """
    if not shared_store_path or not config.get("retrieval_enabled_default_v1", False):
        return [], [_trace_entry(reason="retrieval_disabled_by_config")]

    cap = int(max_records if max_records is not None else config.get("retrieval_max_records_v1") or 5)
    if cap < 1:
        cap = 1

    store_path = Path(shared_store_path)
    if not store_path.exists():
        return [], [_trace_entry(reason="shared_store_not_found", path=str(store_path))]

    trace: list[dict] = []
    symbol = case.get("symbol", "")

    lines: list[str] = []
    with open(store_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)

    candidates: list[tuple[int, dict[str, Any]]] = []
    for i, line in enumerate(lines):
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

        candidates.append((i, rec))

    candidates.sort(
        key=lambda t: (
            _ENTRY_PRIO.get(str(t[1].get("entry_action_v1") or ""), 9),
            -t[0],
        )
    )
    picked = candidates[:cap]
    picked.sort(key=lambda t: t[0])

    eligible = [t[1] for t in picked]
    for _, rec in picked:
        trace.append(_trace_entry(
            reason="retrieved",
            record_id=rec.get("record_id"),
        ))

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
