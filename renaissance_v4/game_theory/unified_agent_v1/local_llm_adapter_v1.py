"""
GT_DIRECTIVE_026AI — Student local Ollama adapter (primary ``qwen2.5:7b``, fallback ``deepseek-r1:14b``).

Base URL must resolve through **API Gateway** in lab (``RUNTIME_LLM_API_GATEWAY_BASE_URL`` per
``student_ollama_base_url_v1``). trx40 is blocked.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_LLM_APPROVED_MODEL_V1,
    STUDENT_LLM_FALLBACK_MODEL_V1,
)
from renaissance_v4.game_theory.ollama_role_routing_v1 import (
    guard_runtime_llm_url_not_trx40_finquant_v1,
    student_ollama_base_url_v1,
)

SCHEMA_RESULT = "local_llm_call_result_v1"
CONTRACT_VERSION = 1


def _single_chat_attempt_v1(
    *,
    base: str,
    model: str,
    user_prompt: str,
    timeout_s: float,
) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/api/chat"
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": user_prompt}],
            "stream": False,
            "options": {"temperature": 0.15, "num_predict": 1024},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:800]
        except OSError:
            detail = str(e)
        ms = (time.perf_counter() - t0) * 1000.0
        return _err_result(
            model_requested=model,
            base_url=base,
            err=f"ollama_http_{e.code}: {detail}",
            latency_ms=ms,
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        ms = (time.perf_counter() - t0) * 1000.0
        return _err_result(
            model_requested=model, base_url=base, err=f"ollama_request_failed:{e}", latency_ms=ms
        )
    ms = (time.perf_counter() - t0) * 1000.0
    msg = body.get("message") if isinstance(body, dict) else None
    if not isinstance(msg, dict):
        return _err_result(
            model_requested=model,
            base_url=base,
            err="ollama_response_missing_message",
            latency_ms=ms,
        )
    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        return _err_result(
            model_requested=model,
            base_url=base,
            err="ollama_response_empty_content",
            latency_ms=ms,
        )
    resolved = str(body.get("model") or model).strip() or model
    return {
        "schema": SCHEMA_RESULT,
        "contract_version": CONTRACT_VERSION,
        "ok": True,
        "error": None,
        "local_model_requested_v1": model,
        "local_model_resolved_v1": resolved,
        "local_base_url_used_v1": base,
        "assistant_text": content.strip(),
        "raw_response": body,
        "latency_ms_v1": round(ms, 3),
    }


def _should_retry_student_llm_with_fallback_v1(err: str | None) -> bool:
    if not err:
        return False
    e = err.lower()
    return any(
        x in e
        for x in (
            "timeout",
            "request_failed",
            "empty_content",
            "missing_message",
            "http_",
            "connection",
            "timed out",
            "broken pipe",
            "reset",
            "errno",
        )
    )


def call_student_local_llm_v1(
    *,
    user_prompt: str,
    model_requested: str | None = None,
    base_url_override: str | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """
    Chat completion with primary model and optional fallback on failure.
    ``base_url_override`` is for tests only.
    """
    primary = STUDENT_LLM_APPROVED_MODEL_V1
    fb = STUDENT_LLM_FALLBACK_MODEL_V1
    model = (model_requested or "").strip() or primary
    if model not in (primary, fb):
        return _err_result(
            model_requested=model,
            base_url=(base_url_override or student_ollama_base_url_v1()),
            err="local_model_not_approved_v1",
            latency_ms=0.0,
        )
    base = (base_url_override or student_ollama_base_url_v1()).rstrip("/")
    guard_runtime_llm_url_not_trx40_finquant_v1(base)

    r = _single_chat_attempt_v1(base=base, model=model, user_prompt=user_prompt, timeout_s=timeout_s)
    if r.get("ok"):
        return r
    if model != primary:
        return r
    err = str(r.get("error") or "")
    if not _should_retry_student_llm_with_fallback_v1(err):
        return r
    r2 = _single_chat_attempt_v1(base=base, model=fb, user_prompt=user_prompt, timeout_s=timeout_s)
    if isinstance(r2, dict) and r2.get("ok"):
        r2["student_llm_fallback_used_v1"] = True
        return r2
    return r


def _err_result(
    *,
    model_requested: str,
    base_url: str,
    err: str,
    latency_ms: float,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_RESULT,
        "contract_version": CONTRACT_VERSION,
        "ok": False,
        "error": err,
        "local_model_requested_v1": model_requested,
        "local_model_resolved_v1": None,
        "local_base_url_used_v1": base_url,
        "assistant_text": None,
        "raw_response": None,
        "latency_ms_v1": round(latency_ms, 3),
    }
