#!/usr/bin/env python3
"""
Phase 4.0 — Load execution context from docs/runtime/execution_context.md and emit JSON.

Intended to run before runtime verification work so phase, host, and proof rules are explicit.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import repo_root


def execution_context_path() -> Path:
    return repo_root() / "docs" / "runtime" / "execution_context.md"


def parse_context_md(text: str) -> dict[str, Any]:
    m = re.search(r"```json\s*([\s\S]*?)```", text)
    if not m:
        return {"error": "no_json_block", "path": str(execution_context_path())}
    raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": "invalid_json_in_context", "detail": str(e)}


def build_output(blob: dict[str, Any]) -> dict[str, Any]:
    if "error" in blob:
        return blob
    env = blob.get("execution_environment") or {}
    return {
        "current_phase": blob.get("current_phase"),
        "last_completed_phase": blob.get("last_completed_phase"),
        "execution_host": env.get("primary_host"),
        "repo_path": env.get("repo_path"),
        "required_execution": env.get("required_execution"),
        "proof_required": blob.get("proof_required", True),
        "proof_standard_reference": blob.get("proof_standard_reference"),
        "rules": list(blob.get("rules") or []),
    }


def main() -> int:
    p = execution_context_path()
    if not p.is_file():
        print(json.dumps({"error": "file_missing", "path": str(p)}, indent=2))
        return 1
    text = p.read_text(encoding="utf-8")
    blob = parse_context_md(text)
    out = build_output(blob)
    print(json.dumps(out, indent=2))
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
