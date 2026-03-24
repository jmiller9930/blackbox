"""
Reusable local Ollama HTTP client (Anna + other agents).
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class LlmResult:
    text: str
    model: str
    error: str | None = None


def ollama_generate(
    prompt: str,
    *,
    base_url: str,
    model: str | None = None,
    timeout: float = 120.0,
) -> LlmResult:
    m = model or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
    url = f"{base_url.rstrip('/')}/api/generate"
    body = json.dumps(
        {"model": m, "prompt": prompt, "stream": False},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return LlmResult(text=(data.get("response") or "").strip(), model=m, error=None)
    except Exception as e:
        return LlmResult(text="", model=m, error=str(e))
