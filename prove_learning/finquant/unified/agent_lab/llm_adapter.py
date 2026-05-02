"""
FinQuant Unified Agent Lab — LLM Adapter (Ollama HTTP client).

Calls the Ollama API and parses the response into a governed decision dict.
Uses only stdlib — no external HTTP libraries required.

Governance rules:
  - Raw model output is always captured.
  - The LLM does not write memory directly.
  - All output is parsed and validated before becoming authoritative.
  - On any failure the caller falls back to the deterministic stub.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.error
from typing import Any

VALID_ACTIONS = {"NO_TRADE", "ENTER_LONG", "ENTER_SHORT", "HOLD", "EXIT"}
VALID_CONFIDENCE = {"low", "medium", "high"}

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_TOKENS = 400


class LLMCallResult:
    """Outcome of a single Ollama call."""

    def __init__(
        self,
        *,
        success: bool,
        raw_output: str = "",
        parsed: dict[str, Any] | None = None,
        error: str = "",
        latency_ms: int = 0,
    ) -> None:
        self.success = success
        self.raw_output = raw_output
        self.parsed = parsed or {}
        self.error = error
        self.latency_ms = latency_ms


def call_ollama(
    *,
    base_url: str,
    model: str,
    prompt: str,
    system_prompt: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.1,
) -> LLMCallResult:
    """Call Ollama /api/generate and return a LLMCallResult."""
    t0 = time.monotonic()

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    payload = json.dumps({
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
            "stop": ["```", "</json>"],
        },
    }).encode("utf-8")

    url = f"{base_url.rstrip('/')}/api/generate"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return LLMCallResult(
            success=False,
            error=f"URLError: {exc}",
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return LLMCallResult(
            success=False,
            error=f"Unexpected: {exc}",
            latency_ms=latency_ms,
        )

    latency_ms = int((time.monotonic() - t0) * 1000)

    try:
        response_obj = json.loads(body)
        raw_text = str(response_obj.get("response", ""))
    except Exception as exc:
        return LLMCallResult(
            success=False,
            raw_output=body[:2000],
            error=f"Response parse error: {exc}",
            latency_ms=latency_ms,
        )

    parsed = extract_decision_json(raw_text)
    if parsed is None:
        return LLMCallResult(
            success=False,
            raw_output=raw_text[:2000],
            error="No valid JSON decision found in model output",
            latency_ms=latency_ms,
        )

    validation_error = validate_parsed_decision(parsed)
    if validation_error:
        return LLMCallResult(
            success=False,
            raw_output=raw_text[:2000],
            error=f"Decision validation: {validation_error}",
            latency_ms=latency_ms,
        )

    return LLMCallResult(
        success=True,
        raw_output=raw_text[:2000],
        parsed=parsed,
        latency_ms=latency_ms,
    )


def extract_decision_json(text: str) -> dict[str, Any] | None:
    """Extract the first valid JSON object from model output text."""
    # Try JSON code fence first
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try first raw JSON object
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try last JSON object (model may reason then conclude)
    all_matches = list(re.finditer(r"\{[^{}]*\}", text, re.DOTALL))
    for m in reversed(all_matches):
        try:
            obj = json.loads(m.group(0))
            if "action" in obj:
                return obj
        except json.JSONDecodeError:
            continue

    return None


def validate_parsed_decision(parsed: dict[str, Any]) -> str:
    """Return an error string if parsed decision is invalid, else empty string."""
    action = str(parsed.get("action", "")).upper().strip()
    if action not in VALID_ACTIONS:
        return f"invalid action '{action}'; must be one of {VALID_ACTIONS}"

    confidence = str(parsed.get("confidence", "low")).lower().strip()
    if confidence not in VALID_CONFIDENCE:
        parsed["confidence"] = "low"

    parsed["action"] = action
    return ""


def normalize_llm_decision(
    parsed: dict[str, Any],
    *,
    case_id: str,
    step_index: int,
    symbol: str,
    raw_output: str,
    latency_ms: int,
) -> dict[str, Any]:
    """Normalize a parsed LLM response into the standard decision field set."""
    action = str(parsed.get("action", "NO_TRADE")).upper()
    confidence = str(parsed.get("confidence", "low")).lower()
    if confidence not in VALID_CONFIDENCE:
        confidence = "low"

    thesis = str(parsed.get("thesis", parsed.get("reasoning", "")) or "").strip()
    if not thesis:
        thesis = f"LLM chose {action} at step {step_index}."

    invalidation = str(parsed.get("invalidation", parsed.get("stop_condition", "")) or "").strip()
    if not invalidation:
        invalidation = "No explicit invalidation provided by model."

    supporting = parsed.get("supporting", parsed.get("supporting_indicators", [])) or []
    conflicting = parsed.get("conflicting", parsed.get("conflicting_indicators", [])) or []
    risk_notes = str(parsed.get("risk_notes", parsed.get("risk", "")) or "").strip()

    return {
        "action": action,
        "thesis_v1": thesis,
        "invalidation_v1": invalidation,
        "confidence_band_v1": confidence,
        "supporting_indicators_v1": [str(s) for s in supporting] if isinstance(supporting, list) else [],
        "conflicting_indicators_v1": [str(c) for c in conflicting] if isinstance(conflicting, list) else [],
        "risk_notes_v1": risk_notes,
        "risk_state_v1": f"llm_conf={confidence}",
        "raw_model_output_v1": raw_output,
        "llm_latency_ms_v1": latency_ms,
    }
