#!/usr/bin/env python3
"""
DV-ARCH-POLICY-GENERATOR-022-C — generate policy packages from Kitchen manifests.

Usage:
  export PYTHONPATH=.
  python3 scripts/generate_policy_packages_022c.py --manifest renaissance_v4/configs/manifests/baseline_v1_recipe.json
  python3 scripts/generate_policy_packages_022c.py --all

Writes policies/generated/<safe_strategy_id>/ and updates policies/generated/_generation_index.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GENERATOR_VERSION = "022-c-1"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _safe_strategy_token(strategy_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", strategy_id.strip()).strip("_")
    return s or "strategy_unknown"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _validate_manifest_file(manifest_path: Path) -> dict[str, Any]:
    from renaissance_v4.manifest.validate import load_manifest_file, validate_manifest_against_catalog

    m = load_manifest_file(manifest_path)
    errs = validate_manifest_against_catalog(m)
    if errs:
        raise RuntimeError("manifest validation failed: " + "; ".join(errs))
    return m


def _render_policy_py(
    *,
    strategy_id: str,
    manifest_rel_posix: str,
    manifest_hash: str,
    safe: str,
) -> str:
    """Deterministic module body (no timestamps)."""
    return f'''\
"""
Auto-generated — DV-ARCH-POLICY-GENERATOR-022-C (generator_version={_GENERATOR_VERSION!r}).

Delegates full deterministic replay to ``renaissance_v4.research.replay_runner.run_manifest_replay``
using manifest: ``{manifest_rel_posix}``. Does not duplicate lifecycle or signal math.

``evaluate_jupiter_4_manifest_policy`` returns a Jupiter4-shaped result for mechanical tests;
authoritative Kitchen truth is ``replay_manifest_policy_checksum()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.anna_training.jupiter_4_sean_policy import Jupiter4SeanPolicyResult

GENERATOR_VERSION = "{_GENERATOR_VERSION}"
STRATEGY_ID = {strategy_id!r}
MANIFEST_REL = {manifest_rel_posix!r}
MANIFEST_HASH = {manifest_hash!r}
REFERENCE_SOURCE = "policy_gen_022c:{safe}"
CATALOG_ID = {strategy_id!r}

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def manifest_path() -> Path:
    return (_REPO_ROOT / MANIFEST_REL).resolve()


def replay_manifest_policy_checksum() -> str:
    from renaissance_v4.research.replay_runner import run_manifest_replay

    out = run_manifest_replay(
        manifest_path=manifest_path(),
        emit_baseline_artifacts=False,
        verbose=False,
    )
    return str(out["validation_checksum"])


