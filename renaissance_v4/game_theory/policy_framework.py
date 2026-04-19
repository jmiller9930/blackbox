"""
Policy Framework v1 — bounded behavior space for pattern learning (audit + validation).

Execution still loads ``manifest_path`` (strategy manifest). The framework JSON declares
rules of exploration, tunable surface alignment, and learning-goal intent; it references the
execution manifest via ``execution_manifest_path``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.hunter_planner import resolve_repo_root
from renaissance_v4.game_theory.memory_bundle import BUNDLE_APPLY_WHITELIST, sha256_file

POLICY_FRAMEWORK_SCHEMA_V1 = "policy_framework_v1"

DEFAULT_BASELINE_POLICY_FRAMEWORK_REL = (
    "renaissance_v4/configs/manifests/baseline_v1_policy_framework.json"
)


def load_policy_framework(path: Path | str) -> dict[str, Any]:
    p = Path(path).expanduser().resolve()
    return json.loads(p.read_text(encoding="utf-8"))


def _repo_relative_under(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def build_policy_framework_audit(
    framework_doc: dict[str, Any],
    framework_path: Path,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Compact JSON-safe audit for scenarios, summaries, and operator batch records."""
    p = framework_path.expanduser().resolve()
    tunable = (
        (framework_doc.get("allowed_adaptations") or {}).get("tunable_surface")
        if isinstance(framework_doc.get("allowed_adaptations"), dict)
        else {}
    )
    if not isinstance(tunable, dict):
        tunable = {}
    mem_keys = tunable.get("memory_bundle_apply_keys")
    n_keys = len(mem_keys) if isinstance(mem_keys, list) else 0
    return {
        "framework_id": framework_doc.get("framework_id"),
        "framework_version": framework_doc.get("framework_version"),
        "policy_framework_path": _repo_relative_under(repo_root, p),
        "policy_framework_sha256": sha256_file(p) if p.is_file() else None,
        "tunable_surface_identifier": tunable.get("identifier"),
        "tunable_surface_summary": tunable.get("summary"),
        "memory_bundle_apply_key_count": n_keys,
        "learning_goal_model": (framework_doc.get("learning_goal_alignment") or {}).get(
            "operator_goal_model"
        ),
    }


def validate_policy_framework_v1(
    doc: dict[str, Any],
    *,
    repo_root: Path,
) -> tuple[bool, list[str]]:
    """Structural + tunable-surface integrity checks (blocking errors only)."""
    msgs: list[str] = []
    if doc.get("schema") != POLICY_FRAMEWORK_SCHEMA_V1:
        msgs.append(f"schema must be {POLICY_FRAMEWORK_SCHEMA_V1!r}")
    fid = doc.get("framework_id")
    if not fid or not isinstance(fid, str):
        msgs.append("framework_id (non-empty str) required")
    ver = doc.get("framework_version")
    if not ver or not isinstance(ver, str):
        msgs.append("framework_version (non-empty str) required")
    em = doc.get("execution_manifest_path")
    if not em or not isinstance(em, str):
        msgs.append("execution_manifest_path (str) required")
    else:
        mp = (repo_root / em).resolve()
        if not mp.is_file():
            msgs.append(f"execution_manifest_path not found: {mp}")
    aa = doc.get("allowed_adaptations")
    if not isinstance(aa, dict):
        msgs.append("allowed_adaptations must be an object")
    else:
        ts = aa.get("tunable_surface")
        if not isinstance(ts, dict):
            msgs.append("allowed_adaptations.tunable_surface must be an object")
        else:
            keys = ts.get("memory_bundle_apply_keys")
            if not isinstance(keys, list) or not keys:
                msgs.append("tunable_surface.memory_bundle_apply_keys must be a non-empty list")
            else:
                bad = [k for k in keys if k not in BUNDLE_APPLY_WHITELIST]
                if bad:
                    msgs.append(
                        "tunable_surface.memory_bundle_apply_keys contains keys not in "
                        f"BUNDLE_APPLY_WHITELIST: {bad!r}"
                    )
    return (len(msgs) == 0, msgs)


def attach_policy_framework_audits(
    scenarios: list[dict[str, Any]],
    *,
    repo_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """
    For each scenario with ``policy_framework_path``, load the framework, validate, ensure the
    scenario's ``manifest_path`` matches ``execution_manifest_path``, and set
    ``policy_framework_audit``.
    """
    root = resolve_repo_root(repo_root)
    batch_msgs: list[str] = []
    for i, s in enumerate(scenarios):
        rel = s.get("policy_framework_path")
        if not rel:
            continue
        if not isinstance(rel, str) or not rel.strip():
            return False, [f"scenario[{i}] policy_framework_path must be a non-empty string when set"]
        fw_path = (root / rel.strip()).resolve()
        if not fw_path.is_file():
            return False, [f"scenario[{i}] policy_framework_path not found: {fw_path}"]
        try:
            doc = load_policy_framework(fw_path)
        except (OSError, json.JSONDecodeError) as e:
            return False, [f"scenario[{i}] policy_framework JSON load failed: {e}"]
        ok, msgs = validate_policy_framework_v1(doc, repo_root=root)
        if not ok:
            return False, [f"scenario[{i}] policy_framework invalid: " + "; ".join(msgs)]
        em = doc.get("execution_manifest_path")
        assert isinstance(em, str)
        expected_manifest = (root / em).resolve()
        sm = s.get("manifest_path")
        if not sm:
            return False, [f"scenario[{i}] missing manifest_path"]
        got = Path(str(sm)).expanduser().resolve()
        if got != expected_manifest:
            return False, [
                f"scenario[{i}] manifest_path {got} does not match framework "
                f"execution_manifest_path {expected_manifest}"
            ]
        s["policy_framework_audit"] = build_policy_framework_audit(doc, fw_path, repo_root=root)
        batch_msgs.append(
            f"scenario[{i}] policy_framework attached: "
            f"{s['policy_framework_audit'].get('framework_id')!r} "
            f"v{s['policy_framework_audit'].get('framework_version')!r}"
        )
    return True, batch_msgs


__all__ = [
    "POLICY_FRAMEWORK_SCHEMA_V1",
    "DEFAULT_BASELINE_POLICY_FRAMEWORK_REL",
    "attach_policy_framework_audits",
    "build_policy_framework_audit",
    "load_policy_framework",
    "validate_policy_framework_v1",
]
