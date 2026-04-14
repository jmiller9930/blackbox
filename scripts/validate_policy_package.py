#!/usr/bin/env python3
"""
Mechanical validation for a Sean / Grok policy package directory (see docs/architect/policy_package_standard.md).

Fails fast before merge review. Does NOT replace integration wiring or pytest.

Usage:
  python3 scripts/validate_policy_package.py path/to/policy_packages/jupv4_foo

Requires: PyYAML (pip install pyyaml) for POLICY_SPEC.yaml parsing.
"""
from __future__ import annotations

import argparse
import ast
import glob
import sys
from pathlib import Path


def _need_yaml():
    try:
        import yaml  # type: ignore  # noqa: F401
    except ImportError:
        print(
            "validate_policy_package: need PyYAML: pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(2)
    import yaml as _yaml

    return _yaml


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate policy package layout and policy module syntax.")
    ap.add_argument("package_dir", type=Path, help="Directory containing POLICY_SPEC.yaml and policy .py")
    args = ap.parse_args()
    root: Path = args.package_dir.resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    errors: list[str] = []

    spec_path = root / "POLICY_SPEC.yaml"
    if not spec_path.is_file():
        errors.append(f"Missing required file: {spec_path}")
    checklist = root / "INTEGRATION_CHECKLIST.md"
    if not checklist.is_file():
        errors.append(f"Missing required file: {checklist}")

    py_files = sorted(
        set(glob.glob(str(root / "jupiter_*_sean_policy.py")))
        | set(glob.glob(str(root / "jupiter_*_policy.py")))
    )
    if not py_files:
        errors.append("Missing jupiter_*_sean_policy.py or jupiter_*_policy.py under package dir")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    yaml = _need_yaml()
    raw = spec_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except Exception as exc:
        print(f"POLICY_SPEC.yaml parse error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print("POLICY_SPEC.yaml must be a mapping at top level.", file=sys.stderr)
        sys.exit(1)

    if data.get("policy_package_version") != 1:
        print(
            "policy_package_version must be 1 (or update validator for new schema).",
            file=sys.stderr,
        )
        sys.exit(1)

    pol = data.get("policy")
    if not isinstance(pol, dict):
        errors.append("policy: missing or not a mapping in POLICY_SPEC.yaml")
    else:
        for k in (
            "id",
            "baseline_policy_slot",
            "signal_mode",
            "catalog_id",
        ):
            if not pol.get(k):
                errors.append(f"policy.{k}: required non-empty string in POLICY_SPEC.yaml")

    inputs = data.get("inputs")
    if isinstance(inputs, dict):
        can = str(inputs.get("canonical") or "").strip()
        if can and can != "ohlcv_lists":
            print(
                f"Warning: inputs.canonical is {can!r} — Blackbox bundle prefers ohlcv_lists.",
                file=sys.stderr,
            )

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    for py_path in py_files:
        p = Path(py_path)
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        except SyntaxError as exc:
            print(f"Syntax error in {p}: {exc}", file=sys.stderr)
            sys.exit(1)
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        has_entry = any(
            f.startswith("evaluate_jupiter") or f.startswith("generate_signal_from_ohlc")
            for f in funcs
        )
        if not has_entry:
            print(
                f"Warning: {p.name} has no obvious entry function "
                "(evaluate_jupiter_* or generate_signal_from_ohlc*) — confirm entrypoint for bridge.",
                file=sys.stderr,
            )

    print(f"OK: policy package structure valid under {root}")


if __name__ == "__main__":
    main()
