"""Pattern hypothesis bundle + pattern_spec_hash."""

from __future__ import annotations

from typing import Any

from .canonical_json import sha256_hex


def pattern_spec_hash(spec: dict[str, Any]) -> str:
    """Hash canonical pattern specification (method params + library versions)."""
    return sha256_hex(spec)
