#!/usr/bin/env python3
"""
NDE LangGraph orchestration — lightweight CI guard.

Fails when scripts under nde/, nde_factory/layout/, or scripts/install_nde_data_layout.sh
look like multi-step pipeline orchestrators (process + train + eval) without referencing
the LangGraph runner surface.

Usage:
  python3 nde/tools/check_langgraph_enforcement.py
  python3 nde/tools/check_langgraph_enforcement.py --demo-violation
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = Path(__file__).resolve().parent / "langgraph_enforcement_allowlist.json"

# Signals that a file participates in pipeline orchestration (substring / regex).
_PROC = re.compile(
    r"nde_source_processor(?:\.py)?|run_processor\.sh|\brun_processor\b",
    re.I,
)
_TRAIN = re.compile(
    r"train_qlora(?:\.py)?|finquant[/\\]training[/\\]train|^\s*python3?\s+.*train_qlora",
    re.I | re.M,
)
_EVAL = re.compile(r"eval_finquant(?:\.py)?|\beval_finquant\b", re.I)

# LangGraph integration surface (must appear when orchestrating multiple pillars).
_LANGGRAPH = re.compile(
    r"nde_graph_runner(?:\.py)?|run_graph\.sh|\bfrom\s+langgraph\b|\bimport\s+langgraph\b",
    re.I,
)

# Always exempt from multi-step rule (canonical integration points).
_BUILTIN_EXEMPT_NAMES = frozenset(
    {
        "nde_graph_runner.py",
        "run_graph.sh",
        "check_langgraph_enforcement.py",
    }
)


def _load_allowlist() -> list[str]:
    if not ALLOWLIST_PATH.is_file():
        return []
    data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    patterns = data.get("patterns") or []
    return [str(x) for x in patterns if isinstance(x, str)]


def _rel_posix(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _allowlisted(rel: str, patterns: list[str]) -> bool:
    for p in patterns:
        if p.endswith("/"):
            if fnmatch.fnmatch(rel + "/", p + "*") or rel.startswith(p.rstrip("/") + "/"):
                return True
        if fnmatch.fnmatch(rel, p) or rel == p.rstrip("/"):
            return True
    return False


def _strip_hashes_lines(text: str) -> str:
    """Rough comment strip to reduce false positives (best-effort)."""
    out: list[str] = []
    for line in text.splitlines():
        ls = line.strip()
        if ls.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def analyze_content(rel_path: str, text: str) -> list[str]:
    """Return human-readable violation messages for file contents."""
    base = Path(rel_path).name
    if base in _BUILTIN_EXEMPT_NAMES:
        return []

    body = _strip_hashes_lines(text)

    has_p = bool(_PROC.search(body))
    has_t = bool(_TRAIN.search(body))
    has_e = bool(_EVAL.search(body))
    has_l = bool(_LANGGRAPH.search(body))

    pillars = sum((has_p, has_t, has_e))
    if pillars < 2:
        return []

    if has_l:
        return []

    combo = []
    if has_p:
        combo.append("process/source")
    if has_t:
        combo.append("train")
    if has_e:
        combo.append("eval")
    return [
        f"{rel_path}: orchestration signals without LangGraph runner "
        f"({', '.join(combo)}). "
        f"Use nde_graph_runner.py / run_graph.sh or add path to langgraph_enforcement_allowlist.json "
        f"(requires architect exception)."
    ]


def iter_scan_files() -> list[Path]:
    paths: list[Path] = []
    for root in (REPO_ROOT / "nde", REPO_ROOT / "nde_factory" / "layout"):
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if "__pycache__" in p.parts:
                continue
            if p.suffix.lower() not in {".py", ".sh"}:
                continue
            paths.append(p)

    inst = REPO_ROOT / "scripts" / "install_nde_data_layout.sh"
    if inst.is_file():
        paths.append(inst)

    # Stable order for deterministic CI output
    return sorted(set(paths), key=lambda x: x.as_posix())


def main() -> int:
    ap = argparse.ArgumentParser(description="NDE LangGraph orchestration CI check")
    ap.add_argument(
        "--demo-violation",
        action="store_true",
        help="Print a sample failing snippet and exit 1 (no repo scan)",
    )
    args = ap.parse_args()

    if args.demo_violation:
        bad = '''#!/bin/bash
set -e
python3 nde/tools/nde_source_processor.py --domain secops
python3 finquant/training/train_qlora.py smoke --config cfg.yaml
python3 finquant/evals/eval_finquant.py
'''
        rel = "(demo synthetic)"
        msgs = analyze_content(rel, bad)
        print("NDE LangGraph enforcement — DEMO FAIL OUTPUT", file=sys.stderr)
        print("---", file=sys.stderr)
        for m in msgs:
            print(m, file=sys.stderr)
        print("---", file=sys.stderr)
        print(f"Violations: {len(msgs)}", file=sys.stderr)
        return 1

    patterns = _load_allowlist()
    violations: list[str] = []
    scanned = iter_scan_files()

    for fp in scanned:
        rel = _rel_posix(fp)
        if _allowlisted(rel, patterns):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            violations.append(f"{rel}: cannot read ({e})")
            continue
        violations.extend(analyze_content(rel, text))

    if violations:
        print("NDE LangGraph enforcement FAILED", file=sys.stderr)
        for v in violations:
            print(v, file=sys.stderr)
        print(f"\nTotal violations: {len(violations)}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "files_scanned": len(scanned),
                "allowlist": str(ALLOWLIST_PATH.relative_to(REPO_ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
