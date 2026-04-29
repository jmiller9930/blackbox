#!/usr/bin/env python3
"""
GT_DIRECTIVE_036 — Contract probe: Student Ollama path produces schema-valid ``student_output_v1``.

Uses ``PATTERN_GAME_STUDENT_TEST_ISOLATION_V1=1`` so the JSON-only banner + deterministic options apply.

Usage (from repo root, with Ollama reachable):

  PYTHONPATH=. PATTERN_GAME_STUDENT_TEST_ISOLATION_V1=1 \\
    python3 scripts/student_llm_json_contract_probe_v1.py

Optional: ``STUDENT_LLM_PROBE_MODEL=qwen2.5:7b``
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", "1")

from renaissance_v4.game_theory.ollama_role_routing_v1 import student_ollama_base_url_v1
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    emit_student_output_via_ollama_v1,
    verify_ollama_model_tag_available_v1,
)


def main() -> int:
    model = (os.environ.get("STUDENT_LLM_PROBE_MODEL") or "qwen2.5:7b").strip()
    base = student_ollama_base_url_v1().strip()
    err = verify_ollama_model_tag_available_v1(base, model, timeout_s=12.0)
    if err:
        print(json.dumps({"ok": False, "phase": "tags", "error": err}, indent=2))
        return 2

    packet = {
        "symbol": "SOLUSDT",
        "bars_inclusive_up_to_t": [
            {"open_time": 1700000000000, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100.0},
        ],
    }
    cap: dict[str, object] = {}
    so, errs = emit_student_output_via_ollama_v1(
        packet,
        graded_unit_id="gt036_json_contract_probe_v1",
        decision_at_ms=1700000000000,
        llm_model=model,
        ollama_base_url=base,
        prompt_version="gt036_json_contract_probe_v1",
        require_directional_thesis_v1=True,
        llm_io_capture_v1=cap,
    )
    out = {
        "ok": bool(so is not None and not errs),
        "student_action_v1": (so or {}).get("student_action_v1"),
        "errors": errs,
        "json_contract_retry_used_v1": cap.get("json_contract_retry_used_v1"),
        "model": model,
        "ollama_base_url": base,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
