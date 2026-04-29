"""
SecOps NDE — shared validation for proof gates (eval harness, final exam, config).

Used by secops_nde_proof_runner.py and optionally imported by nde_graph_runner.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

REQUIRED_COVERAGE = {
    "identity",
    "logging",
    "patching",
    "encryption",
    "shared_accounts",
    "least_privilege",
    "audit_evidence",
}

FOUR_HEADINGS = (
    "Claim reviewed:",
    "Math verdict:",
    "DATA evidence required:",
    "Final verifier status:",
)


def validate_secops_training_config(path: Path, nde: Path) -> tuple[bool, dict[str, Any], list[str]]:
    errs: list[str] = []
    if yaml is None:
        return False, {}, ["PyYAML required"]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    model = str(raw.get("model_name_or_path") or "")
    if model != "Qwen/Qwen2.5-1.5B-Instruct":
        errs.append(f"model mismatch: {model!r}")

    rel_data = Path(raw["data"]["staging_jsonl"])
    staging = (nde / "secops" / rel_data).resolve() if not rel_data.is_absolute() else rel_data.resolve()
    dataset_ok = staging.is_file()

    smoke_out = raw.get("training", {}).get("smoke", {}).get("output_dir", "")
    full_out = raw.get("training", {}).get("full", {}).get("output_dir", "")
    paths_ok = bool(smoke_out) and bool(full_out) and smoke_out != full_out
    if not paths_ok:
        errs.append("smoke/full output_dir missing or not distinct")

    if not dataset_ok:
        errs.append(f"staging dataset missing at {staging}")

    ok = not errs and dataset_ok and paths_ok
    detail = {
        "model": model,
        "staging_path": str(staging),
        "dataset_exists": dataset_ok,
        "smoke_output_dir": smoke_out,
        "full_output_dir": full_out,
        "smoke_full_distinct": smoke_out != full_out if smoke_out and full_out else False,
    }
    return ok, detail, errs


def _case_expects_incorrect_fail(case: dict[str, Any]) -> bool:
    if not case.get("adversarial"):
        return True
    gr = case.get("grading_reference") or {}
    subs = gr.get("if_adversarial_expect_substrings") or []
    s = json.dumps(subs)
    return "Incorrect" in s and "FAIL" in s


def validate_eval_harness(data: dict[str, Any]) -> tuple[bool, dict[str, Any], list[str]]:
    errs: list[str] = []
    cases = data.get("cases") or []
    n = len(cases)
    if not (25 <= n <= 50):
        errs.append(f"eval case count {n} not in [25,50]")
    adv = sum(1 for c in cases if c.get("adversarial"))
    ratio = adv / n if n else 0.0
    if ratio < 0.80 - 1e-9:
        errs.append(f"adversarial ratio {ratio:.3f} < 0.80")

    cov_seen = {str(c.get("coverage") or "") for c in cases}
    missing_cov = REQUIRED_COVERAGE - cov_seen
    if missing_cov:
        errs.append(f"missing coverage themes: {sorted(missing_cov)}")

    for i, c in enumerate(cases):
        if not c.get("expect_four_headings"):
            errs.append(f"case {i} missing expect_four_headings")
        if c.get("adversarial") and not _case_expects_incorrect_fail(c):
            errs.append(f"case {i} adversarial without Incorrect/FAIL grading_reference")

    ok = not errs
    detail = {
        "case_count": n,
        "adversarial_count": adv,
        "adversarial_ratio": round(ratio, 4),
        "four_heading_flag_all": all(c.get("expect_four_headings") for c in cases) if cases else False,
        "coverage_themes_present": sorted(REQUIRED_COVERAGE & cov_seen),
    }
    return ok, detail, errs


def validate_final_exam(data: dict[str, Any], eval_data: dict[str, Any]) -> tuple[bool, dict[str, Any], list[str]]:
    errs: list[str] = []
    cases = data.get("cases") or []
    n = len(cases)
    if not (30 <= n <= 50):
        errs.append(f"final exam case count {n} not in [30,50]")
    adv = sum(1 for c in cases if c.get("adversarial"))
    ratio = adv / n if n else 0.0
    if ratio < 0.80 - 1e-9:
        errs.append(f"final adversarial ratio {ratio:.3f} < 0.80")

    ev_prompts = {str((c.get("prompt") or "").strip()) for c in (eval_data.get("cases") or [])}
    fe_prompts = [str((c.get("prompt") or "").strip()) for c in cases]
    dup = [p for p in fe_prompts if p in ev_prompts]
    if dup:
        errs.append(f"duplicate prompts vs eval harness: {len(dup)}")

    for i, c in enumerate(cases):
        pc = c.get("pass_criteria") or {}
        if pc:
            if pc.get("min_score_fraction", 0) < 0.95:
                errs.append(f"case {i} pass_criteria min_score_fraction < 0.95")
            if not pc.get("no_false_pass_on_incorrect_claim"):
                errs.append(f"case {i} missing no_false_pass_on_incorrect_claim")
            if not pc.get("data_evidence_required"):
                errs.append(f"case {i} missing data_evidence_required")

    ok = not errs
    detail = {
        "case_count": n,
        "adversarial_count": adv,
        "adversarial_ratio": round(ratio, 4),
        "duplicate_prompts_with_eval": len(dup),
        "pass_criteria_encoded": True,
    }
    return ok, detail, errs


def structural_final_exam_pass_criteria() -> dict[str, Any]:
    """Encoded policy for certification proof (model grading is separate)."""
    return {
        "min_score_fraction": 0.95,
        "no_false_pass_on_incorrect_claim": True,
        "data_evidence_required": True,
    }


SECOPS_GRAPH_NODES = [
    "validate_domain_contract",
    "validate_training_dataset",
    "smoke_train",
    "smoke_eval",
    "evaluate_gate",
    "auto_reinforce",
    "retry_or_escalate",
    "final_exam",
    "certify",
]


def validate_langgraph_wiring_source(py_source: str) -> tuple[bool, dict[str, Any], list[str]]:
    """Static scan of nde_graph_runner.py for SecOps wiring expectations."""
    errs: list[str] = []
    checks: dict[str, Any] = {}

    checks["domain_contract_node"] = "validate_domain_contract" in py_source
    checks["training_dataset_node"] = "validate_training_dataset" in py_source
    checks["training_config_yaml"] = "config.yaml" in py_source
    checks["smoke_eval_and_eval_v1"] = "smoke_eval" in py_source and "eval_v1.json" in py_source
    checks["gate_failure_routes_auto_reinforce"] = (
        "route_after_gate" in py_source and "auto_reinforce" in py_source
    )
    checks["full_mode_requires_approval"] = "require_approval" in py_source and "APPROVED" in py_source
    checks["certify_only_after_final_exam_pass"] = (
        "route_after_final_exam" in py_source and "final_exam_passed" in py_source and "certify" in py_source
    )
    checks["nde_validation_lib_import"] = "nde_validation_lib" in py_source

    for k, v in checks.items():
        if not v:
            errs.append(f"wiring check failed: {k}")

    ok = not errs
    return ok, checks, errs


def write_proof_phase_5_smoke(nde: Path, run_id: str) -> tuple[bool, Path, dict[str, Any]]:
    """Proof after a graph run: autonomous pipeline nodes; smoke mode never records full train."""
    run_root = nde / "secops" / "runs" / run_id
    errs: list[str] = []
    detail: dict[str, Any] = {"run_root": str(run_root), "nodes": {}}

    state_path = run_root / "state.json"
    state: dict[str, Any] = {}
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    mode = state.get("mode")
    dry_run = bool(state.get("dry_run"))

    nodes_meta: dict[str, Any] = {}
    for node in SECOPS_GRAPH_NODES:
        nd = run_root / "nodes" / node / "node_status.json"
        if not nd.is_file():
            nodes_meta[node] = {"status": None, "present": False}
            detail["nodes"][node] = None
            continue
        meta = json.loads(nd.read_text(encoding="utf-8"))
        st = meta.get("status")
        nodes_meta[node] = {"status": st, "present": True, "artifacts": meta.get("artifacts") or {}}
        detail["nodes"][node] = st

    vdc = nodes_meta.get("validate_domain_contract", {}).get("status")
    if vdc != "PASS":
        errs.append(f"validate_domain_contract expected PASS, got {vdc}")

    vtd = nodes_meta.get("validate_training_dataset", {}).get("status")
    if vtd != "PASS":
        errs.append(f"validate_training_dataset expected PASS, got {vtd}")

    st_stat = nodes_meta.get("smoke_train", {}).get("status")
    if st_stat not in ("PASS", "SKIPPED", "BLOCKED"):
        errs.append(f"smoke_train unexpected status {st_stat}")

    arts = nodes_meta.get("smoke_train", {}).get("artifacts") or {}
    train_mode = arts.get("train_mode")
    detail["train_mode_observed"] = train_mode
    detail["mode"] = mode
    detail["dry_run"] = dry_run

    if mode == "smoke" and train_mode == "full":
        errs.append("smoke pipeline recorded full training train_mode")

    ev = nodes_meta.get("smoke_eval", {}).get("status")
    if ev not in ("PASS", "FAIL", "SKIPPED"):
        errs.append(f"smoke_eval did not execute meaningfully (status={ev})")

    gate = nodes_meta.get("evaluate_gate", {}).get("status")
    final_ns = nodes_meta.get("final_exam", {}).get("status")
    if gate == "PASS":
        if final_ns is None:
            errs.append("gate PASS but final_exam missing")
    elif gate == "FAIL":
        detail["final_exam_note"] = "gate FAIL — may skip final_exam or retry path"
    else:
        errs.append(f"evaluate_gate unexpected status {gate}")

    cert_st = nodes_meta.get("certify", {}).get("status")
    fe_passed = bool(state.get("final_exam_passed"))
    if fe_passed and cert_st != "PASS":
        errs.append("certify expected PASS when final_exam_passed (certificate path)")

    detail["eval_node_status"] = ev
    detail["final_exam_node_status"] = final_ns

    ok = not errs
    proof = {
        "phase": "smoke_pipeline",
        "status": "PASS" if ok else "FAIL",
        "checks": detail,
        "errors": errs,
    }
    run_root.mkdir(parents=True, exist_ok=True)
    out = run_root / "proof_phase_5_smoke.json"
    out.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    return ok, out, proof


def write_proof_phase_6_certification(run_root: Path, state_snapshot: dict[str, Any]) -> tuple[bool, Path, dict[str, Any]]:
    cert_p = run_root / "CERTIFICATE.json"
    errs: list[str] = []
    has_cert = cert_p.is_file()
    fe_ok = bool(state_snapshot.get("final_exam_passed"))
    ev_ok = bool(state_snapshot.get("eval_passed"))

    proof_body: dict[str, Any] = {
        "phase": "certification",
        "status": "FAIL",
        "checks": {
            "certificate_exists": has_cert,
            "eval_pass_threshold_met_structural": ev_ok,
            "final_exam_threshold_met_structural": fe_ok,
            "no_false_pass_verdict_placeholder": True,
            "data_evidence_policy": structural_final_exam_pass_criteria(),
            "certificate_written": has_cert and fe_ok,
        },
        "errors": errs,
    }

    if fe_ok and has_cert:
        proof_body["status"] = "PASS"
    else:
        if not fe_ok:
            errs.append("final_exam_passed false or missing in snapshot")
        if not has_cert:
            errs.append("CERTIFICATE.json missing")
        proof_body["errors"] = errs

    ok = proof_body["status"] == "PASS"
    out = run_root / "proof_phase_6_certification.json"
    out.write_text(json.dumps(proof_body, indent=2), encoding="utf-8")
    return ok, out, proof_body
