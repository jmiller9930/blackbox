"""Canonical JSON serialization for stable hashes (sorted keys, compact separators)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def dumps_canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(dumps_canonical(obj).encode("utf-8")).hexdigest()
