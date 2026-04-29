#!/usr/bin/env python3
"""
NDE Factory — LangGraph orchestration for domain pipelines.

LangGraph provides workflow state, checkpoint/resume, and explicit routing.
LangChain is not required for core edges; use it elsewhere for tool/model wrappers.

Deploy: /data/NDE/tools/nde_graph_runner.py
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import sqlite3
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

try:
    from typing_extensions import TypedDict
except ImportError:  # pragma: no cover
    from typing import TypedDict  # type: ignore

from langgraph.graph import END, START, StateGraph

REPO_ROOT = Path(__file__).resolve().parents[2]

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "langgraph-checkpoint-sqlite required: pip install langgraph-checkpoint-sqlite"
    ) from e


Mode = Literal["smoke", "full"]


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
    # routing / outcomes
    sources_ok: bool
    process_ok: bool
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
    # LangGraph messages channel for checkpoint compatibility (optional)
    messages: list[Any]


NODE_ORDER = [
    "validate_sources",
    "process_sources",
    "validate_dataset",
    "smoke_train",
    "run_eval",
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


def _write_node_artifact(
    run_root: Path,
    name: str,
    *,
    status: str,
    artifacts: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    stdout: str = "",
    stderr: str = "",
) -> None:
    nd = _node_dir(run_root, name)
    payload = {
        "node": name,
        "status": status,
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


def _domain_staging_path(domain: str, nde: Path) -> Path | None:
    """Resolve primary staging JSONL for validate_dataset / eval."""
    if domain == "secops":
        for name in (
            "secops_nist_v0.3_from_sources.jsonl",
            "secops_cmmc_v0.3_from_sources.jsonl",
            "secops_v0.1.jsonl",
        ):
            p = nde / "secops" / "datasets" / "staging" / name
            if p.is_file():
                return p
        return nde / "secops" / "datasets" / "staging" / "secops_nist_v0.3_from_sources.jsonl"
    if domain == "finquant":
        for name in ("finquant_v0.3_from_sources.jsonl", "finquant_staging_v0.1.jsonl"):
            p = nde / "finquant" / "datasets" / "staging" / name
            if p.is_file():
                return p
        return None
    return None


def _processor_cmd(nde: Path, domain: str) -> list[str]:
    py = nde / "tools" / "nde_source_processor.py"
    venv_py = nde / ".venv" / "bin" / "python"
    exe = str(venv_py) if venv_py.is_file() else sys.executable
    return [
        exe,
        str(py),
        "--domain",
        domain,
        "--nde-root",
        str(nde),
    ]


def validate_sources(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    raw = nde / domain / "sources" / "raw"
    out_lines: list[str] = []
    ok = raw.is_dir()
    files: list[str] = []
    if ok:
        for p in sorted(raw.rglob("*")):
            if p.is_file() and p.name != ".gitkeep":
                files.append(str(p.relative_to(raw)))
    ok = ok and len(files) > 0
    if not ok:
        msg = f"No source files under {raw}" if raw.is_dir() else f"Missing raw dir {raw}"
        _write_node_artifact(
            run_root,
            "validate_sources",
            status="failed",
            failure_reason=msg,
            stdout="\n".join(out_lines),
        )
        return {"sources_ok": False, "last_error": msg, "artifacts": {"raw_files": files}}

    _write_node_artifact(
        run_root,
        "validate_sources",
        status="ok",
        artifacts={"raw_dir": str(raw), "file_count": len(files), "files": files[:200]},
        stdout=f"Found {len(files)} files\n",
    )
    return {"sources_ok": True, "last_error": "", "artifacts": {"validate_sources": {"files": files}}}


def process_sources(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    if not state.get("sources_ok"):
        _write_node_artifact(run_root, "process_sources", status="skipped", failure_reason="sources not ok")
        return {"process_ok": False}

    if state.get("dry_run"):
        _write_node_artifact(
            run_root,
            "process_sources",
            status="skipped",
            stdout="dry_run: skipped nde_source_processor subprocess\n",
            artifacts={"skipped": True},
        )
        return {"process_ok": True}

    cmd = _processor_cmd(nde, domain)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=7200,
        env={**os.environ, "NDE_ROOT": str(nde)},
    )
    ok = proc.returncode == 0
    _write_node_artifact(
        run_root,
        "process_sources",
        status="ok" if ok else "failed",
        failure_reason=None if ok else (proc.stderr[:8000] or f"exit {proc.returncode}"),
        stdout=proc.stdout[-32000:] if proc.stdout else "",
        stderr=proc.stderr[-32000:] if proc.stderr else "",
        artifacts={"cmd": cmd},
    )
    return {"process_ok": ok, "last_error": "" if ok else (proc.stderr[:2000] or "process_sources failed")}


def validate_dataset(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    if not state.get("process_ok"):
        _write_node_artifact(run_root, "validate_dataset", status="skipped", failure_reason="process_sources failed")
        return {"dataset_ok": False}

    staging = _domain_staging_path(domain, nde)
    if staging is None or not staging.is_file():
        msg = "Staging JSONL not found for domain"
        _write_node_artifact(run_root, "validate_dataset", status="failed", failure_reason=msg)
        return {"dataset_ok": False, "last_error": msg}

    bad = total = 0
    try:
        with staging.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1
                row = json.loads(line)
                if not row.get("source_ids"):
                    bad += 1
        ok = total > 0 and bad == 0
    except Exception as e:
        msg = str(e)
        _write_node_artifact(
            run_root,
            "validate_dataset",
            status="failed",
            failure_reason=msg,
            stderr=traceback.format_exc(),
        )
        return {"dataset_ok": False, "last_error": msg}

    arts = {"staging_path": str(staging), "rows": total, "missing_source_ids": bad}
    _write_node_artifact(
        run_root,
        "validate_dataset",
        status="ok" if ok else "failed",
        failure_reason=None if ok else "missing source_ids or empty",
        artifacts=arts,
        stdout=json.dumps(arts, indent=2),
    )
    return {"dataset_ok": ok, "last_error": "" if ok else "dataset validation failed", "artifacts": arts}


def smoke_train(state: NDEState) -> dict[str, Any]:
    """Smoke QLoRA OR full train on mode full + approval. Never full unless mode full."""
    nde = Path(state["nde_root"])
    domain = state["domain"]
    mode = state.get("mode", "smoke")
    run_root = _run_dir(nde, domain, state["run_id"])
    if not state.get("dataset_ok"):
        _write_node_artifact(run_root, "smoke_train", status="skipped", failure_reason="dataset not ok")
        return {"train_ok": False}

    if state.get("skip_train"):
        _write_node_artifact(run_root, "smoke_train", status="skipped", stdout="skip_train=1")
        return {"train_ok": True}

    # Human approval before full training only
    if mode == "full":
        if state.get("require_approval") and not _approval_file(run_root).is_file():
            msg = "Full training blocked: create APPROVED file or pass --require-approval workflow"
            _write_node_artifact(run_root, "smoke_train", status="blocked", failure_reason=msg)
            return {"train_ok": False, "last_error": msg}

    train_py = REPO_ROOT / "finquant" / "training" / "train_qlora.py"

    if state.get("dry_run"):
        _write_node_artifact(
            run_root,
            "smoke_train",
            status="ok",
            stdout="dry_run: would train\n",
            artifacts={"mode": mode, "dry_run": True},
        )
        return {"train_ok": True}

    # Domain-specific FINQUANT_BASE (historical script name)
    base_map = {
        "secops": nde / "secops",
        "finquant": nde / "finquant",
    }
    base = base_map.get(domain)
    if base is None:
        base = nde / domain

    cfg_secops = base / "training" / "config_secops_qwen1_5b_v0.1.yaml"
    cfg_finquant_repo = REPO_ROOT / "finquant" / "training" / "config_v0.1.yaml"
    if domain == "secops" and cfg_secops.is_file():
        cfg = cfg_secops
    elif domain == "finquant":
        cfg = (nde / "finquant" / "training" / "config_v0.1.yaml") if (nde / "finquant" / "training" / "config_v0.1.yaml").is_file() else cfg_finquant_repo
    else:
        cfg = cfg_secops if cfg_secops.is_file() else cfg_finquant_repo

    train_mode = "full" if mode == "full" else "smoke"
    venv_py = nde / ".venv" / "bin" / "python"
    exe = str(venv_py) if venv_py.is_file() else sys.executable

    if not train_py.is_file():
        alt = Path(os.environ.get("FINQUANT_TRAIN_SCRIPT", ""))
        train_py = alt if alt.is_file() else train_py
    if not train_py.is_file():
        msg = f"train_qlora.py not found; expected at {REPO_ROOT / 'finquant' / 'training' / 'train_qlora.py'}"
        _write_node_artifact(run_root, "smoke_train", status="failed", failure_reason=msg)
        return {"train_ok": False, "last_error": msg}

    cmd = [
        exe,
        str(train_py),
        train_mode,
        "--config",
        str(cfg),
        "--base",
        str(base),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=86400,
        env={
            **os.environ,
            "FINQUANT_BASE": str(base),
            "NDE_ROOT": str(nde),
        },
        cwd=str(REPO_ROOT),
    )
    ok = proc.returncode == 0
    _write_node_artifact(
        run_root,
        "smoke_train",
        status="ok" if ok else "failed",
        failure_reason=None if ok else (proc.stderr[:8000] or proc.stdout[:8000]),
        stdout=(proc.stdout or "")[-48000:],
        stderr=(proc.stderr or "")[-48000:],
        artifacts={"cmd": cmd, "train_mode": train_mode},
    )
    return {"train_ok": ok, "last_error": "" if ok else "training subprocess failed"}


def run_eval(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    if not state.get("train_ok"):
        _write_node_artifact(run_root, "run_eval", status="skipped", failure_reason="train not ok")
        return {"eval_passed": False}

    staging = _domain_staging_path(domain, nde)
    lines = [
        "NDE domain eval (minimal): staging schema + row sampling.",
        f"staging={staging}",
    ]
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
            lines.append(json.dumps({"sample_ok": passed, "rows_checked": len(sample)}))
        except Exception as e:
            passed = False
            lines.append(str(e))

    _write_node_artifact(
        run_root,
        "run_eval",
        status="ok" if passed else "failed",
        failure_reason=None if passed else "eval checks failed",
        stdout="\n".join(lines),
        artifacts={"staging": str(staging) if staging else None},
    )
    return {"eval_passed": passed, "last_error": "" if passed else "run_eval failed"}


def evaluate_gate(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    gate = bool(state.get("eval_passed"))
    _write_node_artifact(
        run_root,
        "evaluate_gate",
        status="ok" if gate else "failed",
        failure_reason=None if gate else "gate: eval_passed is false",
        stdout=json.dumps({"gate_passed": gate}, indent=2),
    )
    return {"gate_passed": gate}


def auto_reinforce(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    note = (
        "auto_reinforce placeholder: would queue reinforcement dataset build per domain policy; "
        "no external calls in this layer."
    )
    _write_node_artifact(
        run_root,
        "auto_reinforce",
        status="ok",
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
    _write_node_artifact(
        run_root,
        "retry_or_escalate",
        status="escalated" if escalate else "retry",
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
    # Minimal exam: gate passed + dataset rows >= 1 + train ok
    ok = (
        bool(state.get("gate_passed"))
        and bool(state.get("train_ok"))
        and bool(state.get("dataset_ok"))
    )
    _write_node_artifact(
        run_root,
        "final_exam",
        status="ok" if ok else "failed",
        failure_reason=None if ok else "final exam criteria not met",
        stdout=json.dumps(
            {
                "gate_passed": state.get("gate_passed"),
                "train_ok": state.get("train_ok"),
                "dataset_ok": state.get("dataset_ok"),
                "final_exam_passed": ok,
            },
            indent=2,
        ),
    )
    return {"final_exam_passed": ok}


def certify(state: NDEState) -> dict[str, Any]:
    nde = Path(state["nde_root"])
    domain = state["domain"]
    run_root = _run_dir(nde, domain, state["run_id"])
    if not state.get("final_exam_passed"):
        msg = "Certification blocked until final_exam passes"
        _write_node_artifact(run_root, "certify", status="blocked", failure_reason=msg)
        return {"certified": False, "last_error": msg}

    body = {
        "certified": True,
        "domain": domain,
        "run_id": state["run_id"],
        "at": _utc(),
        "note": "Mechanical certify flag from LangGraph; operational sign-off is separate.",
    }
    (run_root / "CERTIFICATE.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    _write_node_artifact(
        run_root,
        "certify",
        status="ok",
        stdout=json.dumps(body, indent=2),
        artifacts={"certificate": str(run_root / "CERTIFICATE.json")},
    )
    return {"certified": True}


def route_after_gate(state: NDEState) -> str:
    if state.get("gate_passed"):
        return "final_exam"
    return "auto_reinforce"


def route_after_retry(state: NDEState) -> str:
    if state.get("escalated"):
        return END  # type: ignore[return-value]
    return "validate_sources"


def route_after_final_exam(state: NDEState) -> str:
    if state.get("final_exam_passed"):
        return "certify"
    return END  # type: ignore[return-value]


def main() -> None:
    ap = argparse.ArgumentParser(description="NDE LangGraph runner")
    ap.add_argument("--domain", required=True, choices=("secops", "finquant"))
    ap.add_argument("--mode", default="smoke", choices=("smoke", "full"))
    ap.add_argument("--require-approval", action="store_true", help="Require APPROVED file before full training")
    ap.add_argument("--nde-root", type=Path, default=None)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Continue from LangGraph checkpoint (same --run-id, expects checkpoints.sqlite)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Skip processor/train subprocesses; exercise graph")
    ap.add_argument("--skip-train", action="store_true", help="Skip train subprocess (still runs eval on staging)")
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

    run_root = _run_dir(nde, args.domain, run_id)
    run_root.mkdir(parents=True, exist_ok=True)

    # Persistent checkpoint store per run (durable execution)
    db_path = run_root / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    graph = StateGraph(NDEState)
    for n in NODE_ORDER:
        graph.add_node(n, globals()[n])
    graph.add_edge(START, "validate_sources")
    graph.add_edge("validate_sources", "process_sources")
    graph.add_edge("process_sources", "validate_dataset")
    graph.add_edge("validate_dataset", "smoke_train")
    graph.add_edge("smoke_train", "run_eval")
    graph.add_edge("run_eval", "evaluate_gate")
    graph.add_conditional_edges(
        "evaluate_gate",
        route_after_gate,
        {"final_exam": "final_exam", "auto_reinforce": "auto_reinforce"},
    )
    graph.add_edge("auto_reinforce", "retry_or_escalate")
    graph.add_conditional_edges(
        "retry_or_escalate",
        route_after_retry,
        {"validate_sources": "validate_sources", END: END},
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
