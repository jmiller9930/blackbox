#!/usr/bin/env python3
"""
DV-ARCH-POLICY-GENERATOR-022-C — verify VALIDATION_CHECKSUM: direct run_manifest_replay vs generated module.

Usage:
  export PYTHONPATH=.
  python3 scripts/verify_generated_policy_parity_022c.py --package renaissance_baseline_v1_stack
  python3 scripts/verify_generated_policy_parity_022c.py --all
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _load_replay_checksum(mod_path: Path) -> str:
    spec = importlib.util.spec_from_file_location(f"policy_mod_{mod_path.stem}", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "replay_manifest_policy_checksum", None)
    if fn is None:
        raise RuntimeError(f"replay_manifest_policy_checksum missing in {mod_path}")
    return str(fn())


def verify_package(safe_dir: str) -> tuple[str, str, bool]:
    import json

    from renaissance_v4.research.replay_runner import run_manifest_replay

    pkg = _REPO / "policies" / "generated" / safe_dir
    py_files = sorted(pkg.glob("jupiter_4_*_policy.py"))
    if len(py_files) != 1:
        raise FileNotFoundError(f"expected one jupiter_4_*_policy.py in {pkg}")
    mod_path = py_files[0]

    meta_path = pkg / "generation_meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"missing generation_meta.json in {pkg}")
    rel = json.loads(meta_path.read_text(encoding="utf-8")).get("manifest_path")
    if not rel:
        raise RuntimeError(f"generation_meta missing manifest_path in {pkg}")
    mf = (_REPO / str(rel)).resolve()
    if not mf.is_file():
        raise FileNotFoundError(f"manifest not found: {mf}")

    direct = str(
        run_manifest_replay(manifest_path=mf, emit_baseline_artifacts=False, verbose=False)[
            "validation_checksum"
        ]
    )
    via = _load_replay_checksum(mod_path)
    return direct, via, direct == via


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=str, help="safe strategy dir under policies/generated/")
    ap.add_argument("--all", action="store_true", help="verify every subdir with jupiter_4_*_policy.py")
    args = ap.parse_args()

    if args.all:
        root = _REPO / "policies" / "generated"
        dirs = sorted([p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")])
        failed = False
        for d in dirs:
            if not list((root / d).glob("jupiter_4_*_policy.py")):
                continue
            a, b, ok = verify_package(d)
            print(f"[{d}] direct={a}")
            print(f"[{d}] policy={b}")
            print(f"[{d}] {'PARITY_OK' if ok else 'PARITY_FAIL'}")
            if not ok:
                failed = True
        return 1 if failed else 0

    if not args.package:
        ap.error("--package or --all required")
    a, b, ok = verify_package(args.package.strip())
    print(f"direct={a}")
    print(f"policy={b}")
    print("PARITY_OK" if ok else "PARITY_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
