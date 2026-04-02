"""
Anna / training consumer for engine context bundles (Phase 5.9).

Reads an approved ContextBundle-shaped dict, enforces agent contextProfile from
`agents/agent_registry.json`, and fails closed when invalid or stale.

Storage paths must stay under BLACKBOX_CONTEXT_ROOT when loading from disk (engine policy).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT: Path | None = None


def _repo_root() -> Path:
    global _REPO_ROOT
    if _REPO_ROOT is not None:
        return _REPO_ROOT
    here = Path(__file__).resolve()
    root = here.parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ.setdefault("BLACKBOX_REPO_ROOT", str(root))
    _REPO_ROOT = root
    return root


def resolve_context_bundle_attachment(
    bundle_json: str | None,
    bundle_path: Path | None,
    agent_id: str,
    registry_path: Path | None = None,
) -> dict[str, Any] | None:
    """
    Returns None when no bundle supplied.

    When supplied, always returns a dict with consumption + reason (fail-closed).
    """
    if not bundle_json and bundle_path is None:
        return None

    _repo_root()

    from modules.context_engine.consumer import load_bundle_dict, validate_bundle_for_agent
    from modules.context_engine.paths import ContextPathError, resolve_context_root, validate_path_under_root

    bundle, load_err = load_bundle_dict(bundle_json=bundle_json, bundle_path=bundle_path)
    if load_err:
        return {
            "consumption": "rejected",
            "reason": load_err,
            "context_engine": "bundle_load_failed",
        }
    if bundle is None:
        return {
            "consumption": "rejected",
            "reason": "bundle_not_object",
            "context_engine": "bundle_load_failed",
        }

    if bundle_path is not None:
        try:
            root = resolve_context_root()
            validate_path_under_root(root, bundle_path.expanduser().resolve())
        except ContextPathError:
            return {
                "consumption": "rejected",
                "reason": "CTX-GUARD-REJECT:bundle_path_outside_context_mount",
                "context_engine": "path_policy",
            }

    reg = registry_path or (_repo_root() / "agents" / "agent_registry.json")
    try:
        registry = json.loads(reg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {
            "consumption": "rejected",
            "reason": f"registry_load_failed:{e}",
            "context_engine": "registry",
        }

    ok, reason = validate_bundle_for_agent(bundle, agent_id=agent_id, registry=registry)
    if not ok:
        return {
            "consumption": "rejected",
            "reason": reason,
            "context_engine": "policy",
            "validation_state": bundle.get("validation_state"),
            "record_class": bundle.get("record_class"),
        }

    return {
        "consumption": "engaged",
        "reason": "",
        "context_engine": "ok",
        "validation_state": bundle.get("validation_state"),
        "record_class": bundle.get("record_class"),
        "issued_at_utc": bundle.get("issued_at_utc"),
        "sections": bundle.get("sections"),
    }
