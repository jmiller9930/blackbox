"""
Role-based Ollama routing (GT operator stack).

**Critical:** Models do not execute mutations. Callers must route side effects through
validated tool layers and optional operator confirmation.

| Role | Default base | Default model | Env override (base / model) |
|------|----------------|---------------|-----------------------------|
| **PML lightweight** (Barney, Ask DATA) | ``http://172.20.2.230:11434`` | ``qwen2.5:7b`` | ``PML_LIGHTWEIGHT_OLLAMA_BASE_URL`` / ``PML_LIGHTWEIGHT_OLLAMA_MODEL``; model falls back to ``OLLAMA_MODEL`` |
| **Student** (parallel LLM seam) | **172.20.1.66:11434** (approved strong model host) | **qwen3-coder:30b** only (``exam_run_contract_v1``) | ``STUDENT_OLLAMA_BASE_URL`` overrides base **only** (CI/mocks) — not PML/lightweight |
| **System Agent** (operator control brain; propose-only) | ``http://172.20.1.66:11434`` | ``qwen3-coder:30b`` | ``SYSTEM_AGENT_OLLAMA_BASE_URL`` / ``SYSTEM_AGENT_OLLAMA_MODEL`` |
| **System Agent fallback** | (same as primary) | ``qwen2.5-coder:7b`` | ``SYSTEM_AGENT_OLLAMA_MODEL_FALLBACK`` |
| **DeepSeek escalation** (diagnostic / debug only) | ``http://172.20.2.230:11434`` | ``deepseek-v4-flash:cloud`` | ``DEEPSEEK_ESCALATION_OLLAMA_BASE_URL`` / ``DEEPSEEK_ESCALATION_OLLAMA_MODEL`` |

Lab defaults are **overridden** by explicit env in any environment where those IPs are wrong.
``OLLAMA_BASE_URL`` alone still applies to :func:`scripts.runtime._ollama.ollama_base_url` (Anna
and other legacy callers); Barney / Ask DATA **do not** use that unless
``PML_LIGHTWEIGHT_OLLAMA_BASE_URL`` is unset and you set ``OLLAMA_BASE_URL`` as the shared host.
"""

from __future__ import annotations

import os
from typing import Any


def _strip_base(url: str) -> str:
    return (url or "").strip().rstrip("/")


# Lab defaults (override with env in non-lab deployments).
_DEFAULT_PML_LIGHTWEIGHT_BASE = "http://172.20.2.230:11434"
_DEFAULT_STUDENT_OLLAMA_BASE = "http://172.20.1.66:11434"
_DEFAULT_SYSTEM_AGENT_BASE = "http://172.20.1.66:11434"
_DEFAULT_PML_LIGHTWEIGHT_MODEL = "qwen2.5:7b"
_DEFAULT_SYSTEM_AGENT_MODEL = "qwen3-coder:30b"
_DEFAULT_SYSTEM_AGENT_FALLBACK_MODEL = "qwen2.5-coder:7b"
# Ollama library tag for DeepSeek-V4-Flash (V4 series); override via DEEPSEEK_ESCALATION_OLLAMA_MODEL.
_DEFAULT_DEEPSEEK_ESCALATION_MODEL = "deepseek-v4-flash:cloud"


def pml_lightweight_ollama_base_url() -> str:
    """Barney + Ask DATA — fast, UI-responsive path."""
    for key in ("PML_LIGHTWEIGHT_OLLAMA_BASE_URL", "OLLAMA_BASE_URL"):
        v = os.environ.get(key)
        if v and str(v).strip():
            return _strip_base(str(v))
    return _DEFAULT_PML_LIGHTWEIGHT_BASE


def pml_lightweight_ollama_model() -> str:
    for key in ("PML_LIGHTWEIGHT_OLLAMA_MODEL", "OLLAMA_MODEL"):
        v = os.environ.get(key)
        if v and str(v).strip():
            return str(v).strip()
    return _DEFAULT_PML_LIGHTWEIGHT_MODEL


