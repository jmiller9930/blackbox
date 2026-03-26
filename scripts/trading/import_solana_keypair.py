#!/usr/bin/env python3
"""
Import a Solana secret into Drift-style keypair.json (JSON array of 64 bytes).

Input is read with hidden input (not echoed) so it does not appear on screen or
in shell history the same way as plain input().

Usage:
  python3 scripts/trading/import_solana_keypair.py
  python3 scripts/trading/import_solana_keypair.py -o trading_core/keypair.json

Requires: pip install base58

Do not paste secrets into chat or commit keypair.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from getpass import getpass

try:
    import base58
except ImportError:
    print("Install dependency: pip install base58", file=sys.stderr)
    sys.exit(1)


def _parse_secret(raw: str) -> bytes:
    s = raw.strip()
    if not s:
        raise ValueError("Empty input")
    if s.startswith("["):
        arr = json.loads(s)
        if not isinstance(arr, list) or len(arr) != 64:
            raise ValueError("JSON array must contain exactly 64 numbers")
        return bytes(arr[i] & 0xFF for i in range(64))
    out = base58.b58decode(s)
    if len(out) != 64:
        raise ValueError(f"Decoded key must be 64 bytes, got {len(out)}")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Write keypair.json from hidden paste")
    p.add_argument(
        "-o",
        "--output",
        default="trading_core/keypair.json",
        help="Output path (default: trading_core/keypair.json)",
    )
    args = p.parse_args()
    out_path = os.path.abspath(args.output)

    print(
        "Paste your secret on ONE line, then press Enter.",
        "Accepted: base58 secret OR JSON array [n1,n2,...] (64 bytes).",
        "Input is hidden (not echoed).",
        sep="\n",
        file=sys.stderr,
    )
    secret = getpass("Secret: ")
    try:
        key_bytes = _parse_secret(secret)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    arr = list(key_bytes)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(arr, f)
    try:
        os.chmod(out_path, 0o600)
    except OSError:
        pass
    print(f"Wrote {len(arr)}-byte keypair to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
