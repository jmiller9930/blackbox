"""
Normalized Anna / dispatch output for cross-transport comparison (Directive 4.6.3.3).

Required fields for Anna (architect): interpretation.summary, answer_source, intent, topic,
limitation_flag (if present). Adapters format only; they do not alter meaning.
"""

from __future__ import annotations

from typing import Any


def normalized_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Build a transport-agnostic dict for validation / diff across CLI vs Telegram.

    Keys match architect directive (dots in JSON keys for interpretation.summary).
    """
    kind = payload.get("kind")
    if kind == "anna":
        return _normalize_anna(payload)
    if kind == "cody":
        return {
            "kind": "cody",
            "interpretation.summary": None,
            "answer_source": None,
            "intent": None,
            "topic": None,
            "limitation_flag": False,
            "cody_reply": str((payload.get("reply") or ""))[:4000],
        }
    if kind == "identity":
        return {
            "kind": "identity",
            "interpretation.summary": None,
            "answer_source": None,
            "intent": None,
            "topic": None,
            "limitation_flag": False,
            "identity_intent": str(payload.get("intent") or "help"),
        }
    if kind == "data":
        return {
            "kind": "data",
            "interpretation.summary": None,
            "answer_source": None,
            "intent": None,
            "topic": None,
            "limitation_flag": False,
            "data_mode": payload.get("data_mode"),
        }
    if kind == "mia":
        return {
            "kind": "mia",
            "interpretation.summary": None,
            "answer_source": None,
            "intent": None,
            "topic": None,
            "limitation_flag": False,
        }
    if kind == "error":
        return {
            "kind": "error",
            "interpretation.summary": None,
            "answer_source": None,
            "intent": None,
            "topic": None,
            "limitation_flag": False,
            "error_message": str(payload.get("message") or ""),
        }
    return {
        "kind": str(kind),
        "interpretation.summary": None,
        "answer_source": None,
        "intent": None,
        "topic": None,
        "limitation_flag": False,
    }


def _normalize_anna(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or {}
    aa = data.get("anna_analysis") or {}
    interp = aa.get("interpretation") or {}
    hi = aa.get("human_intent") or {}
    pipe = aa.get("pipeline") or {}
    signals = list(interp.get("signals") or [])
    lim = "pipeline:explicit_limitation" in signals
    return {
        "kind": "anna",
        "interpretation.summary": interp.get("summary"),
        "answer_source": pipe.get("answer_source"),
        "intent": hi.get("intent"),
        "topic": hi.get("topic"),
        "limitation_flag": bool(lim),
    }