def student_ollama_base_url_v1() -> str:
    """
    Student LLM (``memory_context_llm_student``) — **approved** Ollama host (strong model; lab default
    **172.20.1.66**). ``STUDENT_OLLAMA_BASE_URL`` may override for integration tests or non-lab
    operators; there is **no** fallback to PML lightweight or generic ``OLLAMA_BASE_URL`` (avoids
    silent routing to the wrong host).
    """
    v = os.environ.get("STUDENT_OLLAMA_BASE_URL")
    if v and str(v).strip():
        return _strip_base(str(v))
    return _DEFAULT_STUDENT_OLLAMA_BASE


def system_agent_ollama_base_url() -> str:
    """Operator System Agent — structured workflows; **not** Barney/Ask DATA."""
    v = os.environ.get("SYSTEM_AGENT_OLLAMA_BASE_URL")
    if v and str(v).strip():
        return _strip_base(str(v))
    return _DEFAULT_SYSTEM_AGENT_BASE


def system_agent_ollama_model_primary() -> str:
    v = os.environ.get("SYSTEM_AGENT_OLLAMA_MODEL")
    if v and str(v).strip():
        return str(v).strip()
    return _DEFAULT_SYSTEM_AGENT_MODEL


def system_agent_ollama_model_fallback() -> str:
    v = os.environ.get("SYSTEM_AGENT_OLLAMA_MODEL_FALLBACK")
    if v and str(v).strip():
        return str(v).strip()
    return _DEFAULT_SYSTEM_AGENT_FALLBACK_MODEL


def deepseek_escalation_ollama_base_url() -> str:
    """Diagnostic / escalation only — not primary execution."""
    v = os.environ.get("DEEPSEEK_ESCALATION_OLLAMA_BASE_URL")
    if v and str(v).strip():
        return _strip_base(str(v))
    return pml_lightweight_ollama_base_url()


def deepseek_escalation_ollama_model() -> str:
    v = os.environ.get("DEEPSEEK_ESCALATION_OLLAMA_MODEL")
    if v and str(v).strip():
        return str(v).strip()
    return _DEFAULT_DEEPSEEK_ESCALATION_MODEL


def ollama_role_routing_snapshot_v1() -> dict[str, Any]:
    """Non-secret JSON for health checks / operator proof (no prompts)."""
    return {
        "schema": "ollama_role_routing_snapshot_v1",
        "pml_lightweight": {
            "ollama_base_url": pml_lightweight_ollama_base_url(),
            "ollama_model": pml_lightweight_ollama_model(),
        },
        "student_parallel_llm": {
            "ollama_base_url": student_ollama_base_url_v1(),
            "ollama_model_approved_v1": "qwen3-coder:30b",
            "note": "Student path is fixed to qwen3-coder:30b (exam_run_contract_v1); STUDENT_OLLAMA_BASE_URL overrides host only",
        },
        "system_agent": {
            "ollama_base_url": system_agent_ollama_base_url(),
            "ollama_model_primary": system_agent_ollama_model_primary(),
            "ollama_model_fallback": system_agent_ollama_model_fallback(),
            "policy": "propose_only_via_tool_layers_no_direct_execution",
        },
        "deepseek_escalation": {
            "ollama_base_url": deepseek_escalation_ollama_base_url(),
            "ollama_model": deepseek_escalation_ollama_model(),
            "policy": "diagnostic_or_debug_only_not_primary_path",
        },
    }


__all__ = [
    "deepseek_escalation_ollama_base_url",
    "deepseek_escalation_ollama_model",
    "ollama_role_routing_snapshot_v1",
    "pml_lightweight_ollama_base_url",
    "pml_lightweight_ollama_model",
    "student_ollama_base_url_v1",
    "system_agent_ollama_base_url",
    "system_agent_ollama_model_fallback",
    "system_agent_ollama_model_primary",
]
