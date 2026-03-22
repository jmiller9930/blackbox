"""Read Ollama base URL from OpenClaw config or env."""
from __future__ import annotations

import json
import os
from pathlib import Path


def ollama_base_url() -> str:
    env = os.environ.get("OLLAMA_BASE_URL")
    if env:
        return env.rstrip("/")
    cfg = Path.home() / ".openclaw" / "openclaw.json"
    if cfg.is_file():
        data = json.loads(cfg.read_text(encoding="utf-8"))
        prov = (data.get("models") or {}).get("providers") or {}
        oll = prov.get("ollama") or {}
        base = oll.get("baseUrl")
        if base:
            return str(base).rstrip("/")
    return "http://127.0.0.1:11434"
