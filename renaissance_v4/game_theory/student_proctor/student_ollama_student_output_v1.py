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
    CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1,
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    GRADED_UNIT_TYPE_V1,
    SCHEMA_STUDENT_OUTPUT_V1,
    validate_student_output_directional_thesis_required_for_llm_profile_v1,
    validate_student_output_v1,
)


def _student_llm_max_trades_v1() -> int | None:
    """
    Cap Ollama calls per batch for safety (full batch can be hundreds of trades).

    ``PATTERN_GAME_STUDENT_LLM_MAX_TRADES`` unset / ``none`` / ``0`` / ``-1`` → **unlimited** (``None``).
    Invalid integer → default cap **20**.
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


def _ensure_conflicting_indicators_llm_contract_v1(out: dict[str, Any]) -> None:
    """
    Hard contract (no schema relaxation): ``conflicting_indicators`` must be a non-empty list.

    When the model leaves it empty, inject the explicit no-contrary-evidence packet label so the
    Student line remains honest and machine-checkable.
    """
    ci = out.get("conflicting_indicators")
    if not isinstance(ci, list):
        return
    if len(ci) == 0:
        out["conflicting_indicators"] = [CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1]


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
    Copy thesis + Student decision-protocol keys from LLM JSON into ``out`` (whitelisted only).

    Shapes are finalized by ``validate_student_output_v1`` on the full document.
    """
    ci = parsed.get("context_interpretation_v1")
    if isinstance(ci, str) and ci.strip():
        out["context_interpretation_v1"] = ci.strip()[:2000]
    hk = parsed.get("hypothesis_kind_v1")
    if isinstance(hk, str) and hk.strip():
        out["hypothesis_kind_v1"] = hk.strip().lower()
    ht = parsed.get("hypothesis_text_v1")
    if isinstance(ht, str) and ht.strip():
        out["hypothesis_text_v1"] = ht.strip()[:512]

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
        raw = sa.strip().lower().replace("-", "_").replace(" ", "_")
        if raw in ("long", "enter_long"):
            out["student_action_v1"] = "enter_long"
        elif raw in ("short", "enter_short"):
            out["student_action_v1"] = "enter_short"
        elif raw in ("no_trade", "no_trade_v1", "flat", "none"):
            out["student_action_v1"] = "no_trade"


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
        "MANDATORY Student decision protocol (all keys below MUST appear in the JSON; no skipping steps; "
        "no narrative-only answer — every value must be substantive, not placeholders like \"n/a\" unless "
        "the field explicitly allows it):\n"
        "1) Context interpretation — context_interpretation_v1: string, >=16 chars, summarize ONLY what "
        "the packet gives (OHLCV / regime / signals / fusion / memory hooks). No invented bars.\n"
        "2) Hypothesis — hypothesis_kind_v1: exactly one of trend_continuation | mean_reversion | no_clear_edge; "
        "hypothesis_text_v1: one concise sentence stating the trade idea or explicit lack of edge.\n"
        "3) Evidence — supporting_indicators: string[] (min 1); conflicting_indicators: string[] (min 1); "
        "each entry a short label grounded in the packet (fusion, regime, indicator, structure). "
        "If you see **no** contrary evidence in the packet, set conflicting_indicators to exactly "
        f"one element: {CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1!r} (do not leave the list empty).\n"
        "4) Resolution — confidence_band: low | medium | high; context_fit: short string "
        "(e.g. trend | chop | reversal | breakout | exhaustion | range | unknown).\n"
        "5) Decision — student_action_v1: enter_long | enter_short | no_trade "
        "(aliases LONG / SHORT / NO_TRADE accepted; MUST agree with act and direction: "
        "no_trade => act false and direction flat; enter_long => act true and direction long; "
        "enter_short => act true and direction short).\n"
        "6) Invalidation — invalidation_text: concrete conditions that would void the thesis "
        "(no future outcomes; for no_trade, state what would need to change to consider a trade).\n"
    )
    if require_directional_thesis_v1:
        thesis_block = (
            "REQUIRED decision-protocol keys (memory_context_llm_student — incomplete JSON is rejected):\n"
            + thesis_lines
        )
    else:
        thesis_block = (
            "Optional thesis / protocol keys (omit any you cannot justify from the packet only):\n" + thesis_lines
        )
    user = (
        "You are the Student (exam). You MUST output a single JSON object only — no markdown, no prose outside JSON.\n"
        "Keys required: act (boolean), direction (string: long | short | flat), confidence_01 (number 0..1), "
        "pattern_recipe_ids (array of strings, non-empty), reasoning_text (short string; may echo protocol).\n"
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
    if require_directional_thesis_v1:
        _ensure_conflicting_indicators_llm_contract_v1(out)
    ve = validate_student_output_v1(out)
    if ve:
        return None, [f"student_output_invalid: {'; '.join(ve)}"]
    if require_directional_thesis_v1:
        te = validate_student_output_directional_thesis_required_for_llm_profile_v1(out)
        if te:
            return None, [f"student_output_thesis_incomplete_for_llm_profile: {'; '.join(te)}"]
    return out, []


def verify_ollama_model_tag_available_v1(
    base_url: str,
    model: str,
    *,
    timeout_s: float = 12.0,
) -> str | None:
    """
    **Pre-flight** for Student LLM: return ``None`` if Ollama ``/api/tags`` includes ``model``;
    else a single human-readable line suitable for run failure (no silent fallback).
    """
    base = (base_url or "").strip().rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        return f"ollama_base_url_invalid_v1: {base_url!r}"
    url = f"{base}/api/tags"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return f"ollama_tags_http_{e.code}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return f"ollama_model_availability_check_failed: {type(e).__name__}: {e}"
    if not isinstance(body, dict):
        return "ollama_tags_response_invalid"
    names: set[str] = set()
    for m in body.get("models") or []:
        if not isinstance(m, dict):
            continue
        for k in ("name", "model"):
            s = m.get(k)
            if isinstance(s, str) and s.strip():
                names.add(s.strip())
    if model in names:
        return None
    return (
        f"student_ollama_model_not_available: model {model!r} not in GET /api/tags on {base} "
        f"({len(names)} models reported)"
    )


__all__ = [
    "emit_student_output_via_ollama_v1",
    "verify_ollama_model_tag_available_v1",
    "_student_llm_max_trades_v1",
]
