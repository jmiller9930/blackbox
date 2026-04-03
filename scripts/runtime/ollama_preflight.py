"""Ollama reachability for Karpathy / Anna — same base URL as ``_ollama.ollama_base_url``."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def _anna_llm_enabled() -> bool:
    return os.environ.get("ANNA_USE_LLM", "1").strip().lower() not in ("0", "false", "no")


def ollama_llm_preflight(*, timeout_sec: float = 3.0) -> dict[str, Any]:
    """
    GET ``{OLLAMA_BASE_URL}/api/tags`` — cheap health probe (same as ``tools/check_ollama_runtime``).

    When ``ANNA_USE_LLM=0``, returns skipped so ticks do not flag LLM.
    """
    if not _anna_llm_enabled():
        return {
            "schema": "ollama_llm_preflight_v1",
            "skipped": True,
            "reason": "ANNA_USE_LLM=0",
        }

    from _ollama import ollama_base_url

    base = ollama_base_url()
    model = (os.environ.get("OLLAMA_MODEL") or "qwen2.5:7b").strip()
    url = f"{base.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as r:
            raw = r.read().decode("utf-8")
            code = r.status
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return {
                "schema": "ollama_llm_preflight_v1",
                "ok": False,
                "base_url": base,
                "probe_url": url,
                "error": f"invalid JSON from /api/tags: {e}",
                "ollama_model_configured": model,
            }
    except urllib.error.HTTPError as e:
        return {
            "schema": "ollama_llm_preflight_v1",
            "ok": False,
            "base_url": base,
            "probe_url": url,
            "error": f"HTTP {e.code} {e.reason}",
            "ollama_model_configured": model,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "schema": "ollama_llm_preflight_v1",
            "ok": False,
            "base_url": base,
            "probe_url": url,
            "error": str(e),
            "ollama_model_configured": model,
        }

    names: list[str] = []
    for m in data.get("models") or []:
        n = m.get("name")
        if n:
            names.append(str(n))
    model_ok = model in names
    return {
        "schema": "ollama_llm_preflight_v1",
        "ok": True,
        "base_url": base,
        "probe_url": url,
        "http_status": code,
        "ollama_model_configured": model,
        "model_present_in_tags": model_ok,
        "installed_model_count": len(names),
        "tags_sample": names[:12],
    }
