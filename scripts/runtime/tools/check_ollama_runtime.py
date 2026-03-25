#!/usr/bin/env python3
"""
Verify Anna / runtime Ollama configuration (Directive: network LLM source-of-truth).

Prints env, resolved base URL, GET /api/tags, and whether OLLAMA_MODEL appears in tags.
Run on the same host and shell environment as telegram_bot.py (e.g. clawbot).

Usage (from repo):
  cd scripts/runtime && PYTHONPATH=. python3 tools/check_ollama_runtime.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _ollama import ollama_base_url  # noqa: E402


def _anna_llm_enabled() -> bool:
    return os.environ.get("ANNA_USE_LLM", "1").strip().lower() not in ("0", "false", "no")


def main() -> int:
    base = ollama_base_url()
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

    print("--- Ollama runtime (same resolution as Anna pipeline) ---")
    print("ANNA_USE_LLM:", repr(os.environ.get("ANNA_USE_LLM", "<unset>")))
    print("  -> LLM path active:", _anna_llm_enabled())
    print("OLLAMA_STRICT:", repr(os.environ.get("OLLAMA_STRICT", "<unset>")))
    print("OLLAMA_BASE_URL:", repr(os.environ.get("OLLAMA_BASE_URL", "<unset>")))
    print("OLLAMA_MODEL:", repr(os.environ.get("OLLAMA_MODEL", "<unset>")))
    print("resolved ollama_base_url():", base)
    print("active model (default if unset):", model)

    url = f"{base.rstrip('/')}/api/tags"
    print()
    print("GET", url)
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10.0) as r:
            raw = r.read().decode("utf-8")
            code = r.status
    except urllib.error.HTTPError as e:
        print("HTTP error:", e.code, e.reason, file=sys.stderr)
        return 1
    except Exception as e:
        print("Request failed:", e, file=sys.stderr)
        return 1

    print("HTTP", code)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print("Invalid JSON:", e, file=sys.stderr)
        return 1

    names: list[str] = []
    for m in data.get("models") or []:
        n = m.get("name")
        if n:
            names.append(str(n))

    print("installed models (name):", names if names else "(none)")
    ok = model in names
    print("OLLAMA_MODEL in tags:", model, "->", "YES" if ok else "NO")
    if not ok and names:
        print(
            "Hint: set OLLAMA_MODEL to one of the names above, or pull the model on the LLM host.",
            file=sys.stderr,
        )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
