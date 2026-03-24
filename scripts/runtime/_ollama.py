"""Resolve Ollama base URL for Anna and other runtime LLM callers.

Single source of truth: **OLLAMA_BASE_URL** when set (required for intentional network LLM on clawbot).

- No `~/.openclaw/openclaw.json` override (removed to avoid hidden routing).
- If **OLLAMA_BASE_URL** is unset: use **http://127.0.0.1:11434** for local dev only.
- If **OLLAMA_STRICT=1** (or `true`/`yes`): **OLLAMA_BASE_URL** is required or this raises at resolve time.
"""
from __future__ import annotations

import os


def ollama_base_url() -> str:
    env = os.environ.get("OLLAMA_BASE_URL")
    if env:
        return env.rstrip("/")
    strict = os.environ.get("OLLAMA_STRICT", "").strip().lower() in ("1", "true", "yes")
    if strict:
        raise RuntimeError(
            "OLLAMA_STRICT is set but OLLAMA_BASE_URL is unset. "
            "Set OLLAMA_BASE_URL to your network LLM host (e.g. http://192.168.1.10:11434)."
        )
    return "http://127.0.0.1:11434"
