#!/usr/bin/env python3
"""
Directive: Cross-run knowledge flow — production vs consumption vs decision influence.

Emits JSON evidence for:
  Run 1 / Run 2: same parallel scenario, isolated PATTERN_GAME_MEMORY_ROOT — logs append;
                  outcomes should match when Groundhog is off (proves logs not fed into replay).
  Run 3: isolated Groundhog state dir — bundle written, then run with auto-resolve ON;
         memory_bundle_proof shows load + merge (narrow closed-loop).

Usage (repo root):

  PYTHONPATH=. python3 scripts/prove_cross_run_knowledge_flow.py

stderr: replay noise may appear unless redirected.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from renaissance_v4.game_theory.groundhog_memory import (  # noqa: E402
    write_groundhog_bundle,
)
from renaissance_v4.game_theory.memory_bundle import sha256_file  # noqa: E402
from renaissance_v4.game_theory.memory_paths import (  # noqa: E402
    default_experience_log_jsonl,
    default_run_memory_jsonl,
)
from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel  # noqa: E402
from renaissance_v4.game_theory.pattern_game import run_pattern_game  # noqa: E402
from renaissance_v4.game_theory.pml_proof_stdio import (  # noqa: E402
    add_proof_stdio_flags,
    begin_pml_proof_stdio,
    proof_json_out,
    raw_stdout_selected,
)


def _file_evidence(path: Path, *, jsonl_first_line: bool = False) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "path": str(path)}
    txt = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in txt.splitlines() if ln.strip()]
    sample_keys: list[str] = []
    if lines:
        try:
            if jsonl_first_line:
                o = json.loads(lines[0])
            else:
                o = json.loads(txt)
            if isinstance(o, dict):
                sample_keys = list(o.keys())
        except json.JSONDecodeError:
            pass
    return {
        "exists": True,
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "line_count": len(lines),
        "sample_top_level_keys": sample_keys,
    }


def _quiet_run_parallel(scenarios: list[dict], *, mem_root: Path) -> list[dict]:
    os.environ["PATTERN_GAME_MEMORY_ROOT"] = str(mem_root)
    os.environ["PATTERN_GAME_GROUNDHOG_BUNDLE"] = "0"
    exp = default_experience_log_jsonl()
    rmem = default_run_memory_jsonl()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return run_scenarios_parallel(
            scenarios,
            max_workers=1,
            experience_log_path=exp,
            run_memory_log_path=rmem,
            write_session_logs=False,
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_proof_stdio_flags(ap)
    args = ap.parse_args()
    begin_pml_proof_stdio("prove_cross_run_knowledge_flow", raw_stdout=raw_stdout_selected(args))

    manifest = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not manifest.is_file():
        proof_json_out({"error": f"manifest not found: {manifest}"})
        return 1

    scenario = {
        "scenario_id": "cross_run_proof",
        "manifest_path": str(manifest.resolve()),
        "skip_groundhog_bundle": True,
    }

    mem_root = Path(tempfile.mkdtemp(prefix="cross_run_mem_"))
    exp_path = mem_root / "experience_log.jsonl"
    rmem_path = mem_root / "run_memory.jsonl"

    # --- Run 1 ---
    os.environ["PATTERN_GAME_MEMORY_ROOT"] = str(mem_root)
    os.environ["PATTERN_GAME_GROUNDHOG_BUNDLE"] = "0"
    results1 = _quiet_run_parallel([dict(scenario)], mem_root=mem_root)
    ev1_exp = _file_evidence(exp_path, jsonl_first_line=True)
    ev1_rm = _file_evidence(rmem_path, jsonl_first_line=True)
    r1 = results1[0] if results1 else {}

    # --- Run 2 (same inputs; logs should append, replay should not read them) ---
    results2 = _quiet_run_parallel([dict(scenario)], mem_root=mem_root)
    ev2_exp = _file_evidence(exp_path, jsonl_first_line=True)
    ev2_rm = _file_evidence(rmem_path, jsonl_first_line=True)
    r2 = results2[0] if results2 else {}

    checksum_match = (r1.get("validation_checksum") == r2.get("validation_checksum")) and r1.get(
        "validation_checksum"
    )

    # --- Run 3: Groundhog bundle isolated (only cross-run auto path) ---
    import renaissance_v4.game_theory.groundhog_memory as gh  # noqa: E402

    gh_root = Path(tempfile.mkdtemp(prefix="cross_run_gh_"))
    saved_gt = gh._GAME_THEORY
    gh._GAME_THEORY = gh_root
    try:
        os.environ["PATTERN_GAME_GROUNDHOG_BUNDLE"] = "1"
        write_groundhog_bundle(atr_stop_mult=2.5, atr_target_mult=4.0, from_run_id="prove_cross_run")
        gh_path = gh.groundhog_bundle_path()
        gh_ev = _file_evidence(gh_path, jsonl_first_line=False)
        buf3 = io.StringIO()
        with contextlib.redirect_stdout(buf3):
            out3 = run_pattern_game(
                manifest,
                memory_bundle_path=None,
                use_groundhog_auto_resolve=True,
                emit_baseline_artifacts=False,
                verbose=False,
            )
        proof3 = out3.get("memory_bundle_proof") or {}
    finally:
        gh._GAME_THEORY = saved_gt

    static = {
        "experience_log_consumed_by_replay": {
            "finding": False,
            "evidence": "renaissance_v4/research/replay_runner.py has no import or read of experience_log.jsonl; "
            "parallel_runner.py only appends after workers complete (lines ~197–202).",
        },
        "run_memory_consumed_by_replay": {
            "finding": False,
            "evidence": "read_run_memory_tail() in run_memory.py is not imported by replay_runner.py or "
            "pattern_game.py; parallel_runner appends run_memory in parent only.",
        },
        "session_artifacts_consumed_by_replay": {
            "finding": False,
            "evidence": "run_session_log.py writes BATCH_README / scenario folders; no loader in replay path.",
        },
    }

    report = {
        "directive": "cross_run_knowledge_flow",
        "memory_root_run1_run2": str(mem_root),
        "run_1": {
            "scenario": scenario,
            "experience_log": ev1_exp,
            "run_memory_jsonl": ev1_rm,
            "validation_checksum": r1.get("validation_checksum"),
            "cumulative_pnl": r1.get("cumulative_pnl"),
        },
        "run_2_same_inputs": {
            "experience_log": ev2_exp,
            "run_memory_jsonl": ev2_rm,
            "validation_checksum": r2.get("validation_checksum"),
            "cumulative_pnl": r2.get("cumulative_pnl"),
            "logs_appended": {
                "experience_line_delta": ev2_exp.get("line_count", 0) - ev1_exp.get("line_count", 0),
                "run_memory_line_delta": ev2_rm.get("line_count", 0) - ev1_rm.get("line_count", 0),
            },
            "outcome_identical_to_run_1": bool(checksum_match),
        },
        "run_3_groundhog_isolated_state_dir": {
            "patched_groundhog_game_theory_root": str(gh_root),
            "groundhog_bundle_file": gh_ev,
            "memory_bundle_proof": proof3,
        },
        "static_code_findings": static,
        "classification": (
            "partially_stateful: only memory bundle (explicit path or Groundhog file when env enabled) "
            "merges whitelisted manifest keys before run_manifest_replay. "
            "experience_log.jsonl and run_memory.jsonl are append-only audit/analysis sinks in this codebase — "
            "not feedback inputs to the replay decision pipeline."
        ),
    }

    proof_json_out(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
