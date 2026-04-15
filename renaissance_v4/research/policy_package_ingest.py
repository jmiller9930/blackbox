"""
policy_package_ingest.py

DV-ARCH-POLICY-INGESTION-024-A — policy package → validation → replay → deterministic JSON.

- Runs ``scripts/validate_policy_package.py`` (mandatory first step).
- Reuses :func:`renaissance_v4.research.replay_runner.run_manifest_replay` when
  ``POLICY_SPEC.yaml`` includes ``parity.manifest_path``.
- Otherwise, if the package policy module defines ``replay_manifest_policy_checksum``,
  delegates to that (same checksum contract as generated Kitchen packages).

No Monte Carlo, no UI, no job queue.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _validate_policy_package_subprocess(package_dir: Path) -> None:
    """Run ``scripts/validate_policy_package.py <package_dir>``; raise on non-zero exit."""
    root = _repo_root()
    script = root / "scripts" / "validate_policy_package.py"
    if not script.is_file():
        raise FileNotFoundError(f"Missing validator script: {script}")
    r = subprocess.run(
        [sys.executable, str(script), str(package_dir)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        err = (r.stderr or "") + (r.stdout or "")
        raise RuntimeError(
            f"validate_policy_package failed (exit {r.returncode}): {err.strip() or 'no output'}"
        )


def _load_policy_spec_yaml(package_dir: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "POLICY_SPEC.yaml requires PyYAML: pip install pyyaml"
        ) from e
    p = package_dir / "POLICY_SPEC.yaml"
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("POLICY_SPEC.yaml must be a mapping at top level")
    return data


def _resolve_manifest_path(spec: dict[str, Any], repo_root: Path) -> Path | None:
    parity = spec.get("parity")
    if not isinstance(parity, dict):
        return None
    mp = str(parity.get("manifest_path") or "").strip()
    if not mp:
        return None
    cand = (repo_root / mp).resolve()
    if cand.is_file():
        return cand
    alt = Path(mp)
    if alt.is_file():
        return alt.resolve()
    return None


def _experiment_id_from_package(package_dir_resolved: Path, policy_id: str) -> str:
    payload = f"{package_dir_resolved.as_posix()}|{policy_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def _policy_slug_safe(pol: dict[str, Any]) -> str:
    raw = str(pol.get("baseline_policy_slot") or pol.get("id") or "policy").strip()
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in raw)[:96]


def _repo_relative_path(path_in: str | Path, repo_root: Path) -> str:
    p = Path(path_in)
    if not p.is_absolute():
        return p.as_posix()
    try:
        return str(Path(p).resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(Path(p).resolve())


def _replay_via_policy_module(package_dir: Path) -> dict[str, Any]:
    """
    Load ``jupiter_*_policy.py`` from the package directory and call
    ``replay_manifest_policy_checksum()`` when defined (Kitchen-generated packages).
    """
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    cands = sorted(package_dir.glob("jupiter_*_sean_policy.py")) + sorted(
        package_dir.glob("jupiter_*_policy.py")
    )
    if not cands:
        raise RuntimeError(
            "No jupiter_*_sean_policy.py or jupiter_*_policy.py under policy package"
        )
    py_path = cands[0]
    mod_name = f"_policy_pkg_{package_dir.name}_{py_path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, py_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load policy module {py_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "replay_manifest_policy_checksum", None)
    if not callable(fn):
        raise RuntimeError(
            "Policy package has no parity.manifest_path in POLICY_SPEC.yaml and the policy module "
            "does not define replay_manifest_policy_checksum(). Add parity.manifest_path or a "
            "Kitchen-style policy module that delegates to run_manifest_replay."
        )
    chk = str(fn()).strip()
    manifest_str = ""
    mp_fn = getattr(mod, "manifest_path", None)
    if callable(mp_fn):
        try:
            manifest_str = str(mp_fn().resolve())
        except Exception:
            manifest_str = str(mp_fn())
    return {
        "validation_checksum": chk,
        "manifest_path": manifest_str,
        "dataset_bars": None,
        "cumulative_pnl": None,
        "summary": None,
        "replay_via": "policy_module_checksum",
    }


def run_policy_package_replay(policy_path: str | Path) -> dict[str, Any]:
    """
    Validate package, run replay (manifest or policy-module checksum path), write deterministic JSON.

    Output: ``renaissance_v4/state/deterministic_{experiment_id}.json``

    Parameters
    ----------
    policy_path
        Repo-relative path to the policy **package directory** (folder with POLICY_SPEC.yaml),
        or an absolute path.
    """
    repo_root = _repo_root()
    raw_in = Path(policy_path)
    package_dir = (repo_root / raw_in).resolve() if not raw_in.is_absolute() else raw_in.resolve()
    if not package_dir.is_dir():
        raise FileNotFoundError(f"Policy package directory not found: {package_dir}")

    _validate_policy_package_subprocess(package_dir)

    spec_data = _load_policy_spec_yaml(package_dir)
    pol = spec_data.get("policy")
    if not isinstance(pol, dict):
        raise ValueError("POLICY_SPEC.yaml must contain a policy: mapping")
    policy_id = str(pol.get("id") or "").strip()
    if not policy_id:
        raise ValueError("policy.id is required in POLICY_SPEC.yaml")
    policy_version = str(
        pol.get("policy_version") or pol.get("catalog_id") or ""
    ).strip() or "unspecified"
    policy_slug = _policy_slug_safe(pol)

    manifest_resolved = _resolve_manifest_path(spec_data, repo_root)
    if manifest_resolved is not None:
        from renaissance_v4.research.replay_runner import run_manifest_replay

        replay_result = run_manifest_replay(
            manifest_path=manifest_resolved,
            emit_baseline_artifacts=False,
            verbose=False,
        )
    else:
        replay_result = _replay_via_policy_module(package_dir)

    experiment_id = _experiment_id_from_package(package_dir, policy_id)
    vchk = str(replay_result.get("validation_checksum") or "")
    rel_path = _repo_relative_path(policy_path, repo_root)

    state_dir = repo_root / "renaissance_v4" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / f"deterministic_{experiment_id}.json"

    payload: dict[str, Any] = {
        "schema": "deterministic_ingested_policy_v1",
        "experiment_id": experiment_id,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_slug": policy_slug,
        "source_type": "ingested_policy",
        "policy_path": rel_path,
        "validation": "pass",
        "replay": {
            "validation_checksum": vchk,
            "manifest_path": str(
                replay_result.get("manifest_path")
                or (str(manifest_resolved) if manifest_resolved else "")
            ),
            "dataset_bars": replay_result.get("dataset_bars"),
            "cumulative_pnl": replay_result.get("cumulative_pnl"),
            "summary": replay_result.get("summary"),
        },
        "lineage": {
            "experiment_id": experiment_id,
            "policy_id": policy_id,
            "policy_version": policy_version,
        },
    }

    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "experiment_id": experiment_id,
        "output_path": str(out_path),
        "payload": payload,
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Validate policy package and run deterministic replay")
    ap.add_argument(
        "policy_path",
        type=str,
        help="Repo-relative path to policy package directory (contains POLICY_SPEC.yaml)",
    )
    args = ap.parse_args()
    out = run_policy_package_replay(args.policy_path)
    print(json.dumps({"ok": out["ok"], "experiment_id": out["experiment_id"], "output_path": out["output_path"]}, indent=2))


if __name__ == "__main__":
    main()
