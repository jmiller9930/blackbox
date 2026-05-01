"""
FinQuant Unified Agent Lab — Retrieval

Retrieves eligible prior learning records for a given case.

Governance rule:
  Only records with retrieval_enabled_v1 == True may be returned.
  Rejected records (promotion_eligible_v1 == False, retrieval_enabled_v1 == False)
  must never surface to the agent without explicit governance override.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from memory_store import MemoryStore


def retrieve_eligible(
    store: "MemoryStore",
    case: dict[str, Any],
    max_records: int = 5,
) -> list[dict[str, Any]]:
    """Return prior learning records eligible for retrieval for this case.

    In scaffold phase: always returns empty list (no prior runs exist yet).
    """
    run_dir = store.get_run_dir().parent
    eligible: list[dict] = []

    # Scan all prior run directories for matching eligible records
    for run_folder in sorted(run_dir.iterdir()):
        lr_file = run_folder / "learning_records.jsonl"
        if not lr_file.exists():
            continue
        with open(lr_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not record.get("retrieval_enabled_v1", False):
                    continue
                if record.get("symbol") != case.get("symbol"):
                    continue
                eligible.append(record)
                if len(eligible) >= max_records:
                    return eligible

    return eligible
