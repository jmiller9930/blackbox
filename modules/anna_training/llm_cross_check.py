"""
Internal LLM cross-check for Anna training — second pass over a draft without external chat.

Uses the same local Ollama path as the analyst pipeline (`llm.local_llm_client.ollama_generate`).
Respects ``ANNA_USE_LLM=0`` (skip, no network). Paper-only framing; no execution advice.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def _ensure_runtime_on_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    rt = root / "scripts" / "runtime"
    for p in (str(root), str(rt)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return root


_VERDICT_RE = re.compile(
    r"^\s*VERDICT\s*:\s*(PASS|REVIEW|FAIL)\b",
    re.IGNORECASE | re.MULTILINE,
)


def training_llm_enabled() -> bool:
    """True when Anna is allowed to call the local LLM (same convention as analyst / Telegram)."""
    import os

    return os.environ.get("ANNA_USE_LLM", "1").strip().lower() not in ("0", "false", "no")


def parse_cross_check_verdict(text: str) -> str | None:
    """Extract VERDICT: PASS|REVIEW|FAIL from model output if present."""
    m = _VERDICT_RE.search(text or "")
    if not m:
        return None
    return m.group(1).upper()


def build_cross_check_prompt(draft: str, *, supporting_context: str | None = None) -> str:
    ctx = (supporting_context or "").strip()
    if not ctx:
        ctx = "(none)"
    draft_stripped = (draft or "").strip()
    return (
        "You are an internal cross-check reviewer for Anna's training harness (paper-only; "
        "no live trading or venue execution).\n"
        "Find logical gaps, inconsistent numbers, or claims not supported by the draft or context.\n"
        "Do not invent prices or market data. Be concise.\n\n"
        "Output format:\n"
        "First line must be exactly one of: VERDICT: PASS  OR  VERDICT: REVIEW  OR  VERDICT: FAIL\n"
        "Then short bullets if REVIEW or FAIL (what to fix or double-check).\n\n"
        f"SUPPORTING CONTEXT:\n{ctx}\n\n"
        f"DRAFT TO CROSS-CHECK:\n{draft_stripped}\n"
    )


def run_llm_cross_check(
    draft: str,
    *,
    supporting_context: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """
    Call the local LLM once with a reviewer prompt. No Telegram/Slack — in-process HTTP to Ollama.

    Returns a dict with: skipped, ok, verdict, raw_text, model, error, llm_called.
    """
    out: dict[str, Any] = {
        "skipped": False,
        "ok": False,
        "verdict": None,
        "raw_text": "",
        "model": "",
        "error": None,
        "llm_called": False,
    }
    if not training_llm_enabled():
        out["skipped"] = True
        out["error"] = "ANNA_USE_LLM disables LLM; set ANNA_USE_LLM=1 to run cross-check."
        return out

    _ensure_runtime_on_path()
    from _ollama import ollama_base_url  # noqa: E402
    from llm.local_llm_client import ollama_generate  # noqa: E402

    prompt = build_cross_check_prompt(draft, supporting_context=supporting_context)
    out["llm_called"] = True
    base = ollama_base_url()
    res = ollama_generate(prompt, base_url=base, timeout=timeout)
    out["model"] = res.model
    if res.error:
        out["error"] = res.error
        return out
    out["raw_text"] = res.text or ""
    out["verdict"] = parse_cross_check_verdict(out["raw_text"])
    out["ok"] = True
    return out


def append_cross_check_log(row: dict[str, Any]) -> Path | None:
    """Append one JSON line under anna_training_dir / llm_cross_checks.jsonl (best-effort)."""
    try:
        from modules.anna_training.store import anna_training_dir, utc_now_iso

        path = anna_training_dir() / "llm_cross_checks.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = dict(row)
        line.setdefault("logged_at_utc", utc_now_iso())
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None
