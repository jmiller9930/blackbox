#!/usr/bin/env python3
"""
Runtime proof acceptance — engineering-owned checks before/after a controlled batch job.

Does **not** replace a full multi-hour run; it verifies persistence paths, imports for fatal
authority/seal wiring, and (after run) terminal JSON + trace integrity for a job_id.

Usage (repo root):
  python3 scripts/runtime_proof_acceptance_v1.py readiness
  python3 scripts/runtime_proof_acceptance_v1.py verify-job <job_id>

Exit codes: 0 = all checks passed; 1 = failure; 2 = misuse.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _prepend_repo() -> None:
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def cmd_readiness() -> int:
    """Pre-run: persistence writable, modules present, key env surfaced."""
    _prepend_repo()
    lines: list[tuple[str, str]] = []

    try:
        from renaissance_v4.game_theory.pml_runtime_layout import (
            ensure_pml_runtime_dirs,
            pml_runtime_batches_dir,
            pml_runtime_root,
        )

        ensure_pml_runtime_dirs()
        root = pml_runtime_root()
        batches = pml_runtime_batches_dir()
        batches.mkdir(parents=True, exist_ok=True)
        probe = batches / ".write_probe_runtime_proof_v1"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        lines.append(("persistence_root_v1", str(root.resolve())))
        lines.append(("batches_dir_writable_v1", str(batches.resolve())))
    except Exception as e:
        print(f"FAIL: persistence — {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        from renaissance_v4.game_theory.parallel_job_terminal_persistence_v1 import (
            terminal_student_runtime_result_path_v1,
        )

        p = terminal_student_runtime_result_path_v1("0" * 32)
        lines.append(("terminal_json_pattern_v1", str(p)))
    except Exception as e:
        print(f"FAIL: terminal path helper — {e}", file=sys.stderr)
        return 1

    try:
        from renaissance_v4.game_theory.learning_trace_events_v1 import (
            count_learning_trace_terminal_integrity_v1,
            default_learning_trace_events_jsonl,
        )

        lt = default_learning_trace_events_jsonl()
        lines.append(("learning_trace_events_jsonl_v1", str(lt.resolve())))
        _ = count_learning_trace_terminal_integrity_v1("__nonexistent_probe_job__")
        lines.append(("trace_integrity_scan_import_v1", "ok"))
    except Exception as e:
        print(f"FAIL: learning trace integrity — {e}", file=sys.stderr)
        return 1

    try:
        from renaissance_v4.game_theory.student_behavior_probe_v1 import (
            finalize_seam_audit_authority_seal_contract_v1,
            student_behavior_probe_enabled_v1,
        )

        lines.append(("finalize_seam_audit_authority_seal_contract_v1", "import_ok"))
        lines.append(
            ("student_behavior_probe_enabled_v1", str(student_behavior_probe_enabled_v1()).lower())
        )
    except Exception as e:
        print(f"FAIL: student_behavior_probe imports — {e}", file=sys.stderr)
        return 1

    try:
        from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
            emit_fatal_authority_seal_mismatch_v1,
        )

        _ = emit_fatal_authority_seal_mismatch_v1  # noqa: SLF001 — presence check
        lines.append(("emit_fatal_authority_seal_mismatch_v1", "import_ok"))
    except Exception as e:
        print(f"FAIL: fatal authority/seal emit — {e}", file=sys.stderr)
        return 1

    stuck = os.environ.get("PATTERN_GAME_BATCH_STUCK_AFTER_SEC", "")
    lines.append(("PATTERN_GAME_BATCH_STUCK_AFTER_SEC", stuck or "(default 3600 in web_app)"))

    print(json.dumps({"schema": "runtime_proof_readiness_v1", "ok_v1": True, "checks": dict(lines)}, indent=2))
    print(
        "Note: confirm Student behavior probe PASS in UI/logs when probe is enabled for the exam.",
        file=sys.stderr,
    )
    return 0


_SR_TERMINAL_OK = frozenset(
    {
        "completed_all_trades_v1",
        "rm_preflight_early_exit_first_seal_v1",
    }
)


def cmd_verify_job(job_id: str, *, require_success_terminal: bool) -> int:
    """Post-run: terminal JSON on disk + authority/seal integrity + fatal flags."""
    _prepend_repo()
    jid = str(job_id or "").strip()
    if not jid:
        print("FAIL: job_id required", file=sys.stderr)
        return 2

    from renaissance_v4.game_theory.learning_trace_events_v1 import (
        count_learning_trace_terminal_integrity_v1,
    )
    from renaissance_v4.game_theory.parallel_job_terminal_persistence_v1 import (
        load_parallel_job_terminal_record_v1,
        terminal_student_runtime_result_path_v1,
    )

    path = terminal_student_runtime_result_path_v1(jid)
    rec = load_parallel_job_terminal_record_v1(jid)
    intr = count_learning_trace_terminal_integrity_v1(jid)

    out: dict[str, object] = {
        "schema": "runtime_proof_verify_job_v1",
        "job_id": jid,
        "terminal_record_path_expected_v1": str(path.resolve()),
        "terminal_record_loaded_v1": rec is not None,
        "learning_trace_terminal_integrity_v1": intr,
    }

    failures: list[str] = []

    if rec is None:
        failures.append("missing_terminal_record_json_v1")
    else:
        ts = str(rec.get("terminal_status") or "").strip().lower()
        out["terminal_status_v1"] = ts
        if ts not in ("done", "error"):
            failures.append(f"unexpected_terminal_status:{ts or 'empty'}")
        full = rec.get("full_parallel_result_v1")
        if isinstance(full, dict):
            out["status_v1_echo"] = full.get("status_v1")
            if full.get("fatal_authority_seal_mismatch_v1") or (
                str(full.get("status_v1") or "") == "fatal_authority_seal_mismatch_v1"
            ):
                failures.append("fatal_authority_seal_mismatch_v1_in_result")
            seam = full.get("student_loop_directive_09_v1")
            if isinstance(seam, dict) and seam.get("fatal_authority_seal_mismatch_v1"):
                failures.append("fatal_authority_seal_mismatch_v1_in_seam_audit")
        seam_audit = rec.get("student_loop_seam_audit_v1")
        if isinstance(seam_audit, dict):
            sr = str(seam_audit.get("student_seam_stop_reason_v1") or "").strip()
            out["student_seam_stop_reason_v1"] = sr
            if require_success_terminal:
                if sr not in _SR_TERMINAL_OK:
                    failures.append(f"stop_reason_not_accepted_for_success_v1:{sr or 'missing'}")
            elif not sr:
                failures.append("student_seam_stop_reason_missing_v1")

    auth = int(intr.get("student_decision_authority_v1_count") or 0)
    sealed = int(intr.get("student_output_sealed_count") or 0)
    ok_int = bool(intr.get("integrity_ok"))
    out["authority_count_v1"] = auth
    out["sealed_count_v1"] = sealed
    out["integrity_ok_v1"] = ok_int
    if auth > 0 or sealed > 0:
        if not ok_int:
            failures.append("authority_ne_sealed_trace_integrity_v1")

    out["failures_v1"] = failures
    out["acceptance_pass_v1"] = len(failures) == 0

    print(json.dumps(out, indent=2, default=str))

    if failures:
        print("FAIL: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Runtime proof readiness / verify-job (engineering).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("readiness", help="Pre-run persistence + import checks")

    vp = sub.add_parser("verify-job", help="Post-run terminal JSON + trace integrity")
    vp.add_argument("job_id", help="32-char hex job id")
    vp.add_argument(
        "--require-success-terminal",
        action="store_true",
        help="Require seam stop_reason in {completed_all_trades_v1, rm_preflight_early_exit_first_seal_v1}",
    )

    args = ap.parse_args()
    if args.cmd == "readiness":
        return cmd_readiness()
    if args.cmd == "verify-job":
        return cmd_verify_job(args.job_id, require_success_terminal=args.require_success_terminal)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
