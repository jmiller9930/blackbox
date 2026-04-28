"""
GT_DIRECTIVE_026AI — Student local Ollama adapter (qwen2.5:7b, single host; **no fallback**).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import STUDENT_LLM_APPROVED_MODEL_V1
from renaissance_v4.game_theory.ollama_role_routing_v1 import student_ollama_base_url_v1

SCHEMA_RESULT = "local_llm_call_result_v1"
CONTRACT_VERSION = 1


def call_student_local_llm_v1(
    *,
    user_prompt: str,
    model_requested: str | None = None,
    base_url_override: str | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """
    Single chat completion. No model fallback; no alternate host fallback.
    ``base_url_override`` is for tests only (still one URL per call).
    """
    model = (model_requested or "").strip() or STUDENT_LLM_APPROVED_MODEL_V1
    if model != STUDENT_LLM_APPROVED_MODEL_V1:
        return _err_result(
            model_requested=model,
            base_url=(base_url_override or student_ollama_base_url_v1()),
            err="local_model_not_approved_v1",
            latency_ms=0.0,
        )
    base = (base_url_override or student_ollama_base_url_v1()).rstrip("/")
    t0 = time.perf_counter()
    url = f"{base}/api/chat"
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
