#!/usr/bin/env python3
"""
NDE Factory — LangGraph orchestration for domain pipelines.

Autonomous flow after staging JSONL exists: domain contract → dataset validation →
train → eval → gate → reinforcement/retry → final exam → certify.

Deploy: /data/NDE/tools/nde_graph_runner.py
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sqlite3
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

try:
    from typing_extensions import TypedDict
except ImportError:  # pragma: no cover
    from typing import TypedDict  # type: ignore

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

from langgraph.graph import END, START, StateGraph

REPO_ROOT = Path(__file__).resolve().parents[2]

try:
    from nde_validation_lib import (
        resolve_staging_jsonl,
        sha256_file,
        validate_domain_contract as validate_domain_contract_lib,
        validate_training_dataset_for_domain,
    )
except ImportError:  # pragma: no cover
    validate_domain_contract_lib = None  # type: ignore
    validate_training_dataset_for_domain = None  # type: ignore
    resolve_staging_jsonl = None  # type: ignore
    sha256_file = None  # type: ignore

try:
    from secops_proof_lib import (
        validate_eval_harness,
        validate_final_exam,
        write_proof_phase_6_certification,
    )
except ImportError:  # pragma: no cover
    validate_eval_harness = None  # type: ignore
    validate_final_exam = None  # type: ignore
    write_proof_phase_6_certification = None  # type: ignore

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "langgraph-checkpoint-sqlite required: pip install langgraph-checkpoint-sqlite"
    ) from e


Mode = Literal["smoke", "full", "simulate"]


class NDEState(TypedDict, total=False):
    domain: str
    mode: Mode
    nde_root: str
    run_id: str
    max_retries: int
    retry_count: int
    require_approval: bool
    dry_run: bool
    skip_train: bool
    simulate_result: str
    contract_ok: bool
    dataset_ok: bool
    train_ok: bool
    eval_passed: bool
    gate_passed: bool
    reinforcement_done: bool
    final_exam_passed: bool
    certified: bool
    escalated: bool
    last_error: str
    escalate_reason: str
    artifacts: dict[str, Any]
    staging_path: str
    dataset_sha256: str
    eval_score: float
    final_exam_score: float
    messages: list[Any]


NODE_ORDER = [
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


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_dir(nde: Path, domain: str, run_id: str) -> Path:
    return nde / domain / "runs" / run_id


def _node_dir(run_root: Path, name: str) -> Path:
    d = run_root / "nodes" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _norm_proof_status(status: str) -> str:
    s = status.lower()
    if s in ("ok", "passed", "pass"):
        return "PASS"
    if s in ("failed", "fail"):
        return "FAIL"
    if s == "skipped":
        return "SKIPPED"
    if s == "blocked":
        return "BLOCKED"
    return status.upper()


def _write_node_proof(
    run_root: Path,
    name: str,
    *,
    status: str,
    inputs: list[Any],
    outputs: list[Any],
    errors: list[str],
    next_node: str,
    artifacts: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    stdout: str = "",
    stderr: str = "",
) -> None:
    nd = _node_dir(run_root, name)
    payload = {
        "node": name,
        "status": _norm_proof_status(status),
        "inputs": inputs,
        "outputs": outputs,
        "errors": errors,
        "next_node": next_node,
        "updated_at": _utc(),
        "artifacts": artifacts or {},
        "failure_reason": failure_reason,
    }
    (nd / "node_status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (nd / "stdout.log").write_text(stdout or "", encoding="utf-8")
    (nd / "stderr.log").write_text(stderr or "", encoding="utf-8")


def _sync_state_json(run_root: Path, state: dict[str, Any]) -> None:
    path = run_root / "state.json"
    snap = dict(state)
    snap.pop("messages", None)
    path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")


def _nde_root() -> Path:
    return Path(os.environ.get("NDE_ROOT", "/data/NDE")).resolve()


def _approval_file(run_root: Path) -> Path:
    return run_root / "APPROVED"


def _load_domain_cfg(nde: Path, domain: str) -> dict[str, Any]:
    p = nde / domain / "domain_config.yaml"
    if yaml is None or not p.is_file():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _staging_path_resolved(nde: Path, domain: str) -> Path | None:
    cfg = _load_domain_cfg(nde, domain)
    if resolve_staging_jsonl:
        return resolve_staging_jsonl(domain, nde, cfg)
    return None


def _secops_eval_paths(nde: Path) -> tuple[Path, Path]:
    ev = nde / "secops" / "eval" / "eval_v1.json"
    if not ev.is_file():
        ev = nde / "secops" / "eval" / "secops_eval_v0.1.json"
    fe = nde / "secops" / "eval" / "final_exam_v1.json"
    if not fe.is_file():
        fe = nde / "secops" / "eval" / "secops_final_exam_v1.json"
    return ev, fe


def _training_config_path(nde: Path, domain: str) -> Path:
    base = nde / domain / "training"
    cand = base / "config.yaml"
    if cand.is_file():
        return cand
    if domain == "secops":
        legacy = base / "config_secops_qwen1_5b_v0.1.yaml"
        if legacy.is_file():
            return legacy
    return cand


def _simulation_model_name(nde: Path, domain: str) -> str:
    p = _training_config_path(nde, domain)
    if yaml and p.is_file():
        try:
            cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            return str(cfg.get("model_name_or_path") or "")
        except Exception:
            pass
    return ""


def _simulated_adapter_bundle_path(nde: Path, domain: str) -> Path:
    return nde / domain / "adapters" / f"{domain}-simulated-adapter"


def _write_simulated_adapter_manifest(nde: Path, domain: str) -> Path:
    """Create adapters/<domain>-simulated-adapter/ with manifest JSON (no GPU/train subprocess)."""
    d = _simulated_adapter_bundle_path(nde, domain)
    d.mkdir(parents=True, exist_ok=True)
    model = _simulation_model_name(nde, domain) or "unknown"
    body = {
        "simulated": True,
        "status": "COMPLETE",
        "domain": domain,
        "model": model,
    }
    out = d / "simulated_adapter.json"
    out.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return out


def validate_domain_contract(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    inputs: list[Any] = [{"nde_root": str(nde), "domain": domain}]
    errors: list[str] = []
    if validate_domain_contract_lib is None:
        errors.append("nde_validation_lib unavailable")
        ok = False
        detail: dict[str, Any] = {}
    else:
        ok, errs, detail = validate_domain_contract_lib(nde, domain)
        errors.extend(errs)
    outs = [detail]
    next_n = "validate_training_dataset" if ok else "END"
    _write_node_proof(
        run_root,
        "validate_domain_contract",
        status="ok" if ok else "failed",
        inputs=inputs,
        outputs=outs,
        errors=errors,
        next_node=next_n,
        failure_reason=None if ok else "; ".join(errors),
        stdout=json.dumps({"contract_ok": ok, "detail": detail}, indent=2),
        artifacts={"detail": detail},
    )
    return {"contract_ok": ok, "last_error": "" if ok else "; ".join(errors)}


def validate_training_dataset(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    inputs = [{"domain": domain, "nde_root": str(nde)}]
    if not state.get("contract_ok"):
        _write_node_proof(
            run_root,
            "validate_training_dataset",
            status="skipped",
            inputs=inputs,
            outputs=[],
            errors=["contract_ok is false"],
            next_node="END",
            failure_reason="skipped: domain contract failed",
        )
        return {"dataset_ok": False}

    if validate_training_dataset_for_domain is None:
        err = "nde_validation_lib unavailable"
        _write_node_proof(
            run_root,
            "validate_training_dataset",
            status="failed",
            inputs=inputs,
            outputs=[],
            errors=[err],
            next_node="END",
            failure_reason=err,
        )
        return {"dataset_ok": False, "last_error": err}

    ok, detail, errs = validate_training_dataset_for_domain(nde, domain)
    staging_s = detail.get("staging_path")
    ds_hash = ""
    if ok and staging_s and sha256_file:
        try:
            ds_hash = sha256_file(Path(staging_s))
        except OSError:
            pass

    next_n = "smoke_train" if ok else "END"
    _write_node_proof(
        run_root,
        "validate_training_dataset",
        status="ok" if ok else "failed",
        inputs=inputs,
        outputs=[detail],
        errors=errs,
        next_node=next_n,
        failure_reason=None if ok else "; ".join(errs),
        stdout=json.dumps({"dataset_ok": ok, "detail": detail}, indent=2),
        artifacts={"staging_path": staging_s, "dataset_sha256": ds_hash},
    )
    out: dict[str, Any] = {
        "dataset_ok": ok,
        "last_error": "" if ok else "; ".join(errs),
        "artifacts": detail,
    }
    if staging_s:
        out["staging_path"] = staging_s
    if ds_hash:
        out["dataset_sha256"] = ds_hash
    return out


def smoke_train(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    mode = state.get("mode", "smoke")
    run_root = _run_dir(nde, domain, state["run_id"])
    inputs = [{"mode": mode}]
    if not state.get("dataset_ok"):
        _write_node_proof(
            run_root,
            "smoke_train",
            status="skipped",
            inputs=inputs,
            outputs=[],
            errors=["dataset_ok is false"],
            next_node="END",
            failure_reason="dataset validation failed",
        )
        return {"train_ok": False}

    if state.get("skip_train"):
        _write_node_proof(
            run_root,
            "smoke_train",
            status="skipped",
            inputs=inputs,
            outputs=[{"skip_train": True}],
            errors=[],
            next_node="smoke_eval",
            stdout="skip_train=1",
            artifacts={"skip_train": True, "train_mode": "smoke"},
        )
        return {"train_ok": True}

    if mode == "simulate":
        manifest_path = _write_simulated_adapter_manifest(nde, domain)
        cfg_path = _training_config_path(nde, domain)
        _write_node_proof(
            run_root,
            "smoke_train",
            status="ok",
            inputs=inputs,
            outputs=[{"simulated": True, "manifest": str(manifest_path)}],
            errors=[],
            next_node="smoke_eval",
            stdout="simulate: no training subprocess; adapter manifest written\n",
            artifacts={
                "train_mode": "simulate",
                "simulated_train": True,
                "training_subprocess_invoked": False,
                "simulated_adapter_manifest": str(manifest_path),
                "training_config": str(cfg_path),
            },
        )
        return {"train_ok": True}

    if mode == "full":
        if state.get("require_approval") and not _approval_file(run_root).is_file():
            msg = "Full training blocked: create APPROVED file or pass --require-approval workflow"
            _write_node_proof(
                run_root,
                "smoke_train",
                status="blocked",
                inputs=inputs,
                outputs=[],
                errors=[msg],
                next_node="END",
                failure_reason=msg,
            )
            return {"train_ok": False, "last_error": msg}

    base_map = {"secops": nde / "secops", "finquant": nde / "finquant"}
    base = base_map.get(domain) or (nde / domain)
    cfg_path = _training_config_path(nde, domain)
    train_py = REPO_ROOT / "finquant" / "training" / "train_qlora.py"

    if state.get("dry_run"):
        train_mode_would = "full" if mode == "full" else "smoke"
        _write_node_proof(
            run_root,
            "smoke_train",
            status="ok",
            inputs=inputs,
            outputs=[{"dry_run": True, "train_mode": train_mode_would, "config": str(cfg_path)}],
            errors=[],
            next_node="smoke_eval",
            stdout="dry_run: would train\n",
            artifacts={
                "mode": mode,
                "dry_run": True,
                "train_mode": train_mode_would,
                "training_config": str(cfg_path),
            },
        )
        return {"train_ok": True}

    cfg_finquant_repo = REPO_ROOT / "finquant" / "training" / "config_v0.1.yaml"
    if cfg_path.is_file():
        cfg = cfg_path
    elif domain == "finquant":
        cfg = (nde / "finquant" / "training" / "config_v0.1.yaml") if (nde / "finquant" / "training" / "config_v0.1.yaml").is_file() else cfg_finquant_repo
    else:
        cfg = cfg_finquant_repo

    train_mode = "full" if mode == "full" else "smoke"
    venv_py = nde / ".venv" / "bin" / "python"
    exe = str(venv_py) if venv_py.is_file() else sys.executable

    if not train_py.is_file():
        alt = Path(os.environ.get("FINQUANT_TRAIN_SCRIPT", ""))
        train_py = alt if alt.is_file() else train_py
    if not train_py.is_file():
        msg = f"train_qlora.py not found; expected at {REPO_ROOT / 'finquant' / 'training' / 'train_qlora.py'}"
        _write_node_proof(
            run_root,
            "smoke_train",
            status="failed",
            inputs=inputs,
            outputs=[],
            errors=[msg],
            next_node="END",
            failure_reason=msg,
        )
        return {"train_ok": False, "last_error": msg}

    cmd = [exe, str(train_py), train_mode, "--config", str(cfg), "--base", str(base)]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=86400,
        env={**os.environ, "FINQUANT_BASE": str(base), "NDE_ROOT": str(nde)},
        cwd=str(REPO_ROOT),
    )
    ok = proc.returncode == 0
    _write_node_proof(
        run_root,
        "smoke_train",
        status="ok" if ok else "failed",
        inputs=inputs,
        outputs=[{"cmd": cmd, "exit_code": proc.returncode}],
        errors=[] if ok else [proc.stderr[:2000] or "training failed"],
        next_node="smoke_eval" if ok else "END",
        failure_reason=None if ok else (proc.stderr[:8000] or proc.stdout[:8000]),
        stdout=(proc.stdout or "")[-48000:],
        stderr=(proc.stderr or "")[-48000:],
        artifacts={"cmd": cmd, "train_mode": train_mode, "training_config": str(cfg)},
    )
    return {"train_ok": ok, "last_error": "" if ok else "training subprocess failed"}


def smoke_eval(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    inputs = [{"domain": domain}]
    mode = state.get("mode", "smoke")
    if not state.get("train_ok"):
        _write_node_proof(
            run_root,
            "smoke_eval",
            status="skipped",
            inputs=inputs,
            outputs=[],
            errors=["train_ok is false"],
            next_node="END",
            failure_reason="train not ok",
        )
        return {"eval_passed": False, "eval_score": 0.0}

    if mode == "simulate":
        sr_raw = state.get("simulate_result") or "pass"
        sr = str(sr_raw).lower().replace("-", "_")
        if sr == "fail_eval":
            passed = False
        elif sr in ("pass", "fail_final"):
            passed = True
        else:
            passed = True
        score = 1.0 if passed else 0.0
        lines = [
            "simulate: smoke_eval short-circuit (no harness inference)",
            f"simulate_result={sr_raw}",
            f"eval_passed={passed}",
        ]
        _write_node_proof(
            run_root,
            "smoke_eval",
            status="ok" if passed else "failed",
            inputs=inputs + [{"simulate_result": sr_raw}],
            outputs=[{"eval_score": score, "simulated_eval": True}],
            errors=[] if passed else ["simulated fail_eval"],
            next_node="evaluate_gate",
            failure_reason=None if passed else "simulated eval gate failure",
            stdout="\n".join(lines),
            artifacts={
                "simulated_eval": True,
                "eval_inference_invoked": False,
                "simulate_result": sr_raw,
                "eval_score": score,
            },
        )
        return {"eval_passed": passed, "eval_score": score, "last_error": "" if passed else "simulated fail_eval"}

    staging = _staging_path_resolved(nde, domain)
    score = 0.0

    if domain == "secops":
        eval_path, _fe_unused = _secops_eval_paths(nde)
        harness_ok = False
        harness_detail: dict[str, Any] = {}
        harness_errs: list[str] = []
        if validate_eval_harness is None:
            harness_errs.append("secops_proof_lib.validate_eval_harness unavailable")
        elif not eval_path.is_file():
            harness_errs.append(f"missing eval harness: {eval_path}")
        else:
            try:
                eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
                harness_ok, harness_detail, harness_errs = validate_eval_harness(eval_data)
            except Exception as e:
                harness_errs.append(str(e))

        staging_ok = staging is not None and staging.is_file()
        sample_ok = False
        sample_note = ""
        if staging_ok:
            try:
                sample: list[Any] = []
                with staging.open(encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i >= 3:
                            break
                        sample.append(json.loads(line))
                sample_ok = all(isinstance(r.get("source_ids"), list) and r["source_ids"] for r in sample)
            except Exception as e:
                sample_note = str(e)

        passed = harness_ok and staging_ok and sample_ok
        score = 1.0 if passed else 0.0
        lines = [
            "SecOps smoke_eval: eval_v1.json harness + staging sample.",
            f"eval_json={eval_path}",
            json.dumps({"harness_ok": harness_ok, "harness_detail": harness_detail}, indent=2),
            f"staging={staging}",
            json.dumps({"staging_sample_ok": sample_ok, "note": sample_note}),
        ]
        if harness_errs:
            lines.append("harness_errors: " + json.dumps(harness_errs))

        fail_reason = None
        if not passed:
            bits = [x for x in harness_errs if x]
            if not staging_ok:
                bits.append("staging missing")
            if staging_ok and not sample_ok:
                bits.append("staging sample invalid: " + sample_note)
            fail_reason = "; ".join(bits) or "eval checks failed"

        _write_node_proof(
            run_root,
            "smoke_eval",
            status="ok" if passed else "failed",
            inputs=inputs,
            outputs=[{"eval_score": score, "harness_detail": harness_detail}],
            errors=harness_errs if not passed else [],
            next_node="evaluate_gate" if passed else "evaluate_gate",
            failure_reason=fail_reason,
            stdout="\n".join(lines),
            artifacts={
                "eval_json": str(eval_path),
                "eval_score": score,
                "staging_path": str(staging) if staging else None,
            },
        )
        return {"eval_passed": passed, "eval_score": score, "last_error": "" if passed else "smoke_eval failed"}

    passed = staging is not None and staging.is_file()
    if passed:
        try:
            sample = []
            with staging.open(encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= 3:
                        break
                    sample.append(json.loads(line))
            passed = all(isinstance(r.get("source_ids"), list) and r["source_ids"] for r in sample)
        except Exception as e:
            passed = False
    score = 1.0 if passed else 0.0
    _write_node_proof(
        run_root,
        "smoke_eval",
        status="ok" if passed else "failed",
        inputs=inputs,
        outputs=[{"eval_score": score}],
        errors=[] if passed else ["staging schema check failed"],
        next_node="evaluate_gate",
        failure_reason=None if passed else "eval checks failed",
        stdout=json.dumps({"staging": str(staging), "passed": passed}),
        artifacts={"staging_path": str(staging) if staging else None, "eval_score": score},
    )
    return {"eval_passed": passed, "eval_score": score, "last_error": "" if passed else "smoke_eval failed"}


def evaluate_gate(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    gate = bool(state.get("eval_passed"))
    next_n = "final_exam" if gate else "auto_reinforce"
    _write_node_proof(
        run_root,
        "evaluate_gate",
        status="ok" if gate else "failed",
        inputs=[{"eval_passed": state.get("eval_passed")}],
        outputs=[{"gate_passed": gate}],
        errors=[] if gate else ["eval_passed is false"],
        next_node=next_n,
        failure_reason=None if gate else "gate: eval_passed is false",
        stdout=json.dumps({"gate_passed": gate}, indent=2),
    )
    return {"gate_passed": gate}


def auto_reinforce(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    note = (
        "auto_reinforce: reinforcement dataset build would run per domain policy; "
        "no external calls in this layer."
    )
    _write_node_proof(
        run_root,
        "auto_reinforce",
        status="ok",
        inputs=[{"gate_passed": state.get("gate_passed")}],
        outputs=[{"policy": "nde reinforcement stub"}],
        errors=[],
        next_node="retry_or_escalate",
        stdout=note + "\n",
        artifacts={"policy": "nde reinforcement stub"},
    )
    return {"reinforcement_done": True}


def retry_or_escalate(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    retries = int(state.get("retry_count", 0))
    max_r = int(state.get("max_retries", 3))
    retries += 1
    escalate = retries > max_r
    reason = f"retry {retries}/{max_r}" + (" — ESCALATE" if escalate else "")
    next_n = "END" if escalate else "validate_training_dataset"
    _write_node_proof(
        run_root,
        "retry_or_escalate",
        status="escalated" if escalate else "ok",
        inputs=[{"retry_before": retries - 1}],
        outputs=[{"retry_count": retries, "max_retries": max_r, "escalate": escalate}],
        errors=[],
        next_node=next_n,
        stdout=reason + "\n",
        failure_reason="max_retries exceeded" if escalate else None,
        artifacts={"retry_count": retries, "max_retries": max_r},
    )
    return {
        "retry_count": retries,
        "escalated": escalate,
        "escalate_reason": "max_retries" if escalate else "",
    }


def final_exam(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    base_ok = (
        bool(state.get("gate_passed"))
        and bool(state.get("train_ok"))
        and bool(state.get("dataset_ok"))
    )
    fe_score = 0.0

    if state.get("mode") == "simulate":
        sr_raw = state.get("simulate_result") or "pass"
        sr = str(sr_raw).lower().replace("-", "_")
        ok = base_ok and sr != "fail_final"
        fe_score = 1.0 if ok else 0.0
        if domain == "secops":
            eval_path, final_path = _secops_eval_paths(nde)
        else:
            eval_path = nde / domain / "eval" / "eval_v1.json"
            final_path = nde / domain / "eval" / "final_exam_v1.json"
        stdout_obj = {
            "simulated_final_exam": True,
            "simulate_result": sr_raw,
            "gate_passed": state.get("gate_passed"),
            "train_ok": state.get("train_ok"),
            "dataset_ok": state.get("dataset_ok"),
            "final_exam_passed": ok,
            "final_exam_score": fe_score,
            "final_exam_inference_invoked": False,
        }
        _write_node_proof(
            run_root,
            "final_exam",
            status="ok" if ok else "failed",
            inputs=[{"simulate_result": sr_raw}],
            outputs=[stdout_obj],
            errors=[] if ok else ["simulated fail_final"],
            next_node="certify" if ok else "END",
            failure_reason=None if ok else "simulated fail_final",
            stdout=json.dumps(stdout_obj, indent=2),
            artifacts={
                "eval_json": str(eval_path),
                "final_exam_json": str(final_path),
                "simulated_final_exam": True,
                "final_exam_score": fe_score,
            },
        )
        return {"final_exam_passed": ok, "final_exam_score": fe_score}

    if domain == "secops":
        eval_path, final_path = _secops_eval_paths(nde)
        fe_ok = False
        fe_detail: dict[str, Any] = {}
        fe_errs: list[str] = []
        if validate_final_exam is None:
            fe_errs.append("secops_proof_lib.validate_final_exam unavailable")
        elif not eval_path.is_file() or not final_path.is_file():
            fe_errs.append("missing eval or final exam JSON")
        else:
            try:
                eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
                final_data = json.loads(final_path.read_text(encoding="utf-8"))
                fe_ok, fe_detail, fe_errs = validate_final_exam(final_data, eval_data)
            except Exception as e:
                fe_errs.append(str(e))

        ok = base_ok and fe_ok
        fe_score = 1.0 if ok else 0.0
        stdout_obj = {
            "gate_passed": state.get("gate_passed"),
            "train_ok": state.get("train_ok"),
            "dataset_ok": state.get("dataset_ok"),
            "final_exam_json_ok": fe_ok,
            "final_exam_detail": fe_detail,
            "final_exam_errors": fe_errs,
            "final_exam_passed": ok,
            "final_exam_score": fe_score,
            "final_exam_json": str(final_path),
        }
        _write_node_proof(
            run_root,
            "final_exam",
            status="ok" if ok else "failed",
            inputs=[{"eval_json": str(eval_path)}],
            outputs=[stdout_obj],
            errors=fe_errs if not ok else [],
            next_node="certify" if ok else "END",
            failure_reason=None if ok else ("; ".join(fe_errs) if fe_errs else "final exam criteria not met"),
            stdout=json.dumps(stdout_obj, indent=2),
            artifacts={
                "eval_json": str(eval_path),
                "final_exam_json": str(final_path),
                "structural_ok": fe_ok,
                "final_exam_score": fe_score,
            },
        )
        return {"final_exam_passed": ok, "final_exam_score": fe_score}

    ok = base_ok
    fe_score = 1.0 if ok else 0.0
    _write_node_proof(
        run_root,
        "final_exam",
        status="ok" if ok else "failed",
        inputs=[],
        outputs=[{"final_exam_passed": ok}],
        errors=[] if ok else ["criteria not met"],
        next_node="certify" if ok else "END",
        failure_reason=None if ok else "final exam criteria not met",
        stdout=json.dumps(
            {
                "gate_passed": state.get("gate_passed"),
                "train_ok": state.get("train_ok"),
                "dataset_ok": state.get("dataset_ok"),
                "final_exam_passed": ok,
                "final_exam_score": fe_score,
            },
            indent=2,
        ),
        artifacts={"final_exam_score": fe_score},
    )
    return {"final_exam_passed": ok, "final_exam_score": fe_score}


def certify(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    if not state.get("final_exam_passed"):
        msg = "Certification blocked until final_exam passes"
        _write_node_proof(
            run_root,
            "certify",
            status="blocked",
            inputs=[],
            outputs=[],
            errors=[msg],
            next_node="END",
            failure_reason=msg,
        )
        return {"certified": False, "last_error": msg}

    cfg_path = _training_config_path(nde, domain)
    model_name = ""
    if yaml and cfg_path.is_file():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            model_name = str(cfg.get("model_name_or_path") or "")
        except Exception:
            pass

    staging = state.get("staging_path") or ""
    ds_hash = state.get("dataset_sha256") or ""
    if not ds_hash and staging:
        p = Path(staging)
        if p.is_file() and sha256_file:
            try:
                ds_hash = sha256_file(p)
            except OSError:
                pass

    eval_score = float(state.get("eval_score") or 0.0)
    fe_score = float(state.get("final_exam_score") or 0.0)

    body = {
        "certified": True,
        "domain": domain,
        "model": model_name,
        "dataset_sha256": ds_hash,
        "staging_path": staging,
        "eval_score": eval_score,
        "final_exam_score": fe_score,
        "run_id": state["run_id"],
        "certified_at": _utc(),
        "training_config": str(cfg_path),
        "note": "Structural certification via LangGraph; operational sign-off is separate.",
    }
    if state.get("mode") == "simulate":
        body["simulation_mode"] = True
    (run_root / "CERTIFICATE.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    _write_node_proof(
        run_root,
        "certify",
        status="ok",
        inputs=[{"final_exam_passed": True}],
        outputs=[body],
        errors=[],
        next_node="END",
        stdout=json.dumps(body, indent=2),
        artifacts={"certificate": str(run_root / "CERTIFICATE.json")},
    )
    if domain == "secops" and write_proof_phase_6_certification is not None:
        snap = {
            "eval_passed": bool(state.get("eval_passed")),
            "final_exam_passed": bool(state.get("final_exam_passed")),
        }
        write_proof_phase_6_certification(run_root, snap)
    return {"certified": True}


def route_after_contract(state: NDEState) -> str:
    if state.get("contract_ok"):
        return "validate_training_dataset"
    return END  # type: ignore[return-value]


def route_after_training_dataset(state: NDEState) -> str:
    if state.get("dataset_ok"):
        return "smoke_train"
    return END  # type: ignore[return-value]


def route_after_gate(state: NDEState) -> str:
    if state.get("gate_passed"):
        return "final_exam"
    return "auto_reinforce"


def route_after_retry(state: NDEState) -> str:
    if state.get("escalated"):
        return END  # type: ignore[return-value]
    return "validate_training_dataset"


def route_after_final_exam(state: NDEState) -> str:
    if state.get("final_exam_passed"):
        return "certify"
    return END  # type: ignore[return-value]


def main() -> None:
    ap = argparse.ArgumentParser(description="NDE LangGraph runner")
    ap.add_argument("--domain", required=True)
    ap.add_argument("--mode", default="smoke", choices=("smoke", "full", "simulate"))
    ap.add_argument(
        "--simulate-result",
        choices=("pass", "fail_eval", "fail_final"),
        default=None,
        help="With --mode simulate: pass | fail_eval | fail_final (no GPU/train/eval inference)",
    )
    ap.add_argument("--require-approval", action="store_true", help="Require APPROVED file before full training")
    ap.add_argument("--nde-root", type=Path, default=None)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Continue from LangGraph checkpoint (same --run-id, expects checkpoints.sqlite)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Skip train subprocess; exercise graph")
    ap.add_argument("--skip-train", action="store_true", help="Skip train subprocess (still runs eval)")
    args = ap.parse_args()

    nde = (args.nde_root or _nde_root()).resolve()
    run_id = args.run_id or str(uuid.uuid4())
    mode: Mode = args.mode  # type: ignore

    if mode == "full" and not args.require_approval:
        print(
            "error: --mode full requires --require-approval (and APPROVED file before training executes)",
            file=sys.stderr,
        )
        sys.exit(2)

    if mode == "simulate":
        if not args.simulate_result:
            print(
                "error: --mode simulate requires --simulate-result {pass|fail_eval|fail_final}",
                file=sys.stderr,
            )
            sys.exit(2)
    elif args.simulate_result:
        print("error: --simulate-result is only valid with --mode simulate", file=sys.stderr)
        sys.exit(2)

    run_root = _run_dir(nde, args.domain, run_id)
    run_root.mkdir(parents=True, exist_ok=True)

    db_path = run_root / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    graph = StateGraph(NDEState)
    for n in NODE_ORDER:
        graph.add_node(n, globals()[n])

    graph.add_edge(START, "validate_domain_contract")
    graph.add_conditional_edges(
        "validate_domain_contract",
        route_after_contract,
        {"validate_training_dataset": "validate_training_dataset", END: END},
    )
    graph.add_conditional_edges(
        "validate_training_dataset",
        route_after_training_dataset,
        {"smoke_train": "smoke_train", END: END},
    )
    graph.add_edge("smoke_train", "smoke_eval")
    graph.add_edge("smoke_eval", "evaluate_gate")
    graph.add_conditional_edges(
        "evaluate_gate",
        route_after_gate,
        {"final_exam": "final_exam", "auto_reinforce": "auto_reinforce"},
    )
    graph.add_edge("auto_reinforce", "retry_or_escalate")
    graph.add_conditional_edges(
        "retry_or_escalate",
        route_after_retry,
        {"validate_training_dataset": "validate_training_dataset", END: END},
    )
    graph.add_conditional_edges(
        "final_exam",
        route_after_final_exam,
        {"certify": "certify", END: END},
    )
    graph.add_edge("certify", END)

    app = graph.compile(checkpointer=checkpointer)

    initial: NDEState = {
        "domain": args.domain,
        "mode": mode,
        "nde_root": str(nde),
        "run_id": run_id,
        "max_retries": args.max_retries,
        "retry_count": 0,
        "require_approval": bool(args.require_approval),
        "dry_run": bool(args.dry_run),
        "skip_train": bool(args.skip_train),
        "simulate_result": args.simulate_result if mode == "simulate" else "",
        "messages": [],
    }

    cfg = {"configurable": {"thread_id": run_id}}
    if args.resume:
        db_chk = run_root / "checkpoints.sqlite"
        if not db_chk.is_file():
            print(f"error: --resume requires existing checkpoint DB: {db_chk}", file=sys.stderr)
            sys.exit(3)

    try:
        if args.resume:
            result = app.invoke(None, cfg)
        else:
            result = app.invoke(initial, cfg)
    except Exception as e:
        traceback.print_exc()
        _sync_state_json(run_root, {"error": str(e), "run_id": run_id})
        sys.exit(1)

    _sync_state_json(run_root, dict(result))
    print(json.dumps({"run_id": run_id, "run_root": str(run_root), "result_keys": list(result.keys())}, indent=2))


if __name__ == "__main__":
    main()
