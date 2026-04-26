"""
GT_DIRECTIVE_026AI — OpenAI **Responses** HTTP adapter (no key in return objects; never log key).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

SCHEMA_RESULT = "external_openai_call_result_v1"
CONTRACT_VERSION = 1


def _get_api_key(api_key_env_var: str) -> str | None:
    v = (os.environ.get(str(api_key_env_var or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY") or "").strip()
    return v if v else None


def call_openai_responses_v1(
    *,
    model_requested: str,
    system_instruction: str,
    user_text: str,
    api_key_env_var: str = "OPENAI_API_KEY",
    response_json_schema: dict[str, Any] | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """
    POST ``/v1/responses`` per OpenAI Responses API. No API key in returned dict.
    """
    t0 = time.perf_counter()
    key = _get_api_key(api_key_env_var)
    if not key:
        return _fail(
            model_requested,
            "missing_key",
            None,
            None,
            None,
            0.0,
            (time.perf_counter() - t0) * 1000.0,
            "missing api key in environment",
        )
    # Responses API — prefer ``instructions`` + string ``input`` (see OpenAI docs).
    body_obj: dict[str, Any] = {
        "model": model_requested,
        "instructions": system_instruction,
        "input": user_text,
    }
    if response_json_schema is not None:
        body_obj["text"] = {
            "format": {
                "type": "json_schema",
                "name": "external_reasoning_review",
                "strict": True,
                "schema": response_json_schema,
            }
        }
    body = json.dumps(body_obj).encode("utf-8")
    url = "https://api.openai.com/v1/responses"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:2000]
        except OSError:
            detail = str(e)
        ms = (time.perf_counter() - t0) * 1000.0
        return _fail(
            model_requested,
            f"http_{e.code}",
            None,
            None,
            None,
            0.0,
            ms,
            detail,
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        ms = (time.perf_counter() - t0) * 1000.0
        return _fail(
            model_requested, "request_failed", None, None, None, 0.0, ms, str(e)
        )
    ms = (time.perf_counter() - t0) * 1000.0
    return _parse_openai_responses_body(model_requested, raw, ms)


def _parse_openai_responses_body(
    model_requested: str, raw: dict[str, Any], latency_ms: float
) -> dict[str, Any]:
    """Normalize diverse Responses output shapes; never include secrets."""
    resolved = str(raw.get("model") or model_requested)
    out_text: str | None = raw.get("output_text") if isinstance(raw.get("output_text"), str) else None
    if not out_text and isinstance(raw.get("output"), list):
        for item in raw["output"]:
            if not isinstance(item, dict):
                continue
            c = item.get("content")
            if isinstance(c, list) and c:
                for x in c:
                    if isinstance(x, dict) and x.get("type") in ("output_text", "text"):
                        t = x.get("text")
                        if isinstance(t, str):
                            out_text = t
                            break
            if out_text:
                break
    if not out_text and isinstance(raw.get("output_text"), str):
        out_text = raw.get("output_text")
    if not out_text and isinstance(raw.get("text"), str):
        out_text = raw["text"]
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    outp = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    tot = int(usage.get("total_tokens") or (inp + outp))
    parsed_json: Any = None
    if out_text:
        try:
            parsed_json = json.loads(out_text)
        except json.JSONDecodeError:
            parsed_json = None
    return {
        "schema": SCHEMA_RESULT,
        "contract_version": CONTRACT_VERSION,
        "ok": out_text is not None,
        "error": None if out_text else "empty_output",
        "provider": "openai",
        "model_requested": model_requested,
        "model_resolved": resolved,
        "response_text": out_text,
        "parsed_json": parsed_json,
        "input_tokens": inp,
        "output_tokens": outp,
        "total_tokens": tot,
        "latency_ms": round(latency_ms, 3),
        "response_status": "ok" if out_text else "error",
    }


def _fail(
    model_requested: str,
    response_status: str,
    model_resolved: str | None,
    inp: int | None,
    outp: int | None,
    tot: int | None,
    latency_ms: float,
    err: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_RESULT,
        "contract_version": CONTRACT_VERSION,
        "ok": False,
        "error": err[:2000],
        "provider": "openai",
        "model_requested": model_requested,
        "model_resolved": model_resolved,
        "response_text": None,
        "parsed_json": None,
        "input_tokens": inp or 0,
        "output_tokens": outp or 0,
        "total_tokens": tot or 0,
        "latency_ms": round(latency_ms, 3),
        "response_status": response_status,
    }


def run_smoke_test_strict_json_v1(
    *,
    api_key_env_var: str = "OPENAI_API_KEY",
    model: str = "gpt-5.5",
) -> dict[str, Any]:
    """
    Minimal /v1/responses call; returns structured result (no key printed by caller).
    For CLI: ``python -m renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 smoke``.
    """
    out = call_openai_responses_v1(
        model_requested=model,
        system_instruction="Return only a JSON object with one key 'ok' true",
        user_text="Smoke test. Reply with JSON only.",
        api_key_env_var=api_key_env_var,
        response_json_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    )
    return {
        "smoke_ok": bool(out.get("ok")),
        "model_resolved": out.get("model_resolved"),
        "input_tokens": out.get("input_tokens"),
        "output_tokens": out.get("output_tokens"),
        "total_tokens": out.get("total_tokens"),
        "latency_ms": out.get("latency_ms"),
        "error": out.get("error"),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "smoke":
        r = run_smoke_test_strict_json_v1()
        # Never print secrets; safe summary only
        print(json.dumps({k: v for k, v in r.items() if k != "key"}, indent=2))
    else:
        print("Usage: python -m renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 smoke")
