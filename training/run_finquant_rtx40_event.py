#!/usr/bin/env python3
"""
Unified FinQuant launcher for RTX 40 (trx40): validate corpus → train (optional) → verifier exam.

Typical use (from your Mac: SSH into trx40, attach tmux, then):

  export BLACKBOX_REPO_ROOT=~/blackbox    # or /data/NDE/blackbox
  export FINQUANT_BASE=/data/NDE/finquant/agentic_v05
  cd \"$BLACKBOX_REPO_ROOT\"
  # Smoke (default): short train — wiring / sanity only
  python3 training/test.py --train smoke --adapter adapters/finquant-1-qwen7b-v0.1-smoke

  # Production full train — long run; requires explicit confirmation flag
  python3 training/test.py --train full --confirm-production-train \\
    --adapter adapters/finquant-1-qwen7b-v0.1

What runs where:
  * **Execution** is on the GPU host (trx40) inside your SSH/tmux session — not on your laptop.
  * **Normative final exam JSON** (`final_exam_v1.json`) is checked for placeholder vs populated cases.
    The **graded verifier battery** is `training/verifier_eval_finquant.py` only (FinQuant training
    isolation). Override with env `FINQUANT_VERIFIER_EVAL_PY` if trx40 keeps a copy under `/data`.
    When `final_exam_v1.json` gains non-empty `cases`, a quant runner can be added here.

Recommended data layout on `/data` (FINQUANT_BASE):

  datasets/corpus_v05_agentic_seed.jsonl
  finquant_memory/exemplar_store.jsonl
  adapters/<run_name>/
  reports/
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root(cli: Path | None) -> Path:
    if cli is not None:
        return cli.expanduser().resolve()
    env = (os.environ.get("BLACKBOX_REPO_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def _default_finquant_base() -> Path:
    env = (os.environ.get("FINQUANT_BASE") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path("/data/NDE/finquant/agentic_v05")


def _default_corpus_path(repo: Path, base: Path) -> Path:
    """Prefer FINQUANT_BASE copy; fall back to repo seed when datasets/ was never populated."""
    primary = (base / "datasets" / "corpus_v05_agentic_seed.jsonl").resolve()
    if primary.is_file():
        return primary
    shipped = (repo / "training" / "corpus_v05_agentic_seed.jsonl").resolve()
    if shipped.is_file():
        return shipped
    return primary


def _default_final_exam(finquant_base: Path) -> Path:
    env = (os.environ.get("FINQUANT_FINAL_EXAM_JSON") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # e.g. FINQUANT_BASE=/data/NDE/finquant/agentic_v05 → .../finquant/eval/
    sibling = finquant_base.parent / "eval" / "final_exam_v1.json"
    if sibling.is_file():
        return sibling
    return Path("/data/NDE/finquant/eval/final_exam_v1.json")


def _banner_train_profile(train_mode: str, *, corpus: Path, adapter_arg: str, base: Path) -> None:
    """Make smoke vs production visually unmistakable in tmux logs."""
    if train_mode == "none":
        print(
            "\n=== FINQUANT RTX40 — TRAIN PROFILE: none (validate ± exam only) ===\n"
            f"FINQUANT_BASE={base}\n"
            f"corpus={corpus}\n",
            flush=True,
        )
        return
    if train_mode == "smoke":
        print(
            "\n=== FINQUANT RTX40 — TRAIN PROFILE: SMOKE ===\n"
            "Short QLoRA run (low max_steps). Use for pipeline checks — not a release-quality adapter.\n"
            f"FINQUANT_BASE={base}\n"
            f"corpus={corpus}\n"
            f"adapter (for exam step)={adapter_arg}\n",
            flush=True,
        )
        return
    # full
    print(
        "\n=== FINQUANT RTX40 — TRAIN PROFILE: PRODUCTION (full) ===\n"
        "Long QLoRA run per config — real GPU/time/disk cost. Do not mistake this for smoke.\n"
        f"FINQUANT_BASE={base}\n"
        f"corpus={corpus}\n"
        f"adapter (for exam step)={adapter_arg}\n",
        flush=True,
    )


def _announce_final_exam(path: Path) -> None:
    if not path.is_file():
        print(
            f"NOTE: final exam JSON not found ({path}). "
            "Verifier eval still runs; deploy exam JSON under /data when ready.",
            flush=True,
        )
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"WARN: final exam JSON unreadable ({path}): {e}", flush=True)
        return
    cases = data.get("cases") or []
    if len(cases) == 0:
        print(
            f"NOTE: {path} has empty cases (placeholder). "
            "Training gate for this version = verifier exam (`training/verifier_eval_finquant.py`).",
            flush=True,
        )
    else:
        print(
            f"NOTE: {path} lists {len(cases)} case(s). "
            "Quant-exam LLM grading is not wired in this launcher yet; "
            "still running verifier battery only (`training/verifier_eval_finquant.py`).",
            flush=True,
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="FinQuant RTX40 unified training + exam launcher")
    ap.add_argument("--repo-root", type=Path, default=None, help="Blackbox repo (default: BLACKBOX_REPO_ROOT or cwd)")
    ap.add_argument(
        "--finquant-base",
        type=Path,
        default=None,
        help="FINQUANT_BASE (default: env or /data/NDE/finquant/agentic_v05)",
    )
    ap.add_argument(
        "--corpus",
        "--dataset",
        type=Path,
        dest="corpus",
        default=None,
        help=(
            "Training JSONL passed to train_qlora --dataset (default: "
            "FINQUANT_BASE/datasets/corpus_v05_agentic_seed.jsonl if present, else repo training/corpus_v05_agentic_seed.jsonl). "
            "Alias: --dataset."
        ),
    )
    ap.add_argument(
        "--memory-store",
        type=Path,
        default=None,
        help="exemplar_store.jsonl (default: FINQUANT_BASE/finquant_memory/exemplar_store.jsonl)",
    )
    ap.add_argument(
        "--train",
        choices=("none", "smoke", "full"),
        default="smoke",
        help=(
            "QLoRA: smoke = short wiring run (default); full = production-length run "
            "(requires --confirm-production-train); none = skip train"
        ),
    )
    ap.add_argument(
        "--confirm-production-train",
        action="store_true",
        help="Must be set with --train full — acknowledges a long production training run on GPU",
    )
    ap.add_argument(
        "--adapter",
        type=str,
        default="adapters/finquant-1-qwen7b-v0.1-smoke",
        help=(
            "Adapter dir relative to FINQUANT_BASE (exam step); smoke YAML writes "
            "adapters/finquant-1-qwen7b-v0.1-smoke; full train uses adapters/finquant-1-qwen7b-v0.1"
        ),
    )
    ap.add_argument("--config", type=Path, default=None, help="train_qlora YAML (default: training/config_v0.1.yaml)")
    ap.add_argument("--model", type=str, default="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", help="Base HF model id")
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument("--skip-exam", action="store_true")
    ap.add_argument("--exam-write-report", action="store_true", help="Pass --write-report to eval_finquant.py")
    ap.add_argument("--final-exam-json", type=Path, default=None, help="Override path announced before exam")
    ap.add_argument("--eval-max-new-tokens", type=int, default=768)
    ap.add_argument(
        "--eval-script",
        type=Path,
        default=None,
        help="Verifier eval Python file (default: env FINQUANT_VERIFIER_EVAL_PY or training/verifier_eval_finquant.py)",
    )
    args = ap.parse_args()

    if args.train == "full" and not args.confirm_production_train:
        print(
            "ERROR: --train full requires --confirm-production-train "
            "(smoke uses --train smoke; see --help).",
            file=sys.stderr,
        )
        return 2

    repo = _repo_root(args.repo_root)
    base = (args.finquant_base or _default_finquant_base()).resolve()
    primary = (base / "datasets" / "corpus_v05_agentic_seed.jsonl").resolve()
    shipped = (repo / "training" / "corpus_v05_agentic_seed.jsonl").resolve()

    if args.corpus is not None:
        corpus = args.corpus.expanduser().resolve()
        # Shell defaults often pass FINQUANT_BASE/datasets/... even when that copy was never installed.
        if not corpus.is_file() and corpus == primary and shipped.is_file():
            print(
                f"NOTE: corpus not found under FINQUANT_BASE ({primary}); using repo seed {shipped}",
                flush=True,
            )
            corpus = shipped
    else:
        corpus = _default_corpus_path(repo, base)
        if corpus != primary and corpus.is_file():
            print(
                f"NOTE: corpus not found under FINQUANT_BASE ({primary}); using repo seed {corpus}",
                flush=True,
            )
    mem = args.memory_store or (base / "finquant_memory" / "exemplar_store.jsonl").resolve()
    train_py = repo / "training" / "train_qlora.py"
    validate_py = repo / "training" / "validate_agentic_corpus_v1.py"
    env_eval = (os.environ.get("FINQUANT_VERIFIER_EVAL_PY") or "").strip()
    if args.eval_script is not None:
        eval_py = args.eval_script.expanduser().resolve()
    elif env_eval:
        eval_py = Path(env_eval).expanduser().resolve()
    else:
        eval_py = (repo / "training" / "verifier_eval_finquant.py").resolve()
    cfg = args.config or (repo / "training" / "config_v0.1.yaml")

    for label, p in ("train_qlora.py", train_py), ("validate_agentic_corpus_v1.py", validate_py), ("verifier_eval_finquant.py", eval_py):
        if not p.is_file():
            print(f"ERROR: missing {label} at {p}", file=sys.stderr)
            return 2

    env = os.environ.copy()
    env["FINQUANT_BASE"] = str(base)

    _banner_train_profile(args.train, corpus=corpus, adapter_arg=args.adapter, base=base)

    fe = args.final_exam_json or _default_final_exam(base)
    _announce_final_exam(fe)

    if not args.skip_validate:
        r = subprocess.run(
            [sys.executable, str(validate_py), str(corpus), "--store", str(mem)],
            cwd=str(repo),
            env=env,
        )
        if r.returncode != 0:
            return r.returncode

    if args.train != "none":
        cmd = [
            sys.executable,
            str(train_py),
            args.train,
            "--config",
            str(cfg),
            "--dataset",
            str(corpus),
            "--base",
            str(base),
        ]
        r = subprocess.run(cmd, cwd=str(repo), env=env)
        if r.returncode != 0:
            return r.returncode

    if not args.skip_exam:
        adapter_resolved = Path(args.adapter)
        if not adapter_resolved.is_absolute():
            adapter_resolved = (base / adapter_resolved).resolve()
        if not adapter_resolved.is_dir():
            print(f"ERROR: adapter not found: {adapter_resolved}", file=sys.stderr)
            return 2
        cmd = [
            sys.executable,
            str(eval_py),
            "--base",
            str(base),
            "--model",
            args.model,
            "--adapter",
            str(adapter_resolved),
            "--max-new-tokens",
            str(args.eval_max_new_tokens),
        ]
        if args.exam_write_report:
            cmd.append("--write-report")
        r = subprocess.run(cmd, cwd=str(repo), env=env)
        if r.returncode != 0:
            return r.returncode

    if args.train == "full":
        print("FINQUANT_RTX40_EVENT_COMPLETE_TRAIN_FULL_PRODUCTION", flush=True)
    elif args.train == "smoke":
        print("FINQUANT_RTX40_EVENT_COMPLETE_TRAIN_SMOKE", flush=True)
    else:
        print("FINQUANT_RTX40_EVENT_COMPLETE_NO_TRAIN", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
