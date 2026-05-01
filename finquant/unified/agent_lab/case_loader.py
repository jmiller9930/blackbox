"""
FinQuant Unified Agent Lab — Case Loader

Loads and minimally validates lifecycle case packs.
No app imports.
"""

import json
from pathlib import Path
from typing import Any


def load_cases(path: str) -> list[dict[str, Any]]:
    """Load cases from a JSON file.

    Accepts either:
      - a top-level list of case objects
      - a wrapper object: { "cases": [...] }
    """
    with open(path, "r") as f:
        raw = json.load(f)

    if isinstance(raw, list):
        cases = raw
    elif isinstance(raw, dict) and "cases" in raw:
        cases = raw["cases"]
    else:
        raise ValueError(f"case pack must be a list or {{\"cases\": [...]}} object: {path}")

    if not cases:
        raise ValueError(f"case pack contains no cases: {path}")

    for i, case in enumerate(cases):
        _validate_case_minimal(case, index=i)

    return cases


def _validate_case_minimal(case: dict[str, Any], index: int) -> None:
    required_fields = ["case_id", "schema", "symbol", "steps"]
    missing = [f for f in required_fields if f not in case]
    if missing:
        raise ValueError(
            f"case at index {index} missing required fields: {missing}"
        )
    if not isinstance(case["steps"], list):
        raise ValueError(
            f"case '{case['case_id']}' steps must be a list"
        )
