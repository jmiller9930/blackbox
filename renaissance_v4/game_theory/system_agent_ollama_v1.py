"""
Operator **System Agent** — Ollama **routing + optional generate** for structured workflows.

**Policy:** This module does **not** execute restarts, uploads, or mutations. Production flows must
call **tool APIs** with validation and optional operator confirmation; the LLM may only **propose**
structured steps. Use :func:`deepseek_escalation_generate_v1` only for diagnostic / escalation.

See :mod:`renaissance_v4.game_theory.ollama_role_routing_v1` for env keys and lab defaults.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.ollama_role_routing_v1 import (
    deepseek_escalation_ollama_base_url,
    deepseek_escalation_ollama_model,
    system_agent_ollama_base_url,
    system_agent_ollama_model_fallback,
    system_agent_ollama_model_primary,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _ollama_generate() -> Any:
    rt = str(_REPO_ROOT / "scripts" / "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    from llm.local_llm_client import ollama_generate

    return ollama_generate


def system_agent_generate_with_fallback_v1(
    prompt: str,
    *,
    timeout: float = 180.0,
) -> tuple[str, str | None, str]:
    """
    Try **primary** System Agent model on its host; on failure, retry **fallback** model
    (same host). Returns ``(text, error_or_none, model_used_tag)``.
    """
    gen = _ollama_generate()
    base = system_agent_ollama_base_url()
    primary = system_agent_ollama_model_primary()
    fb = system_agent_ollama_model_fallback()
    res = gen(prompt, base_url=base, model=primary, timeout=timeout)
    if not res.error:
        return (res.text or "").strip(), None, primary
    res2 = gen(prompt, base_url=base, model=fb, timeout=timeout)
    if not res2.error:
        return (res2.text or "").strip(), None, f"{fb} (fallback after primary error)"
    return "", res2.error or res.error, fb


def deepseek_escalation_generate_v1(prompt: str, *, timeout: float = 240.0) -> tuple[str, str | None]:
    """Diagnostic / debug path only — **not** for Barney, Ask DATA, or primary System Agent."""
    gen = _ollama_generate()
    base = deepseek_escalation_ollama_base_url()
    model = deepseek_escalation_ollama_model()
    res = gen(prompt, base_url=base, model=model, timeout=timeout)
    # Audit line for operator proof (Pattern Game log / stderr): requested vs Ollama-reported model.
    print(
        "[deepseek_escalation_v1] "
        f"base_url={base} requested_model={model} ollama_reported_model={res.model} "
        f"error={res.error!r}",
        file=sys.stderr,
        flush=True,
    )
    if res.error:
        return "", res.error
    return (res.text or "").strip(), None


__all__ = [
    "deepseek_escalation_generate_v1",
    "system_agent_generate_with_fallback_v1",
]
