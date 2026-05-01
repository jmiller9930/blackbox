"""
FinQuant Unified Agent Lab — Case Loader.

Loads and validates lifecycle case JSON files.
Rejects malformed cases with clear errors.
No app imports.
"""

from __future__ import annotations
import json
from typing import Any

from schemas import validate_case


def load_case(path: str) -> dict[str, Any]:
    """Load a single case from a JSON file and validate it."""
    with open(path, "r") as f:
        case = json.load(f)
    if not isinstance(case, dict):
        raise ValueError(f"case file must be a JSON object: {path}")
    validate_case(case)
    return case


def load_cases(path: str) -> list[dict[str, Any]]:
    """Load one or more cases from a JSON file.

    Accepts:
      - A single case object.
      - A list of case objects.
      - A wrapper: { "cases": [...] }.
    """
    with open(path, "r") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "cases" in raw:
        cases = raw["cases"]
    elif isinstance(raw, dict):
        cases = [raw]
    elif isinstance(raw, list):
        cases = raw
    else:
        raise ValueError(f"unrecognized case pack format in {path}")

    if not cases:
        raise ValueError(f"case file contains no cases: {path}")

    for case in cases:
        validate_case(case)

    return cases
