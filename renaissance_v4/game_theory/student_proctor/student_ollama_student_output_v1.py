"""
GT_DIRECTIVE_015 — Student **memory_context_llm_student** profile: Ollama with **run-scoped**
``student_llm_v1`` (provider, model, role). Model tag is **metadata** under the brain profile, not a
separate top-level “lane.”

Bounded JSON-only completion over ``/api/chat``; parsed output must pass ``validate_student_output_v1``.
(Future: refine-then-seal / H1–H4 deliberation roles — v1 default role is single-shot output.)
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from typing import Any

_NS_OLLAMA_REF = uuid.UUID("b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e")


from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    GRADED_UNIT_TYPE_V1,
    SCHEMA_STUDENT_OUTPUT_V1,
    validate_student_output_directional_thesis_required_for_llm_profile_v1,
    validate_student_output_v1,
)


def _student_llm_max_trades_v1() -> int | None:
    """
    Cap Ollama calls per batch for safety (full batch can be hundreds of trades).

    ``PATTERN_GAME_STUDENT_LLM_MAX_TRADES`` unset → **20**. ``none`` / ``0`` / ``-1`` → unlimited.
    """
    raw = (os.environ.get("PATTERN_GAME_STUDENT_LLM_MAX_TRADES") or "").strip().lower()
    if raw in ("", "none", "unlimited", "-1"):
        return None
    if raw == "0":
        return None
    try:
        n = int(raw)
        return n if n > 0 else None
    except ValueError:
        return 20


def _ollama_chat_once_v1(
    *,
    base_url: str,
    model: str,
    user_prompt: str,
    timeout_s: float = 180.0,
) -> tuple[str | None, str | None]:
    """Returns ``(assistant_text, error)``."""
    base = base_url.rstrip("/")
    url = f"{base}/api/chat"
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": user_prompt}],
            "stream": False,
            "options": {"temperature": 0.15, "num_predict": 512},
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
        return None, f"ollama_http_{e.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, f"ollama_request_failed: {type(e).__name__}: {e}"
    msg = body.get("message") if isinstance(body, dict) else None
    if not isinstance(msg, dict):
        return None, "ollama_response_missing_message"
    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        return None, "ollama_response_empty_content"
    return content.strip(), None


def _merge_optional_thesis_from_parsed_v1(parsed: dict[str, Any], out: dict[str, Any]) -> None:
    """
    Copy optional §1.0 thesis keys from LLM JSON into ``out`` (only whitelisted keys).

    Shapes are finalized by ``validate_student_output_v1`` on the full document.
    """
    cb = parsed.get("confidence_band")
    if isinstance(cb, str) and cb.strip():
        out["confidence_band"] = cb.strip().lower()
    for key in ("supporting_indicators", "conflicting_indicators"):
        v = parsed.get(key)
        if v is None:
            continue
        if isinstance(v, list):
            out[key] = [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()][
                :32
            ]
        elif isinstance(v, str) and v.strip():
            out[key] = [s.strip() for s in v.split(",") if s.strip()][:32]
    cf = parsed.get("context_fit")
    if isinstance(cf, str) and cf.strip():
        out["context_fit"] = cf.strip()[:128]
    inv = parsed.get("invalidation_text")
    if isinstance(inv, str) and inv.strip():
        out["invalidation_text"] = inv.strip()[:4000]
    sa = parsed.get("student_action_v1")
    if isinstance(sa, str) and sa.strip():
        raw = sa.strip().lower().replace("-", "_")
        if raw in ("enter_long", "enter_short", "no_trade"):
            out["student_action_v1"] = raw


def _extract_json_object_v1(text: str) -> dict[str, Any] | None:
    t = text.strip()
    m = re.search(r"\{[\s\S]*\}\s*$", t)
    if not m:
        m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def emit_student_output_via_ollama_v1(
    packet: dict[str, Any],
    *,
    graded_unit_id: str,
    decision_at_ms: int,
    llm_model: str,
    ollama_base_url: str,
    prompt_version: str,
    require_directional_thesis_v1: bool = True,
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    One Ollama completion → ``student_output_v1`` or validation errors.

    Prompt is **strictly** pre-reveal packet JSON + JSON-only output contract (no future leakage).

    When ``require_directional_thesis_v1`` is True (default), output must include the full §1.0 thesis
    bundle for ``memory_context_llm_student`` — precondition for **GT_DIRECTIVE_017**.
    """
    pkt_json = json.dumps(packet, ensure_ascii=False, default=str)[:12000]
    thesis_lines = (
        "- confidence_band: low | medium | high\n"
        "- supporting_indicators: string[]\n"
        "- conflicting_indicators: string[]\n"
        "- context_fit: short string, e.g. trend | chop | reversal | breakout | exhaustion | unknown\n"
        "- invalidation_text: what would prove the thesis wrong (no future prices or outcomes)\n"
        "- student_action_v1: enter_long | enter_short | no_trade — MUST agree with act and direction "
        "(no_trade requires act false; enter_long requires act true and direction long; enter_short "
        "requires act true and direction short).\n"
    )
    if require_directional_thesis_v1:
        thesis_block = (
            "REQUIRED thesis keys (all MUST be present; use [] for an empty indicator list if honest; "
            "do not invent post-hoc outcomes):\n" + thesis_lines
        )
    else:
        thesis_block = (
            "Optional thesis keys (omit any you cannot justify from the packet only):\n" + thesis_lines
        )
    user = (
        "You are the Student (exam). You MUST output a single JSON object only — no markdown, no prose outside JSON.\n"
        "Keys required: act (boolean), direction (string: long | short | flat), confidence_01 (number 0..1), "
        "pattern_recipe_ids (array of strings, non-empty), reasoning_text (short string).\n"
        + thesis_block
        + f"prompt_version_echo: {prompt_version}\n"
        + f"graded_unit_id: {graded_unit_id}\n"
        + f"decision_open_time_ms: {decision_at_ms}\n"
        + "Pre-reveal decision packet (JSON):\n"
        + f"{pkt_json}\n"
    )
    text, err = _ollama_chat_once_v1(base_url=ollama_base_url, model=llm_model, user_prompt=user)
    if err or text is None:
        return None, [err or "ollama_empty"]

    parsed = _extract_json_object_v1(text)
    if parsed is None:
        return None, [f"ollama_response_not_json_object: {text[:400]}"]

    t = int(decision_at_ms)
    out: dict[str, Any] = {
        "schema": SCHEMA_STUDENT_OUTPUT_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_type": GRADED_UNIT_TYPE_V1,
        "graded_unit_id": str(graded_unit_id),
        "decision_at_ms": t,
        "act": bool(parsed.get("act")),
        "direction": str(parsed.get("direction") or "flat").strip().lower(),
        "pattern_recipe_ids": parsed.get("pattern_recipe_ids") if isinstance(parsed.get("pattern_recipe_ids"), list) else [],
        "confidence_01": float(parsed.get("confidence_01") or 0.0),
        "reasoning_text": str(parsed.get("reasoning_text") or "")[:4000],
        "student_decision_ref": str(parsed.get("student_decision_ref") or "")[:128],
    }
    if not out["student_decision_ref"] or len(out["student_decision_ref"]) < 36:
        out["student_decision_ref"] = str(
            uuid.uuid5(_NS_OLLAMA_REF, f"ollama_student_v1:{llm_model}:{graded_unit_id}:{t}")
        )
    pr = out["pattern_recipe_ids"]
    if not pr or not all(isinstance(x, str) for x in pr):
        out["pattern_recipe_ids"] = [f"ollama_{llm_model.replace(':', '_')}_v1"]
    _merge_optional_thesis_from_parsed_v1(parsed, out)
    ve = validate_student_output_v1(out)
    if ve:
        return None, [f"student_output_invalid: {'; '.join(ve)}"]
    if require_directional_thesis_v1:
        te = validate_student_output_directional_thesis_required_for_llm_profile_v1(out)
        if te:
            return None, [f"student_output_thesis_incomplete_for_llm_profile: {'; '.join(te)}"]
    return out, []


__all__ = [
    "emit_student_output_via_ollama_v1",
    "_student_llm_max_trades_v1",
]
