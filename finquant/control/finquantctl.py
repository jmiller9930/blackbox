#!/usr/bin/env python3
"""
FinQuant control plane CLI — M1 scaffolding only.

- Default `submit` is dry registration (no training subprocess).
- Training subprocess is NOT started in M1 even with `--execute` (deferred to later phases).

Deploy: symlink or PATH to finquantctl:
  /data/finquant-1/control/finquantctl.py

Does not modify adapters, active configs on disk used by other processes, or kill Ollama.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_finquant_base() -> Path:
    env = (os.environ.get("FINQUANT_BASE") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def new_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"fq-{ts}-{uuid.uuid4().hex[:6]}"


def check_vram_ollama_block() -> tuple[bool, str]:
    """
    Detect Ollama (or similar) using substantial GPU memory — informational guard only.
    Does not kill or stop any process.
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return _fallback_ollama_from_full_smi(str(e))

    if out.returncode != 0:
        return _fallback_ollama_from_full_smi("query-compute-apps failed")

    blocked = False
    reasons: list[str] = []
    for line in out.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        pid, name, mem = parts[0], parts[1], parts[2]
        if "ollama" in name.lower():
            m = re.search(r"(\d+)", mem)
            mib = int(m.group(1)) if m else 0
            if mib >= 4096:
                blocked = True
                reasons.append(f"process={name} pid={pid} gpu_mem={mem}")

    if blocked:
        return True, "; ".join(reasons) if reasons else "ollama-like process on GPU"
    return False, "no large Ollama GPU footprint detected"


def _fallback_ollama_from_full_smi(reason: str) -> tuple[bool, str]:
    """Parse full `nvidia-smi` text if CSV query is unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return False, f"nvidia-smi unavailable ({reason}): {e}"

    text = (out.stdout or "") + (out.stderr or "")
    if "ollama" not in text.lower():
        return False, f"{reason}; no ollama in nvidia-smi text"

    for line in text.splitlines():
        if "ollama" in line.lower() and "MiB" in line:
            return True, f"fallback_parse: {line.strip()[:200]}"
    return True, f"fallback_parse: ollama mentioned ({reason})"


def cmd_submit(args: argparse.Namespace, base: Path) -> int:
    if args.mode == "full" and not args.confirm_full:
        print("error: --mode full requires --confirm-full", file=sys.stderr)
        return 2

    runs = base / "runs"
    runs.mkdir(parents=True, exist_ok=True)

    run_id = new_run_id()
    run_dir = runs / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = (base / dataset_path).resolve()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (base / config_path).resolve()

    vram_blocked, vram_note = check_vram_ollama_block()

    submit_payload: dict[str, Any] = {
        "run_id": run_id,
        "dataset": str(dataset_path),
        "config": str(config_path),
        "mode": args.mode,
        "dry_run_default": True,
        "execute_requested": bool(args.execute),
        "confirm_full": bool(args.confirm_full),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs" / ".gitkeep").write_text("", encoding="utf-8")

    resolved_dst = run_dir / "resolved_config.yaml"
    if config_path.is_file():
        shutil.copy2(config_path, resolved_dst)
    else:
        resolved_dst.write_text(f"# missing at submit time\n# expected: {config_path}\n", encoding="utf-8")

    (run_dir / "submit.json").write_text(json.dumps(submit_payload, indent=2), encoding="utf-8")

    if vram_blocked:
        state = "blocked_vram"
        blocked_reason = vram_note
    elif args.execute:
        state = "execute_recorded_no_subprocess_m1"
        blocked_reason = (
            "M1 does not spawn train_qlora.py; --execute only records intent. "
            "Future phases will launch training here."
        )
    else:
        state = "dry_registered"
        blocked_reason = ""

    run_state: dict[str, Any] = {
        "run_id": run_id,
        "state": state,
        "mode": args.mode,
        "dataset_version_hint": str(dataset_path.name),
        "config_resolved_path": str(resolved_dst),
        "vram_guard": {"blocked": vram_blocked, "detail": vram_note},
        "blocked_reason": blocked_reason or None,
        "m1_note": "No training subprocess started by finquantctl M1.",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "run_state.json").write_text(json.dumps(run_state, indent=2), encoding="utf-8")

    print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "state": state}, indent=2))
    return 0


def cmd_status(args: argparse.Namespace, base: Path) -> int:
    rid = args.run_id.strip()
    run_dir = base / "runs" / rid
    state_path = run_dir / "run_state.json"
    if not state_path.is_file():
        print(f"error: unknown run_id or missing run_state.json: {rid}", file=sys.stderr)
        return 1
    print(state_path.read_text(encoding="utf-8"))
    return 0


def cmd_list(_args: argparse.Namespace, base: Path) -> int:
    runs = base / "runs"
    if not runs.is_dir():
        print("[]")
        return 0
    rows: list[dict[str, Any]] = []
    for d in sorted(runs.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        sf = d / "run_state.json"
        if sf.is_file():
            try:
                st = json.loads(sf.read_text(encoding="utf-8"))
                rows.append({"run_id": d.name, "state": st.get("state"), "mode": st.get("mode")})
            except json.JSONDecodeError:
                rows.append({"run_id": d.name, "state": "corrupt_state", "mode": None})
        else:
            rows.append({"run_id": d.name, "state": "incomplete", "mode": None})
    print(json.dumps(rows, indent=2))
    return 0


def main() -> None:
    base = default_finquant_base()

    ap = argparse.ArgumentParser(prog="finquantctl", description="FinQuant control plane (M1)")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("submit", help="Register a run (dry by default)")
    sp.add_argument("--dataset", required=True, help="Path to staging JSONL (relative to FINQUANT_BASE or absolute)")
    sp.add_argument("--config", required=True, help="Path to training YAML (relative to FINQUANT_BASE or absolute)")
    sp.add_argument("--mode", choices=("smoke", "full"), required=True)
    sp.add_argument("--confirm-full", action="store_true", help="Required when --mode full")
    sp.add_argument(
        "--execute",
        action="store_true",
        help="Record execute intent only (M1 does not start training subprocess)",
    )

    st = sub.add_parser("status", help="Show run_state.json for a run")
    st.add_argument("run_id", help="Run id (fq-...)")

    ls = sub.add_parser("list", help="List runs under FINQUANT_BASE/runs/")

    args = ap.parse_args()

    if args.command == "submit":
        sys.exit(cmd_submit(args, base))
    if args.command == "status":
        sys.exit(cmd_status(args, base))
    if args.command == "list":
        sys.exit(cmd_list(args, base))

    raise AssertionError("unreachable")


if __name__ == "__main__":
    main()
