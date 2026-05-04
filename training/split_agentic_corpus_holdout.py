#!/usr/bin/env python3
"""
Split finquant_agentic_qa_v1 JSONL into train vs holdout for honest evaluation.

Seed rows (case_id prefix FQ-AGENTIC-) always go to TRAIN.

Usage:
  python3 training/split_agentic_corpus_holdout.py \\
    --input merged.jsonl --train-out train.jsonl --holdout-out holdout.jsonl \\
    --strategy live_tail_fraction --live-holdout-fraction 0.15 --report split_report.json

  python3 training/split_agentic_corpus_holdout.py \\
    --input merged.jsonl ... --strategy hash_ratio --holdout-ratio 0.12 --split-seed 42

Strategies:
  live_tail_fraction   Among FQ-LIVE-* rows, sort by (case_num, cycle); last fraction → holdout.
  live_tail_count      Last K FQ-LIVE rows → holdout (same sort).
  hash_ratio           Deterministic hash per case_id (non-seed); mimics reproducible held-out fraction.

Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEED_PREFIX = "FQ-AGENTIC-"
LIVE_RE = re.compile(r"^FQ-LIVE-(\d+)-C(.+)$")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {e}") from e
    return rows


def _write_jsonl(path: Path, objs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for o in objs:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


def _case_id(row: dict[str, Any], strict: bool, row_idx: int) -> str | None:
    cid = row.get("case_id")
    if isinstance(cid, str) and cid.strip():
        return cid.strip()
    if strict:
        raise SystemExit(f"row {row_idx}: missing case_id (--strict)")
    return None


def _parse_live(case_id: str) -> tuple[int, str] | None:
    m = LIVE_RE.match(case_id)
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip()


def _hash_holdout(case_id: str, split_seed: int, ratio: float) -> bool:
    h = hashlib.sha256(f"{split_seed}:{case_id}".encode()).digest()
    val = int.from_bytes(h[:8], "big") / (2**64)
    return val < ratio


def main() -> None:
    ap = argparse.ArgumentParser(description="Holdout split for agentic JSONL")
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--train-out", type=Path, required=True)
    ap.add_argument("--holdout-out", type=Path, required=True)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument(
        "--strategy",
        choices=("live_tail_fraction", "live_tail_count", "hash_ratio"),
        required=True,
    )
    ap.add_argument("--live-holdout-fraction", type=float, default=0.15)
    ap.add_argument("--live-holdout-count", type=int, default=50)
    ap.add_argument("--holdout-ratio", type=float, default=0.12)
    ap.add_argument("--split-seed", type=int, default=42)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    rows = _read_jsonl(args.input)
    n = len(rows)
    if n == 0:
        raise SystemExit("input JSONL is empty")

    holdout_idx: set[int] = set()

    # --- live_tail_* : compute holdout global indices among FQ-LIVE rows only ---
    if args.strategy in ("live_tail_fraction", "live_tail_count"):
        live_entries: list[tuple[int, int, str]] = []
        for i, row in enumerate(rows):
            cid = _case_id(row, args.strict, i)
            if cid is None:
                continue
            if cid.startswith(SEED_PREFIX):
                continue
            pl = _parse_live(cid)
            if pl is None:
                continue
            case_num, cyc = pl
            live_entries.append((i, case_num, cyc))
        live_entries.sort(key=lambda t: (t[1], t[2]))
        if args.strategy == "live_tail_fraction":
            frac = args.live_holdout_fraction
            if not (0.0 <= frac <= 0.95):
                raise SystemExit("live-holdout-fraction must be in [0, 0.95]")
            k = min(len(live_entries), math.ceil(len(live_entries) * frac))
        else:
            k_in = args.live_holdout_count
            if k_in < 0:
                raise SystemExit("live-holdout-count must be >= 0")
            k = min(len(live_entries), k_in)
        for _gidx, case_num, cyc in live_entries[-k:] if k else []:
            pass
        # recover global indices from tail slice
        tail = live_entries[-k:] if k else []
        holdout_idx = {gidx for gidx, _cn, _cy in tail}

    # --- hash_ratio ---
    if args.strategy == "hash_ratio":
        ratio = args.holdout_ratio
        if not (0.0 < ratio < 0.5):
            raise SystemExit("holdout-ratio should be in (0, 0.5) for sanity")
        for i, row in enumerate(rows):
            cid = _case_id(row, args.strict, i)
            if cid is None:
                continue
            if cid.startswith(SEED_PREFIX):
                continue
            if _hash_holdout(cid, args.split_seed, ratio):
                holdout_idx.add(i)

    train_rows: list[dict[str, Any]] = []
    hold_rows: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        cid = _case_id(row, args.strict, i)
        if cid and cid.startswith(SEED_PREFIX):
            train_rows.append(row)
            continue
        if i in holdout_idx:
            hold_rows.append(row)
        else:
            train_rows.append(row)

    _write_jsonl(args.train_out, train_rows)
    _write_jsonl(args.holdout_out, hold_rows)

    summary = {
        "schema": "agentic_holdout_split_report_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input": str(args.input.resolve()),
        "strategy": args.strategy,
        "counts": {"total": n, "train": len(train_rows), "holdout": len(hold_rows)},
        "params": {
            "live_holdout_fraction": args.live_holdout_fraction,
            "live_holdout_count": args.live_holdout_count,
            "holdout_ratio": args.holdout_ratio,
            "split_seed": args.split_seed,
        },
        "notes": [
            "FQ-AGENTIC-* always train.",
            "live_tail_* : holdout = trailing FQ-LIVE-*-* by (case_num, cycle).",
            "hash_ratio : deterministic SHA256 split per case_id (exclude seeds).",
            "Do not tune hyperparameters or prompts against holdout labels between promotion attempts.",
        ],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary["counts"], indent=2))


if __name__ == "__main__":
    main()
