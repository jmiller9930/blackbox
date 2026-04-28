"""
Role-based Ollama routing (GT operator stack).

**FinQuant training isolation:** trx40 (**172.20.1.66**) must not receive runtime inference traffic.
Runtime LLM calls must enter via the **API Gateway** base URL (``RUNTIME_LLM_API_GATEWAY_BASE_URL``),
which forwards to inference backends (e.g. **172.20.2.230:11434**). Do not configure Pattern Machine
to POST ``/api/chat`` directly to bare Ollama on .230 — that bypasses the gateway.

**Critical:** Models do not execute mutations. Callers must route side effects through
validated tool layers and optional operator confirmation.

| Role | Resolution order | Default when unset (dev) |
|------|-------------------|---------------------------|
| **Student** (parallel LLM seam) | ``STUDENT_OLLAMA_BASE_URL`` → ``RUNTIME_LLM_API_GATEWAY_BASE_URL`` → ``RUNTIME_LLM_DEV_FALLBACK_BASE_URL`` (127.0.0.1:11434) | localhost |
| **PML lightweight** | ``PML_LIGHTWEIGHT_OLLAMA_BASE_URL`` / ``OLLAMA_BASE_URL`` → gateway → ``http://127.0.0.1:11434`` | localhost |
| **System Agent** | ``SYSTEM_AGENT_OLLAMA_BASE_URL`` → gateway → localhost | localhost |
| **DeepSeek escalation** | ``DEEPSEEK_ESCALATION_OLLAMA_BASE_URL`` → gateway → localhost | localhost |

Lab operators **must** set ``RUNTIME_LLM_API_GATEWAY_BASE_URL`` to the operator API Gateway URL that
proxies to **172.20.2.230** (not trx40).
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

_LOG = logging.getLogger(__name__)

# trx40 — reserved for FinQuant training; runtime inference must not use this host.
_TRX40_RUNTIME_LLM_BLOCKED_HOST_V1 = "172.20.1.66"


def _strip_base(url: str) -> str:
    return (url or "").strip().rstrip("/")


def runtime_llm_api_gateway_base_url_v1() -> str | None:
    """Canonical API Gateway base for Ollama-compatible ``/api/*`` (no trailing slash)."""
    v = (os.environ.get("RUNTIME_LLM_API_GATEWAY_BASE_URL") or "").strip()
    return _strip_base(v) if v else None


def guard_runtime_llm_url_not_trx40_finquant_v1(base_url: str) -> None:
    """
    Block runtime inference URLs that target trx40. Logs ``api_gw_blocked_trx40_training_v1``.
    """
    u = _strip_base(base_url)
    if not u:
        return
    host = (urlparse(u).hostname or "").strip().lower()
    if host == _TRX40_RUNTIME_LLM_BLOCKED_HOST_V1:
        _LOG.error("api_gw_blocked_trx40_training_v1 host=%s url=%s", host, u)
        raise RuntimeError("api_gw_blocked_trx40_training_v1")


def _dev_fallback_ollama_base_v1() -> str:
    return _strip_base(os.environ.get("RUNTIME_LLM_DEV_FALLBACK_BASE_URL", "http://127.0.0.1:11434"))


_DEFAULT_PML_LIGHTWEIGHT_MODEL = "qwen2.5:7b"
_DEFAULT_SYSTEM_AGENT_MODEL = "qwen2.5:7b"
_DEFAULT_SYSTEM_AGENT_FALLBACK_MODEL = "deepseek-r1:14b"
_DEFAULT_DEEPSEEK_ESCALATION_MODEL = "deepseek-r1:14b"


def pml_lightweight_ollama_base_url() -> str:
    """Barney + Ask DATA — prefer gateway during FinQuant isolation; never trx40."""
    v = os.environ.get("PML_LIGHTWEIGHT_OLLAMA_BASE_URL")
    if v and str(v).strip():
        out = _strip_base(str(v))
    elif os.environ.get("OLLAMA_BASE_URL", "").strip():
        out = _strip_base(os.environ["OLLAMA_BASE_URL"])
    elif runtime_llm_api_gateway_base_url_v1():
        out = runtime_llm_api_gateway_base_url_v1()  # type: ignore[assignment]
    else:
        out = _dev_fallback_ollama_base_v1()
    guard_runtime_llm_url_not_trx40_finquant_v1(out)
    return out


def pml_lightweight_ollama_model() -> str:
    for key in ("PML_LIGHTWEIGHT_OLLAMA_MODEL", "OLLAMA_MODEL"):
        v = os.environ.get(key)
        if v and str(v).strip():
            return str(v).strip()
    return _DEFAULT_PML_LIGHTWEIGHT_MODEL


def student_ollama_base_url_v1() -> str:
    """
    Student LLM — **must** use the API Gateway URL in lab (``RUNTIME_LLM_API_GATEWAY_BASE_URL`` or
    explicit ``STUDENT_OLLAMA_BASE_URL``). Dev fallback: ``RUNTIME_LLM_DEV_FALLBACK_BASE_URL`` or localhost.
    """
    if os.environ.get("STUDENT_OLLAMA_BASE_URL", "").strip():
        out = _strip_base(os.environ["STUDENT_OLLAMA_BASE_URL"])
    elif runtime_llm_api_gateway_base_url_v1():
        out = runtime_llm_api_gateway_base_url_v1()  # type: ignore[assignment]
    else:
        out = _dev_fallback_ollama_base_v1()
    guard_runtime_llm_url_not_trx40_finquant_v1(out)
    return out


def system_agent_ollama_base_url() -> str:
    if os.environ.get("SYSTEM_AGENT_OLLAMA_BASE_URL", "").strip():
        out = _strip_base(os.environ["SYSTEM_AGENT_OLLAMA_BASE_URL"])
    elif runtime_llm_api_gateway_base_url_v1():
        out = runtime_llm_api_gateway_base_url_v1()  # type: ignore[assignment]
    else:
        out = _dev_fallback_ollama_base_v1()
    guard_runtime_llm_url_not_trx40_finquant_v1(out)
    return out


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
    if os.environ.get("DEEPSEEK_ESCALATION_OLLAMA_BASE_URL", "").strip():
        out = _strip_base(os.environ["DEEPSEEK_ESCALATION_OLLAMA_BASE_URL"])
    elif runtime_llm_api_gateway_base_url_v1():
        out = runtime_llm_api_gateway_base_url_v1()  # type: ignore[assignment]
    else:
        out = _dev_fallback_ollama_base_v1()
    guard_runtime_llm_url_not_trx40_finquant_v1(out)
    return out


def deepseek_escalation_ollama_model() -> str:
    v = os.environ.get("DEEPSEEK_ESCALATION_OLLAMA_MODEL")
    if v and str(v).strip():
        return str(v).strip()
    return _DEFAULT_DEEPSEEK_ESCALATION_MODEL


def ollama_role_routing_snapshot_v1() -> dict[str, Any]:
    """Non-secret JSON for health checks / operator proof (no prompts)."""
    from renaissance_v4.game_theory.exam_run_contract_v1 import STUDENT_LLM_APPROVED_MODEL_V1

    gw = runtime_llm_api_gateway_base_url_v1()
    return {
        "schema": "ollama_role_routing_snapshot_v1",
        "runtime_llm_api_gateway_base_url_v1": gw,
        "policy_finquant_runtime_v1": (
            "Student/runtime inference must use RUNTIME_LLM_API_GATEWAY_BASE_URL (API GW entry); "
            "trx40 (172.20.1.66) blocked; gateway backends target 172.20.2.230 — prove path on host, "
            "not direct curl to Ollama."
        ),
        "pml_lightweight": {
            "ollama_base_url": pml_lightweight_ollama_base_url(),
            "ollama_model": pml_lightweight_ollama_model(),
        },
        "student_parallel_llm": {
            "ollama_base_url": student_ollama_base_url_v1(),
            "ollama_model_approved_v1": STUDENT_LLM_APPROVED_MODEL_V1,
            "note": "Base URL must be API GW in lab; approved model from exam_run_contract_v1",
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
            "policy": "internal_adversarial_reviewer_not_authority_local_r1",
        },
        "internal_dual_reasoning_v1": {
            "qwen_primary": {
                "ollama_base_url": system_agent_ollama_base_url(),
                "ollama_model": system_agent_ollama_model_primary(),
                "role": "builder_primary_internal",
            },
            "deepseek_reviewer": {
                "ollama_base_url": deepseek_escalation_ollama_base_url(),
                "ollama_model": deepseek_escalation_ollama_model(),
                "role": "adversarial_second_opinion_local",
            },
            "modes": ["qwen_only", "deepseek_only", "dual_review"],
            "env_override": "INTERNAL_REASONING_MODE",
            "external_openai_in_ask_data_path_v1": False,
        },
    }


__all__ = [
    "deepseek_escalation_ollama_base_url",
    "deepseek_escalation_ollama_model",
    "guard_runtime_llm_url_not_trx40_finquant_v1",
    "ollama_role_routing_snapshot_v1",
    "pml_lightweight_ollama_base_url",
    "pml_lightweight_ollama_model",
    "runtime_llm_api_gateway_base_url_v1",
    "student_ollama_base_url_v1",
    "system_agent_ollama_base_url",
    "system_agent_ollama_model_fallback",
    "system_agent_ollama_model_primary",
]
