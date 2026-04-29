#!/usr/bin/env python3
"""
SecOps NDE — phased proof gates (config, eval harness, final exam, graph wiring, smoke run, certification).

Writes JSON proofs under ``<nde-root>/secops/reports/`` (phases 1–4) and
``<nde-root>/secops/runs/<run_id>/`` (phases 5–6).

Deploy mirror: ``/data/NDE/secops/...``
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from secops_proof_lib import (
    validate_eval_harness,
    validate_final_exam,
    validate_langgraph_wiring_source,
    validate_secops_training_config,
    write_proof_phase_5_smoke,
    write_proof_phase_6_certification,
)

REPORTS_REL = Path("secops") / "reports"
GRAPH_RUNNER = Path(__file__).resolve().parent / "nde_graph_runner.py"


def _write_reports(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def phase_1_config(nde: Path) -> tuple[bool, Path]:
    cfg = nde / "secops" / "training" / "config_secops_qwen1_5b_v0.1.yaml"
    ok, detail, errs = validate_secops_training_config(cfg, nde)
    proof = {"phase": "config", "status": "PASS" if ok else "FAIL", "checks": detail, "errors": errs}
    out = nde / REPORTS_REL / "proof_phase_1_config.json"
    _write_reports(out, proof)
    return ok, out


def phase_2_eval(nde: Path) -> tuple[bool, Path]:
    eval_path = nde / "secops" / "eval" / "secops_eval_v0.1.json"
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    ok, detail, errs = validate_eval_harness(data)
    proof = {"phase": "eval", "status": "PASS" if ok else "FAIL", "checks": detail, "errors": errs}
    out = nde / REPORTS_REL / "proof_phase_2_eval.json"
    _write_reports(out, proof)
    return ok, out


def phase_3_final_exam(nde: Path) -> tuple[bool, Path]:
    eval_path = nde / "secops" / "eval" / "secops_eval_v0.1.json"
    final_path = nde / "secops" / "eval" / "secops_final_exam_v1.json"
    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    final_data = json.loads(final_path.read_text(encoding="utf-8"))
    ok, detail, errs = validate_final_exam(final_data, eval_data)
    proof = {
        "phase": "final_exam",
        "status": "PASS" if ok else "FAIL",
        "checks": detail,
        "errors": errs,
        "encoded_pass_policy": {
            "min_score_fraction": 0.95,
            "no_false_pass_on_incorrect_claim": True,
            "data_evidence_required": True,
        },
    }
    out = nde / REPORTS_REL / "proof_phase_3_final_exam.json"
    _write_reports(out, proof)
    return ok, out


def phase_4_graph_wiring_write(nde: Path) -> tuple[bool, Path]:
    src = GRAPH_RUNNER.read_text(encoding="utf-8")
    ok, checks, errs = validate_langgraph_wiring_source(src)
    proof_payload: dict[str, object] = {
        "phase": "graph_wiring",
        "status": "PASS" if ok else "FAIL",
        "checks": checks,
        "errors": errs,
    }
    out = nde / REPORTS_REL / "proof_phase_4_graph_wiring.json"
    _write_reports(out, proof_payload)
    return ok, out


def phase_5_smoke(nde: Path, run_id: str) -> tuple[bool, Path]:
    ok, out, _proof = write_proof_phase_5_smoke(nde, run_id)
    return ok, out


def phase_6_cert(nde: Path, run_id: str) -> tuple[bool, Path]:
    run_root = nde / "secops" / "runs" / run_id
    sp = run_root / "state.json"
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.is_file() else {}
    ok, out, _body = write_proof_phase_6_certification(run_root, state)
    return ok, out


def main() -> None:
    ap = argparse.ArgumentParser(description="SecOps NDE proof gates")
    ap.add_argument(
        "--nde-root",
        type=Path,
        default=None,
        help="NDE root (secops lives under <nde-root>/secops). Default: $NDE_ROOT or repo nde_factory/layout",
    )
    ap.add_argument("--run-id", default=None, help="Run id for phases 5–6 (under secops/runs/)")
    ap.add_argument(
        "--phases",
        default="1,2,3,4,5,6",
        help="Comma-separated phase numbers to run (default all)",
    )
    args = ap.parse_args()

    nde_default = Path(__file__).resolve().parents[2] / "nde_factory" / "layout"
    if args.nde_root is not None:
        nde = args.nde_root.resolve()
    else:
        env_nde = os.environ.get("NDE_ROOT", "").strip()
        nde = Path(env_nde).resolve() if env_nde else nde_default

    phases = [int(x.strip()) for x in args.phases.split(",") if x.strip()]
    results: list[tuple[int, str, str]] = []

    if 1 in phases:
        ok, out = phase_1_config(nde)
        results.append((1, str(out), "PASS" if ok else "FAIL"))
        if not ok:
            print(json.dumps({"stopped_at": 1, "proof": str(out)}, indent=2))
            sys.exit(1)

    if 2 in phases:
        ok, out = phase_2_eval(nde)
        results.append((2, str(out), "PASS" if ok else "FAIL"))
        if not ok:
            print(json.dumps({"stopped_at": 2, "proof": str(out)}, indent=2))
            sys.exit(1)

    if 3 in phases:
        ok, out = phase_3_final_exam(nde)
        results.append((3, str(out), "PASS" if ok else "FAIL"))
        if not ok:
            print(json.dumps({"stopped_at": 3, "proof": str(out)}, indent=2))
            sys.exit(1)

    if 4 in phases:
        ok, out = phase_4_graph_wiring_write(nde)
        results.append((4, str(out), "PASS" if ok else "FAIL"))
        if not ok:
            print(json.dumps({"stopped_at": 4, "proof": str(out)}, indent=2))
            sys.exit(1)

    if 5 in phases:
        rid = args.run_id
        if not rid:
            print("error: phase 5 requires --run-id", file=sys.stderr)
            sys.exit(2)
        ok, out = phase_5_smoke(nde, rid)
        results.append((5, str(out), "PASS" if ok else "FAIL"))
        if not ok:
            print(json.dumps({"stopped_at": 5, "proof": str(out)}, indent=2))
            sys.exit(1)

    if 6 in phases:
        rid = args.run_id
        if not rid:
            print("error: phase 6 requires --run-id", file=sys.stderr)
            sys.exit(2)
        ok, out = phase_6_cert(nde, rid)
        results.append((6, str(out), "PASS" if ok else "FAIL"))
        if not ok:
            print(json.dumps({"stopped_at": 6, "proof": str(out)}, indent=2))
            sys.exit(1)

    print(json.dumps({"nde_root": str(nde), "results": [{"phase": p, "proof": o, "status": s} for p, o, s in results]}, indent=2))


if __name__ == "__main__":
    main()
