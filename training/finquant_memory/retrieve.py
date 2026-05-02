#!/usr/bin/env python3
"""
Minimal retrieval helper for training-time memory cites.

Usage:
  python3 retrieve.py --id MEM-CHOP-ATR-001
  python3 retrieve.py --ids MEM-CHOP-ATR-001,MEM-RSI-MID-002
  python3 retrieve.py --list
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _store_path() -> Path:
    return Path(__file__).resolve().parent / "exemplar_store.jsonl"


def load_store(path: Path | None = None) -> dict[str, dict]:
    p = path or _store_path()
    out: dict[str, dict] = {}
    raw = p.read_text(encoding="utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        mid = obj.get("memory_id")
        if isinstance(mid, str):
            out[mid] = obj
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Retrieve FinQuant training memory rows by id.")
    ap.add_argument("--store", type=Path, default=None, help="Override exemplar_store.jsonl path")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", type=str, help="Single memory_id")
    g.add_argument("--ids", type=str, help="Comma-separated memory_ids")
    g.add_argument("--list", action="store_true", help="Print all ids")
    args = ap.parse_args()
    store = load_store(args.store)
    if args.list:
        for k in sorted(store):
            print(k)
        return
    ids = [args.id] if args.id else [x.strip() for x in args.ids.split(",") if x.strip()]
    for mid in ids:
        row = store.get(mid)
        if row is None:
            raise SystemExit(f"unknown memory_id: {mid}")
        print(json.dumps(row, indent=2))


if __name__ == "__main__":
    main()
