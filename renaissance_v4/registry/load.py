"""Load plugin catalog JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_catalog(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("catalog must be a JSON object")
    if raw.get("schema") != "renaissance_v4_plugin_catalog_v1":
        raise ValueError("unsupported catalog schema")
    return raw