def evaluate_jupiter_4_manifest_policy(
    *,
    bars_asc: list[dict[str, Any]],
    free_collateral_usd: float | None = None,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> Jupiter4SeanPolicyResult:
    _ = (free_collateral_usd, training_state, ledger_db_path)
    return Jupiter4SeanPolicyResult(
        trade=False,
        side="flat",
        reason_code="kitchen_full_manifest_replay_required",
        pnl_usd=None,
        features={{
            "reference": REFERENCE_SOURCE,
            "catalog_id": CATALOG_ID,
            "generator_version": GENERATOR_VERSION,
            "strategy_id": STRATEGY_ID,
            "manifest_path": str(manifest_path()),
            "manifest_hash": MANIFEST_HASH,
            "bars_asc_len": len(bars_asc),
        }},
    )
'''


def _render_policy_spec(
    *,
    manifest: dict[str, Any],
    manifest_rel_posix: str,
    manifest_hash: str,
    replay_checksum: str,
) -> str:
    pol_id = str(manifest.get("strategy_id") or "unknown")
    lines = [
        "policy_package_version: 1",
        f"generator_version: {_GENERATOR_VERSION}",
        f"manifest_hash: {manifest_hash}",
        f"replay_checksum: {replay_checksum}",
        "policy:",
        f'  id: {pol_id}',
        f'  display_name: {json.dumps(manifest.get("strategy_name") or pol_id)}',
        "  baseline_policy_slot: research_kitchen_generated",
        f'  signal_mode: kitchen_manifest_{_safe_strategy_token(pol_id)}',
        f"  catalog_id: {pol_id}",
        "  timeframe: 5m",
        f"  instrument: {json.dumps(str(manifest.get('symbol') or 'SOLUSDT'))}",
        "",
        "inputs:",
        '  canonical: ohlcv_lists',
        "",
        "parity:",
        f"  kitchen_replay_module: renaissance_v4/research/replay_runner.py",
        f"  manifest_path: {manifest_rel_posix}",
        "",
    ]
    return "\n".join(lines) + "\n"


def _render_readme(*, strategy_id: str, manifest_rel: str, safe: str, module_file: str) -> str:
    return f"""# Generated policy package — `{strategy_id}`

**Manifest:** `{manifest_rel}`

**Generator:** DV-ARCH-POLICY-GENERATOR-022-C (`generator_version={_GENERATOR_VERSION}`)

## Validate

```bash
export PYTHONPATH=.
python3 scripts/validate_policy_package.py policies/generated/{safe}
```

## Parity

```bash
python3 scripts/verify_generated_policy_parity_022c.py --package {safe}
```

## Module

- `{module_file}` — `replay_manifest_policy_checksum()`, `evaluate_jupiter_4_manifest_policy()`

Authoritative replay uses `run_manifest_replay` (same engine as `replay_runner`).
"""


def _render_checklist(*, safe: str, module_file: str) -> str:
    return f"""# INTEGRATION_CHECKLIST — `{safe}`

**022-C generated package** — `policies/generated/{safe}/`

## Mechanical

- [x] `python3 scripts/validate_policy_package.py policies/generated/{safe}`

## Live BlackBox wiring (optional)

- [ ] Slot + bridge only if this policy should be operator-selectable as a Jupiter baseline.

## Proof

- [x] Parity: `python3 scripts/verify_generated_policy_parity_022c.py --package {safe}`
"""


def generate_one(
    repo: Path,
    manifest_rel: str,
    *,
    skip_replay: bool = False,
) -> dict[str, Any]:
    """Generate one package; return index entry dict."""
    manifest_rel = manifest_rel.strip().replace("\\\\", "/")
    if ".." in manifest_rel or manifest_rel.startswith("/"):
        raise ValueError(f"invalid manifest path: {manifest_rel!r}")

    mf = (repo / manifest_rel).resolve()
    try:
        mf.relative_to(repo.resolve())
    except ValueError as e:
        raise ValueError(f"manifest outside repo: {manifest_rel}") from e

    if not mf.is_file():
        raise FileNotFoundError(f"manifest not found: {mf}")

    manifest = _validate_manifest_file(mf)
    strategy_id = str(manifest.get("strategy_id") or "").strip()
    if not strategy_id:
        raise RuntimeError("manifest missing strategy_id")

    safe = _safe_strategy_token(strategy_id)
    out_dir = repo / "policies" / "generated" / safe
    manifest_hash = _sha256_file(mf)
    manifest_rel_posix = str(mf.relative_to(repo)).replace("\\\\", "/")

    module_file = f"jupiter_4_{safe}_policy.py"
    replay_checksum = ""
    if not skip_replay:
        from renaissance_v4.research.replay_runner import run_manifest_replay

        rr = run_manifest_replay(manifest_path=mf, emit_baseline_artifacts=False, verbose=False)
        replay_checksum = str(rr["validation_checksum"])

    py_body = _render_policy_py(
        strategy_id=strategy_id,
        manifest_rel_posix=manifest_rel_posix,
        manifest_hash=manifest_hash,
        safe=safe,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "__init__.py").write_text('"""Generated policy package."""\n', encoding="utf-8")
    (out_dir / module_file).write_text(py_body, encoding="utf-8")

    spec_body = _render_policy_spec(
        manifest=manifest,
        manifest_rel_posix=manifest_rel_posix,
        manifest_hash=manifest_hash,
        replay_checksum=replay_checksum,
    )
    (out_dir / "POLICY_SPEC.yaml").write_text(spec_body, encoding="utf-8")
    (out_dir / "README.md").write_text(
        _render_readme(
            strategy_id=strategy_id,
            manifest_rel=manifest_rel_posix,
            safe=safe,
            module_file=module_file,
        ),
        encoding="utf-8",
    )
    (out_dir / "INTEGRATION_CHECKLIST.md").write_text(
        _render_checklist(safe=safe, module_file=module_file),
        encoding="utf-8",
    )

    meta = {
        "schema": "policy_generator_022c_package_meta_v1",
        "generator_version": _GENERATOR_VERSION,
        "strategy_id": strategy_id,
        "manifest_path": manifest_rel_posix,
        "manifest_hash": manifest_hash,
        "replay_checksum": replay_checksum,
        "package_dir": f"policies/generated/{safe}",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "generation_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return meta


def _load_index(repo: Path) -> dict[str, Any]:
    p = repo / "policies" / "generated" / "_generation_index.json"
    if not p.is_file():
        return {"schema": "policy_generator_022c_index_v1", "generator_version": _GENERATOR_VERSION, "entries": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _save_index(repo: Path, data: dict[str, Any]) -> None:
    p = repo / "policies" / "generated" / "_generation_index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Kitchen manifest policy packages (022-C)")
    ap.add_argument("--manifest", type=str, help="Repo-relative path to a single manifest JSON")
    ap.add_argument(
        "--all",
        action="store_true",
        help="Generate for every *.json under renaissance_v4/configs/manifests/",
    )
    ap.add_argument(
        "--skip-replay",
        action="store_true",
        help="Skip running replay to fill replay_checksum (for dry environments without DB)",
    )
    args = ap.parse_args()
    repo = _REPO_ROOT

    manifests: list[str] = []
    if args.all:
        root = repo / "renaissance_v4" / "configs" / "manifests"
        for p in sorted(root.glob("*.json")):
            manifests.append(str(p.relative_to(repo)).replace("\\\\", "/"))
    elif args.manifest:
        manifests.append(args.manifest.strip())
    else:
        ap.error("provide --manifest PATH or --all")

    index = _load_index(repo)
    entries: list[dict[str, Any]] = list(index.get("entries") or [])
    seen_sid: set[str] = set()

    for rel in manifests:
        meta = generate_one(repo, rel, skip_replay=args.skip_replay)
        sid = meta["strategy_id"]
        if sid in seen_sid:
            print(f"duplicate strategy_id in batch: {sid}", file=sys.stderr)
            return 1
        seen_sid.add(sid)
        # replace entry with same strategy_id
        entries = [e for e in entries if e.get("strategy_id") != sid]
        entries.append(meta)

    index["generator_version"] = _GENERATOR_VERSION
    index["entries"] = sorted(entries, key=lambda e: str(e.get("strategy_id", "")))
    _save_index(repo, index)

    print(f"OK: generated {len(manifests)} package(s); index -> policies/generated/_generation_index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
