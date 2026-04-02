"""Dedicated context storage root + fail-closed path guards."""

from __future__ import annotations

import os
from pathlib import Path


class ContextPathError(ValueError):
    """Path violates context mount policy."""


def resolve_context_root(repo_root: Path | None = None) -> Path:
    """
    Context data lives only under BLACKBOX_CONTEXT_ROOT (clawbot/runtime policy).

    Default: <repo>/data/context_engine
    """
    explicit = os.environ.get("BLACKBOX_CONTEXT_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    base = repo_root
    if base is None:
        br = os.environ.get("BLACKBOX_REPO_ROOT", "").strip()
        base = Path(br).resolve() if br else Path.cwd().resolve()
    return (base / "data" / "context_engine").resolve()


def validate_path_under_root(root: Path, target: Path) -> Path:
    """
    Fail closed: resolved target must be equal to or under root.
    Rejects symlinks that escape the mount when resolved.
    """
    r = root.resolve()
    t = target.expanduser().resolve()
    try:
        t.relative_to(r)
    except ValueError as e:
        raise ContextPathError(f"context path outside mount: {t} not under {r}") from e
    return t


def safe_relative_file(root: Path, *parts: str) -> Path:
    """Build a path under root; reject '..' segments and absolute parts."""
    for p in parts:
        if not p or p == "." or p == ".." or p.startswith("/"):
            raise ContextPathError(f"unsafe context relative segments: {parts!r}")
    rel = Path(*parts)
    if rel.is_absolute():
        raise ContextPathError("absolute paths not allowed for context-relative files")
    candidate = (root / rel).resolve()
    return validate_path_under_root(root, candidate)
